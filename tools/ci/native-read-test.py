#!/usr/bin/env python3
"""Complete-read contract tests; native hosted cases are added with integration.

These portable checks establish the borrowed buffered-reader ownership contract,
not execution or acceptance of the Linux C backend.
"""
import io
import faulthandler
import cProfile
import hashlib
import importlib.util
import os
import pstats
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock,MagicMock,patch

sys.dont_write_bytecode=True
faulthandler.enable(all_threads=True)
import native_read_probe as probe

spec=importlib.util.spec_from_file_location('_metadata_read_cases',Path(__file__).with_name('native-metadata-test.py'))
metadata_cases=importlib.util.module_from_spec(spec);spec.loader.exec_module(metadata_cases)


class FakeNative(metadata_cases.FakeNative):
    def __init__(self):super().__init__();self.reads=0;self.preparations=0
    def read_counts(self):return {'read':self.reads,'prepare':self.preparations}
    def read_file(self,kind,name,parents,uid,maximum,executable,opener,reader_type):
        self.reads+=1;raw=b'one';info=(1,2,3,4,5,uid,0o100600,1)
        return raw,info if kind<2 else None,info if kind<2 else None
    def prepare_tables(self,*_):self.preparations+=1;return ('ephemeral',)


def models():
    modules=metadata_cases.models();service,binding,*_=modules
    for module in (service,binding):module.hashlib=hashlib
    exec('def root_file(path,maximum=16777216,*,executable=False): return ("original-root",path)\n'
         'def read_bytes(path,maximum=16384): return b"original-service"\n',vars(service))
    exec('def private_file(path,uid,maximum=131072): return ("original-private",path)\n'
         'def _canonical_private_path(path): return Path(path)\n',vars(binding))
    kernel=types.ModuleType('native_kernel_backend');kernel.os=os;kernel.require=service.require
    exec('def _read(path,maximum=16384): return "original-kernel"\n',vars(kernel))
    return modules,kernel


class ReadAdapterTest(unittest.TestCase):
    def setUp(self):
        for name in ('getuid','geteuid','getgid','getegid'):
            if not hasattr(os,name):self.enterContext(patch.object(os,name,lambda:0,create=True))
        # Windows lacks the flags even though these tests never perform OS reads.
        for name in ('O_NOFOLLOW','O_CLOEXEC','O_NONBLOCK'):
            if not hasattr(os,name):self.enterContext(patch.object(os,name,0,create=True))
        self.modules,self.kernel=models();self.native=FakeNative()
        self.adapter=probe.Adapter(self.modules,self.native,self.kernel,owner_check=lambda:None)

    def test_root_and_raw_return_shapes_and_all_original_classes_retained(self):
        a=self.adapter;owners=a.owners
        with a.installed():
            identity,raw=self.modules[0].root_file('/synthetic',3)
            self.assertIs(type(identity),dict);self.assertEqual(raw,b'one')
            self.assertEqual(identity['sha256'],hashlib.sha256(b'one').hexdigest())
            self.assertEqual(self.modules[0].read_bytes('/synthetic',3),b'one')
            self.assertEqual(self.kernel._read('/synthetic',3),'one');self.assertEqual(a.owners,owners)
        self.assertTrue(a.restored());self.assertEqual(self.native.reads,3)

    def test_size_and_ascii_checks_follow_native_close_boundary_without_retry(self):
        with self.adapter.installed():
            with self.assertRaises(ValueError):self.modules[0].read_bytes('/synthetic',2)
            with self.assertRaises(ValueError):self.kernel._read('/synthetic',0)
            with patch.object(self.native,'read_file',return_value=(b'\xff',None,None)):
                with self.assertRaises(UnicodeDecodeError):self.kernel._read('/synthetic')
            with patch.object(self.native,'read_file',return_value=(None,None,None)):
                with self.assertRaises(TypeError):self.kernel._read('/synthetic')
        self.assertFalse(any(self.adapter.fallbacks.values()));self.assertTrue(self.adapter.restored())

    def test_unsupported_only_falls_back_before_native_admission(self):
        with self.adapter.installed():
            with patch.object(self.native,'read_file',return_value=NotImplemented):
                self.assertEqual(self.kernel._read('/synthetic'),'original-kernel')
            self.assertEqual(self.modules[0].read_bytes('/synthetic',-1),b'original-service')
        self.assertEqual(self.native.reads,0);self.assertEqual(self.adapter.fallbacks['kernel_read'],1)
        self.assertEqual(self.adapter.fallbacks['read_bytes'],1)

    def test_postclose_metadata_mismatch_refuses_without_retry(self):
        before=(1,2,3,4,5,0,0o100600,1);after=(*before[:3],before[3]+1,*before[4:])
        with self.adapter.installed(),patch.object(self.native,'read_file',return_value=(b'one',before,after)):
            with self.assertRaises(ValueError):self.modules[0].root_file('/synthetic')
        self.assertFalse(any(self.adapter.fallbacks.values()));self.assertTrue(self.adapter.restored())

    def test_native_errors_including_unsupported_exception_never_retry(self):
        for failure in (KeyboardInterrupt('original'),OSError(5,'read failed'),probe.Unsupported()):
            with self.adapter.installed(),patch.object(self.native,'read_file',side_effect=failure):
                with self.assertRaises(type(failure)) as caught:self.kernel._read('/synthetic')
            self.assertIs(caught.exception,failure)
        self.assertEqual(self.adapter.fallbacks['kernel_read'],0)

    def test_fdopen_code_and_io_hook_replacement_fall_back_before_native(self):
        failure=KeyboardInterrupt('io hook')
        with self.adapter.installed(),patch.object(io,'open',Mock(side_effect=failure)):
            self.assertEqual(self.kernel._read('/synthetic'),'original-kernel')
        fn=os.fdopen;original=fn.__code__
        def changed(fd,mode='r',buffering=-1,encoding=None,*args,**kwargs):raise KeyboardInterrupt('code hook')
        try:
            with self.adapter.installed():
                fn.__code__=changed.__code__
                self.assertEqual(self.modules[0].read_bytes('/synthetic'),b'original-service')
        finally:fn.__code__=original
        self.assertEqual(self.native.reads,0)

    def test_preparation_is_native_and_returns_only_ephemeral_arguments(self):
        self.assertEqual(self.adapter.plan_arguments(object()),('ephemeral',))
        self.assertEqual(self.adapter.custody_arguments(object()),('ephemeral',))
        self.assertEqual(self.native.read_counts(),{'read':0,'prepare':2})
        with patch.object(self.native,'prepare_tables',return_value=NotImplemented):
            with self.assertRaises(probe.Unsupported):self.adapter.plan_arguments(object())

    def test_code_custody_rejects_added_io_code_and_api_changes_before_filesystem_validation(self):
        def original():return 'original'
        def altered():raise KeyboardInterrupt('altered I/O code')
        code=original.__code__;loaded=object.__new__(probe.Loaded)
        loaded.extra_functions=(original,);loaded.original_codes={id(original):code}
        loaded.native=types.ModuleType('_native_metadata_probe');loaded.native.read_file=object()
        loaded.native_apis={'read_file':loaded.native.read_file}
        loaded.extra_files={};loaded.runtime_files={}
        loaded.base=types.SimpleNamespace(validate=Mock(side_effect=AssertionError('filesystem validation ran before code admission')))
        try:
            original.__code__=altered.__code__
            with self.assertRaises(ValueError):loaded.validate()
        finally:original.__code__=code
        loaded.base.validate.assert_not_called()
        loaded.native.read_file=object()
        with self.assertRaises(ValueError):loaded.validate()
        loaded.base.validate.assert_not_called()

    def test_existing_and_late_import_aliases_restore_after_interruption(self):
        a=self.adapter;failure=KeyboardInterrupt('original');directory=Path.cwd()/'synthetic-installed'
        a.installed_directory=directory;alias=types.ModuleType('_read_alias_fixture');alias.__file__=str(directory/'alias.py')
        alias.helper=a.read_originals[0];late=types.ModuleType('_read_late_alias_fixture');late.__file__=str(directory/'late.py')
        with patch.dict(sys.modules,{alias.__name__:alias}):
            try:
                with self.assertRaises(KeyboardInterrupt) as caught:
                    with a.installed():
                        self.assertIs(alias.helper,a.read_replacements[0])
                        late.helper=a.read_replacements[2];sys.modules[late.__name__]=late
                        raise failure
                self.assertIs(caught.exception,failure);self.assertIs(alias.helper,a.read_originals[0])
                self.assertIs(late.helper,a.read_originals[2]);self.assertTrue(a.restored())
            finally:sys.modules.pop(late.__name__,None)

    def test_partial_install_attempts_all_restorations_and_preserves_pending_error(self):
        a=self.adapter;original_setattr=setattr;failure=KeyboardInterrupt('install');seen=[]
        def assign(owner,name,value):
            seen.append((owner,name,value))
            if owner is a.binding and name=='private_file' and value is a.read_replacements[1]:raise failure
            original_setattr(owner,name,value)
        with patch.object(probe,'setattr',assign,create=True),self.assertRaises(KeyboardInterrupt) as caught:
            with a.installed():self.fail('partial installation entered')
        self.assertIs(caught.exception,failure);self.assertTrue(a.restored())
        self.assertTrue(all(any(o is owner and n==name and v is old for o,n,v in seen)
            for owner,name,old,_new in a.entries[:6]))

    def test_alias_restore_failure_poisons_adapter_and_preserves_original_error(self):
        a=self.adapter;directory=Path.cwd()/'synthetic-installed';a.installed_directory=directory
        alias=types.ModuleType('_read_failed_alias');alias.__file__=str(directory/'failed.py');alias.helper=a.read_originals[0]
        original_setattr=setattr;failure=KeyboardInterrupt('original');restored=[]
        def assign(owner,name,value):
            if owner is alias and value is a.read_originals[0]:raise OSError('restore failed')
            original_setattr(owner,name,value)
            if any(o is owner and n==name and old is value for o,n,old,_new in a.entries):restored.append((owner,name))
        with patch.dict(sys.modules,{alias.__name__:alias}):
            try:
                with patch.object(probe,'setattr',assign,create=True),self.assertRaises(KeyboardInterrupt) as caught:
                    with a.installed():raise failure
                self.assertIs(caught.exception,failure);self.assertTrue(a.broken);self.assertFalse(a.active)
                self.assertEqual(len(restored),len(a.entries))
                with self.assertRaises(ValueError):
                    with a.installed():self.fail('poisoned adapter reused')
            finally:alias.helper=a.read_originals[0]

    def test_twenty_pairs_alternate_on_same_actor_with_originals_between_samples(self):
        a=self.adapter;stage=types.SimpleNamespace(usable=True,state='ready');order=[]
        def guard(subject):
            self.assertIs(subject,stage);order.append(a.active)
            if a.active:
                for name in self.native.values:self.native.values[name]+=1
                self.native.reads+=1;self.native.preparations+=1
                for name in probe.FAMILIES:a.count(name)
            return ('same',)
        loaded=types.SimpleNamespace(modules=self.modules,native=self.native,kernel=self.kernel,
            original_codes={},validate=Mock(),evidence=lambda:{'synthetic':True})
        with patch.object(probe,'Adapter',return_value=a),patch.object(probe.metadata,'root_owner',lambda:None):
            result=probe.compare_guard(loaded,guard,stage)
        self.assertEqual(order,[selected for number in range(20)
            for selected in ((False,True) if number%2==0 else (True,False))])
        self.assertEqual(len(result['pairs']),20);self.assertEqual(result['native_calls'],{
            'fingerprint':20,'persistent':20,'custody':20,'read':20,'prepare':20})
        self.assertTrue(a.restored());loaded.validate.assert_called_once()

    def test_first_guard_starts_measurements_only_after_restoration_and_poison_on_failure(self):
        stage=types.SimpleNamespace(usable=True,state='ready',allocation=types.SimpleNamespace(usable=True,close=Mock()),close=Mock())
        class Owner:
            def check(subject):return 'original'
        original=Owner.check;measurement=MagicMock();loaded=object()
        with patch.object(probe,'compare_guard',return_value={'paired':True}) as comparison:
            with probe.AtFirstGuard(loaded,Owner,measurement) as gate:
                self.assertEqual(Owner.check(stage),'original');self.assertEqual(gate.result,{'paired':True})
                self.assertIs(Owner.check,original);measurement.__enter__.assert_called_once()
            comparison.assert_called_once_with(loaded,original,stage)
        measurement.__exit__.assert_called_once();self.assertIs(Owner.check,original)
        failure=KeyboardInterrupt('paired failure')
        with patch.object(probe,'compare_guard',side_effect=failure):
            with self.assertRaises(KeyboardInterrupt) as caught:
                with probe.AtFirstGuard(loaded,Owner,Mock()):Owner.check(stage)
        self.assertIs(caught.exception,failure);self.assertFalse(stage.usable);self.assertFalse(stage.allocation.usable)
        stage.close.assert_called_once();stage.allocation.close.assert_called_once();self.assertIs(Owner.check,original)


class ReadProfileTest(unittest.TestCase):
    setUp=ReadAdapterTest.setUp
    def profile_fixture(self):return {name+'_synthetic':name for name in probe.NATIVE_APIS}
    def sources(self):
        return {name:Path(probe.__file__).with_name(name).read_bytes()
            for name in ('native_metadata_probe.py','native_read_probe.py')}
    def costs(self):
        return [{'file':'native-read-api.py','function':name,'line':0,'calls':1,'self_us':1,'cumulative_us':1}
            for name in probe.NATIVE_APIS]
    def loaded(self):
        sources=self.sources()
        return types.SimpleNamespace(modules=self.modules,native=self.native,kernel=self.kernel,original_codes=None,
            base=types.SimpleNamespace(files={'native_metadata_probe.py':(sources['native_metadata_probe.py'],None)}),
            extra_files={'native_read_probe.py':(sources['native_read_probe.py'],None)},
            validate=Mock(),evidence=lambda:{'synthetic':True})
    def test_actual_python_profile_uses_public_labels_without_source_paths(self):
        profile=cProfile.Profile();profile.runcall(self.adapter.eligible)
        rows=probe.profile_costs(pstats.Stats(profile).stats,self.sources(),self.profile_fixture())
        row=next(r for r in rows if r['function']=='eligible')
        self.assertEqual(row['file'],'native-read-self.py');self.assertEqual(row['calls'],1)
        self.assertNotIn(str(Path.cwd()),str(rows))
        self.assertEqual(len([r for r in rows if r['file']=='native-read-api.py']),8)
    def test_unknown_private_rows_are_ignored_without_inspecting_values(self):
        opaque=Mock();opaque.__str__=Mock(side_effect=AssertionError('private value read'))
        rows=probe.profile_costs({('/private/secret.py',12,'password'):opaque,
            ('~',0,'private_secret'):opaque,('/private/secret.py',True,'password'):opaque},self.sources(),self.profile_fixture())
        self.assertEqual(len(rows),8);self.assertTrue(all(r['calls']==0 for r in rows))
        self.assertNotIn('secret',str(rows));opaque.__str__.assert_not_called()
    def test_known_rows_ignore_private_caller_values_and_reject_invalid_numbers(self):
        key=('~',0,'same_bindings_synthetic');opaque=Mock()
        opaque.__str__=Mock(side_effect=AssertionError('private caller read'))
        rows=probe.profile_costs({key:(opaque,2,.001,.002,opaque)},self.sources(),self.profile_fixture())
        row=next(r for r in rows if r['function']=='same_bindings')
        self.assertEqual(row['calls'],2);self.assertEqual(row['self_us'],1000)
        opaque.__str__.assert_not_called()
        for calls,total,cumulative in [(True,0,0),(-1,0,0),(10000001,0,0),(1,True,1),
                (1,float('nan'),1),(1,float('inf'),1),(1,-1,1),(1,1,0),(1,0,1201),(1,10**500,10**500)]:
            with self.subTest(calls=calls,total=total),self.assertRaises(ValueError):
                probe.profile_costs({key:(opaque,calls,total,cumulative,opaque)},self.sources(),self.profile_fixture())
    def test_both_authenticated_sources_have_deterministic_sixteen_row_limit(self):
        stats={};sources=self.sources()
        for filename,helper,inventory in (('native_metadata_probe.py',probe.metadata,probe.metadata.PROFILE_PYTHON),
                ('native_read_probe.py',probe,probe.PROFILE_PYTHON)):
            code=probe.metadata.functions(compile(sources[filename],helper.__file__,'exec'))
            for index,(qualified,_label) in enumerate(inventory):
                fn=code[qualified];stats[fn.co_filename,fn.co_firstlineno,fn.co_name]=(1,index+1,.001,.002,None)
        for name in probe.NATIVE_APIS:stats['~',0,name+'_synthetic']=(1,2,0,0,None)
        rows=probe.profile_costs(stats,sources,self.profile_fixture())
        self.assertEqual(len(rows),16)
        self.assertEqual({r['function'] for r in rows if r['file']=='native-read-api.py'},set(probe.NATIVE_APIS))
        self.assertEqual(rows,probe.profile_costs(dict(reversed(list(stats.items()))),sources,self.profile_fixture()))
        allowed={'file','function','line','calls','self_us','cumulative_us'}
        self.assertTrue(all(set(row)==allowed for row in rows))
    def test_source_and_native_label_schema_refuse_before_export(self):
        sources=self.sources();codes=self.profile_fixture()
        for invalid in ({}, {**sources,'private.py':b'private'}, {**sources,'native_read_probe.py':b''},
                {**sources,'native_read_probe.py':'private'}, {**sources,'native_read_probe.py':b'x'*262145}):
            with self.assertRaises(ValueError):probe.profile_costs({},invalid,codes)
        for invalid in ({}, {**codes,'private':'private'}, {**codes,'read_file_synthetic':'fingerprint'}):
            with self.assertRaises(ValueError):probe.profile_costs({},sources,invalid)
    def test_python_standins_cannot_authenticate_as_native_profiler_labels(self):
        with patch.object(self.native,'counts',side_effect=AssertionError('standin invoked')) as replaced:
            with self.assertRaises(ValueError):probe.native_profile_codes(self.native)
        replaced.assert_not_called()
        self.assertEqual(probe.counts(self.native),dict.fromkeys(('fingerprint','persistent','custody','read','prepare'),0))
    def test_label_discovery_refuses_and_preserves_existing_profiler(self):
        original=sys.getprofile()
        def foreign(*_):pass
        try:
            sys.setprofile(foreign)
            with self.assertRaises(ValueError):probe.native_profile_codes(self.native)
            self.assertIs(sys.getprofile(),foreign)
        finally:sys.setprofile(original)
        self.assertEqual(self.native.read_counts(),{'read':0,'prepare':0})
    def test_first_guard_starts_original_measurements_only_tenth_enables_native(self):
        sample=metadata_cases.original_sample();a=self.adapter;test=self;events=[];loaded=self.loaded()
        class Stage:
            usable=True;allocation=types.SimpleNamespace(usable=True,close=Mock());close=Mock()
            def check(subject):
                events.append(a.active)
                if a.active:
                    for family in probe.FAMILIES:a.count(family)
                    for name in test.native.values:test.native.values[name]+=1
                    test.native.reads+=1;test.native.preparations+=1
                else:test.assertTrue(a.restored())
                return 'original'
        original=Stage.check
        class Measurements:
            def __init__(subject):subject.sample=sample
            def __enter__(subject):test.assertIs(Stage.check,original);Stage.check=sample.wrap(original)
            def __exit__(subject,*_):Stage.check=original
        with patch.object(probe,'Adapter',return_value=a),patch.object(probe,'native_profile_codes',return_value=self.profile_fixture()),patch.object(probe,'profile_costs',return_value=self.costs()),patch.object(probe,'compare_guard',side_effect=AssertionError('rejected comparison repeated')):
            with probe.AtFirstGuardProfile(loaded,Stage,Measurements()) as diagnostic:
                for number in range(12):
                    self.assertEqual(Stage().check(),'original');self.assertTrue(a.restored())
                    self.assertEqual(sum(probe.counts(self.native).values()),0 if number<9 else 5)
            result=diagnostic.result
        self.assertEqual(events,[False]*9+[True]+[False]*2);self.assertEqual(sample.calls,12)
        self.assertIs(Stage.check,original);self.assertNotIn('wrap',vars(sample))
        self.assertEqual(result['guard_number'],10);self.assertEqual(result['extra_guard_calls'],0)
        self.assertEqual(result['native_calls'],dict.fromkeys(probe.counts(self.native),1))
        self.assertTrue(result['direct_aliases_restored']);loaded.validate.assert_called_once()
    def test_sample_interruption_restores_descriptors_direct_and_late_aliases(self):
        sample=metadata_cases.original_sample();a=self.adapter;loaded=self.loaded();failure=KeyboardInterrupt('original')
        directory=Path.cwd()/'synthetic-installed';a.installed_directory=directory
        alias=types.ModuleType('_profile_alias');alias.__file__=str(directory/'alias.py');alias.helper=a.read_originals[0]
        late=types.ModuleType('_profile_late');late.__file__=str(directory/'late.py')
        def guard():
            if a.active:
                self.assertIs(alias.helper,a.read_replacements[0])
                late.helper=a.read_replacements[2];sys.modules[late.__name__]=late
                raise failure
        with patch.dict(sys.modules,{alias.__name__:alias}),patch.object(probe,'Adapter',return_value=a),patch.object(probe,'native_profile_codes',return_value=self.profile_fixture()):
            try:
                with probe.GuardTenSample(loaded,sample) as diagnostic:
                    wrapped=sample.wrap(guard)
                    for _ in range(9):wrapped()
                    with self.assertRaises(KeyboardInterrupt) as caught:wrapped()
                self.assertIs(late.helper,a.read_originals[2])
            finally:sys.modules.pop(late.__name__,None)
        self.assertIs(caught.exception,failure);self.assertTrue(a.restored());self.assertIsNone(diagnostic.result)
        self.assertIs(alias.helper,a.read_originals[0]);self.assertNotIn('wrap',vars(sample))
        self.assertIsNone(sys.getprofile());self.assertEqual(sample.calls,10);loaded.validate.assert_not_called()
    def test_first_guard_setup_failure_preserves_error_and_attempts_both_closes(self):
        sample=metadata_cases.original_sample();failure=KeyboardInterrupt('original');loaded=self.loaded()
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

    def test_postsample_custody_failure_prevents_effect_and_preserves_original_wrap(self):
        sample=metadata_cases.original_sample();a=self.adapter;loaded=self.loaded();failure=KeyboardInterrupt('custody')
        loaded.validate.side_effect=failure;original_wrap=sample.wrap;sample.wrap=original_wrap;effect=Mock()
        def guard():
            if a.active:
                for family in probe.FAMILIES:a.count(family)
                for name in self.native.values:self.native.values[name]+=1
                self.native.reads+=1;self.native.preparations+=1
        with patch.object(probe,'Adapter',return_value=a),patch.object(probe,'native_profile_codes',return_value=self.profile_fixture()):
            with probe.GuardTenSample(loaded,sample) as diagnostic:
                wrapped=sample.wrap(guard)
                for _ in range(9):wrapped()
                with self.assertRaises(KeyboardInterrupt) as caught:
                    wrapped();effect()
        self.assertIs(caught.exception,failure);self.assertIs(sample.wrap,original_wrap)
        self.assertTrue(a.restored());self.assertIsNone(diagnostic.result);self.assertIsNone(sys.getprofile())
        effect.assert_not_called();loaded.validate.assert_called_once()


class BufferedReadOwnershipTest(unittest.TestCase):
    def test_buffered_read_keeps_maximum_plus_one_and_owner_closes_descriptor(self):
        source=tempfile.TemporaryFile(mode='w+b')
        fd=source.fileno()
        try:
            source.write(b'abcdef');source.flush();source.seek(0)
            reader=io.open(fd,'rb',closefd=False)
            with reader as opened:
                self.assertIs(opened,reader);self.assertEqual(opened.read(3+1),b'abcd')
            self.assertTrue(reader.closed);os.fstat(fd)
        finally:source.close()
        with self.assertRaises(OSError):os.fstat(fd)

    def test_failed_borrowed_reader_construction_keeps_descriptor_with_owner(self):
        source=tempfile.TemporaryFile(mode='w+b');fd=source.fileno()
        try:
            with self.assertRaises(ValueError):io.open(fd,'invalid-mode',closefd=False)
            os.fstat(fd)
        finally:source.close()
        with self.assertRaises(OSError):os.fstat(fd)

    def test_original_read_error_survives_borrowed_reader_and_owner_cleanup(self):
        source=tempfile.TemporaryFile(mode='w+b');fd=source.fileno();failure=KeyboardInterrupt('original')
        try:
            with self.assertRaises(KeyboardInterrupt) as caught:
                with io.open(fd,'rb',closefd=False):raise failure
            self.assertIs(caught.exception,failure);os.fstat(fd)
        finally:source.close()
        with self.assertRaises(OSError):os.fstat(fd)


@unittest.skipUnless(sys.platform=='linux' and sys.version_info[:2]==(3,12)
    and getattr(os,'geteuid',lambda:-1)()==0,'Actual hosted Linux CPython3.12 Root required')
class HostedReadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        metadata_cases.HostedMetadataTest.setUpClass.__func__(cls)
        helper=Path(__file__).with_name('native_read_probe.py');destination=cls.root/helper.name
        shutil.copyfile(helper,destination);destination.chmod(0o644)
        cls.loaded=probe.Loaded(cls.root,base=cls.loaded)

    def adapter(self):return probe.Adapter(self.loaded.modules,self.loaded.native,self.loaded.kernel,original_codes=self.loaded.original_codes)
    custody=metadata_cases.HostedMetadataTest.custody

    def test_guard_ten_profile_authenticates_native_labels_and_all_eight_fresh_roles(self):
        service,binding,generation,_lifecycle=self.loaded.modules;kernel=self.loaded.kernel
        before=probe.counts(self.loaded.native);codes=probe.native_profile_codes(self.loaded.native)
        self.assertEqual(set(codes.values()),set(probe.NATIVE_APIS))
        self.assertEqual(probe.counts(self.loaded.native),before)
        custody,_leaf,_other=self.custody()
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            root=Path(directory);root.chmod(0o700)
            executable=root/'executable';executable.write_bytes(b'one');executable.chmod(0o700)
            private=root/'private';private.write_bytes(b'one');private.chmod(0o600)
            machine=root/'machine';machine.write_bytes(b'machine');machine.chmod(0o600)
            plan=generation._PersistentFingerprintPlan.__new__(generation._PersistentFingerprintPlan)
            info=root.lstat();plan.uid=0;plan.entries=((root,frozenset({'executable','private','machine'})),)
            plan.directories=((root,str(root),info.st_dev,info.st_ino,0),);plan.machine=machine
            plan.files=tuple((path,str(path),0,False,path.lstat().st_size,path.lstat().st_dev,path.lstat().st_ino)
                for path in (executable,private))
            plan.parents=tuple((p,str(p),False,False) for p in root.parents)
            def guard():
                custody.check()
                return (service._CapturedRootFiles._fingerprint(executable,4096,True),
                    binding._CapturedExecutableDigests._fingerprint(str(executable)),plan.read(),
                    service.root_file(executable,4096,executable=True),binding.private_file(private,0),
                    service.read_bytes(private),kernel._read(private))
            expected=guard();sample=metadata_cases.original_sample()
            with probe.GuardTenSample(self.loaded,sample) as diagnostic:
                wrapped=sample.wrap(guard)
                for _ in range(12):
                    self.assertEqual(wrapped(),expected);self.assertTrue(diagnostic.adapter.restored())
            result=diagnostic.result
        self.assertEqual(sample.calls,12);self.assertNotIn('wrap',vars(sample));self.assertIsNone(sys.getprofile())
        self.assertEqual(result['extra_guard_calls'],0);self.assertEqual(result['guard_number'],10)
        self.assertEqual(set(result['native_calls']),{'fingerprint','persistent','custody','read','prepare'})
        self.assertTrue(all(v>0 for v in result['native_calls'].values()))
        self.assertEqual(set(result['families']),set(probe.FAMILIES))
        self.assertTrue(all(v>0 for v in result['families'].values()));self.assertFalse(any(result['fallbacks'].values()))
        native_rows=[r for r in result['rows'] if r['file']=='native-read-api.py']
        self.assertEqual({r['function'] for r in native_rows},set(probe.NATIVE_APIS))
        self.assertEqual({r['function'] for r in native_rows if r['calls']>0},set(probe.NATIVE_APIS)-{'read_counts'})
        self.assertEqual(next(r['calls'] for r in native_rows if r['function']=='counts'),3)
        self.assertLessEqual(len(result['rows']),16);self.assertNotIn(str(self.root),str(result['rows']))
        self.assertTrue(result['direct_aliases_restored']);self.loaded.validate()

    def test_zz_all_original_372_root_cases_with_eight_role_adapter(self):
        spec=importlib.util.spec_from_file_location('_original_read_lexical_cases',Path(__file__).with_name('lexical-path-test.py'))
        original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
        suite=unittest.TestSuite()
        for name,count in original.ROOT_SCOPES:
            scope=unittest.defaultTestLoader.loadTestsFromName(name)
            self.assertEqual(scope.countTestCases(),count);suite.addTest(scope)
        a=self.adapter();stream=io.StringIO()
        class RootProgress(unittest.TextTestResult):
            def startTest(self,test):
                # Fixed public source symbols only, before the test can enter
                # native code. No paths, values or private records are emitted.
                print('native_read_root_case='+type(test).__name__+'.'+test._testMethodName,flush=True)
                super().startTest(test)
        with a.installed():result=unittest.TextTestRunner(stream=stream,resultclass=RootProgress).run(suite)
        self.assertEqual(result.testsRun,372);self.assertFalse(result.skipped)
        self.assertTrue(result.wasSuccessful(),stream.getvalue());self.assertTrue(a.restored());self.loaded.validate()
        self.assertGreater(a.calls['root_file'],0);self.assertGreater(a.calls['private_file'],0)
        print('native_read_original_root_cases=372',flush=True)

    def leaf(self,raw=b'one',mode=0o600):
        directory=Path(tempfile.mkdtemp(prefix='read-',dir=self.root));directory.chmod(0o700)
        self.addCleanup(shutil.rmtree,directory);leaf=directory/'leaf';leaf.write_bytes(raw);leaf.chmod(mode);return leaf

    def test_complete_reads_match_original_types_values_and_fresh_replacements(self):
        service,binding,*_=self.loaded.modules;kernel=self.loaded.kernel;leaf=self.leaf();a=self.adapter()
        expected=(service.root_file(leaf),binding.private_file(leaf,0),service.read_bytes(leaf),kernel._read(leaf))
        with a.installed():
            actual=(service.root_file(leaf),binding.private_file(leaf,0),service.read_bytes(leaf),kernel._read(leaf))
            self.assertEqual(actual,expected);self.assertEqual(tuple(type(x) for x in actual),(tuple,tuple,bytes,str))
            leaf.write_bytes(b'changed');self.assertEqual(service.read_bytes(leaf),b'changed')
            self.assertEqual(binding.private_file(leaf,0)[1],b'changed');self.assertEqual(kernel._read(leaf),'changed')
            leaf.unlink();leaf.write_bytes(b'replaced');leaf.chmod(0o600)
            self.assertNotEqual(service.root_file(leaf),expected[0])
        self.assertGreaterEqual(self.loaded.native.read_counts()['read'],8)
        self.assertTrue(all(a.calls[name]>0 for name in probe.READ_FAMILIES));self.assertFalse(any(a.fallbacks.values()))
        self.assertTrue(a.restored());self.loaded.validate()

    def test_distinct_empty_size_ascii_and_executable_predicates_match(self):
        service,binding,*_=self.loaded.modules;kernel=self.loaded.kernel;leaf=self.leaf();a=self.adapter()
        def outcomes():
            result=[]
            for fn,args,kwargs in ((service.root_file,(leaf,2),{}),(service.root_file,(leaf,),{'executable':True}),
                    (binding.private_file,(leaf,0,2),{}),(service.read_bytes,(leaf,2),{}),(kernel._read,(leaf,2),{})):
                try:result.append(('value',fn(*args,**kwargs)))
                except BaseException as error:result.append((type(error),str(error)))
            return result
        baseline=outcomes()
        with a.installed():self.assertEqual(outcomes(),baseline)
        leaf.write_bytes(b'')
        self.assertEqual(service.read_bytes(leaf),b'')
        with a.installed():
            self.assertEqual(service.read_bytes(leaf),b'')
            with self.assertRaises(service.ServiceRefused):service.root_file(leaf)
            with self.assertRaises(binding.BindingRefused):binding.private_file(leaf,0)
            with self.assertRaises(kernel.DatabaseRefused):kernel._read(leaf)
        leaf.write_bytes(b'\xff')
        with a.installed(),self.assertRaises(UnicodeDecodeError):kernel._read(leaf)
        self.assertFalse(any(a.fallbacks.values()));self.assertTrue(a.restored())

    def test_link_owner_mode_and_missing_path_refusals_match_without_descriptor_leaks(self):
        service,binding,*_=self.loaded.modules;leaf=self.leaf();a=self.adapter()
        def signature(fn,*args):
            try:return ('value',fn(*args))
            except BaseException as error:return type(error),getattr(error,'errno',None),getattr(error,'filename',None),str(error)
        def compare(path,uid=0):
            baseline=(signature(service.root_file,path),signature(binding.private_file,path,uid))
            descriptors=len(os.listdir('/proc/self/fd'))
            with a.installed():self.assertEqual((signature(service.root_file,path),signature(binding.private_file,path,uid)),baseline)
            self.assertEqual(len(os.listdir('/proc/self/fd')),descriptors)
        compare(leaf.with_name('missing'))
        link=leaf.with_name('symlink');link.symlink_to(leaf);compare(link)
        hard=leaf.with_name('hardlink');os.link(leaf,hard);compare(leaf);hard.unlink()
        leaf.chmod(0o622);compare(leaf);leaf.chmod(0o400);compare(leaf)
        leaf.chmod(0o600);os.chown(leaf,65503,1000);compare(leaf,0);compare(leaf,65503)
        self.assertFalse(any(a.fallbacks.values()));self.assertTrue(a.restored())

    def test_real_read_error_closes_descriptor_and_preserves_oserror(self):
        service=self.loaded.modules[0];kernel=self.loaded.kernel;a=self.adapter()
        # Opening a directory is allowed by the raw roles, then the original
        # buffered constructor refuses it. Both owners must release the FD.
        path=self.leaf().parent
        for owner,name in ((service,'read_bytes'),(kernel,'_read')):
            try:getattr(owner,name)(path)
            except OSError as error:expected=(type(error),error.errno)
            else:self.fail('original directory read unexpectedly passed')
            before=len(os.listdir('/proc/self/fd'))
            with a.installed(),self.assertRaises(OSError) as caught:getattr(owner,name)(path)
            self.assertEqual((type(caught.exception),caught.exception.errno),expected)
            self.assertEqual(len(os.listdir('/proc/self/fd')),before)
        self.assertFalse(any(a.fallbacks.values()))

    def test_restored_mtime_still_poisons_original_capture(self):
        service=self.loaded.modules[0];leaf=self.leaf();a=self.adapter()
        captured=service._CapturedRootFiles()
        with a.installed():
            captured.read(leaf);captured.frozen=True;before=leaf.stat()
            leaf.write_bytes(b'one');os.utime(leaf,ns=(before.st_atime_ns,before.st_mtime_ns))
            with self.assertRaises(service.ServiceRefused):captured.read(leaf)
        self.assertFalse(captured.usable)
        self.assertFalse(any(a.fallbacks.values()))

    def test_native_api_replacement_is_rejected_before_observations_and_code_custody(self):
        service=self.loaded.modules[0];leaf=self.leaf();a=self.adapter();before=self.loaded.native.read_counts()
        original=self.loaded.native.read_file
        try:
            with a.installed():
                self.loaded.native.read_file=Mock(side_effect=AssertionError('replaced native called'))
                self.assertEqual(service.read_bytes(leaf),b'one')
                self.loaded.native.read_file.assert_not_called()
                with self.assertRaises(ValueError):self.loaded.validate()
        finally:self.loaded.native.read_file=original
        self.assertEqual(self.loaded.native.read_counts(),before);self.loaded.validate()

    def test_sdk_hook_and_source_code_mutation_fall_back_before_native(self):
        service=self.loaded.modules[0];a=self.adapter();leaf=self.leaf();failure=KeyboardInterrupt('original hook')
        before=self.loaded.native.read_counts()
        opened=[];original_open=os.open
        def tracked(*args,**kwargs):
            fd=original_open(*args,**kwargs);opened.append(fd);return fd
        # The deliberately replaced original fdopen owns no descriptor. Record
        # and close only these test-owned opens after exercising its error.
        try:
            with a.installed(),patch.object(os,'open',tracked),patch.object(os,'fdopen',Mock(side_effect=failure)),self.assertRaises(KeyboardInterrupt) as caught:
                service.read_bytes(leaf)
        finally:
            for fd in opened:os.close(fd)
        self.assertIs(caught.exception,failure);self.assertEqual(self.loaded.native.read_counts(),before)
        fn=os.fdopen;code=fn.__code__
        def altered(fd,mode='r',buffering=-1,encoding=None,*args,**kwargs):raise KeyboardInterrupt('code mutation')
        opened.clear()
        try:
            with a.installed(),patch.object(os,'open',tracked):
                fn.__code__=altered.__code__
                with self.assertRaises(ValueError):self.loaded.validate()
                with self.assertRaises(KeyboardInterrupt):service.read_bytes(leaf)
        finally:
            fn.__code__=code
            for fd in opened:os.close(fd)
        self.assertEqual(self.loaded.native.read_counts(),before);self.loaded.validate()

    def test_native_preparation_matches_python_tables_and_rejects_descriptors_before_observations(self):
        generation=self.loaded.modules[2];leaf=self.leaf();root=leaf.parent;a=self.adapter()
        plan=generation._PersistentFingerprintPlan.__new__(generation._PersistentFingerprintPlan)
        plan.uid=0;plan.entries=((root,frozenset({'leaf'})),);plan.directories=();plan.files=();plan.parents=();plan.machine=leaf
        expected=probe.metadata.Adapter.plan_arguments(a,plan);before=self.loaded.native.counts()
        self.assertEqual(a.plan_arguments(plan),expected)
        custody,_leaf,_other=self.custody()
        self.assertEqual(a.custody_arguments(custody),probe.metadata.Adapter.custody_arguments(a,custody))
        self.assertEqual(self.loaded.native.counts(),before)
        for field in ('uid','entries','machine'):
            with patch.object(type(plan),field,property(lambda _:self.fail('descriptor executed')),create=True):
                with self.assertRaises(probe.Unsupported):a.plan_arguments(plan)
        bad=object();plan.entries=((bad,frozenset()),)
        with self.assertRaises(probe.Unsupported):a.plan_arguments(plan)
        self.assertEqual(self.loaded.native.counts(),before)
        # A present retained None differs from an absent retained descriptor.
        held=custody.retained[_leaf]
        try:
            custody.retained[_leaf]=None
            with self.assertRaises(probe.Unsupported):a.custody_arguments(custody)
        finally:custody.retained[_leaf]=held

    def test_preparation_reads_builtin_object_ancestor_namespace_without_observations(self):
        owner=self.loaded.modules[2]._PersistentFingerprintPlan
        self.assertIs(owner.__mro__[-1],object)
        plan=owner.__new__(owner);plan.uid=0;plan.entries=();plan.directories=()
        plan.files=();plan.parents=();plan.machine=Path('/synthetic-not-observed')
        before=self.loaded.native.counts();counts=self.loaded.native.read_counts()
        self.assertEqual(self.loaded.native.prepare_tables(0,plan,owner,type(plan.machine)),
            (0,(),(),'/synthetic-not-observed',(),()))
        self.assertEqual(self.loaded.native.counts(),before)
        self.assertEqual(self.loaded.native.read_counts(),{'read':counts['read'],'prepare':counts['prepare']+1})

    def test_complete_read_preflight_and_audit_refusal_leave_counts_and_descriptors_bounded(self):
        native=self.loaded.native;before=native.read_counts();leaf=self.leaf()
        self.assertIs(native.read_file(0,str(leaf),('bad',object()),0,8,False,io.open,io.BufferedReader),NotImplemented)
        self.assertIs(native.prepare_tables(0,object(),object,Path),NotImplemented)
        self.assertEqual(native.read_counts(),before)
        # Audit hooks cannot be removed. A subprocess performs event-order and
        # exception-identity checks without affecting later tests or staging.
        import subprocess
        script='''import importlib.util,io,os,sys
spec=importlib.util.spec_from_file_location('_native_metadata_probe',sys.argv[1]);n=importlib.util.module_from_spec(spec);spec.loader.exec_module(n)
leaf=sys.argv[2];events=[];enabled=False;failure=KeyboardInterrupt('audit');refuse=False
def audit(event,args):
 if enabled and event=='open':
  events.append(args)
  if refuse and len(events)==2:raise failure
sys.addaudithook(audit)
def original():
 fd=os.open(leaf,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 with os.fdopen(fd,'rb') as source:return source.read(9)
enabled=True
assert original()==b'one';expected=list(events);events.clear()
assert n.read_file(2,leaf,(),0,8,False,io.open,io.BufferedReader)[0]==b'one'
assert len(events)==len(expected)==2
assert events[0]==expected[0] and events[1][1:]==expected[1][1:]
events.clear();refuse=True;before=len(os.listdir('/proc/self/fd'))
try:n.read_file(2,leaf,(),0,8,False,io.open,io.BufferedReader)
except KeyboardInterrupt as error:assert error is failure
else:raise AssertionError('audit refusal missed')
assert len(os.listdir('/proc/self/fd'))==before
'''
        subprocess.run([sys.executable,'-X','faulthandler','-B','-c',script,
            str(self.root/probe.metadata.extension_name()),str(leaf)],check=True,timeout=15)


if __name__=='__main__':unittest.main(verbosity=2)
