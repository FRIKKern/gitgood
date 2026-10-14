import copy
import os
from pathlib import Path
import stat
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch

from native_root_lifecycle import (NativeRootLifecycleObservation, RootLifecycleRefused,
    _RootGenerationHistory, _RootLifecycleHistory, _RootPrivateInputs, _RootReadOnlyCustody, parse_generation_seal)
from resource_generations import canonical
import test_native_durable_database as database_fixture
import test_resource_generations as generation_fixture


def fixture():
    value = generation_fixture.ResourceGenerationRecordTest();value.setUp()
    seal = {'protocol':2,'kind':'native_generation_admission_seal','installation':value.installation,
        'binding_sha256':'b'*64, 'unit_sha256':value.scope['unit_definition']['sha256'],
        'history_identity':{'device':1,'inode':2,'uid':value.scope['uid']},
        'lock_identity':{'device':1,'inode':3,'uid':value.scope['uid']},
        'executables':{name:'/fixed/'+name for name in ('python','node','git','psql','caddy')},
        'limits':{name:value.scope['limits'][name] for name in ('cpu_quota_us','memory_bytes')},
        'database':copy.deepcopy(database_fixture.GOOD)}
    return value,seal


class RootGenerationSealTest(unittest.TestCase):
    def test_closed_policy_matches_original_unit_limits_and_ordinary_history_owner(self):
        value,seal = fixture()
        self.assertEqual(parse_generation_seal(canonical(seal),value.installation,value.scope),seal)

    def test_unknown_paths_programs_and_caller_authority_maps_refuse(self):
        value,seal = fixture()
        for name in ('path','program','callback','environment','scope','authority'):
            with self.subTest(name=name),self.assertRaises(Exception):
                parse_generation_seal(canonical(dict(seal,**{name:'caller'})),value.installation,value.scope)

    def test_boolean_owner_limit_and_foreign_original_unit_refuse(self):
        value,original = fixture()
        for name,field,item in (('history_identity','uid',True),('lock_identity','inode',True),
            ('history_identity','uid',0),('limits','memory_bytes',True),('limits','cpu_quota_us',200001)):
            seal = copy.deepcopy(original);seal[name][field] = item
            with self.subTest(name=name,field=field),self.assertRaises(Exception):
                parse_generation_seal(canonical(seal),value.installation,value.scope)
        with self.assertRaises(Exception):
            parse_generation_seal(canonical(dict(original,unit_sha256='f'*64)),value.installation,value.scope)

    def test_duplicate_noncanonical_policy_and_privileged_database_refuse(self):
        value,seal = fixture();raw = canonical(seal)
        for changed in (raw+b'\n',raw.replace(b'"protocol":2',b'"protocol":2,"protocol":2')):
            with self.assertRaises(Exception):parse_generation_seal(changed,value.installation,value.scope)
        seal['database']['superuser'] = True
        with self.assertRaises(Exception):parse_generation_seal(canonical(seal),value.installation,value.scope)


class RootReadOnlyBoundaryTest(unittest.TestCase):
    def test_invalid_identifier_or_ordinary_caller_refuses_before_controller_and_root_policy(self):
        value,_ = fixture();operation = '00000000-0000-4000-8000-000000000099'
        with patch('native_root_lifecycle.NativeRootControllerObservation') as controller, \
             patch('native_root_lifecycle.root_file') as root:
            for identity in (None,True,'../outside',value.installation.upper()):
                # This fixture UUID has no letters; choose an invalid suffix too.
                if identity == value.installation:identity += '/'
                with self.assertRaises(RootLifecycleRefused):NativeRootLifecycleObservation(identity,operation)
            with patch('native_root_lifecycle.os.getuid',return_value=1000,create=True):
                with self.assertRaises(RootLifecycleRefused):NativeRootLifecycleObservation(value.installation,operation)
            controller.assert_not_called();root.assert_not_called()

    def test_root_history_cannot_publish_write_borrow_admit_or_retain(self):
        history = _RootGenerationHistory.__new__(_RootGenerationHistory)
        custody = _RootReadOnlyCustody.__new__(_RootReadOnlyCustody)
        for action in (lambda:history.publish(operation='caller'),lambda:history._write('/caller',{}),
            lambda:history.admit(worker='native',owner_pid=123),lambda:history.borrow_custody(Mock()),
            lambda:custody.retain({}),lambda:custody._open(Path('/caller'),os.O_WRONLY)):
            with self.assertRaises(RootLifecycleRefused):action()

    def test_opened_input_directory_replacement_refuses_before_private_file_reads(self):
        info = SimpleNamespace(st_dev=1,st_ino=999,st_uid=1000,st_gid=1000,
            st_mode=stat.S_IFDIR|0o700,st_mtime_ns=1,st_ctime_ns=2)
        directory = Mock();directory.lstat.return_value = info
        seal = {'purpose':'native_initial_enrollment','directory_identity':{'device':1,'inode':2,'uid':1000}}
        with ExitStack() as stack:
            for name in ('O_DIRECTORY','O_NOFOLLOW','O_CLOEXEC'):
                stack.enter_context(patch('native_root_lifecycle.os.'+name,0,create=True))
            stack.enter_context(patch('native_root_lifecycle.private_directory',return_value=(seal['directory_identity'],())))
            opened = stack.enter_context(patch('native_root_lifecycle.os.open',return_value=13))
            stack.enter_context(patch('native_root_lifecycle.os.fstat',return_value=info))
            close = stack.enter_context(patch('native_root_lifecycle.os.close'))
            with self.assertRaises(RootLifecycleRefused):_RootPrivateInputs(directory,1000,1000,seal)
            self.assertEqual(opened.call_count,1);close.assert_called_once_with(13)

    def test_interrupted_history_constructor_closes_its_owned_descriptors(self):
        custody = SimpleNamespace(uid=1000,gid=1000)
        def interrupted(value,_custody):
            value.usable = True;value.descriptors = {'history':13,'records':14}
            raise KeyboardInterrupt('fixture interruption')
        with patch('native_root_lifecycle.NativeLifecycleHistory.__init__',autospec=True,side_effect=interrupted), \
             patch('native_root_lifecycle.os.close') as close:
            with self.assertRaises(KeyboardInterrupt):_RootLifecycleHistory(custody)
            self.assertEqual([item.args[0] for item in close.call_args_list],[13,14])


class RootOriginalViewTest(unittest.TestCase):
    def view(self):
        value = NativeRootLifecycleObservation.__new__(NativeRootLifecycleObservation)
        value.usable = True;value.owner = (42,43);value.installation = 'fixed-installation';value.operation = 'fixed-operation'
        value.worker = {'candidate':'c'*40,'request_sha256':'d'*64}
        value.original = {'lifecycle':{'generation_sha256':'e'*64,'epoch':1,'stage':'stage','status':'running'}}
        value._snapshot = Mock(return_value=copy.deepcopy(value.original))
        value.inputs = Mock();value.history = Mock();value.controller = Mock()
        return value

    def test_original_summary_contains_no_private_payload_and_grants_no_effects(self):
        value = self.view()
        with patch('native_root_lifecycle.root_owner',return_value=value.owner):observed = value.check()
        self.assertTrue(observed['original_controller_and_complete_history_observed'])
        for name in ('stage_effect_authorized','lifecycle_exclusion_established',
            'live_durable_resource_identity_verified','complete_journey_acceptance'):
            self.assertIs(observed[name],False)
        self.assertFalse({'inputs','request','password','database','configuration'} & set(observed))

    def test_changed_history_permanently_poisons_view_and_closes_owned_observers(self):
        value = self.view();value._snapshot.return_value = {'changed':'history'}
        with patch('native_root_lifecycle.root_owner',return_value=value.owner):
            with self.assertRaises(RootLifecycleRefused):value.check()
            self.assertFalse(value.usable)
            value.inputs.close.assert_called_once_with();value.history.close.assert_called_once_with()
            value.controller.close.assert_called_once_with()
            value._snapshot.return_value = value.original
            with self.assertRaises(RootLifecycleRefused):value.check()
            self.assertEqual(value._snapshot.call_count,1)

    def test_different_process_or_thread_refuses_before_history_read(self):
        value = self.view()
        with patch('native_root_lifecycle.root_owner',return_value=(42,44)):
            with self.assertRaises(RootLifecycleRefused):value.check()
        value._snapshot.assert_not_called()


if __name__ == '__main__':unittest.main()
