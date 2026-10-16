#!/usr/bin/env python3
"""Protocol, restoration and actual same-connection tests for the hosted probe."""
import ctypes
import io
import os
from pathlib import Path, PurePosixPath
import shutil
import signal
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
import selected_bus_probe as probe


class AdapterTest(unittest.TestCase):
    def setUp(self):
        class Library:pass
        self.Library = Library
        class Owner:
            usable=True
            def __init__(self):self.library=Library();self.bus=ctypes.c_void_p(1)
            def _read_selected(self,path,properties):return {'S':'fresh'}
        self.Owner = Owner;self.original = vars(Owner)['_read_selected']
        self.module = SimpleNamespace(ReadOnlySystemdProperties=Owner,require=probe.require)
        self.native = SimpleNamespace(bind_owner=Mock(side_effect=lambda owner:object()),
            read_selected=Mock(return_value={'S':'fresh'}))
        self.adapter = probe.Adapter(self.module,self.native)
        self.addCleanup(self.adapter.close)
        self.library_patch = patch.object(probe.ctypes,'CDLL',Library)
        self.library_patch.start();self.addCleanup(self.library_patch.stop)
        class Stage:
            usable=True;state='ready'
            def __init__(stage):stage.subject=Owner();stage.allocation=SimpleNamespace(usable=True,close=Mock())
            def check(stage):return stage.subject._read_selected('/fixed',(('interface','S','s'),))
            def close(stage):stage.usable=False
        self.Stage = Stage;self.stage = Stage()

    def test_binds_original_owner_once_but_observes_each_time_without_results_cache(self):
        with self.adapter.installed():
            for _ in range(3):self.assertEqual(self.stage.check(),{'S':'fresh'})
        self.native.bind_owner.assert_called_once_with(self.stage.subject)
        self.assertEqual(self.native.read_selected.call_count,3)
        self.assertFalse(self.stage.subject._selected_active)
        self.assertIs(vars(self.Owner)['_read_selected'],self.original)
        self.adapter.close();self.assertFalse(self.adapter.bindings)
        self.assertTrue(self.stage.subject.usable)

    def test_model_fallback_is_once_and_never_enters_native(self):
        subject=self.Owner();subject.library=object()
        original=Mock(return_value={'S':'model'});self.adapter.original=original
        self.assertEqual(self.adapter.read(subject,'/fixed',()),{'S':'model'})
        original.assert_called_once_with(subject,'/fixed',())
        self.native.bind_owner.assert_not_called();self.native.read_selected.assert_not_called()

    def test_refusal_or_interruption_restores_method_and_active_flag_without_retry(self):
        for value in (None,KeyboardInterrupt('original')):
            self.native.read_selected.reset_mock()
            self.native.read_selected.side_effect=value if isinstance(value,BaseException) else None
            self.native.read_selected.return_value=value
            with self.subTest(value=type(value).__name__),self.assertRaises((ValueError,KeyboardInterrupt)):
                with self.adapter.installed():self.stage.check()
            self.assertFalse(self.stage.subject._selected_active)
            self.assertIs(vars(self.Owner)['_read_selected'],self.original)
            self.assertEqual(self.native.read_selected.call_count,1)

    def test_reentrant_and_ninth_connection_refuse_without_more_native_calls(self):
        self.stage.subject._selected_active=True
        with self.assertRaises(ValueError):self.adapter.read(self.stage.subject,'/fixed',())
        self.native.bind_owner.assert_not_called();self.stage.subject._selected_active=False
        with self.adapter.installed():
            for _ in range(8):self.Owner()._read_selected('/fixed',(('i','S','s'),))
            with self.assertRaises(ValueError):self.Owner()._read_selected('/fixed',(('i','S','s'),))
        self.assertEqual(len(self.adapter.bindings),8);self.assertEqual(self.native.bind_owner.call_count,8)

    def test_whole_guard_pairs_alternate_and_restore_before_measurements(self):
        sequence=[];events=[];original_guard=self.Stage.check
        def check(stage):
            sequence.append(vars(self.Owner)['_read_selected'] is self.original)
            events.append('guard');return original_guard(stage)
        self.Stage.check=check
        class Measurements:
            def __enter__(inner):events.append('enter')
            def __exit__(inner,*_):events.append('exit')
        with probe.AtFirstGuard(self.module,self.native,self.Stage,Measurements()) as trial:self.stage.check()
        self.assertEqual(sequence[:40],[value for index in range(20) for value in
            ((True,False) if index%2==0 else (False,True))])
        self.assertEqual(events,['guard']*40+['enter','guard','exit'])
        self.assertEqual(sequence[-1],True);self.assertIs(self.Stage.check,check)
        self.assertEqual(len(trial.result['pairs']),20)
        self.assertEqual(trial.result['native_selected_calls'],20)
        self.assertEqual(trial.result['original_bus_bindings'],1)
        self.assertFalse(trial.result['production_adopted']);self.assertFalse(trial.result['observation_results_retained'])

    def test_comparison_mismatch_and_interruption_poison_both_owners_and_keep_original_error(self):
        for failure in (None,KeyboardInterrupt('original')):
            stage=self.Stage();stage.close=Mock(side_effect=RuntimeError('cleanup'))
            stage.allocation.close=Mock(side_effect=RuntimeError('cleanup'))
            self.native.read_selected.side_effect=failure
            self.native.read_selected.return_value={'S':'changed'}
            with self.subTest(failure=type(failure).__name__),self.assertRaises((ValueError,KeyboardInterrupt)) as caught:
                with probe.AtFirstGuard(self.module,self.native,self.Stage,Mock()):stage.check()
            if failure is not None:self.assertIs(caught.exception,failure)
            self.assertFalse(stage.usable);self.assertFalse(stage.allocation.usable)
            stage.close.assert_called_once();stage.allocation.close.assert_called_once()
            self.assertIs(vars(self.Owner)['_read_selected'],self.original)

    def test_unready_stage_and_existing_profiler_refuse_before_native(self):
        self.stage.state='staged'
        with self.assertRaises(ValueError):probe.compare_guard(self.module,self.native,self.Stage.check,self.stage)
        self.stage.state='ready'
        with patch.object(probe.sys,'getprofile',return_value=object()),self.assertRaises(ValueError):
            probe.compare_guard(self.module,self.native,self.Stage.check,self.stage)
        self.native.bind_owner.assert_not_called()


@unittest.skipUnless(sys.platform=='linux' and getattr(os,'geteuid',lambda:-1)()==0,
    'Compiled hosted probe and actual Root Linux required')
class HostedProtocolTest(unittest.TestCase):
    fields=[('org.fixture.Interface',name,signature) for name,signature in [('S','s'),('U','u'),('B','b'),('A','as')]]

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'deployment'))
        import native_systemd_properties
        cls.module=native_systemd_properties
        cls.namespace=tempfile.TemporaryDirectory(prefix='gitgood-selected-bus-',dir='/var/lib')
        cls.addClassCleanup(cls.namespace.cleanup);cls.root=Path(cls.namespace.name);cls.root.chmod(0o700)
        source=Path(__file__).resolve().parent;built=source.parents[1]/'.gitgood/selected-bus-probe'
        for path in [source/'selected-bus-probe.c',source/'selected_bus_probe.py',built/probe.extension_name(),
                source/'selected-bus-fixture.c',built/'selected-bus-fixture.so']:
            destination=cls.root/path.name;shutil.copyfile(path,destination);destination.chmod(0o644)
        cls.native,cls.hashes=probe.load_native(cls.root)
        cls.library=ctypes.CDLL(str(cls.root/'selected-bus-fixture.so'))
        cls.library.fixture_reset.argtypes=[ctypes.c_int];cls.library.fixture_reset.restype=None
        cls.library.fixture_bus.argtypes=[];cls.library.fixture_bus.restype=ctypes.c_void_p
        cls.library.fixture_stat.argtypes=[ctypes.c_int];cls.library.fixture_stat.restype=ctypes.c_int
        cls.library.sd_bus_flush_close_unref.argtypes=[ctypes.c_void_p]
        cls.library.sd_bus_flush_close_unref.restype=ctypes.c_void_p

    def subject(self,mode=0):
        self.library.fixture_reset(mode)
        subject=self.module.ReadOnlySystemdProperties.__new__(self.module.ReadOnlySystemdProperties)
        subject.library=self.library;subject.bus=ctypes.c_void_p(self.library.fixture_bus());subject.usable=True
        subject.path=PurePosixPath('/fixture/library');subject.original=('captured',)
        subject.files=SimpleNamespace(usable=True,read=Mock(return_value=(subject.original,None)))
        return subject

    def snapshot(self):
        return {'queued':self.library.fixture_stat(0),'processes':self.library.fixture_stat(1),
            'waits':self.library.fixture_stat(2),'request_unrefs':self.library.fixture_stat(3),
            'reply_unrefs':self.library.fixture_stat(4),'closed':self.library.fixture_stat(5),
            'wire_ok':self.library.fixture_stat(6),'cancel_at_close':self.library.fixture_stat(40),
            'cancelled':[self.library.fixture_stat(8+index) for index in range(self.library.fixture_stat(7))]}

    def observe(self,subject,fields=None):
        adapter=probe.Adapter(self.module,self.native)
        try:
            with adapter.installed():return subject._get_many('/fixture',self.fields if fields is None else fields)
        finally:adapter.close()

    def assert_lost(self,subject,queued=4,requests=4):
        snapshot=self.snapshot()
        self.assertFalse(subject.usable);self.assertFalse(subject.files.usable);self.assertFalse(subject.bus)
        self.assertFalse(subject._selected_active);self.assertEqual(snapshot['closed'],1)
        self.assertEqual(snapshot['cancelled'],list(range(queued,0,-1)))
        self.assertEqual(snapshot['cancel_at_close'],queued)
        self.assertEqual(snapshot['request_unrefs'],requests);self.assertEqual(snapshot['reply_unrefs'],0)
        with self.assertRaises(self.module.BusRefused):subject._get_many('/fixture',self.fields)
        self.assertEqual(self.snapshot(),snapshot)

    def test_exact_typed_values_reverse_completion_fresh_batches_and_borrowed_reply_ownership(self):
        subject=self.subject();adapter=probe.Adapter(self.module,self.native)
        with adapter.installed():
            self.assertEqual(subject._get_many('/fixture',self.fields),{'S':'live','U':'4294967295','B':'yes','A':'live live'})
        self.assertEqual(subject.files.read.call_count,2)
        self.assertEqual(self.snapshot()['cancelled'],[4,3,2,1]);self.assertEqual(self.snapshot()['reply_unrefs'],0)
        self.assertEqual(self.snapshot()['wire_ok'],1);adapter.close()
        self.assertTrue(subject.usable);self.assertTrue(subject.bus);self.assertEqual(self.snapshot()['closed'],0)
        self.library.fixture_reset(27)
        self.assertEqual(self.observe(subject)['B'],'no')
        self.assertEqual(self.snapshot()['queued'],4);subject.close()

    def test_malformed_reply_types_containers_ascii_bounds_and_slots_never_publish_partial_result(self):
        for mode in [1,2,3,4,5,6,7,8,9,10,11,12,23,24,25,28,29]:
            subject=self.subject(mode)
            with self.subTest(mode=mode),self.assertRaises(self.module.BusRefused):self.observe(subject)
            self.assert_lost(subject)

    def test_exact_string_array_and_boolean_boundaries_are_supported(self):
        for mode,name,expected in [(26,'S','x'*2048),(30,'A',' '.join(['live']*32)),(31,'A',''),(27,'B','no')]:
            subject=self.subject(mode)
            with self.subTest(mode=mode):self.assertEqual(self.observe(subject)[name],expected)
            subject.close()

    def test_partial_queue_request_and_async_errors_cancel_only_owned_slots(self):
        for mode,queued,requests in [(13,2,2),(20,1,2),(21,1,2)]:
            subject=self.subject(mode)
            with self.subTest(mode=mode),self.assertRaises(self.module.BusRefused):self.observe(subject)
            self.assert_lost(subject,queued,requests)
        subject=self.subject(22)
        with self.assertRaises(self.module.BusRefused):self.observe(subject)
        self.assert_lost(subject,0,1)

    def test_process_wait_and_4096_pump_limit_refuse_without_reconnection(self):
        for mode in (14,15,16):
            subject=self.subject(mode)
            with self.subTest(mode=mode),self.assertRaises(self.module.BusRefused):self.observe(subject)
            self.assert_lost(subject)
            if mode==16:self.assertEqual(self.snapshot()['processes'],4096)
            if mode==15:self.assertEqual(self.snapshot()['waits'],1)

    def test_original_five_second_deadline_is_not_extended(self):
        import time
        subject=self.subject(17);started=time.monotonic()
        with self.assertRaises(self.module.BusRefused):self.observe(subject)
        elapsed=time.monotonic()-started
        self.assertGreaterEqual(elapsed,4.9);self.assertLess(elapsed,7)
        self.assertEqual(self.snapshot()['waits'],1);self.assert_lost(subject)

    def test_original_signal_exception_identity_and_reverse_cleanup_before_close(self):
        subject=self.subject(18);failure=KeyboardInterrupt('Owned fixture interruption')
        def interrupted(*_):raise failure
        original=signal.signal(signal.SIGINT,interrupted)
        try:
            with self.assertRaises(KeyboardInterrupt) as caught:self.observe(subject)
        finally:signal.signal(signal.SIGINT,original)
        self.assertIs(caught.exception,failure);self.assert_lost(subject)

    def test_library_custody_before_and_after_native_batch_is_still_original(self):
        subject=self.subject();subject.files.read.return_value=(('replaced',),None)
        with self.assertRaises(self.module.BusRefused):self.observe(subject)
        self.assertEqual(self.snapshot()['queued'],0);self.assertFalse(subject.usable)
        subject=self.subject();subject.files.read.side_effect=[(subject.original,None),(('replaced',),None)]
        with self.assertRaises(self.module.BusRefused):self.observe(subject)
        self.assert_lost(subject)

    def test_capsule_rejects_changed_bus_handle_library_thread_or_usable_owner(self):
        for mode in ('bus','handle','library','usable','thread'):
            subject=self.subject();binding=self.native.bind_owner(subject);self.assertIsNotNone(binding)
            original_handle=self.library._handle
            try:
                if mode=='bus':subject.bus=ctypes.c_void_p(123)
                elif mode=='handle':self.library._handle=original_handle+1
                elif mode=='library':subject.library=ctypes.CDLL(str(self.root/'selected-bus-fixture.so'))
                elif mode=='usable':subject.usable=False
                if mode=='thread':
                    result=[];thread=threading.Thread(target=lambda:result.append(self.native.read_selected(binding,'/fixture',tuple(self.fields))))
                    thread.start();thread.join(timeout=5);self.assertFalse(thread.is_alive());self.assertEqual(result,[None])
                else:self.assertIsNone(self.native.read_selected(binding,'/fixture',tuple(self.fields)))
                self.assertEqual(self.snapshot()['queued'],0)
            finally:self.library._handle=original_handle

    def test_native_entry_rejects_out_of_domain_inputs_before_queueing(self):
        subject=self.subject();binding=self.native.bind_owner(subject)
        for path,fields in [('relative',tuple(self.fields)),('/x\0y',tuple(self.fields)),('/'+'x'*1024,tuple(self.fields)),
                ('/fixture',()),('/fixture',self.fields),('/fixture',tuple(self.fields)*9),
                ('/fixture',(('i','S','d'),)),('/fixture',(('i','S','s'),('j','S','u'))),
                ('/fixture',(('i\0','S','s'),)),('/fixture',(('i','x'*257,'s'),))]:
            with self.subTest(path=path[:10],count=len(fields)):
                self.assertIsNone(self.native.read_selected(binding,path,fields))
        self.assertEqual(self.snapshot()['queued'],0)

    def test_same_original_systemd_connection_matches_twenty_baseline_batches(self):
        subject=self.module.ReadOnlySystemdProperties();self.addCleanup(subject.close)
        import test_native_systemd_properties as original_tests
        path=original_tests.ActualSystemdInterfaceTest.path
        fields=[(interface,name,signature) for interface,selected in original_tests.ActualSystemdInterfaceTest.fields
            for name,signature in selected.items()]
        original=self.module.ReadOnlySystemdProperties._read_selected
        identity=(subject.library,subject.library._handle,subject.bus,subject.bus.value,os.getpid(),threading.get_ident())
        adapter=probe.Adapter(self.module,self.native)
        try:
            for _ in range(20):
                expected=subject._get_many(path,fields)
                with adapter.installed():actual=subject._get_many(path,fields)
                self.assertEqual(actual,expected)
                self.assertEqual((subject.library,subject.library._handle,subject.bus,subject.bus.value,os.getpid(),threading.get_ident()),identity)
            self.assertEqual(adapter.calls,20);self.assertEqual(len(adapter.bindings),1)
        finally:adapter.close()
        self.assertIs(self.module.ReadOnlySystemdProperties._read_selected,original)
        print('native_selected_same_connection_pairs=20',flush=True)

    def test_original_33_systemd_cases_with_native_adapter_and_model_fallback(self):
        suite=unittest.defaultTestLoader.loadTestsFromName('test_native_systemd_properties')
        adapter=probe.Adapter(self.module,self.native);stream=io.StringIO()
        try:
            with adapter.installed():result=unittest.TextTestRunner(stream=stream).run(suite)
        finally:adapter.close()
        self.assertEqual(result.testsRun,33);self.assertFalse(result.skipped)
        self.assertTrue(result.wasSuccessful(),stream.getvalue())
        self.assertGreater(adapter.calls,0);self.assertGreater(adapter.fallbacks,0)
        print('native_selected_original_systemd_cases=33',flush=True)


if __name__=='__main__':unittest.main(verbosity=2)
