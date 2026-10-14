"""Read-only composition tests with explicit Root/observer stand-ins."""
import os
import threading
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from native_root_controller import (RootControllerRefused,_RootObservationPass,
    _within_root_observation_pass)


class _Observer:
    def __init__(self):
        self.owner=(os.getpid(),threading.get_ident());self.usable=True
        self.calls=0;self.value={'original':True,'stage_effect_authorized':False}

    @_within_root_observation_pass
    def check(self):
        self.calls+=1
        if not self.usable:raise RootControllerRefused('Fixture observer unavailable')
        return dict(self.value)


class RootObservationPassTest(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        for name in ('getuid','geteuid','getgid','getegid'):
            self.stack.enter_context(patch.object(os,name,return_value=0,create=True))

    def test_standalone_checks_remain_fresh_without_an_active_pass(self):
        value=_Observer();value.check();value.check();self.assertEqual(value.calls,2)

    def test_duplicate_dependency_reads_share_only_the_current_pass(self):
        value=_Observer()
        with _RootObservationPass():
            first=value.check();first['original']='caller mutation'
            self.assertEqual(value.check(),{'original':True,'stage_effect_authorized':False})
        self.assertEqual(value.calls,1)
        with _RootObservationPass():value.check()
        value.check();self.assertEqual(value.calls,3)

    def test_changed_resource_is_observed_by_the_separate_final_pass(self):
        value=_Observer()
        with _RootObservationPass():value.check();value.check()
        value.value['original']=False
        with _RootObservationPass():self.assertIs(value.check()['original'],False)
        self.assertEqual(value.calls,2)

    def test_original_observer_loss_cannot_return_a_cached_success(self):
        value=_Observer()
        with self.assertRaises(RootControllerRefused):
            with _RootObservationPass() as current:
                value.check();value.usable=False
                with self.assertRaises(RootControllerRefused):value.check()
                value.usable=True
                with self.assertRaises(RootControllerRefused):value.check()
                self.assertTrue(current.failed);self.assertEqual(current.values,{})

    def test_different_observers_never_share_results(self):
        first=_Observer();second=_Observer();second.value['original']=False
        with _RootObservationPass():
            self.assertTrue(first.check()['original']);self.assertFalse(second.check()['original'])
        self.assertEqual((first.calls,second.calls),(1,1))

    def test_nested_or_reused_pass_refuses_and_retains_the_original_context(self):
        current=_RootObservationPass();value=_Observer()
        with current:
            with self.assertRaises(RootControllerRefused):
                with _RootObservationPass():pass
            value.check()
        with self.assertRaises(RootControllerRefused):
            with current:pass
        value.check();self.assertEqual(value.calls,2)

    def test_ordinary_identity_refuses_before_dependency_access(self):
        value=_Observer()
        with patch.object(os,'getuid',return_value=1000):
            with self.assertRaises(RootControllerRefused):
                with _RootObservationPass():value.check()
        self.assertEqual(value.calls,0)

    def test_foreign_thread_never_inherits_the_owner_cache(self):
        value=_Observer();counts=[]
        with _RootObservationPass():
            value.check()
            thread=threading.Thread(target=lambda:(value.check(),counts.append(value.calls)))
            thread.start();thread.join(timeout=2);self.assertFalse(thread.is_alive())
            value.check()
        # The stand-in has no service/thread authority. It verifies only that
        # another thread cannot receive this thread's cached observation.
        self.assertEqual(counts,[2]);self.assertEqual(value.calls,2)

    def test_interruption_discards_every_retained_result(self):
        value=_Observer();current=_RootObservationPass()
        with self.assertRaises(KeyboardInterrupt):
            with current:value.check();raise KeyboardInterrupt('Fixture interruption')
        self.assertFalse(current.active);self.assertEqual(current.values,{})
        value.check();self.assertEqual(value.calls,2)

    def test_observer_bound_refuses_and_discards_results_before_returning_success(self):
        observers=[_Observer() for _ in range(33)]
        with self.assertRaises(RootControllerRefused):
            with _RootObservationPass() as current:
                for value in observers:value.check()
        self.assertEqual(current.values,{});self.assertFalse(current.active)
