#!/usr/bin/env python3
"""SDK/admission/restoration contract; actual native Root execution is separate."""
import ast
import faulthandler
import importlib.util
import itertools
import os
from pathlib import Path
import pathlib
import posixpath
import shutil
import sys
import types
import threading
import unittest
from unittest.mock import Mock,patch

sys.dont_write_bytecode=True
faulthandler.enable(all_threads=True)
import native_path_probe as probe


class FakeNative(types.ModuleType):
    """Exercise the Python boundary using original SDK bodies, never C evidence."""
    def __init__(self):
        super().__init__('_native_path_contract_fake')
        self.originals=tuple(vars(owner)[name] for owner,name in probe.TARGETS)
        self.path_plan=self.path_plan;self.path_call=self.path_call
    def path_plan(self,tables,concrete,pid,thread,capacity):
        return types.SimpleNamespace(tables=tables,concrete=concrete,owner=(pid,thread),capacity=capacity,
            counts={**dict.fromkeys(probe.ROLES,0),'cache_entries':0,'cache_hits':0,'cache_misses':0})
    @staticmethod
    def admitted(table):
        for owner,name,value in table:
            if type(owner) is types.FunctionType:current=owner.__code__
            elif type(owner) is types.CellType:current=owner.cell_contents
            elif type(owner) is type:
                current=next((vars(base)[name] for base in owner.__mro__ if name in vars(base)),None)
            else:current=owner.get(name)
            if current is not value:return False
        return True
    def path_call(self,op,plan,subject,args):
        if op==4:return plan.counts.copy()
        if op==5:plan.counts['cache_entries']=0;return None
        if not self.admitted(plan.tables[op]) or type(subject) is not plan.concrete:return NotImplemented
        if op in {0,3} and any(type(v) not in {str,plan.concrete} for v in args):return NotImplemented
        result=self.originals[op](subject,*args)
        plan.counts[probe.ROLES[op]]+=1
        return result


class ComparisonContractTest(unittest.TestCase):
    def setUp(self):
        self.native=FakeNative();self.adapter=probe.Adapter(self.native,owner_check=lambda:None)
        self.addCleanup(self.adapter.close)
        self.loaded=types.SimpleNamespace(native=self.native,codes=None,validate=Mock(),evidence=lambda:{'synthetic':True})
        self.stage=types.SimpleNamespace(usable=True,state='ready',allocation=types.SimpleNamespace(usable=True,close=Mock()),close=Mock())
        self.events=[]
    def guard(self,stage):
        self.assertIs(stage,self.stage);self.events.append(self.adapter.active)
        p=Path('/synthetic');p._load_parts();q=p/'leaf'
        return str(q),q.parts
    def compare(self,guard=None):
        # This boundary fixture does no representative I/O. Use a deterministic
        # positive clock rather than Windows' coarse monotonic resolution.
        with patch.object(probe.metadata,'root_owner',lambda:None),patch.object(probe,'Adapter',return_value=self.adapter),\
                patch.object(probe.time,'monotonic_ns',side_effect=itertools.count(1000,1000).__next__):
            return probe.compare_guard(self.loaded,self.guard if guard is None else guard,self.stage)
    def test_twenty_alternating_pairs_clear_capsule_and_validate_before_effects(self):
        result=self.compare()
        self.assertEqual(self.events,[x for n in range(20) for x in ((False,True) if n%2==0 else (True,False))])
        self.assertEqual(len(result['pairs']),20);self.assertEqual(result['paired_checks'],40)
        self.assertTrue(all(v>0 for v in result['native_calls'].values()));self.assertFalse(any(result['fallbacks'].values()))
        self.assertTrue(result['lexical_cache_cleared']);self.assertIsNone(self.adapter.plan)
        self.assertEqual(self.adapter.values()['cache_entries'],0);self.assertTrue(self.adapter.restored())
        self.loaded.validate.assert_called_once();self.stage.close.assert_not_called()
    def test_unequal_observations_refuse_after_restoration_and_clear(self):
        def changed(stage):self.guard(stage);return self.adapter.active
        with self.assertRaises(ValueError):self.compare(changed)
        self.assertTrue(self.adapter.restored());self.assertTrue(self.adapter.closed);self.assertIsNone(self.adapter.plan)
        self.loaded.validate.assert_not_called()
    def test_original_guard_error_wins_over_clear_error_and_context_is_released(self):
        failure=KeyboardInterrupt('original guard');original=self.adapter.call
        def call(op,*args):
            if op==5:raise OSError('clear error')
            return original(op,*args)
        self.adapter.call=call
        def interrupted(stage):self.guard(stage);raise failure
        with self.assertRaises(KeyboardInterrupt) as caught:self.compare(interrupted)
        self.assertIs(caught.exception,failure);self.assertTrue(self.adapter.restored());self.assertIsNone(self.adapter.plan)
    def test_missing_native_role_and_any_fallback_refuse(self):
        def missing(stage):return 'unchanged'
        with self.assertRaises(ValueError):self.compare(missing)
        self.adapter=probe.Adapter(self.native,owner_check=lambda:None);self.addCleanup(self.adapter.close)
        self.adapter.fallbacks['string']=1
        with self.assertRaises(ValueError):self.compare()
        self.assertTrue(self.adapter.restored());self.assertTrue(self.adapter.closed)
    def first_fixture(self):
        events=[]
        class Stage:
            usable=True;state='ready'
            def __init__(subject):subject.allocation=types.SimpleNamespace(usable=True,close=Mock());subject.close=Mock()
            def check(subject):events.append('original');return 'original value'
        original=Stage.check
        class Measurements:
            def __enter__(subject):self.assertIs(Stage.check,original);events.append('measurements')
            def __exit__(subject,*exc):events.append(('exit',exc[1]))
        return Stage,original,Measurements(),events
    def test_first_guard_comparison_precedes_original_measurements_and_is_not_repeated(self):
        Stage,original,measurements,events=self.first_fixture()
        def compared(*args):events.append('comparison');return {'diagnostic_only':True}
        with patch.object(probe,'compare_guard',side_effect=compared) as comparison:
            with probe.AtFirstGuard(self.loaded,Stage,measurements) as diagnostic:
                self.assertEqual(Stage().check(),'original value');self.assertEqual(Stage().check(),'original value')
            self.assertEqual(comparison.call_count,1)
        self.assertEqual(events,['comparison','measurements','original','original',('exit',None)])
        self.assertTrue(diagnostic.attempted);self.assertIs(Stage.check,original)
    def test_source_custody_failure_poisons_and_closes_without_starting_measurements(self):
        Stage,original,measurements,events=self.first_fixture();stage=Stage();failure=KeyboardInterrupt('custody')
        with patch.object(probe,'compare_guard',side_effect=failure),self.assertRaises(KeyboardInterrupt) as caught:
            with probe.AtFirstGuard(self.loaded,Stage,measurements):stage.check()
        self.assertIs(caught.exception,failure);self.assertFalse(stage.usable);self.assertFalse(stage.allocation.usable)
        stage.close.assert_called_once();stage.allocation.close.assert_called_once();self.assertEqual(events,[])
        self.assertIs(Stage.check,original)
    def test_measurement_exit_error_preserves_pending_original_error_and_restores(self):
        Stage,original,measurements,events=self.first_fixture();failure=KeyboardInterrupt('effect boundary')
        with patch.object(probe,'compare_guard',return_value={}),patch.object(type(measurements),'__exit__',side_effect=OSError('exit')):
            with self.assertRaises(KeyboardInterrupt) as caught:
                with probe.AtFirstGuard(self.loaded,Stage,measurements):Stage().check();raise failure
        self.assertIs(caught.exception,failure);self.assertIs(Stage.check,original)


class SDKContractTest(unittest.TestCase):
    def test_preexisting_slot_descriptor_hook_refuses_without_invocation(self):
        class Changed:
            def __get__(self,*args):raise AssertionError('foreign descriptor executed')
            def __set__(self,*args):raise AssertionError('foreign descriptor executed')
        native=FakeNative()
        with patch.object(pathlib.PurePath,'_raw_paths',Changed()),patch.object(native,'path_plan') as plan,self.assertRaises(ValueError):
            probe.Adapter(native,owner_check=lambda:None)
        plan.assert_not_called()
    def test_loaded_code_custody_refuses_before_any_source_reread(self):
        fn=probe.Adapter.values;before=fn.__code__
        loaded=probe.Loaded.__new__(probe.Loaded);loaded.own_functions=(fn,);loaded.own_codes={id(fn):before}
        loaded.base=types.SimpleNamespace(validate=Mock())
        def changed(self):raise AssertionError('changed helper invoked')
        try:
            fn.__code__=changed.__code__
            with patch.object(probe,'_read_owned') as read,self.assertRaises(ValueError):loaded.validate()
            read.assert_not_called();loaded.base.validate.assert_not_called()
        finally:fn.__code__=before
    def test_preexisting_sdk_environment_changes_refuse_before_plan_creation(self):
        for owner,name,value in ((posixpath,'sep','!'),(posixpath,'altsep','!'),(os,'fspath',lambda x:x),(sys,'intern',lambda x:x)):
            native=FakeNative()
            with patch.object(owner,name,value),patch.object(native,'path_plan') as plan,self.assertRaises(ValueError):
                probe.Adapter(native,owner_check=lambda:None)
            plan.assert_not_called()
    def test_actual_sdk_bodies_and_code_objects_match_closed_contract(self):
        raw=Path(pathlib.__file__).read_bytes();codes=probe.sdk_code(raw,pathlib.__file__)
        for name in probe.SDK_AST:
            cls,method=name.split('.')
            self.assertEqual(codes[name],probe.raw_function(vars(getattr(pathlib,cls))[method]).__code__)
    def test_sdk_source_is_compiled_without_execution_and_docs_are_not_behavior(self):
        raw=Path(pathlib.__file__).read_bytes()+b'\nraise KeyboardInterrupt("private SDK source executed")\n'
        self.assertEqual(set(probe.sdk_code(raw,'fixed-sdk.py'))&set(probe.SDK_AST),set(probe.SDK_AST))
        tree=ast.parse(raw)
        for owner in tree.body:
            if not isinstance(owner,ast.ClassDef):continue
            for method in owner.body:
                if (isinstance(method,ast.FunctionDef) and method.body and isinstance(method.body[0],ast.Expr)
                        and isinstance(method.body[0].value,ast.Constant) and type(method.body[0].value.value) is str):
                    method.body[0].value.value='Different SDK documentation'
        self.assertTrue(probe.sdk_code(ast.unparse(tree).encode(),'fixed-sdk.py'))
    def test_changed_body_signature_decorator_and_bounds_are_refused(self):
        raw=Path(pathlib.__file__).read_bytes()
        for value in (b'',b' '*262145,raw.replace(b'return type(self)(*pathsegments)',b'return 42'),
                raw.replace(b'def with_segments(self, *pathsegments):',b'def with_segments(self, segment):')):
            with self.subTest(size=len(value)),self.assertRaises(ValueError):probe.sdk_code(value,'fixed-sdk.py')
    def test_older_exact_constructor_contract_is_supported_without_broadening_other_bodies(self):
        tree=ast.parse(Path(pathlib.__file__).read_bytes())
        owner=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='PurePath')
        older=next(n for n in owner.body if isinstance(n,ast.FunctionDef) and n.name=='__init__')
        loop=next(n for n in older.body if isinstance(n,ast.For))
        branch=loop.body[0].body[0]
        branch.test=ast.parse('arg._flavour is ntpath and self._flavour is posixpath',mode='eval').body
        branch.body=ast.parse(r"paths.extend(path.replace('\\', '/') for path in arg._raw_paths)").body
        self.assertTrue(probe.sdk_code(ast.unparse(tree).encode(),'fixed-sdk.py'))
        older.body[-1]=ast.parse('self._raw_paths = []').body[0]
        with self.assertRaises(ValueError):probe.sdk_code(ast.unparse(tree).encode(),'fixed-sdk.py')
    def test_posix_frozen_code_is_authenticated_from_actual_sdk_source(self):
        with open(posixpath.__file__,'rb') as source:raw=source.read(262145)
        codes=probe.posix_code(raw)
        self.assertEqual(set(codes),{'posixpath.'+name for name in probe.POSIX_AST})
        for name in probe.POSIX_AST:self.assertEqual(codes['posixpath.'+name],getattr(posixpath,name).__code__)
        tree=ast.parse(raw)
        join=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='join')
        join.body=[ast.Return(value=ast.Constant(value='private'))]
        with self.assertRaises(ValueError):probe.posix_code(ast.unparse(tree).encode())


class AdapterContractTest(unittest.TestCase):
    def setUp(self):
        self.native=FakeNative();self.adapter=probe.Adapter(self.native,owner_check=lambda:None)
        self.addCleanup(self.adapter.close)
    def observe(self):
        result=[]
        for raw in ('','.', '/', '//server/share','/a//b/../c','/caf\u00e9/\u732b','a\0b'):
            p=Path(raw);q=p/'child'
            result.append((type(q),str(q),q.parts,q.anchor,str(q.parent),tuple(map(str,q.parents)),hash(q)))
        return result
    def test_original_classes_values_and_all_four_descriptors_restore(self):
        expected=self.observe();classes=(pathlib.Path,pathlib.PurePath,type(Path('/')))
        with self.adapter.installed():
            self.assertEqual(self.observe(),expected)
            self.assertEqual((pathlib.Path,pathlib.PurePath,type(Path('/'))),classes)
        self.assertTrue(self.adapter.restored());self.assertFalse(any(self.adapter.fallbacks.values()))
        self.assertTrue(all(v>0 for v in self.adapter.calls.values()))
        self.assertEqual({k:self.adapter.values()[k] for k in probe.ROLES},self.adapter.calls)
    def test_native_api_replacement_falls_back_without_calling_replaced_entry(self):
        with self.adapter.installed(),patch.object(self.native,'path_call',Mock(side_effect=AssertionError('replaced entry ran'))):
            self.assertEqual(str(Path('/synthetic')/'child'),str(Path('/synthetic/child')))
            self.native.path_call.assert_not_called()
        self.assertGreater(sum(self.adapter.fallbacks.values()),0)
    def test_native_failure_is_not_retried_and_keeps_original_exception(self):
        failure=KeyboardInterrupt('native original');calls=[];original=self.adapter.call
        def interrupted(*args):calls.append(args[0]);raise failure
        self.adapter.call=interrupted
        try:
            with self.adapter.installed(),self.assertRaises(KeyboardInterrupt) as caught:Path('/synthetic')
        finally:self.adapter.call=original
        self.assertIs(caught.exception,failure);self.assertEqual(calls,[0]);self.assertTrue(self.adapter.restored())
    def test_tables_pin_live_code_identity_after_authenticating_sdk_semantics(self):
        for table in self.adapter.tables:
            for owner,name,expected in table:
                if type(owner) is types.FunctionType:self.assertIs(expected,owner.__code__)
        with self.adapter.installed():self.assertTrue(all(self.native.admitted(t) for t in self.adapter.tables))
    def test_same_sdk_code_in_foreign_globals_refuses_before_constructor_or_plan(self):
        original=self.adapter.originals[0]
        changed=types.FunctionType(original.__code__,dict(original.__globals__),original.__name__,
            original.__defaults__,original.__closure__)
        with patch.object(pathlib.Path,'__init__',changed),patch.object(self.native,'path_plan',wraps=self.native.path_plan) as planned:
            with self.assertRaises(ValueError):probe.Adapter(self.native,owner_check=lambda:None)
            planned.assert_not_called()
    def test_in_place_parser_code_and_constructor_class_cell_changes_are_live(self):
        parser=vars(pathlib.PurePath)['_parse_path'].__func__;original=parser.__code__
        def altered(cls,path):raise KeyboardInterrupt('parser original')
        try:
            with self.adapter.installed():
                parser.__code__=altered.__code__
                self.assertFalse(self.native.admitted(self.adapter.tables[1]))
                with self.assertRaises(KeyboardInterrupt) as caught:str(Path('/synthetic'))
                self.assertEqual(caught.exception.args,('parser original',))
                parser.__code__=original
        finally:parser.__code__=original
        cell=self.adapter.sdk_functions['Path.__init__'].__closure__[0];saved=cell.cell_contents
        try:
            with self.adapter.installed():
                self.assertTrue(self.native.admitted(self.adapter.tables[0]))
                cell.cell_contents=object
                self.assertFalse(self.native.admitted(self.adapter.tables[0]));cell.cell_contents=saved
        finally:cell.cell_contents=saved
    def test_pathlike_callback_subclass_and_error_arguments_keep_original_behavior(self):
        failure=KeyboardInterrupt('pathlike original')
        class Value:
            def __fspath__(self):raise failure
        def error():
            try:Path(b'bytes')
            except TypeError as e:return e.args
        expected=error()
        with self.adapter.installed():
            self.assertEqual(error(),expected)
            with self.assertRaises(KeyboardInterrupt) as caught:Path(Value())
            self.assertIs(caught.exception,failure)
        self.assertTrue(self.adapter.restored());self.assertGreater(self.adapter.fallbacks['constructor'],0)
    def test_live_metadata_hook_is_always_original(self):
        failure=KeyboardInterrupt('original metadata hook')
        with self.adapter.installed(),patch.object(pathlib.Path,'stat',Mock(side_effect=failure)):
            p=Path('/synthetic')
            with self.assertRaises(KeyboardInterrupt) as caught:p.stat()
            self.assertIs(caught.exception,failure);pathlib.Path.stat.assert_called_once()
    def test_new_concrete_class_shadow_of_inherited_dependency_is_detected(self):
        with self.adapter.installed():
            self.assertTrue(self.native.admitted(self.adapter.tables[0]))
            with patch.object(self.adapter.concrete,'_flavour',object(),create=True):
                self.assertFalse(self.native.admitted(self.adapter.tables[0]))
            self.assertTrue(self.native.admitted(self.adapter.tables[0]))
    def test_preexisting_concrete_helper_shadow_refuses_without_invoking_it(self):
        changed=Mock(side_effect=AssertionError('foreign helper executed'))
        with patch.object(self.adapter.concrete,'_format_parsed_parts',changed,create=True):
            with self.assertRaises(ValueError):probe.Adapter(self.native,owner_check=lambda:None)
            changed.assert_not_called()
    def test_new_objects_and_mutable_raw_lists_are_not_shared(self):
        with self.adapter.installed():
            a=Path('/synthetic');b=Path('/synthetic');self.assertIsNot(a,b);self.assertIsNot(a._raw_paths,b._raw_paths)
            a._raw_paths.append('changed');self.assertEqual(str(b),str(Path('/synthetic')))
            a._load_parts();b._load_parts();self.assertIsNot(a._tail_cached,b._tail_cached)
    def test_lazy_slots_and_explicit_reload_match_original_sdk(self):
        with self.adapter.installed():
            p=Path('/synthetic');self.assertFalse(hasattr(p,'_drv'));self.assertFalse(hasattr(p,'_str'))
            self.assertEqual(str(p),str(Path('/synthetic')));p._raw_paths[:]=['/changed'];p._load_parts()
            self.assertEqual(p.parts,Path('/changed').parts)
            # Original _load_parts leaves the independent _str cache alone.
            self.assertEqual(str(p),str(Path('/synthetic')))
    def test_partial_install_restores_all_touched_descriptors_and_pending_error(self):
        original_setattr=setattr;failure=KeyboardInterrupt('install');seen=[]
        def assign(owner,name,value):
            seen.append((owner,name,value))
            if owner is pathlib.PurePath and name=='__str__' and value is self.adapter.replacements[2]:raise failure
            original_setattr(owner,name,value)
        with patch.object(probe,'setattr',assign,create=True),self.assertRaises(KeyboardInterrupt) as caught:
            with self.adapter.installed():self.fail('partial installation entered')
        self.assertIs(caught.exception,failure);self.assertTrue(self.adapter.restored())
        self.assertTrue(all(any(o is owner and n==name and value is old for o,n,value in seen)
            for owner,name,old,_new in self.adapter.entries[:3]))
    def test_counter_schema_is_closed_and_bounded_and_cache_is_cleared(self):
        for change in ({'private_path':'/private'},{'cache_entries':257},{'constructor':True},{'string':-1}):
            original=self.native.path_call
            def value(op,*args):return {**original(op,*args),**change}
            old=self.adapter.call;self.adapter.call=value
            try:
                with self.assertRaises(ValueError):self.adapter.values()
            finally:self.adapter.call=old
        self.adapter.plan.counts['cache_entries']=12;self.adapter.clear()
        self.assertEqual(self.adapter.values()['cache_entries'],0)
    def test_clear_failure_keeps_pending_error_and_close_is_not_repeated(self):
        original=self.adapter.call;failure=KeyboardInterrupt('original');clears=[]
        def failed(op,*args):
            if op==5:clears.append(op);raise OSError('clear failed')
            return original(op,*args)
        self.adapter.call=failed
        with self.assertRaises(KeyboardInterrupt) as caught:
            try:raise failure
            finally:self.adapter.close()
        self.assertIs(caught.exception,failure);self.assertTrue(self.adapter.closed);self.assertTrue(self.adapter.broken)
        self.adapter.close();self.assertEqual(clears,[5])


@unittest.skipUnless(sys.platform=='linux' and sys.version_info[:2]==(3,12)
    and getattr(os,'geteuid',lambda:-1)()==0,'Actual hosted Linux CPython3.12 Root required')
class HostedPathTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location('_path_original_read_cases',Path(__file__).with_name('native-read-test.py'))
        original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
        original.HostedReadTest.setUpClass.__func__(cls)
        source=Path(__file__).with_name('native_path_probe.py');target=cls.root/source.name
        shutil.copyfile(source,target);target.chmod(0o644)
        cls.loaded=probe.Loaded(cls.root,base=cls.loaded)
    def adapter(self):
        value=probe.Adapter(self.loaded.native,sdk_codes=self.loaded.codes)
        self.addCleanup(value.close);return value
    @staticmethod
    def observe():
        rows=[]
        for args in ((),('',),('.',),('/',),('//',),('///',),('/a','b'),('/a','/b',''),
                ('a','','c'),('a\\b',),('/caf\u00e9/\u732b',),('a\0b',),('x/..','./y'),('//srv//share','leaf')):
            p=Path(*args);absolute=p.is_absolute();q=p/'child'
            rows.append((type(p),str(p),p.parts,p.drive,p.root,p.anchor,p.name,p.suffix,p.suffixes,p.stem,
                absolute,str(q),str(p.parent),tuple(map(str,p.parents)),hash(p)))
        return rows
    def test_actual_native_values_all_roles_and_fresh_slot_lists_match_sdk(self):
        expected=self.observe();a=self.adapter();classes=(pathlib.Path,pathlib.PurePath,pathlib.PosixPath)
        with a.installed():
            self.assertEqual(self.observe(),expected);self.assertEqual(self.observe(),expected)
            p=Path('/same');q=Path('/same');self.assertIsNot(p,q);self.assertIsNot(p._raw_paths,q._raw_paths)
            p._load_parts();q._load_parts();self.assertIsNot(p._tail_cached,q._tail_cached)
            p._tail_cached.append('changed');self.assertEqual(q.parts,('/', 'same'))
        self.assertEqual((pathlib.Path,pathlib.PurePath,pathlib.PosixPath),classes)
        self.assertTrue(a.restored());self.assertTrue(all(v>0 for v in a.calls.values()))
        self.assertFalse(any(a.fallbacks.values()));self.loaded.validate()
        self.assertEqual({k:a.values()[k] for k in probe.ROLES},a.calls)
    def test_actual_cache_bounds_clear_and_no_path_instance_reuse(self):
        a=self.adapter()
        with a.installed():
            for i in range(300):self.assertEqual(str(Path('/synthetic/'+str(i))),'/synthetic/'+str(i))
            self.assertEqual(str(Path('/synthetic/299')),'/synthetic/299')
        stats=a.values();self.assertGreater(stats['cache_misses'],256);self.assertGreater(stats['cache_hits'],0)
        self.assertLessEqual(stats['cache_entries'],256);a.clear();self.assertEqual(a.values()['cache_entries'],0)
    def test_actual_lazy_slots_changed_raw_inputs_and_original_str_cache(self):
        a=self.adapter()
        with a.installed():
            p=Path('/before');self.assertFalse(hasattr(p,'_drv'));self.assertFalse(hasattr(p,'_str'))
            self.assertEqual(str(p),'/before');p._raw_paths[:]=['/after'];p._load_parts()
            self.assertEqual(p.parts,('/', 'after'));self.assertEqual(str(p),'/before')
            q=Path('/other');q._drv='';q._root='//'
            # Partially supplied lazy state is unsupported before mutation;
            # the original property evaluation order remains authoritative.
            self.assertEqual(str(q),'//other')
        self.assertGreater(a.fallbacks['string'],0);self.assertTrue(a.restored())
    def test_actual_pathlike_subclass_mixed_flavour_and_long_inputs_keep_original(self):
        failure=KeyboardInterrupt('original pathlike');calls=[]
        class Value:
            def __fspath__(self):calls.append(1);raise failure
        class Child(pathlib.PosixPath):pass
        inputs=[(pathlib.PureWindowsPath('C:/base'),),(b'bytes',),(None,),(7,),('x'*8193,),tuple('x' for _ in range(65))]
        def outcomes():
            out=[]
            for args in inputs:
                try:out.append(('value',str(Path(*args))))
                except BaseException as e:out.append((type(e),e.args))
            return out
        expected=outcomes();a=self.adapter()
        with a.installed():
            self.assertEqual(outcomes(),expected);self.assertIs(type(Child('/child')/'leaf'),Child)
            with self.assertRaises(KeyboardInterrupt) as caught:Path(Value())
            self.assertIs(caught.exception,failure)
        self.assertEqual(calls,[1]);self.assertTrue(a.restored());self.loaded.validate()
    def test_actual_metadata_calls_are_original_and_observe_changes(self):
        leaf=self.root/'sdk-metadata-leaf';leaf.write_bytes(b'one');self.addCleanup(leaf.unlink)
        a=self.adapter()
        with a.installed():
            p=Path(leaf);self.assertEqual(p.stat().st_size,3);leaf.write_bytes(b'changed')
            self.assertEqual(p.stat().st_size,7)
            failure=KeyboardInterrupt('original metadata')
            with patch.object(os,'stat',Mock(side_effect=failure)),self.assertRaises(KeyboardInterrupt) as caught:p.stat()
            self.assertIs(caught.exception,failure)
        self.assertTrue(a.restored())
    def test_actual_changed_namespace_code_and_class_cells_fall_back_before_mutation(self):
        a=self.adapter();fn=vars(pathlib.PurePath)['_parse_path'].__func__;code=fn.__code__
        def altered(cls,path):raise KeyboardInterrupt('original parse hook')
        try:
            with a.installed():
                fn.__code__=altered.__code__
                with self.assertRaises(KeyboardInterrupt) as caught:str(Path('/synthetic'))
                self.assertEqual(caught.exception.args,('original parse hook',))
                fn.__code__=code
                with patch.object(pathlib.PosixPath,'_flavour',object(),create=True):
                    self.assertIs(self.loaded.native.path_call(0,a.plan,object.__new__(pathlib.PosixPath),('/synthetic',)),NotImplemented)
        finally:fn.__code__=code
        self.assertTrue(a.restored());self.loaded.validate()
    def test_actual_foreign_thread_uses_original_sdk_without_shared_cache(self):
        a=self.adapter();values=[];errors=[]
        def worker():
            try:values.append(str(Path('/synthetic')/'thread'))
            except BaseException as e:errors.append(e)
        with a.installed():
            thread=threading.Thread(target=worker);thread.start();thread.join(5)
            self.assertFalse(thread.is_alive());self.assertFalse(errors);self.assertEqual(values,['/synthetic/thread'])
        self.assertEqual(a.values()['cache_entries'],0);self.assertGreater(a.fallbacks['constructor'],0)
    def test_actual_interruption_restores_sdk_and_preserves_error(self):
        failure=KeyboardInterrupt('original interruption');a=self.adapter()
        with self.assertRaises(KeyboardInterrupt) as caught:
            with a.installed():
                self.assertEqual(str(Path('/synthetic')),'/synthetic');raise failure
        self.assertIs(caught.exception,failure);self.assertTrue(a.restored());a.clear();self.loaded.validate()
    def test_actual_native_preflight_rejects_malformed_context_without_observation(self):
        n=self.loaded.native;a=self.adapter();before=(n.counts(),n.read_counts(),a.values())
        for args in (((),pathlib.PosixPath,os.getpid(),threading.get_ident(),256),
                (((),)*4,pathlib.PosixPath,os.getpid(),threading.get_ident(),257)):
            with self.assertRaises(TypeError):n.path_plan(*args)
        for args in ((True,a.plan,None,()),(6,a.plan,None,()),(4,a.plan,object(),())):
            with self.assertRaises(TypeError):n.path_call(*args)
        self.assertEqual((n.counts(),n.read_counts(),a.values()),before)
    def test_zz_all_original_372_root_cases_with_pure_lexical_sdk_adapter(self):
        import io
        spec=importlib.util.spec_from_file_location('_path_original_lexical_cases',Path(__file__).with_name('lexical-path-test.py'))
        original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
        suite=unittest.TestSuite()
        for name,count in original.ROOT_SCOPES:
            scope=unittest.defaultTestLoader.loadTestsFromName(name)
            self.assertEqual(scope.countTestCases(),count);suite.addTest(scope)
        a=self.adapter();stream=io.StringIO()
        class RootProgress(unittest.TextTestResult):
            def startTest(self,test):
                print('native_path_root_case='+type(test).__name__+'.'+test._testMethodName,flush=True)
                super().startTest(test)
        with a.installed():result=unittest.TextTestRunner(stream=stream,resultclass=RootProgress).run(suite)
        self.assertEqual(result.testsRun,372);self.assertFalse(result.skipped)
        self.assertTrue(result.wasSuccessful(),stream.getvalue());self.assertTrue(a.restored());self.loaded.validate()
        print('native_path_original_root_cases=372',flush=True)


if __name__=='__main__':unittest.main(verbosity=2)
