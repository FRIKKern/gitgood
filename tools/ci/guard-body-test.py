#!/usr/bin/env python3
"""Source, restoration and actual Root regression gates for installed bodies."""
import ast
import builtins
from contextlib import nullcontext
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock,patch

sys.dont_write_bytecode=True
import guard_body_probe as probe
from guard_body_source import BODY_COUNT,EXCLUDED,MODULE_NAMES,constant_default,redirect_guard_globals,select_sources,validate_donors


def model():
    modules=[];native=types.ModuleType('synthetic_guard_native');rows=[];bindings={};counts={name:0 for name in MODULE_NAMES}
    for number,name in enumerate(MODULE_NAMES):
        module=types.ModuleType(name);modules.append(module)
        module.helper=lambda value:value+1
        text='def read(value=3): return helper(value)\n'
        if number==0:
            text+='class Thing:\n @staticmethod\n def static(value): return helper(value)\n @classmethod\n def klass(cls,value): return cls,helper(value)\n'
        exec(text,vars(module))
        donor_name='GuardBody'+str(number)+'_Top'
        wrapped=ast.parse('class '+donor_name+':\n'+''.join(' '+line+'\n' for line in text.splitlines()[:1]))
        generated,_=redirect_guard_globals(wrapped)
        def lookup(name,number=number):
            counts[MODULE_NAMES[number]]+=1
            globals_dict=bindings['globals'][number];builtin_dict=bindings['builtins'][number];missing=object()
            value=globals_dict.get(name,missing)
            if value is missing:value=builtin_dict.get(name,missing)
            if value is missing:raise NameError('name '+repr(name)+' is not defined',name=name)
            return value
        vars(native)['_gitgood_path_body_name']=lookup
        exec(generated,vars(native))
        rows.append({'module':name,'owner':'','method':'read','donor':donor_name})
        # Give every generated function a distinct dictionary as Cython's
        # separate inline lookup functions do in the hosted extension.
        donor=vars(native)[donor_name]
        for key,raw in tuple(vars(donor).items()):
            if type(raw) is types.FunctionType:
                clone=types.FunctionType(raw.__code__,{**raw.__globals__,'_gitgood_path_body_name':lookup},raw.__name__,raw.__defaults__,raw.__closure__)
                setattr(donor,key,clone)
        if number==0:
            donor_text='class GuardThing:\n @staticmethod\n def static(value): return helper(value)\n @classmethod\n def klass(cls,value): return cls,helper(value)\n'
            generated,_=redirect_guard_globals(ast.parse(donor_text))
            isolated={'_gitgood_path_body_name':lookup};exec(generated,isolated)
            native.GuardThing=isolated['GuardThing']
            for method in ('static','klass'):rows.append({'module':name,'owner':'Thing','method':method,'donor':'GuardThing'})
    def bind(globals_list,builtins_list):
        bindings.update(globals=globals_list,builtins=builtins_list);return True
    native.bind_original=bind;native.load_counts=lambda:dict(counts)
    alias=types.ModuleType('synthetic_alias');alias.read=modules[0].read
    return modules,native,rows,alias


class SourceTest(unittest.TestCase):
    def sources(self):
        root=Path(__file__).resolve().parents[1]/'deployment'
        return {name:(root/(name+'.py')).read_bytes() for name in MODULE_NAMES}

    def test_actual_116_bodies_have_exact_source_and_inverse_ast_identity(self):
        sources=self.sources();generated,evidence=select_sources(sources)
        self.assertEqual(len(evidence['bodies']),BODY_COUNT)
        self.assertEqual(evidence['original_source_hashes'],{name+'.py':hashlib.sha256(raw).hexdigest() for name,raw in sources.items()})
        self.assertGreater(len(generated),100000)
        self.assertTrue(evidence['global_loads_only_transformed']);self.assertFalse(evidence['original_classes_replaced'])
        self.assertEqual(len({(row['module'],row['owner'],row['method']) for row in evidence['bodies']}),116)

    def test_actual_multi_function_modules_emit_each_selected_body_once(self):
        generated,evidence=select_sources(self.sources());tree=ast.parse(generated)
        classes={node.name:node for node in tree.body}
        self.assertEqual(len(classes),len(tree.body))
        for row in evidence['bodies']:
            self.assertEqual(sum(isinstance(node,ast.FunctionDef) and node.name==row['method']
                for node in classes[row['donor']].body),1)
        for number,module in enumerate(MODULE_NAMES):
            expected={row['method'] for row in evidence['bodies'] if row['module']==module and row['owner']==''}
            actual={node.name for node in classes['GuardBody'+str(number)+'_Top'].body}
            self.assertEqual(actual,expected)
        self.assertGreater(len(classes['GuardBody0_Top'].body),2)

    def test_duplicate_classes_methods_and_missing_body_admission_refuse(self):
        row={'donor':'Donor','method':'read'}
        for source,rows in [('class Donor:\n def read(self): pass\nclass Donor:\n def other(self): pass\n',[row]),
                ('class Donor:\n def read(self): pass\n def read(self): pass\n',[row]),
                ('class Donor:\n def other(self): pass\n',[row]),
                ('class Donor:\n def read(self): pass\n',[row,row])]:
            with self.subTest(source=source),self.assertRaises(ValueError):validate_donors(ast.parse(source),rows)

    def test_source_shape_scope_and_mutable_or_executable_defaults_refuse(self):
        sources=self.sources()
        for change in (lambda raw:raw+b'\ndef extra(): return 1\n',
                lambda raw:raw.replace(b'def require(value):',b'@arbitrary\ndef require(value):',1),
                lambda raw:raw.replace(b'def require(value):',b'def require(value: int):',1),
                lambda raw:raw.replace(b'def require(value):',b'def require(value=callback()):',1),
                lambda raw:raw.replace(b'def require(value):',b'def require(value=[]):',1)):
            altered=dict(sources);altered[MODULE_NAMES[0]]=change(sources[MODULE_NAMES[0]])
            with self.subTest(change=change),self.assertRaises(ValueError):select_sources(altered)
        with self.assertRaises(ValueError):select_sources(dict(list(sources.items())[1:]))

    def test_literal_arithmetic_is_bounded_without_execution(self):
        self.assertEqual(constant_default(ast.parse('2**64-1',mode='eval').body),2**64-1)
        for value in ('2**65','2**10000000','call()','name','[1]','2/1'):
            with self.subTest(value=value),self.assertRaises(ValueError):constant_default(ast.parse(value,mode='eval').body)

    def test_comprehension_first_iterators_and_nested_lexical_scopes_stay_live(self):
        tree=ast.parse('class Donor:\n def read(self):\n  def nested(value=2): return value+external\n  return [nested(x) for x in x]\n')
        generated,_=redirect_guard_globals(tree);state={'external':5,'x':[1,2]}
        namespace={'_gitgood_path_body_name':lambda key:state[key]};exec(generated,namespace)
        self.assertEqual(namespace['Donor']().read(),[6,7])
        state.update(external=9,x=[4]);self.assertEqual(namespace['Donor']().read(),[13])


class AdapterTest(unittest.TestCase):
    def setUp(self):
        self.modules,self.native,self.rows,self.alias=model()
        self.adapter=probe.Adapter(self.modules,self.native,self.rows,alias_modules=[self.alias],owner_check=lambda:None)

    def test_classes_static_class_methods_and_direct_aliases_use_live_original_globals(self):
        cls=self.modules[0].Thing;original=self.modules[0].read
        with self.adapter.installed():
            self.assertIs(self.modules[0].Thing,cls);self.assertIs(self.alias.read,self.modules[0].read)
            self.assertIsNot(self.alias.read,original);self.assertEqual(self.alias.read(),4)
            self.assertEqual(cls.static(2),3);self.assertEqual(cls.klass(2),(cls,3))
            self.modules[0].helper=lambda value:value*7
            self.assertEqual(self.alias.read(3),21);self.assertEqual(cls.static(3),21)
        self.assertTrue(self.adapter.restored());self.assertIs(self.alias.read,original)

    def test_original_error_identity_and_missing_global_metadata_are_preserved(self):
        failure=KeyboardInterrupt('synthetic original')
        with self.adapter.installed():
            self.modules[0].helper=Mock(side_effect=failure)
            with self.assertRaises(KeyboardInterrupt) as caught:self.alias.read()
            self.assertIs(caught.exception,failure)
            del self.modules[0].helper
            with self.assertRaises(NameError) as caught:self.alias.read()
            self.assertEqual(caught.exception.name,'helper')
        self.assertTrue(self.adapter.restored())

    def test_nested_foreign_owner_and_foreign_class_refuse(self):
        with self.adapter.installed():
            with self.assertRaises(ValueError):
                with self.adapter.installed():pass
        with patch.object(probe.threading,'get_ident',return_value=-1),self.assertRaises(ValueError):self.adapter.check()
        self.modules[0].Thing=type('Foreign',(),{})
        with self.assertRaises(ValueError):self.adapter.check()
        self.assertTrue(self.adapter.restored())

    def test_interruption_and_partial_install_restore_all_targets_and_aliases(self):
        failure=KeyboardInterrupt('synthetic original')
        with self.assertRaises(KeyboardInterrupt) as caught:
            with self.adapter.installed():raise failure
        self.assertIs(caught.exception,failure);self.assertTrue(self.adapter.restored())
        def assign(owner,name,value):
            if owner is self.modules[2] and value is not vars(owner).get(name):raise failure
            builtins.setattr(owner,name,value)
        with patch.object(probe,'setattr',assign,create=True),self.assertRaises(KeyboardInterrupt) as caught:
            with self.adapter.installed():pass
        self.assertIs(caught.exception,failure);self.assertTrue(self.adapter.restored())

    def test_failed_cleanup_attempts_every_restore_and_preserves_pending_error(self):
        failure=KeyboardInterrupt('synthetic original');restored=[];originals={(id(o),n):v for o,n,v,_ in self.adapter.entries}
        def assign(owner,name,value):
            if value is originals[id(owner),name]:
                restored.append((id(owner),name))
                if owner is self.modules[0] and name=='read':raise RuntimeError('cleanup')
            builtins.setattr(owner,name,value)
        try:
            with patch.object(probe,'setattr',assign,create=True),self.assertRaises(KeyboardInterrupt) as caught:
                with self.adapter.installed():
                    del self.alias.read
                    raise failure
            self.assertIs(caught.exception,failure);self.assertTrue(self.adapter.broken)
            self.assertEqual(len(restored),len(self.adapter.entries))
        finally:
            for owner,name,old,_ in self.adapter.entries:builtins.setattr(owner,name,old)

    def test_twenty_pairs_alternate_original_actors_and_restore_before_baseline(self):
        adapter=self.adapter;original=self.modules[0].read;order=[]
        stage=types.SimpleNamespace(usable=True,state='ready')
        def guard(subject):
            self.assertIs(subject,stage);order.append(self.modules[0].read is original)
            return [module.read() for module in self.modules]
        loaded=types.SimpleNamespace(modules=self.modules,native=self.native,rows=self.rows,
            original_codes=None,validate=Mock(),evidence=lambda:{})
        with patch.object(probe,'root_owner'),patch.object(probe,'Adapter',return_value=adapter):
            result=probe.compare_guard(loaded,guard,stage)
        self.assertEqual(order,[value for index in range(20) for value in ((True,False) if index%2==0 else (False,True))])
        self.assertEqual(len(result['pairs']),20);self.assertTrue(adapter.restored())
        self.assertFalse(result['production_adopted']);self.assertFalse(result['observation_results_retained'])
        self.assertTrue(all(value>0 for value in result['compiled_global_loads'].values()))
        loaded.validate.assert_called_once()

    def test_first_guard_restores_before_measurements_and_effects_and_poisons_on_failure(self):
        events=[];test=self
        class Stage:
            usable=True;state='ready'
            def check(self):events.append('guard');return {'same':True}
        original=Stage.check;result={'private':True}
        class Measurements:
            def __enter__(self):test.assertIs(Stage.check,original);events.append('measurements')
            def __exit__(self,*_):events.append('exit')
        with patch.object(probe,'compare_guard',return_value=result):
            with probe.AtFirstGuard(None,Stage,Measurements()) as trial:self.assertEqual(Stage().check(),{'same':True})
        self.assertEqual(events,['measurements','guard','exit']);self.assertIs(trial.result,result)
        stage=Stage();stage.close=Mock(side_effect=RuntimeError('cleanup'))
        stage.allocation=types.SimpleNamespace(usable=True,close=Mock());failure=KeyboardInterrupt('original')
        with patch.object(probe,'compare_guard',side_effect=failure),self.assertRaises(KeyboardInterrupt) as caught:
            with probe.AtFirstGuard(None,Stage,Measurements()):stage.check()
        self.assertIs(caught.exception,failure);self.assertIs(Stage.check,original)
        self.assertFalse(stage.usable);self.assertFalse(stage.allocation.usable)
        stage.close.assert_called_once();stage.allocation.close.assert_called_once()


@unittest.skipUnless(sys.platform=='linux' and sys.version_info[:2]==(3,12)
    and getattr(os,'geteuid',lambda:-1)()==0,'Actual hosted Linux CPython3.12 Root required')
class HostedInstalledBodiesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ci=Path(__file__).resolve().parent;built=ci.parents[1]/'.gitgood/guard-body-probe'
        cls.namespace=tempfile.TemporaryDirectory(prefix='gitgood-guard-bodies-',dir='/var/lib')
        cls.addClassCleanup(cls.namespace.cleanup);cls.root=Path(cls.namespace.name);cls.root.chmod(0o700)
        for source in [*(ci/name for name in probe.HELPERS),
                *(built/name for name in (*(name+'.py' for name in MODULE_NAMES),
                    'guard-body-donor.pyx','manifest.json',probe.extension_name()))]:
            destination=cls.root/source.name;shutil.copyfile(source,destination);destination.chmod(0o644)
        # Test only copied Root-owned deployment modules. No source checkout is
        # admitted as production code by the loader.
        original_deployment=ci.parents[0]/'deployment';cls.deployment=cls.root/'deployment';cls.deployment.mkdir()
        for source in original_deployment.glob('*.py'):
            destination=cls.deployment/source.name;shutil.copyfile(source,destination);destination.chmod(0o644)
        sys.path.insert(0,str(cls.deployment));cls.addClassCleanup(sys.path.remove,str(cls.deployment))
        cls.loaded=probe.Loaded(cls.root)

    def adapter(self):return probe.Adapter(self.loaded.modules,self.loaded.native,self.loaded.rows,original_codes=self.loaded.original_codes)

    def test_original_code_source_and_extension_custody_are_fresh(self):
        self.loaded.validate()
        source=self.root/'guard_body_source.py';raw=source.read_bytes()
        try:
            source.write_bytes(raw+b'\n# synthetic mutation\n')
            with self.assertRaises(ValueError):self.loaded.validate()
        finally:source.write_bytes(raw)
        # A restored byte sequence has a different retained metadata identity.
        with self.assertRaises(ValueError):self.loaded.validate()
        # Refresh only this test fixture's identity, never production state.
        self.loaded.files['guard_body_source.py']=probe._read_owned(source,262144)
        self.loaded.validate()

    def test_fresh_root_file_mutations_and_live_global_errors(self):
        service=self.loaded.modules[0];adapter=self.adapter()
        with tempfile.TemporaryDirectory(prefix='fresh-',dir=self.root) as directory:
            path=Path(directory)/'leaf';path.write_bytes(b'one');path.chmod(0o644)
            with adapter.installed():
                identity,raw=service.root_file(path);self.assertEqual(raw,b'one')
                path.write_bytes(b'new bytes');self.assertEqual(service.root_file(path)[1],b'new bytes')
                path.rename(path.with_name('retained'));path.write_bytes(b'other')
                self.assertNotEqual(service.root_file(path)[0]['inode'],identity['inode'])
                path.chmod(0o666)
                with self.assertRaises(service.ServiceRefused):service.root_file(path)
                failure=KeyboardInterrupt('original')
                with patch.object(service,'os',types.SimpleNamespace(open=Mock(side_effect=failure))):
                    with self.assertRaises(KeyboardInterrupt) as caught:service.read_bytes('/synthetic')
                    self.assertIs(caught.exception,failure)
        self.assertTrue(adapter.restored());self.loaded.validate()

    def test_all_original_372_root_cases_with_compiled_installed_bodies(self):
        from importlib.util import module_from_spec,spec_from_file_location
        spec=spec_from_file_location('_original_lexical_cases',Path(__file__).with_name('lexical-path-test.py'))
        original=module_from_spec(spec);spec.loader.exec_module(original)
        suite=unittest.TestSuite()
        for name,count in original.ROOT_SCOPES:
            scope=unittest.defaultTestLoader.loadTestsFromName(name)
            self.assertEqual(scope.countTestCases(),count);suite.addTest(scope)
        adapter=self.adapter();stream=io.StringIO();before=self.loaded.native.load_counts()
        with adapter.installed():result=unittest.TextTestRunner(stream=stream).run(suite)
        self.assertEqual(result.testsRun,372);self.assertFalse(result.skipped)
        self.assertTrue(result.wasSuccessful(),stream.getvalue());self.assertTrue(adapter.restored())
        self.assertGreater(sum(self.loaded.native.load_counts().values()),sum(before.values()));self.loaded.validate()
        print('guard_body_original_root_cases=372',flush=True)


if __name__=='__main__':unittest.main(verbosity=2)
