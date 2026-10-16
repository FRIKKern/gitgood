#!/usr/bin/env python3
"""Fresh metadata semantics, hook fallback, restoration and actual Root gates."""
import ast
import builtins
import cProfile
import hashlib
import importlib.util
import io
import os
import pathlib
import pstats
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock,patch

sys.dont_write_bytecode=True
import native_metadata_probe as probe


class FakeNative:
    def __init__(self):self.values={'fingerprint':0,'persistent':0,'custody':0}
    def counts(self):return dict(self.values)
    def same_bindings(self,bindings,*_):
        for namespace,key,value in bindings:
            current=(namespace.__code__ if type(namespace) is types.FunctionType and key=='__code__'
                else getattr(namespace,key) if isinstance(namespace,type) else namespace.get(key))
            if type(current) is types.MethodType and type(value) is types.MethodType:
                if current.__func__ is not value.__func__ or current.__self__ is not value.__self__:return False
            elif current is not value:return False
        return True
    def fingerprint(self,*_):
        self.values['fingerprint']+=1
        return (1,2,3,4,5,0,0o100600,1),(('parent',1,2,0,0o40700),)
    def persistent(self,*_):
        self.values['persistent']+=1;return {'fresh':True}
    def custody(self,*_):
        self.values['custody']+=1;return True


def models():
    modules=[]
    for name in probe.MODULE_NAMES:
        module=types.ModuleType(name);module.Path=Path;module.os=os
        import stat;module.stat=stat
        exec('def require(value):\n if not value: raise ValueError("original refusal")\n',vars(module))
        modules.append(module)
    service,binding,generation,lifecycle=modules
    exec('def _root_file_path(path): return Path(path)\n'
        'def _root_file_parent_plan(path): return tuple((p,str(p)) for p in path.parents)\n'
        '_root_file_parents=_root_file_parent_plan\n'
        'class _CapturedRootFiles:\n @staticmethod\n def _fingerprint(path,maximum,executable): return str(Path(path)),maximum,executable\n',vars(service))
    exec('class _CapturedExecutableDigests:\n @staticmethod\n def _fingerprint(path): return str(Path(path))\n',vars(binding))
    exec('class _PersistentFingerprintPlan:\n def read(self): return {"original":True}\n',vars(generation))
    def within(method):
        def wrapped(subject):return method(subject)
        wrapped.__wrapped__=method;return wrapped
    lifecycle._within_root_observation_pass=within
    lifecycle.root_owner=lambda:(os.getpid(),threading.get_ident())
    lifecycle.private_directory=lambda *_:('same',)
    lifecycle.directory_identity=lambda *_:(1,2,3,4,5,6,7)
    exec('class _RootReadOnlyCustody:\n'
        ' def _file(self,value): return value\n'
        ' @staticmethod\n def _names(fd): return []\n'
        ' @staticmethod\n def _directory_metadata(value): return value\n'
        ' @_within_root_observation_pass\n'
        ' def check(self): return "original"\n',vars(lifecycle))
    return modules


class AdapterTest(unittest.TestCase):
    def setUp(self):
        # Portable stand-ins only. Actual owner/OS evidence is a hosted gate.
        for name in ('getuid','geteuid','getgid','getegid'):
            if not hasattr(os,name):self.enterContext(patch.object(os,name,lambda:0,create=True))
        self.modules=models();self.native=FakeNative()
        self.adapter=probe.Adapter(self.modules,self.native,owner_check=lambda:None)
    def test_four_original_classes_retained_and_native_fingerprint_types_match(self):
        owners=self.adapter.owners
        with self.adapter.installed():
            result=self.modules[0]._CapturedRootFiles._fingerprint('/synthetic',4096,False)
            self.assertIs(type(result),tuple);self.assertEqual(len(result[0]),8)
            result=self.modules[1]._CapturedExecutableDigests._fingerprint(str(Path.cwd()))
            self.assertEqual(result[0],str(Path.cwd()));self.assertEqual(len(result[1]),8)
            self.assertEqual(self.adapter.owners,owners)
        self.assertTrue(self.adapter.restored());self.assertEqual(self.native.counts()['fingerprint'],2)
    def test_pathlike_and_replaced_metadata_hooks_fall_back_before_native_observation(self):
        class PathLike:
            calls=0
            def __fspath__(subject):subject.calls+=1;return '/synthetic'
        value=PathLike()
        with self.adapter.installed():
            result=self.modules[0]._CapturedRootFiles._fingerprint(value,5,False)
            self.assertEqual(value.calls,1);self.assertEqual(result[1:],(5,False))
            with patch.object(Path,'stat',Mock()):
                self.assertEqual(self.modules[0]._CapturedRootFiles._fingerprint('/synthetic',6,False)[1:],(6,False))
        self.assertEqual(self.native.counts()['fingerprint'],0);self.assertEqual(self.adapter.fallbacks['root_files'],2)
    def test_native_refusal_and_original_oserror_never_retry_python(self):
        failure=OSError(5,'original')
        with self.adapter.installed(),patch.object(self.native,'fingerprint',return_value=None):
            with self.assertRaises(ValueError):self.modules[0]._CapturedRootFiles._fingerprint('/synthetic',8,False)
        with self.adapter.installed(),patch.object(self.native,'fingerprint',side_effect=failure):
            with self.assertRaises(OSError) as caught:self.modules[0]._CapturedRootFiles._fingerprint('/synthetic',8,False)
        self.assertIs(caught.exception,failure);self.assertEqual(self.adapter.fallbacks['root_files'],0)
    def test_persistent_unsupported_schema_falls_back_before_native_and_returns_original_value(self):
        cls=self.modules[2]._PersistentFingerprintPlan;subject=cls()
        with self.adapter.installed():self.assertEqual(subject.read(),{'original':True})
        self.assertEqual(self.native.counts()['persistent'],0);self.assertEqual(self.adapter.fallbacks['persistent'],1)
    def test_sdk_global_and_concrete_path_hook_changes_fall_back_before_native(self):
        with self.adapter.installed():
            with patch.object(pathlib,'os',Mock(wraps=os)):
                self.assertFalse(self.adapter.eligible())
                self.assertEqual(self.modules[0]._CapturedRootFiles._fingerprint('/synthetic',7,False)[1:],(7,False))
            with patch.object(self.adapter.path_type,'stat',Mock()):
                self.assertFalse(self.adapter.eligible())
                self.assertEqual(self.modules[0]._CapturedRootFiles._fingerprint('/synthetic',8,False)[1:],(8,False))
        self.assertEqual(self.native.counts()['fingerprint'],0);self.assertEqual(self.adapter.fallbacks['root_files'],2)
    def test_in_place_metadata_code_change_falls_back_before_native(self):
        fn=Path.stat;original=fn.__code__
        def altered(self,*,follow_symlinks=True):raise KeyboardInterrupt('metadata hook')
        try:
            with self.adapter.installed():
                fn.__code__=altered.__code__
                self.assertFalse(self.adapter.eligible())
                self.assertEqual(self.modules[0]._CapturedRootFiles._fingerprint('/synthetic',6,False)[1:],(6,False))
        finally:fn.__code__=original
        self.assertEqual(self.native.counts()['fingerprint'],0);self.assertEqual(self.adapter.fallbacks['root_files'],1)
    def test_present_retained_none_is_unsupported_before_any_observation(self):
        cls=self.modules[3]._RootReadOnlyCustody;subject=cls();root=Path('/synthetic');directory=root/'history';leaf=directory/'record'
        subject.uid=65503;subject.gid=1000;subject.root=root;subject.directory=directory;subject.lock_path=directory/'lock'
        subject.directories={directory:(3,(1,2,65503,1000,0o40700,4,5))}
        subject.known={leaf:(1,3,65503,1000,0o100600,1,6,7,8)}
        subject.retained={leaf:None};subject.entries=None;subject.directory_metadata={};subject.lock=None
        subject.usable=True;subject.owner=self.adapter.owner
        with self.assertRaises(probe.Unsupported):self.adapter.custody_arguments(subject)
        callback=Mock(side_effect=AssertionError('early observation'));self.modules[3].private_directory=callback
        adapter=probe.Adapter(self.modules,self.native,owner_check=lambda:None)
        with adapter.installed():self.assertEqual(subject.check(),'original')
        callback.assert_not_called()
        self.assertEqual(self.native.counts()['custody'],0);self.assertEqual(adapter.fallbacks['custody'],1)
    def test_live_binding_change_after_native_call_refuses_without_retry(self):
        original=self.modules[0].require
        def change(*_):
            self.modules[0].require=lambda value:None
            return ((1,2,3,4,5,0,0o100600,1),())
        try:
            with self.adapter.installed(),patch.object(self.native,'fingerprint',side_effect=change),self.assertRaises(ValueError):
                self.modules[0]._CapturedRootFiles._fingerprint('/synthetic',8,False)
        finally:self.modules[0].require=original
        self.assertEqual(self.adapter.fallbacks['root_files'],0);self.assertTrue(self.adapter.restored())
    def test_partial_install_interruption_and_all_restorations_preserve_original_error(self):
        failure=KeyboardInterrupt('original')
        with self.assertRaises(KeyboardInterrupt) as caught:
            with self.adapter.installed():raise failure
        self.assertIs(caught.exception,failure);self.assertTrue(self.adapter.restored())
        def assign(owner,name,value):
            if owner is self.adapter.owners[2] and value is not vars(owner)[name]:raise failure
            builtins.setattr(owner,name,value)
        with patch.object(probe,'setattr',assign,create=True),self.assertRaises(KeyboardInterrupt) as caught:
            with self.adapter.installed():pass
        self.assertIs(caught.exception,failure);self.assertTrue(self.adapter.restored())
    def test_failed_cleanup_attempts_all_restorations_and_poisons_adapter(self):
        failure=KeyboardInterrupt('original');restored=[]
        originals={(id(owner),name):old for owner,name,old,_ in self.adapter.entries}
        def assign(owner,name,value):
            if value is originals[id(owner),name]:
                restored.append((id(owner),name))
                if owner is self.adapter.owners[0]:raise RuntimeError('cleanup')
            builtins.setattr(owner,name,value)
        try:
            with patch.object(probe,'setattr',assign,create=True),self.assertRaises(KeyboardInterrupt) as caught:
                with self.adapter.installed():raise failure
            self.assertIs(caught.exception,failure);self.assertEqual(len(restored),4);self.assertTrue(self.adapter.broken)
        finally:
            for owner,name,old,_ in self.adapter.entries:builtins.setattr(owner,name,old)
    def test_nested_install_and_foreign_owner_refuse(self):
        with self.adapter.installed():
            with self.assertRaises(ValueError):
                with self.adapter.installed():pass
        with patch.object(probe.threading,'get_ident',return_value=-1),self.assertRaises(ValueError):self.adapter.check()
        self.assertTrue(self.adapter.restored())
    def test_first_guard_restores_before_measurements_and_preserves_poisoning(self):
        events=[];test=self
        class Stage:
            usable=True;state='ready'
            def check(self):events.append('guard');return None
        original=Stage.check
        class Measurements:
            def __enter__(self):test.assertIs(Stage.check,original);events.append('measurements')
            def __exit__(self,*_):events.append('exit')
        result={'private':True}
        with patch.object(probe,'compare_guard',return_value=result):
            with probe.AtFirstGuard(None,Stage,Measurements()) as trial:Stage().check()
        self.assertIs(trial.result,result);self.assertEqual(events,['measurements','guard','exit'])
        stage=Stage();stage.close=Mock(side_effect=RuntimeError('cleanup'));stage.allocation=types.SimpleNamespace(usable=True,close=Mock())
        failure=KeyboardInterrupt('original')
        with patch.object(probe,'compare_guard',side_effect=failure),self.assertRaises(KeyboardInterrupt) as caught:
            with probe.AtFirstGuard(None,Stage,Measurements()):stage.check()
        self.assertIs(caught.exception,failure);self.assertIs(Stage.check,original)
        self.assertFalse(stage.usable);self.assertFalse(stage.allocation.usable)
        stage.close.assert_called_once();stage.allocation.close.assert_called_once()

    def test_whole_guard_pairs_alternate_on_original_stage_and_restore_every_time(self):
        a=self.adapter;events=[];stage=types.SimpleNamespace(usable=True,state='ready')
        loaded=types.SimpleNamespace(modules=self.modules,native=self.native,original_codes=None,
            validate=Mock(),evidence=lambda:{'synthetic':True})
        def guard(subject):
            self.assertIs(subject,stage);events.append(a.active)
            if a.active:
                for family in probe.FAMILIES:a.count(family)
                for name in self.native.values:self.native.values[name]+=1
            else:self.assertTrue(a.restored())
            return {'same':'observation'}
        with patch.object(probe,'Adapter',return_value=a),patch.object(probe,'root_owner',lambda:None):
            result=probe.compare_guard(loaded,guard,stage)
        self.assertEqual(events,[selected for n in range(20) for selected in
            ((False,True) if n%2==0 else (True,False))])
        self.assertTrue(a.restored());self.assertEqual(len(result['pairs']),20)
        self.assertEqual(result['native_calls'],dict.fromkeys(self.native.values,20))
        self.assertEqual(result['families'],dict.fromkeys(probe.FAMILIES,20))
        self.assertEqual(result['fallbacks'],dict.fromkeys(probe.FAMILIES,0))
        loaded.validate.assert_called_once()
        failure=KeyboardInterrupt('original');events.clear()
        def interrupted(subject):
            guard(subject)
            if a.active:raise failure
        with patch.object(probe,'Adapter',return_value=a),patch.object(probe,'root_owner',lambda:None):
            with self.assertRaises(KeyboardInterrupt) as caught:probe.compare_guard(loaded,interrupted,stage)
        self.assertIs(caught.exception,failure);self.assertTrue(a.restored())


def original_sample():
    spec=importlib.util.spec_from_file_location('_metadata_original_proof',Path(__file__).with_name('native-owned-proof.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.RootGuardSample()


class ProfileTest(unittest.TestCase):
    setUp=AdapterTest.setUp
    def profile_fixture(self):
        return {name+'_synthetic':name for name in probe.NATIVE_APIS}
    def source(self):return Path(probe.__file__).read_bytes()
    def costs(self):
        return [{'file':'native-metadata-api.py','function':name,'line':0,'calls':1,'self_us':1,'cumulative_us':1}
            for name in probe.NATIVE_APIS]
    def loaded(self):
        return types.SimpleNamespace(modules=self.modules,native=self.native,original_codes=None,
            files={'native_metadata_probe.py':(self.source(),None)},validate=Mock(),evidence=lambda:{'synthetic':True})
    def test_actual_python_profile_uses_public_labels_without_source_paths(self):
        profile=cProfile.Profile();profile.runcall(self.adapter.eligible)
        rows=probe.profile_costs(pstats.Stats(profile).stats,self.source(),self.profile_fixture())
        row=next(r for r in rows if r['function']=='eligible')
        self.assertEqual(row['file'],'native-metadata-self.py');self.assertEqual(row['calls'],1)
        self.assertNotIn(str(Path.cwd()),str(rows))
    def test_profile_ignores_private_rows_without_inspecting_values(self):
        opaque=Mock();opaque.__str__=Mock(side_effect=AssertionError('private value read'))
        rows=probe.profile_costs({('/private/secret.py',12,'password'):opaque,
            ('~',0,'private_secret'):opaque},self.source(),self.profile_fixture())
        self.assertEqual(rows,[]);opaque.__str__.assert_not_called()
    def test_profile_rejects_invalid_numeric_fields_and_counter_bounds(self):
        key=('~',0,'same_bindings_synthetic')
        for calls,total,cumulative in [(True,0,0),(-1,0,0),(10000001,0,0),(1,True,1),
                (1,float('nan'),1),(1,float('inf'),1),(1,-1,1),(1,1,0),(1,0,1201)]:
            with self.subTest(calls=calls,total=total),self.assertRaises(ValueError):
                probe.profile_costs({key:(1,calls,total,cumulative,None)},self.source(),self.profile_fixture())
    def test_profile_reserves_native_rows_and_has_deterministic_sixteen_row_cap(self):
        code=probe.functions(compile(self.source(),probe.__file__,'exec'));stats={}
        for index,(name,_label) in enumerate(probe.PROFILE_PYTHON):
            fn=code[name];stats[fn.co_filename,fn.co_firstlineno,fn.co_name]=(1,index+1,.001,.002,None)
        for name in probe.NATIVE_APIS:stats['~',0,name+'_synthetic']=(1,2,0,0,None)
        rows=probe.profile_costs(stats,self.source(),self.profile_fixture())
        self.assertEqual(len(rows),16)
        self.assertEqual({r['function'] for r in rows if r['file']=='native-metadata-api.py'},set(probe.NATIVE_APIS))
        self.assertEqual(rows,probe.profile_costs(dict(reversed(list(stats.items()))),self.source(),self.profile_fixture()))
    def test_python_standins_cannot_authenticate_as_native_profiler_labels(self):
        with self.assertRaises(ValueError):probe.native_profile_codes(self.native)
        self.assertEqual(self.native.counts(),dict.fromkeys(('fingerprint','persistent','custody'),0))
    def test_label_discovery_refuses_and_preserves_an_existing_profiler(self):
        original=sys.getprofile()
        def foreign(*_):pass
        try:
            sys.setprofile(foreign)
            with self.assertRaises(ValueError):probe.native_profile_codes(self.native)
            self.assertIs(sys.getprofile(),foreign)
        finally:sys.setprofile(original)
        self.assertEqual(self.native.counts(),dict.fromkeys(('fingerprint','persistent','custody'),0))
    def test_first_guard_starts_original_measurements_and_only_tenth_enables_native(self):
        sample=original_sample();a=self.adapter;test=self;events=[];loaded=self.loaded()
        class Stage:
            usable=True;allocation=types.SimpleNamespace(usable=True,close=Mock());close=Mock()
            def check(subject):
                events.append(a.active)
                if a.active:
                    for family in probe.FAMILIES:a.count(family)
                    for name in test.native.values:test.native.values[name]+=1
                else:test.assertTrue(a.restored())
                return 'original'
        original=Stage.check
        class Measurements:
            def __init__(subject):subject.sample=sample
            def __enter__(subject):test.assertIs(Stage.check,original);Stage.check=sample.wrap(original)
            def __exit__(subject,*_):Stage.check=original
        with patch.object(probe,'Adapter',return_value=a),patch.object(probe,'native_profile_codes',return_value=self.profile_fixture()),patch.object(probe,'profile_costs',return_value=self.costs()):
            with probe.AtFirstGuardProfile(loaded,Stage,Measurements()) as diagnostic:
                for number in range(12):
                    self.assertEqual(Stage().check(),'original');self.assertTrue(a.restored())
                    self.assertEqual(sum(self.native.values.values()),0 if number<9 else 3)
            result=diagnostic.result
        self.assertEqual(events,[False]*9+[True]+[False]*2);self.assertEqual(sample.calls,12)
        self.assertIs(Stage.check,original);self.assertNotIn('wrap',vars(sample))
        self.assertEqual(result['guard_number'],10);self.assertEqual(result['extra_guard_calls'],0)
        self.assertEqual(result['native_calls'],dict.fromkeys(self.native.values,1));loaded.validate.assert_called_once()
    def test_sample_interruption_preserves_error_and_restores_every_descriptor(self):
        sample=original_sample();a=self.adapter;loaded=self.loaded();failure=KeyboardInterrupt('original')
        def guard():
            if a.active:raise failure
        with patch.object(probe,'Adapter',return_value=a),patch.object(probe,'native_profile_codes',return_value=self.profile_fixture()):
            with probe.GuardTenSample(loaded,sample) as diagnostic:
                wrapped=sample.wrap(guard)
                for _ in range(9):wrapped()
                with self.assertRaises(KeyboardInterrupt) as caught:wrapped()
        self.assertIs(caught.exception,failure);self.assertTrue(a.restored());self.assertIsNone(diagnostic.result)
        self.assertNotIn('wrap',vars(sample));self.assertIsNone(sys.getprofile());self.assertEqual(sample.calls,10)
    def test_first_guard_setup_failure_restores_wrapper_and_attempts_both_closes(self):
        sample=original_sample();failure=KeyboardInterrupt('original');loaded=self.loaded()
        class Stage:
            usable=True;allocation=types.SimpleNamespace(usable=True,close=Mock());close=Mock(side_effect=RuntimeError('cleanup'))
            def check(self):raise AssertionError('guard ran')
        original=Stage.check;stage=Stage()
        class Measurements:
            def __init__(self):self.sample=sample
            def __enter__(self):raise failure
        with patch.object(probe,'Adapter',return_value=self.adapter),patch.object(probe,'native_profile_codes',return_value=self.profile_fixture()):
            with self.assertRaises(KeyboardInterrupt) as caught:
                with probe.AtFirstGuardProfile(loaded,Stage,Measurements()):stage.check()
        self.assertIs(caught.exception,failure);self.assertIs(Stage.check,original);self.assertNotIn('wrap',vars(sample))
        self.assertFalse(stage.usable);self.assertFalse(stage.allocation.usable)
        stage.close.assert_called_once();stage.allocation.close.assert_called_once()


@unittest.skipUnless(sys.platform=='linux' and sys.version_info[:2]==(3,12)
    and getattr(os,'geteuid',lambda:-1)()==0,'Actual hosted Linux CPython3.12 Root required')
class HostedMetadataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ci=Path(__file__).resolve().parent;built=ci.parents[1]/'.gitgood/native-metadata-probe'
        cls.namespace=tempfile.TemporaryDirectory(prefix='gitgood-native-metadata-',dir='/var/lib')
        cls.addClassCleanup(cls.namespace.cleanup);cls.root=Path(cls.namespace.name);cls.root.chmod(0o700)
        for source in [*(ci/name for name in probe.HELPERS),built/'manifest.json',built/probe.extension_name()]:
            destination=cls.root/source.name;shutil.copyfile(source,destination);destination.chmod(0o644)
        cls.deployment=cls.root/'deployment';cls.deployment.mkdir()
        for source in (ci.parents[0]/'deployment').glob('*.py'):
            destination=cls.deployment/source.name;shutil.copyfile(source,destination);destination.chmod(0o644)
        sys.path.insert(0,str(cls.deployment));cls.addClassCleanup(sys.path.remove,str(cls.deployment))
        cls.loaded=probe.Loaded(cls.root)
    def adapter(self):return probe.Adapter(self.loaded.modules,self.loaded.native,original_codes=self.loaded.original_codes)
    def test_all_original_372_root_cases_with_metadata_adapter(self):
        spec=importlib.util.spec_from_file_location('_original_lexical_cases',Path(__file__).with_name('lexical-path-test.py'))
        original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
        suite=unittest.TestSuite()
        for name,count in original.ROOT_SCOPES:
            scope=unittest.defaultTestLoader.loadTestsFromName(name)
            self.assertEqual(scope.countTestCases(),count);suite.addTest(scope)
        a=self.adapter();stream=io.StringIO()
        with a.installed():result=unittest.TextTestRunner(stream=stream).run(suite)
        self.assertEqual(result.testsRun,372);self.assertFalse(result.skipped)
        self.assertTrue(result.wasSuccessful(),stream.getvalue());self.assertTrue(a.restored());self.loaded.validate()
        self.assertGreater(a.calls['root_files'],0);self.assertGreater(a.calls['executables'],0);self.assertGreater(a.calls['persistent'],0)
        print('native_metadata_original_root_cases=372',flush=True)
    def test_native_fingerprints_match_exact_values_and_stay_fresh(self):
        service,binding,*_=self.loaded.modules;a=self.adapter()
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            leaf=Path(directory)/'executable';leaf.write_bytes(b'one');leaf.chmod(0o700)
            expected=service._CapturedRootFiles._fingerprint(leaf,4096,True)
            executable=binding._CapturedExecutableDigests._fingerprint(str(leaf))
            with a.installed():
                self.assertEqual(service._CapturedRootFiles._fingerprint(leaf,4096,True),expected)
                self.assertEqual(binding._CapturedExecutableDigests._fingerprint(str(leaf)),executable)
                leaf.write_bytes(b'changed')
                self.assertNotEqual(service._CapturedRootFiles._fingerprint(leaf,4096,True),expected)
                leaf.chmod(0o722)
                with self.assertRaises(service.ServiceRefused):service._CapturedRootFiles._fingerprint(leaf,4096,True)
                target=leaf.with_name('target');target.write_bytes(b'target');target.chmod(0o700)
                leaf.unlink();leaf.symlink_to(target)
                with self.assertRaises(service.ServiceRefused):service._CapturedRootFiles._fingerprint(leaf,4096,True)
                # Executable resolution remains the original resolving walk.
                native_resolved=binding._CapturedExecutableDigests._fingerprint(str(leaf))
            self.assertEqual(binding._CapturedExecutableDigests._fingerprint(str(leaf)),native_resolved)
            with a.installed():
                leaf.unlink();leaf.write_bytes(b'replacement');leaf.chmod(0o700)
                self.assertNotEqual(service._CapturedRootFiles._fingerprint(leaf,4096,True),expected)
                with self.assertRaises(FileNotFoundError):service._CapturedRootFiles._fingerprint(leaf.with_name('missing'),4096,True)
            self.assertGreater(a.calls['root_files'],0);self.assertGreater(a.calls['executables'],0)
        self.loaded.validate()
    def test_native_persistent_result_matches_original_and_refuses_changed_entries(self):
        generation=self.loaded.modules[2];a=self.adapter()
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            root=Path(directory);machine=root/'machine';machine.write_bytes(b'machine');machine.chmod(0o600)
            leaf=root/'leaf';leaf.write_bytes(b'one');leaf.chmod(0o600)
            plan=generation._PersistentFingerprintPlan.__new__(generation._PersistentFingerprintPlan)
            info=root.lstat();file=leaf.lstat()
            plan.uid=0;plan.entries=((root,frozenset({'machine','leaf'})),)
            plan.directories=((root,str(root),info.st_dev,info.st_ino,0),);plan.machine=machine
            plan.files=((leaf,str(leaf),0,False,file.st_size,file.st_dev,file.st_ino),)
            plan.parents=tuple((p,str(p),False,False) for p in root.parents)
            expected=plan.read()
            with a.installed():
                self.assertEqual(plan.read(),expected)
                (root/'unexpected').write_bytes(b'x')
                with self.assertRaises(generation.PublicationRefused):plan.read()
            self.assertGreater(a.calls['persistent'],0);self.assertEqual(a.fallbacks['persistent'],0)
        self.loaded.validate()
    def custody(self):
        lifecycle=self.loaded.modules[3];root=Path(tempfile.mkdtemp(prefix='custody-',dir=self.root));root.chmod(0o700)
        self.addCleanup(shutil.rmtree,root)
        uid,gid=65503,1000;os.chown(root,uid,gid)
        history=root/'history';history.mkdir(mode=0o700);store=history/'records';store.mkdir(mode=0o700)
        for path in (history,store):os.chown(path,uid,gid)
        lock=history/'lock';lock.write_bytes(b'lock');lock.chmod(0o600)
        leaf=store/'record';leaf.write_bytes(b'record');leaf.chmod(0o600)
        other=store/'other';other.write_bytes(b'other');other.chmod(0o600)
        for path in (lock,leaf,other):os.chown(path,uid,gid)
        cls=lifecycle._RootReadOnlyCustody;value=cls.__new__(cls)
        value.usable=False;value.owner=(os.getpid(),threading.get_ident());value.uid=uid;value.gid=gid
        value.root=root;value.directory=history;value.store=store;value.lock_path=lock
        value.directories={};value.known={};value.retained={};value.entries=None;value.directory_metadata={};value.lock=None
        value.root_custody=lifecycle.private_directory(root,uid,gid)
        value._identity(history);value._identity(store);value.usable=True
        self.addCleanup(value.__exit__,None,None,None)
        value.lock=value._open(lock,os.O_RDONLY)
        for path in (lock,leaf,other):value.retained[path]=value._open(path,os.O_RDONLY)
        value.entries={path:sorted(os.listdir(fd)) for path,(fd,_original) in value.directories.items()}
        value.directory_metadata={path:value._directory_metadata(os.fstat(fd)) for path,(fd,_original) in value.directories.items()}
        value.check();return value,leaf,other
    def test_native_custody_observes_actual_held_and_named_descriptors(self):
        value,leaf,_=self.custody();a=self.adapter();before=leaf.read_bytes()
        with a.installed():
            value.check();value.check()
            self.assertGreater(a.calls['custody'],0);self.assertEqual(a.fallbacks['custody'],0)
        self.assertEqual(leaf.read_bytes(),before);self.assertTrue(a.restored());self.loaded.validate()
    def test_native_custody_descriptor_rebinding_refuses_without_fallback(self):
        lifecycle=self.loaded.modules[3];value,leaf,other=self.custody();a=self.adapter()
        with a.installed():
            value.check();fd=os.open(other,os.O_RDONLY)
            try:os.dup2(fd,value.retained[leaf])
            finally:os.close(fd)
            with self.assertRaises(lifecycle.RootLifecycleRefused):value.check()
        self.assertGreater(a.calls['custody'],0);self.assertEqual(a.fallbacks['custody'],0)
    def test_present_retained_none_preserves_original_type_error_before_native(self):
        value,leaf,_=self.custody();a=self.adapter();fd=value.retained[leaf]
        before=self.loaded.native.counts()
        try:
            value.retained[leaf]=None
            with a.installed(),self.assertRaises(TypeError):value.check()
        finally:value.retained[leaf]=fd
        self.assertEqual(self.loaded.native.counts(),before);self.assertEqual(a.fallbacks['custody'],1)
    def test_native_admission_detects_in_place_code_change_and_code_custody_refuses(self):
        service=self.loaded.modules[0];a=self.adapter();fn=Path.stat;original=fn.__code__
        def altered(self,*,follow_symlinks=True):raise KeyboardInterrupt('metadata hook')
        before=self.loaded.native.counts()
        try:
            with a.installed():
                fn.__code__=altered.__code__
                self.assertFalse(a.eligible())
                with self.assertRaises(ValueError):self.loaded.validate()
                with self.assertRaises(KeyboardInterrupt) as caught:service._CapturedRootFiles._fingerprint('/synthetic',4096,False)
                self.assertEqual(caught.exception.args,('metadata hook',))
        finally:fn.__code__=original
        self.assertEqual(self.loaded.native.counts(),before);self.assertEqual(a.fallbacks['root_files'],1)
        self.loaded.validate()
        helper=self.loaded.modules[3].directory_identity.__globals__['require'];original=helper.__code__
        try:
            with a.installed():
                helper.__code__=altered.__code__
                self.assertFalse(a.eligible())
                with self.assertRaises(ValueError):self.loaded.validate()
        finally:helper.__code__=original
        self.assertEqual(self.loaded.native.counts(),before);self.loaded.validate()
    def test_native_custody_metadata_and_entry_change_refuse(self):
        lifecycle=self.loaded.modules[3];value,leaf,_=self.custody();a=self.adapter()
        with a.installed():
            value.check();leaf.chmod(0o400)
            with self.assertRaises(lifecycle.RootLifecycleRefused):value.check()
        self.assertGreater(a.calls['custody'],0)
        value2,leaf2,_=self.custody();a2=self.adapter()
        with a2.installed():
            value2.check();extra=leaf2.with_name('transient');extra.write_bytes(b'x');extra.unlink()
            with self.assertRaises(lifecycle.RootLifecycleRefused):value2.check()
        self.assertGreater(a2.calls['custody'],0);self.assertEqual(a2.fallbacks['custody'],0)
    def test_native_custody_keeps_separate_passes_and_refuses_restored_mtime(self):
        from native_root_controller import _RootObservationPass
        lifecycle=self.loaded.modules[3];value,leaf,_=self.custody();a=self.adapter()
        with a.installed():
            with _RootObservationPass():
                value.check();count=self.loaded.native.counts()['custody']
                value.check();self.assertEqual(self.loaded.native.counts()['custody'],count)
            before=leaf.stat();leaf.write_bytes(leaf.read_bytes());os.utime(leaf,ns=(before.st_atime_ns,before.st_mtime_ns))
            with self.assertRaises(lifecycle.RootLifecycleRefused):
                with _RootObservationPass():value.check()
        self.assertGreater(self.loaded.native.counts()['custody'],count)
        self.assertEqual(a.fallbacks['custody'],0)
    def test_native_descriptor_loss_poisons_original_public_view_and_preserves_files(self):
        import test_native_root_lifecycle as original
        lifecycle=self.loaded.modules[3];value,leaf,_=self.custody();a=self.adapter()
        public=original.RootOriginalViewTest().view();public.owner=value.owner
        public.history=types.SimpleNamespace(custody=value,close=value.__exit__)
        descriptors=[*value.retained.values(),*(fd for fd,_ in value.directories.values()),value.lock]
        before=leaf.read_bytes()
        with a.installed():
            public.check();os.close(value.retained[leaf])
            with self.assertRaises(lifecycle.RootLifecycleRefused):public.check()
            with self.assertRaises(lifecycle.RootLifecycleRefused):public.check()
        self.assertFalse(public.usable);self.assertFalse(value.usable)
        for fd in descriptors:
            with self.assertRaises(OSError):os.fstat(fd)
        self.assertEqual(leaf.read_bytes(),before);self.assertGreater(a.calls['custody'],0)
    def test_native_preflight_refuses_unsupported_tables_without_observations(self):
        native=self.loaded.native;before=native.counts()
        self.assertIs(native.persistent(0,(),(('bad',),),'/synthetic',(),(),os.listdir),NotImplemented)
        self.assertIs(native.custody(0,0,(('bad',),),(),None,lambda fd:[]),NotImplemented)
        self.assertEqual(native.counts(),before)
    def test_actual_native_guard_ten_profile_uses_original_metadata_and_restores_before_next_guard(self):
        service,binding,generation,_=self.loaded.modules;custody,_,_=self.custody()
        before=self.loaded.native.counts();codes=probe.native_profile_codes(self.loaded.native)
        self.assertEqual(set(codes.values()),set(probe.NATIVE_APIS));self.assertEqual(self.loaded.native.counts(),before)
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            root=Path(directory);machine=root/'machine';machine.write_bytes(b'machine');machine.chmod(0o600)
            leaf=root/'executable';leaf.write_bytes(b'one');leaf.chmod(0o700)
            plan=generation._PersistentFingerprintPlan.__new__(generation._PersistentFingerprintPlan)
            info=root.lstat();file=leaf.lstat();plan.uid=0
            plan.entries=((root,frozenset({'machine','executable'})),)
            plan.directories=((root,str(root),info.st_dev,info.st_ino,0),);plan.machine=machine
            plan.files=((leaf,str(leaf),0,True,file.st_size,file.st_dev,file.st_ino),)
            plan.parents=tuple((p,str(p),False,False) for p in root.parents)
            class Stage:
                calls=0
                def check(subject):
                    subject.calls+=1
                    service._CapturedRootFiles._fingerprint(leaf,4096,True)
                    binding._CapturedExecutableDigests._fingerprint(str(leaf))
                    plan.read();custody.check()
            stage=Stage();sample=original_sample()
            with probe.GuardTenSample(self.loaded,sample) as diagnostic:
                checked=sample.wrap(Stage.check)
                for number in range(12):
                    checked(stage);self.assertTrue(diagnostic.adapter.restored())
                    if number<9:self.assertEqual(self.loaded.native.counts(),before)
                result=diagnostic.result
            self.assertEqual(stage.calls,12);self.assertEqual(sample.calls,12);self.assertEqual(result['extra_guard_calls'],0)
            self.assertEqual(result['guard_number'],10);self.assertEqual(result['profiled_checks'],1)
            self.assertTrue(all(v>0 for v in result['native_calls'].values()))
            self.assertTrue(all(v>0 for v in result['families'].values()));self.assertFalse(any(result['fallbacks'].values()))
            self.assertEqual({r['function'] for r in result['rows'] if r['file']=='native-metadata-api.py' and r['calls']>0},set(probe.NATIVE_APIS))
            self.assertTrue(0<len(result['rows'])<=16);self.assertNotIn('wrap',vars(sample));self.loaded.validate()
    def test_original_errors_and_namespace_mutation_fall_back_before_native(self):
        service=self.loaded.modules[0];a=self.adapter();failure=KeyboardInterrupt('original')
        with a.installed(),patch.object(Path,'lstat',side_effect=failure):
            with self.assertRaises(KeyboardInterrupt) as caught:service._CapturedRootFiles._fingerprint('/synthetic',4096,False)
        self.assertIs(caught.exception,failure);self.assertGreater(a.fallbacks['root_files'],0)
    def test_native_sdk_global_and_effective_concrete_hook_changes_preserve_original_error(self):
        service=self.loaded.modules[0];a=self.adapter();failure=KeyboardInterrupt('original SDK hook')
        class ChangedOS:
            def __getattr__(self,name):return getattr(os,name)
            stat=Mock(side_effect=failure)
        before=self.loaded.native.counts()
        with a.installed():
            with patch.object(pathlib,'os',ChangedOS()):
                self.assertFalse(a.eligible())
                with self.assertRaises(KeyboardInterrupt) as caught:service._CapturedRootFiles._fingerprint('/synthetic',4096,False)
                self.assertIs(caught.exception,failure)
            with patch.object(a.path_type,'stat',side_effect=failure):
                self.assertFalse(a.eligible())
                with self.assertRaises(KeyboardInterrupt) as caught:service._CapturedRootFiles._fingerprint('/synthetic',4096,False)
                self.assertIs(caught.exception,failure)
        self.assertEqual(self.loaded.native.counts(),before);self.assertEqual(a.fallbacks['root_files'],2)
        self.loaded.validate()
    def test_code_custody_is_reread_after_comparison(self):
        path=self.root/'native-metadata-probe.c';raw=path.read_bytes()
        try:
            path.write_bytes(raw+b'\n/* own fixture mutation */\n')
            with self.assertRaises(ValueError):self.loaded.validate()
        finally:path.write_bytes(raw)
        with self.assertRaises(ValueError):self.loaded.validate()
        # Explicitly reseal only this disposable test's restored source.
        self.loaded.files[path.name]=probe._read_owned(path,262144);self.loaded.validate()


if __name__=='__main__':unittest.main(verbosity=2)
