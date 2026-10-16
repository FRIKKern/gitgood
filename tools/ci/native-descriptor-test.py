#!/usr/bin/env python3
"""Scope contracts locally; actual bound methods/notifications only on Root CI."""
import builtins
import importlib.util
import io
import itertools
import os
from pathlib import Path
import pathlib
import sys
import threading
import types
import unittest
from unittest.mock import Mock,patch

sys.dont_write_bytecode=True
import native_path_probe as probe

spec=importlib.util.spec_from_file_location('_descriptor_legacy_path_cases',Path(__file__).with_name('native-path-test.py'))
legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)


class FakeDescriptorNative(legacy.FakeNative):
    """Python scope model, deliberately not native notification evidence."""
    def __init__(self):
        super().__init__();self.plans=[];self.live=None
        for name in probe.DESCRIPTOR_APIS:setattr(self,name,getattr(self,name))
    def descriptor_plan(self,concrete,originals,pid,thread,capacity,import_globals):
        plan=types.SimpleNamespace(concrete=concrete,originals=originals,active=False,closed=False,bound=False,
            issued=False,tables=(),counts={key:dict.fromkeys(probe.ROLES,0) for key in ('calls','entries','fallbacks')},
            cache_entries=0,cache_hits=0,cache_misses=0,dirty=False)
        self.plans.append(plan);return plan
    def descriptor_entries(self,plan):
        if plan.issued:raise ValueError('already issued')
        plan.issued=True
        def create(op,original):
            def method(subject,*args,**kwargs):
                name=probe.ROLES[op];plan.counts['entries'][name]+=1
                if not plan.closed and plan.active and not plan.dirty and not kwargs:
                    if not self.admitted(plan.tables[op]):plan.dirty=True
                    elif type(subject) is plan.concrete and not any(type(v) not in {str,plan.concrete} for v in args):
                        result=original(subject,*args);plan.counts['calls'][name]+=1;return result
                plan.counts['fallbacks'][name]+=1;return original(subject,*args,**kwargs)
            return method
        return tuple(create(op,fn) for op,fn in enumerate(plan.originals))
    def descriptor_bind(self,plan,tables,modules):
        if plan.bound:raise ValueError('already bound')
        plan.bound=True;plan.tables=tables
    def descriptor_phase(self,plan,phase):
        if phase==0:
            if self.live is not None or plan.closed or not self.admitted(plan.tables[0]):raise ValueError('activation')
            self.live=plan;plan.active=True;plan.dirty=False
        else:
            plan.active=False
            if self.live is plan:self.live=None
    def descriptor_counts(self,plan):
        return {**{key:value.copy() for key,value in plan.counts.items()},
            **{name:getattr(plan,name) for name in ('cache_entries','cache_hits','cache_misses')},
            'phase':'closed' if plan.closed else 'active' if plan.active else 'inactive',
            'watching':plan.active,'code_changed':plan.dirty,'code_inputs':0 if plan.closed else 32}
    def descriptor_close(self,plan):
        if plan.active:raise ValueError('active')
        plan.closed=True;plan.tables=();plan.cache_entries=0


class DescriptorScopeTest(unittest.TestCase):
    def setUp(self):
        self.native=FakeDescriptorNative()
        self.adapter=probe.DescriptorAdapter(self.native,owner_check=lambda:None)
        self.addCleanup(self.adapter.close)
    def test_partial_install_interrupt_restores_all_touched_entries_and_releases_scope(self):
        assign=setattr;failure=KeyboardInterrupt('partial install')
        def interrupted(owner,name,value):
            if owner is pathlib.PurePath and name=='__str__' and value is self.adapter.replacements[2]:raise failure
            assign(owner,name,value)
        with patch.object(probe,'setattr',interrupted,create=True),self.assertRaises(KeyboardInterrupt) as caught:
            with self.adapter.installed():self.fail('entered partial installation')
        self.assertIs(caught.exception,failure);self.assertTrue(self.adapter.restored());self.assertIsNone(self.native.live)
        self.adapter.close();self.assertEqual(self.adapter.details()['code_inputs'],0);self.assertIsNone(self.adapter.plan)
    def test_bind_failure_closes_partially_prepared_context(self):
        failure=KeyboardInterrupt('bind')
        with patch.object(self.native,'descriptor_bind',side_effect=failure),self.assertRaises(KeyboardInterrupt) as caught:
            probe.DescriptorAdapter(self.native,owner_check=lambda:None)
        self.assertIs(caught.exception,failure);self.assertTrue(self.native.plans[-1].closed)
    def test_pending_body_error_wins_over_phase_cleanup_and_close_errors(self):
        failure=KeyboardInterrupt('body');phase=self.native.descriptor_phase
        def interrupted(plan,number):
            phase(plan,number)
            if number==1:raise OSError('deactivate')
        self.adapter.descriptor_apis['descriptor_phase']=interrupted
        with self.assertRaises(KeyboardInterrupt) as caught:
            with self.adapter.installed():raise failure
        self.assertIs(caught.exception,failure);self.assertTrue(self.adapter.restored());self.assertIsNone(self.native.live)
        self.adapter.descriptor_apis['descriptor_close']=Mock(side_effect=OSError('close'))
        with self.assertRaises(KeyboardInterrupt) as caught:
            try:raise failure
            finally:self.adapter.close()
        self.assertIs(caught.exception,failure);self.assertIsNone(self.adapter.plan);self.assertTrue(self.adapter.closed)
    def test_closed_counter_schema_rejects_extra_fields_booleans_and_unbounded_inputs(self):
        count=self.adapter.descriptor_apis['descriptor_counts']
        for change in ({'private_path':'private'},{'code_inputs':257},{'cache_entries':True},{'phase':'unknown'},
                {'watching':1},{'entries':dict.fromkeys(probe.ROLES,True)}):
            self.adapter.descriptor_apis['descriptor_counts']=lambda plan:{**count(plan),**change}
            with self.assertRaises(ValueError):self.adapter.details()
        self.adapter.descriptor_apis['descriptor_counts']=count
    def test_nested_scope_does_not_replace_or_unregister_first_scope(self):
        other=probe.DescriptorAdapter(self.native,owner_check=lambda:None);self.addCleanup(other.close)
        expected=str(Path('/still-active'))
        with self.adapter.installed():
            with self.assertRaises(ValueError):
                with other.installed():self.fail('nested')
            self.assertIs(self.native.live,self.adapter.plan)
            self.assertEqual(str(Path('/still-active')),expected)
        self.assertTrue(self.adapter.restored());self.assertIsNone(self.native.live)
    def test_saved_method_after_close_calls_original_sdk(self):
        expected=str(Path('/after'))
        with self.adapter.installed():
            p=Path('/before');saved=p.with_segments
        self.adapter.close();self.assertEqual(str(saved('/after')),expected)
        self.assertEqual(self.adapter.details()['phase'],'closed');self.assertFalse(self.adapter.details()['watching'])
    def test_posix_dependency_bindings_code_and_builtin_custody_are_complete(self):
        table=self.adapter.tables[0]
        for owner,name in ((vars(probe.posixpath),'os'),(vars(probe.posixpath),'_get_sep'),
                (vars(builtins),'map'),(vars(builtins),'bytes')):
            self.assertTrue(any(o is owner and n==name and v is owner[name] for o,n,v in table))
        fn=probe.posixpath._get_sep
        self.assertTrue(any(o is fn and n=='__code__' and v is fn.__code__ for o,n,v in table))
        with self.adapter.installed():
            self.assertTrue(self.native.admitted(table))
            with patch.object(probe.posixpath,'_get_sep',lambda path:'/'):
                self.assertFalse(self.native.admitted(table))
        for owner,name,value in ((probe.posixpath,'os',object()),(builtins,'map',lambda *args:iter(())),
                (builtins,'bytes',str)):
            with patch.object(owner,name,value),patch.object(self.native,'descriptor_plan') as planned:
                with self.assertRaises(ValueError):probe.DescriptorAdapter(self.native,owner_check=lambda:None)
                planned.assert_not_called()
    def test_comparison_keeps_twenty_alternating_original_guards_and_removes_notifications(self):
        stage=types.SimpleNamespace(usable=True,state='ready');events=[]
        loaded=types.SimpleNamespace(native=self.native,codes=None,validate=Mock(),evidence=lambda:{'synthetic':True})
        def guard(value):
            self.assertIs(value,stage);events.append(self.adapter.active)
            p=Path('/synthetic');p._load_parts();return str(p/'leaf')
        with patch.object(probe.metadata,'root_owner',lambda:None),\
                patch.object(probe,'DescriptorAdapter',return_value=self.adapter),\
                patch.object(probe.time,'monotonic_ns',side_effect=itertools.count(1000,1000).__next__):
            # Avoid isinstance against the patched constructor; use the exact
            # adapter factory argument and test native entry evidence separately.
            with patch.object(probe,'isinstance',lambda value,kind:True,create=True):
                result=probe.compare_descriptor_guard(loaded,guard,stage)
        self.assertEqual(events,[x for n in range(20) for x in ((False,True) if n%2==0 else (True,False))])
        self.assertEqual(result['paired_checks'],40);self.assertEqual(result['native_entries'],result['native_calls'])
        self.assertTrue(result['dictionary_notifications_removed']);self.assertTrue(self.adapter.restored())
        self.assertFalse(self.adapter.details()['watching']);self.assertEqual(self.adapter.details()['code_inputs'],0)
        self.assertEqual(loaded.validate.call_count,2)


@unittest.skipUnless(sys.platform=='linux' and sys.version_info[:2]==(3,12)
    and getattr(os,'geteuid',lambda:-1)()==0,'Actual hosted Linux CPython3.12 Root required')
class HostedDescriptorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):legacy.HostedPathTest.setUpClass.__func__(cls)
    def adapter(self):
        value=probe.DescriptorAdapter(self.loaded.native,sdk_codes=self.loaded.codes)
        self.addCleanup(value.close);return value
    def test_actual_c_bound_four_roles_fresh_objects_and_original_classes(self):
        expected=legacy.HostedPathTest.observe();a=self.adapter();original_classes=(pathlib.Path,pathlib.PurePath,pathlib.PosixPath)
        with a.installed():
            self.assertEqual(legacy.HostedPathTest.observe(),expected)
            self.assertTrue(all(type(getattr(pathlib.PosixPath,name)) is types.BuiltinFunctionType
                for name in ('__init__','_load_parts','__str__','with_segments')))
            p=Path('/same');q=Path('/same');self.assertIsNot(p,q);self.assertIsNot(p._raw_paths,q._raw_paths)
            p._load_parts();q._load_parts();self.assertIsNot(p._tail_cached,q._tail_cached)
            p._tail_cached.append('changed');self.assertEqual(q.parts,('/','same'))
        self.assertEqual((pathlib.Path,pathlib.PurePath,pathlib.PosixPath),original_classes)
        stats=a.details();self.assertEqual(stats['entries'],stats['calls']);self.assertFalse(any(stats['fallbacks'].values()))
        self.assertTrue(all(v>0 for v in stats['calls'].values()));self.assertFalse(stats['watching']);self.loaded.validate()
    def test_actual_cache_bound_lazy_state_and_original_metadata(self):
        a=self.adapter();leaf=self.root/'descriptor-leaf';leaf.write_bytes(b'one');self.addCleanup(leaf.unlink)
        with a.installed():
            for n in range(300):self.assertEqual(str(Path('/synthetic/'+str(n))),'/synthetic/'+str(n))
            p=Path('/before');self.assertFalse(hasattr(p,'_drv'));self.assertEqual(str(p),'/before')
            p._raw_paths[:]=['/after'];p._load_parts();self.assertEqual(p.parts,('/','after'));self.assertEqual(str(p),'/before')
            self.assertEqual(leaf.stat().st_size,3);leaf.write_bytes(b'changed');self.assertEqual(leaf.stat().st_size,7)
        stats=a.details();self.assertLessEqual(stats['cache_entries'],256);self.assertGreater(stats['cache_misses'],256)
        a.close();self.assertEqual(a.details()['cache_entries'],0);self.assertEqual(a.details()['code_inputs'],0)
    def test_actual_notification_is_permanent_even_after_binding_restored_and_unrelated_writes_are_ignored(self):
        a=self.adapter();before=a.values()
        with a.installed():
            setattr(pathlib,'_gitgood_unrelated_test',1)
            try:self.assertEqual(str(Path('/supported')),'/supported');self.assertFalse(a.details()['code_changed'])
            finally:delattr(pathlib,'_gitgood_unrelated_test')
            original=vars(builtins)['len'];vars(builtins)['len']=lambda x:original(x);vars(builtins)['len']=original
            self.assertTrue(a.details()['code_changed']);self.assertEqual(str(Path('/fallback')),'/fallback')
        self.assertGreater(a.details()['fallbacks']['constructor'],0)
        supported=a.values()
        with a.installed():self.assertEqual(str(Path('/fresh-scope')),'/fresh-scope')
        self.assertGreater(a.values()['constructor'],supported['constructor']);self.assertGreater(supported['constructor'],before['constructor'])
    def test_actual_new_inherited_shadow_and_noninterned_key_invalidate_before_native_slot_mutation(self):
        a=self.adapter();name=''.join(('_fl','avour'));self.assertEqual(name,'_flavour')
        with a.installed():
            setattr(pathlib.PosixPath,name,object())
            try:
                self.assertTrue(a.details()['code_changed']);before=a.values()
                self.assertEqual(Path('/fallback')._raw_paths,['/fallback']);self.assertEqual(a.values(),before)
            finally:delattr(pathlib.PosixPath,name)
        self.assertTrue(a.restored());self.loaded.validate()
        a.close();a=self.adapter()
        with a.installed():
            setattr(pathlib.PosixPath,'__getattr__',lambda self,name:None)
            delattr(pathlib.PosixPath,'__getattr__')
            self.assertTrue(a.details()['code_changed'])
            self.assertEqual(str(Path('/fallback')),'/fallback');self.assertEqual(a.values()['constructor'],0)
    def test_actual_direct_function_code_defaults_and_class_cells_invalidate(self):
        parser=vars(pathlib.PurePath)['_parse_path'].__func__;code=parser.__code__
        def changed(cls,path):raise KeyboardInterrupt('original parser')
        for field,after in (('__code__',changed.__code__),('__defaults__',())):
            a=self.adapter();saved=getattr(parser,field)
            try:
                with a.installed():
                    setattr(parser,field,after)
                    if field=='__code__':
                        with self.assertRaises(KeyboardInterrupt) as caught:str(Path('/fallback'))
                        self.assertEqual(caught.exception.args,('original parser',))
                    else:self.assertEqual(str(Path('/fallback')),'/fallback')
                    self.assertTrue(a.details()['code_changed'])
                    setattr(parser,field,saved)
            finally:setattr(parser,field,saved);a.close()
        self.assertIs(parser.__code__,code)
        a=self.adapter();cell=a.sdk_functions['Path.__init__'].__closure__[0];saved=cell.cell_contents
        try:
            with a.installed():
                cell.cell_contents=object
                try:a.originals[0](object.__new__(pathlib.PosixPath),'/fallback')
                except BaseException as error:expected=(type(error),error.args)
                else:self.fail('changed original class cell unexpectedly succeeded')
                with self.assertRaises(expected[0]) as caught:Path('/fallback')
                self.assertEqual(caught.exception.args,expected[1])
                self.assertTrue(a.details()['code_changed']);cell.cell_contents=saved
        finally:cell.cell_contents=saved
    def test_actual_module_class_hook_falls_back_and_preserves_original_callback(self):
        a=self.adapter();module_type=type(os);events=[]
        class Module(module_type):
            def __getattribute__(self,name):
                if name=='fspath':events.append(name)
                return super().__getattribute__(name)
        class Value:
            def __fspath__(self):return '/callback'
        try:
            with a.installed():
                os.__class__=Module
                self.assertEqual(str(Path(Value())),'/callback');self.assertTrue(events)
                self.assertTrue(a.details()['code_changed']);self.assertEqual(a.values()['constructor'],0)
                os.__class__=module_type
        finally:os.__class__=module_type
        self.assertTrue(a.restored());self.loaded.validate()
    def test_actual_posix_join_dependency_changes_preserve_original_callbacks_and_errors(self):
        events=[];flavour=probe.posixpath
        original_sep=flavour._get_sep;original_fspath=os.fspath;original_map=builtins.map
        def separator(value):events.append('separator');return original_sep(value)
        def fspath(value):events.append('fspath');return original_fspath(value)
        def mapped(fn,*values):
            if fn is original_fspath:events.append('map')
            return original_map(fn,*values)
        class BytesMeta(type):
            def __instancecheck__(cls,value):events.append('bytes');return False
        class Bytes(metaclass=BytesMeta):pass
        targets=((flavour,'_get_sep',separator),(flavour,'os',types.SimpleNamespace(fspath=fspath)),
            (builtins,'map',mapped),(builtins,'bytes',Bytes))
        def observe():return str(Path('/dependency')/'leaf')
        for owner,name,value in targets:
            events.clear()
            with patch.object(owner,name,value):expected=observe();expected_events=events[:]
            self.assertTrue(expected_events,(name,'original callback missing'));events.clear();a=self.adapter()
            with a.installed():
                before=a.values()
                with patch.object(owner,name,value):actual=observe();actual_events=events[:]
                self.assertTrue(a.details()['code_changed']);self.assertEqual(a.values(),before)
            self.assertEqual(actual,expected);self.assertEqual(actual_events,expected_events)
            self.assertGreater(a.details()['fallbacks']['constructor'],0);a.close();self.loaded.validate()
        # Changing an existing helper's code does not emit a dictionary event.
        # Its direct live function check must still decline before SDK slots.
        a=self.adapter();code=original_sep.__code__
        def changed(path):raise KeyboardInterrupt('original separator')
        try:
            with a.installed():
                original_sep.__code__=changed.__code__
                with self.assertRaises(KeyboardInterrupt) as caught:observe()
                self.assertEqual(caught.exception.args,('original separator',));self.assertTrue(a.details()['code_changed'])
                self.assertEqual(a.values()['constructor'],0);original_sep.__code__=code
        finally:original_sep.__code__=code
        self.assertTrue(a.restored());self.loaded.validate()
    def test_actual_import_spec_dict_replacement_callbacks_hook_failure_and_module_loss(self):
        a=self.adapter()
        if a.import_globals is None:self.skipTest('SDK does not import ntpath locally')
        argument=Path('/before');events=[];original_spec=probe.ntpath.__spec__
        class Spec:
            def __getattribute__(self,name):
                if name=='_initializing':argument._raw_paths[:]=['/after'];events.append(name);return False
                raise AssertionError('unexpected spec observation')
        with a.installed():
            probe.ntpath.__spec__=Spec()
            try:result=Path(argument)
            finally:probe.ntpath.__spec__=original_spec
        self.assertTrue(events);self.assertEqual(str(result),'/after');self.assertEqual(a.values()['constructor'],0)
        a.close();a=self.adapter();original_dict=original_spec.__dict__
        try:
            with a.installed():
                original_spec.__dict__=dict(original_dict)
                self.assertEqual(str(Path('/fallback')),'/fallback');self.assertTrue(a.details()['code_changed'])
                original_spec.__dict__=original_dict
        finally:original_spec.__dict__=original_dict
        a.close();a=self.adapter();failure=KeyboardInterrupt('original import');calls=[];original_import=__import__
        def changed(name,*args,**kwargs):
            if name=='ntpath':calls.append(name);raise failure
            return original_import(name,*args,**kwargs)
        with a.installed(),patch.object(builtins,'__import__',changed):
            with self.assertRaises(KeyboardInterrupt) as caught:Path('/fallback')
            self.assertIs(caught.exception,failure)
        self.assertEqual(calls,['ntpath']);self.assertEqual(a.values()['constructor'],0)
        a.close();a=self.adapter()
        with a.installed():
            module=sys.modules.pop('ntpath')
            try:self.assertTrue(a.details()['code_changed'])
            finally:sys.modules['ntpath']=module
            self.assertEqual(str(Path('/fallback')),'/fallback');self.assertEqual(a.values()['constructor'],0)
    def test_actual_foreign_thread_original_fallback_and_saved_method_after_close(self):
        a=self.adapter();values=[];errors=[]
        def worker():
            try:values.append(str(Path('/thread')/'leaf'))
            except BaseException as error:errors.append(error)
        with a.installed():
            t=threading.Thread(target=worker);t.start();t.join(5)
            self.assertFalse(t.is_alive());self.assertFalse(errors);self.assertEqual(values,['/thread/leaf'])
            saved=Path('/saved').with_segments
        self.assertGreater(a.details()['fallbacks']['constructor'],0);a.close()
        self.assertEqual(str(saved('/after-close')),'/after-close');self.assertTrue(a.restored())
    def test_actual_owner_preflight_oneshot_lifecycle_nested_and_interruption(self):
        n=self.loaded.native;a=self.adapter();b=self.adapter();before=(n.counts(),n.read_counts())
        for args in ((pathlib.PosixPath,(),os.getpid(),threading.get_ident(),256,None),
                (pathlib.PosixPath,a.originals,os.getpid(),threading.get_ident(),257,None)):
            with self.assertRaises(TypeError):n.descriptor_plan(*args)
        with self.assertRaises(ValueError):n.descriptor_entries(a.plan)
        with self.assertRaises(TypeError):n.descriptor_bind(a.plan,a.tables,a.modules)
        failure=KeyboardInterrupt('body')
        with self.assertRaises(KeyboardInterrupt) as caught:
            with a.installed():
                with self.assertRaises(ValueError):n.descriptor_phase(b.plan,0)
                with self.assertRaises(ValueError):n.descriptor_close(a.plan)
                self.assertEqual(str(Path('/supported')),'/supported');raise failure
        self.assertIs(caught.exception,failure);self.assertTrue(a.restored());self.assertFalse(a.details()['watching'])
        a.close();b.close();self.assertEqual((n.counts(),n.read_counts()),before)
    def test_zz_all_original_372_root_cases_with_bound_descriptors(self):
        spec=importlib.util.spec_from_file_location('_descriptor_original_lexical_cases',Path(__file__).with_name('lexical-path-test.py'))
        original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original);suite=unittest.TestSuite()
        for name,count in original.ROOT_SCOPES:
            scope=unittest.defaultTestLoader.loadTestsFromName(name);self.assertEqual(scope.countTestCases(),count);suite.addTest(scope)
        a=self.adapter();stream=io.StringIO()
        class Progress(unittest.TextTestResult):
            def startTest(self,test):
                print('native_descriptor_root_case='+type(test).__name__+'.'+test._testMethodName,flush=True)
                super().startTest(test)
        with a.installed():result=unittest.TextTestRunner(stream=stream,resultclass=Progress).run(suite)
        self.assertEqual(result.testsRun,372);self.assertFalse(result.skipped);self.assertTrue(result.wasSuccessful(),stream.getvalue())
        self.assertTrue(a.restored());self.loaded.validate();a.close();self.assertFalse(a.details()['watching'])
        print('native_descriptor_original_root_cases=372',flush=True)


if __name__=='__main__':unittest.main(verbosity=2)
