"""Source composition with explicit Root/service/allocation/effect stand-ins."""
from contextlib import ExitStack
import copy
import os
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import native_protected_artifact as protected
import native_root_artifact_dispatch as dispatch
import native_root_controller as controller
from resource_generations import canonical


class SharedControllerObservationTest(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        for name in ('getuid','geteuid','getgid','getegid'):
            self.stack.enter_context(patch.object(os,name,return_value=0,create=True))
        self.installation='12345678-1234-4234-8234-123456789abc'
        self.owner=(os.getpid(),threading.get_ident())
        original=controller.NativeRootControllerObservation.__new__(controller.NativeRootControllerObservation)
        original.owner=self.owner;original.usable=True;original.installation=self.installation
        original.seal={'uid':1000,'gid':1000};original.raw=canonical(original.seal)
        original.directory=Path('/synthetic/controller');original.directory_custody=('original',)
        original.original={'installation':self.installation,'original_controller':True,'stage_effect_authorized':False}
        original._service=Mock(side_effect=lambda:copy.deepcopy(original.original));original._policy=Mock();original.files=Mock()
        self.original=original
        self.stack.enter_context(patch.object(controller,'private_directory',return_value=original.directory_custody))
        allocation=dispatch.NativeRootArtifactPolicyAllocation.__new__(dispatch.NativeRootArtifactPolicyAllocation)
        allocation.owner=self.owner;allocation.usable=True;allocation.installation=self.installation
        allocation.exclusion=SimpleNamespace(live=SimpleNamespace(lifecycle=SimpleNamespace(controller=original)))
        self.allocation=allocation
        value=dispatch._ObservedArtifactStage.__new__(dispatch._ObservedArtifactStage)
        value.owner=self.owner;value.installation=self.installation;value.allocation=allocation
        value.allocation_original={'original':True};value.usable=True
        self.value=value
        self.new=self.stack.enter_context(patch.object(protected,'NativeRootControllerObservation'))

    def select(self):
        self.value.controller=self.value._controller_observation()
        return self.value.controller

    def compose(self,body=None):
        self.select()
        self.allocation.check=Mock(side_effect=lambda:(self.original.check(),dict(self.value.allocation_original))[1])
        self.allocation.close=Mock(side_effect=self.original.close)
        self.value.close=Mock(side_effect=self.original.close)
        def checked(value):
            observed=value.controller.check()
            if body is not None:body()
            return {'artifact_staged':False,'controller':observed}
        self.stage=self.stack.enter_context(patch.object(protected.NativeProtectedArtifactStage,'check',autospec=True,side_effect=checked))

    def test_standalone_stage_still_constructs_its_own_observer(self):
        value=protected.NativeProtectedArtifactStage.__new__(protected.NativeProtectedArtifactStage)
        value.installation=self.installation
        self.assertIs(value._controller_observation(),self.new.return_value)
        self.new.assert_called_once_with(self.installation)

    def test_dispatch_selects_only_the_same_original_observer(self):
        self.assertIs(self.select(),self.original);self.new.assert_not_called()

    def test_ordinary_identity_refuses_before_allocation_access(self):
        del self.value.allocation
        with patch.object(os,'getuid',return_value=1000):
            with self.assertRaises(dispatch.RootArtifactDispatchRefused):self.select()
        self.new.assert_not_called()

    def test_foreign_process_or_thread_refuses_before_allocation_access(self):
        del self.value.allocation
        for owner in [(os.getpid()+1,self.owner[1]),(self.owner[0],self.owner[1]+1)]:
            self.value.owner=owner
            with self.subTest(owner=owner),self.assertRaises(dispatch.RootArtifactDispatchRefused):self.select()
        self.new.assert_not_called()

    def test_caller_map_or_foreign_allocation_owner_refuses(self):
        self.value.allocation={'controller':self.original}
        with self.assertRaises(dispatch.RootArtifactDispatchRefused):self.select()
        self.value.allocation=self.allocation;self.allocation.owner=(os.getpid()+1,self.owner[1])
        with self.assertRaises(dispatch.RootArtifactDispatchRefused):self.select()
        self.new.assert_not_called()

    def test_closed_allocation_or_observer_refuses_without_replacement(self):
        self.allocation.usable=False
        with self.assertRaises(dispatch.RootArtifactDispatchRefused):self.select()
        self.allocation.usable=True;self.original.usable=False
        with self.assertRaises(dispatch.RootArtifactDispatchRefused):self.select()
        self.new.assert_not_called()

    def test_foreign_installation_owner_or_observer_map_refuses(self):
        self.allocation.installation='foreign'
        with self.assertRaises(dispatch.RootArtifactDispatchRefused):self.select()
        self.allocation.installation=self.installation;self.original.installation='foreign'
        with self.assertRaises(dispatch.RootArtifactDispatchRefused):self.select()
        self.original.installation=self.installation;self.original.owner=(os.getpid()+1,self.owner[1])
        with self.assertRaises(dispatch.RootArtifactDispatchRefused):self.select()
        self.allocation.exclusion.live.lifecycle.controller={'authorized':True}
        with self.assertRaises(dispatch.RootArtifactDispatchRefused):self.select()
        self.new.assert_not_called()

    def test_each_effect_guard_keeps_two_fresh_original_service_observations(self):
        self.compose()
        self.value.check();self.value.check()
        self.assertEqual(self.original._service.call_count,4)
        self.assertEqual(self.allocation.check.call_count,4);self.assertEqual(self.stage.call_count,2)
        self.new.assert_not_called()

    def test_original_observer_loss_during_initial_pass_refuses_final_guard(self):
        self.compose(lambda:setattr(self.original,'usable',False))
        with self.assertRaises(dispatch.RootArtifactDispatchRefused):self.value.check()
        self.assertFalse(self.original.usable)
        self.value.close.assert_called_once();self.allocation.close.assert_called_once();self.new.assert_not_called()

    def test_stage_close_invalidates_shared_observer_and_retains_original_scope(self):
        self.select();scope=copy.deepcopy(self.original.original)
        protected.NativeProtectedArtifactStage.close(self.value)
        self.assertFalse(self.value.usable);self.assertFalse(self.original.usable)
        self.assertEqual(self.original.original,scope);self.original.files.close.assert_called_once()
        self.assertIs(self.allocation.exclusion.live.lifecycle.controller,self.original)
        self.new.assert_not_called()


if __name__=='__main__':unittest.main()
