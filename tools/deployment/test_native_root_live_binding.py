import copy
import os
import threading
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

import native_durable_binding as binding
import native_root_live_binding as root
from resource_generations import canonical
import test_resource_generations as generation_fixture


class RootBindingAdmissionTest(unittest.TestCase):
    def setUp(self):
        value = generation_fixture.ResourceGenerationRecordTest();value.setUp()
        self.scope = value.scope;self.installation = value.installation
        self.operation = '00000000-0000-4000-8000-000000000099'

    def identities(self, stack, uid):
        for name in ('getuid','geteuid','getgid','getegid'):
            stack.enter_context(patch.object(binding.os,name,return_value=uid,create=True))

    def test_public_ordinary_binding_still_refuses_root_before_shared_validation(self):
        with ExitStack() as stack:
            self.identities(stack,0)
            shared = stack.enter_context(patch.object(binding,'_persistent_identity'))
            with self.assertRaises(binding.BindingRefused):
                binding.persistent_identity('/caller',self.scope,{})
            shared.assert_not_called()

    def test_private_root_entry_refuses_ordinary_caller_before_private_files_or_database(self):
        with ExitStack() as stack:
            self.identities(stack,1000)
            shared = stack.enter_context(patch.object(binding,'_persistent_identity'))
            with self.assertRaises(binding.BindingRefused):binding._root_persistent_identity('/caller',self.scope,{})
            shared.assert_not_called()

    def test_root_namespace_replacement_refuses_before_live_observation(self):
        for namespaces in (['mnt:[999]'],[self.scope['manager']['mount_namespace'],'cgroup:[999]']):
            with ExitStack() as stack:
                self.identities(stack,0)
                stack.enter_context(patch.object(binding.os,'readlink',side_effect=namespaces))
                shared = stack.enter_context(patch.object(binding,'_persistent_identity'))
                with self.assertRaises(binding.BindingRefused):binding._root_persistent_identity('/caller',self.scope,{})
                shared.assert_not_called()

    def test_matching_root_namespaces_reuse_the_same_shared_resource_validator(self):
        cache = Mock();paths = {'python':'/fixed/python'}
        with ExitStack() as stack:
            self.identities(stack,0)
            stack.enter_context(patch.object(binding.os,'readlink',side_effect=[self.scope['manager'][name]
                for name in ('mount_namespace','cgroup_namespace')]))
            shared = stack.enter_context(patch.object(binding,'_persistent_identity',return_value={'observed':True}))
            self.assertEqual(binding._root_persistent_identity('/fixed',self.scope,paths,_executable_files=cache),{'observed':True})
            shared.assert_called_once_with('/fixed',self.scope,paths,_executable_files=cache)

    def test_uuid_only_constructor_refuses_invalid_identifier_or_non_root_before_lifecycle_reads(self):
        with patch.object(root,'NativeRootLifecycleObservation') as lifecycle:
            for identity in (None,True,'../caller',self.installation+'/'):
                with self.assertRaises(root.RootLiveBindingRefused):root.NativeRootLiveBindingObservation(identity,self.operation)
            with patch.object(root.os,'getuid',return_value=1000,create=True):
                with self.assertRaises(root.RootLiveBindingRefused):root.NativeRootLiveBindingObservation(self.installation,self.operation)
            lifecycle.assert_not_called()


class RootBindingObservationTest(unittest.TestCase):
    def view(self):
        value = root.NativeRootLiveBindingObservation.__new__(root.NativeRootLiveBindingObservation)
        value.usable = True;value.owner = (os.getpid(),threading.get_ident())
        value.lifecycle = Mock();value.executables = Mock();value.database_reader = Mock()
        value.observed_lifecycle = {'installation':'fixed','operation':'fixed-operation',
            'candidate':'a'*40,'stage':'stage','recorded_status':'running'}
        value.binding = {'private':'not returned'};value.binding_raw = canonical(value.binding)
        value.files = {'original':'metadata'};value.root = '/fixed';value.scope = {'original':'scope'}
        value.lifecycle.check.return_value = copy.deepcopy(value.observed_lifecycle)
        value.lifecycle.generation_seal = {'executables':{'python':'/fixed/python'}}
        return value

    def root_context(self, stack):
        for name in ('getuid','geteuid','getgid','getegid'):
            stack.enter_context(patch.object(root.os,name,return_value=0,create=True))

    def test_observe_brackets_actual_binding_read_with_original_history_and_file_metadata(self):
        value = self.view()
        with ExitStack() as stack:
            self.root_context(stack)
            files = stack.enter_context(patch.object(root,'persistent_fingerprint',return_value=value.files))
            observe = stack.enter_context(patch.object(root,'_root_persistent_identity',return_value=copy.deepcopy(value.binding)))
            result = value.check()
            self.assertEqual(value.lifecycle.check.call_count,2);self.assertEqual(files.call_count,2)
            observe.assert_called_once_with(value.root,value.scope,value.lifecycle.generation_seal['executables'],
                _executable_files=value.executables,_database_reader=value.database_reader)
        self.assertTrue(result['live_durable_resource_identity_verified'])
        self.assertIs(result['stage_effect_authorized'],False)
        self.assertIs(result['lifecycle_exclusion_established'],False)
        self.assertIs(result['complete_journey_acceptance'],False)
        self.assertFalse({'binding','database','private','configuration','executables'} & set(result))

    def test_changed_live_binding_poison_cannot_be_revived_by_later_matching_result(self):
        value = self.view()
        with ExitStack() as stack:
            self.root_context(stack)
            stack.enter_context(patch.object(root,'persistent_fingerprint',return_value=value.files))
            observe = stack.enter_context(patch.object(root,'_root_persistent_identity',return_value={'different':'identity'}))
            with self.assertRaises(root.RootLiveBindingRefused):value.check()
            self.assertFalse(value.usable)
            value.lifecycle.close.assert_called_once_with();value.executables.close.assert_called_once_with()
            observe.return_value = value.binding
            with self.assertRaises(root.RootLiveBindingRefused):value.check()
            self.assertEqual(observe.call_count,1)

    def test_changed_original_file_or_history_refuses_before_database_read(self):
        for target in ('files','history'):
            value = self.view()
            with ExitStack() as stack:
                self.root_context(stack)
                stack.enter_context(patch.object(root,'persistent_fingerprint',return_value=
                    {'changed':'metadata'} if target == 'files' else value.files))
                if target == 'history':value.lifecycle.check.return_value = {'changed':'history'}
                observe = stack.enter_context(patch.object(root,'_root_persistent_identity'))
                with self.assertRaises(root.RootLiveBindingRefused):value.check()
                observe.assert_not_called()


if __name__ == '__main__':unittest.main()
