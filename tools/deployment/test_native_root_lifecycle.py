import copy
import os
from pathlib import Path
import stat
import sys
import tempfile
import threading
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch

from native_root_lifecycle import (NativeRootLifecycleObservation, RootLifecycleRefused,
    _RootGenerationHistory, _RootLifecycleHistory, _RootPrivateInputs, _RootReadOnlyCustody, parse_generation_seal)
from resource_generations import canonical
from native_operation_inputs import OperationInputsRefused, file_identity, file_record, parse_request
import test_native_durable_database as database_fixture
import test_native_operation_inputs as input_fixture
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
        value.original_raw = canonical(value.original);value._current = Mock()
        value._snapshot = Mock(side_effect=AssertionError('Immutable history must not be replayed again'))
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
        value = self.view();value.original['lifecycle']['epoch'] = 2
        with patch('native_root_lifecycle.root_owner',return_value=value.owner):
            with self.assertRaises(RootLifecycleRefused):value.check()
            self.assertFalse(value.usable)
            value.inputs.close.assert_called_once_with();value.history.close.assert_called_once_with()
            value.controller.close.assert_called_once_with()
            value.original['lifecycle']['epoch'] = 1
            with self.assertRaises(RootLifecycleRefused):value.check()
            value._snapshot.assert_not_called();self.assertEqual(value._current.call_count,1)

    def test_different_process_or_thread_refuses_before_history_read(self):
        value = self.view()
        with patch('native_root_lifecycle.root_owner',return_value=(42,44)):
            with self.assertRaises(RootLifecycleRefused):value.check()
        value._snapshot.assert_not_called()
        value._current.assert_not_called()

    def test_each_observation_rechecks_actual_resources_before_and_after_cached_history(self):
        value = self.view()
        with patch('native_root_lifecycle.root_owner',return_value=value.owner):
            first = value.check();self.assertEqual(first,value.check())
        self.assertEqual(value._current.call_count,4)
        self.assertEqual(value.history.custody.check.call_count,2)
        value._snapshot.assert_not_called()

    def test_original_descriptor_loss_poisoning_does_not_adopt_restored_resources(self):
        value = self.view();value.history.custody.check.side_effect = OSError('Lost original descriptor')
        with patch('native_root_lifecycle.root_owner',return_value=value.owner):
            with self.assertRaises(RootLifecycleRefused):value.check()
            value.history.custody.check.side_effect = None
            with self.assertRaises(RootLifecycleRefused):value.check()
        self.assertFalse(value.usable);value._snapshot.assert_not_called()


@unittest.skipUnless(sys.platform == 'linux' and os.getuid() == 0,'Actual isolated Root history descriptors')
class RootRetainedHistoryDescriptorTest(unittest.TestCase):
    """Real original descriptors; snapshot semantics and ancestor policy stand-ins.

    Complete generation/lifecycle replay is exercised by installed hosted cases,
    not inferred from these deliberately small filesystem custody fixtures.
    """
    def setUp(self):
        temporary = tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)/'installation';root.mkdir(mode=0o700)
        self.uid,self.gid = 65503,1000;os.chown(root,self.uid,self.gid)
        value = _RootReadOnlyCustody.__new__(_RootReadOnlyCustody)
        value.usable = False;value.owner = (os.getpid(),threading.get_ident())
        value.uid,value.gid = self.uid,self.gid;value.root = root
        value.directory = root/'history';value.store = value.directory/'generation-records-v2'
        value.lock_path = value.directory/'.upgrade-history-lock-v1'
        value.lock = None;value.directories = {};value.known = {};value.retained = {}
        value.entries = None;value.directory_metadata = {}
        for relative in ('history','history/generation-records-v2','history/generation-transitions-v2',
                'history/generation-receipts-v2','history/lifecycle-responsibility-v2',
                'history/lifecycle-responsibility-v2/heads','history/lifecycle-responsibility-v2/records'):
            path = root/relative;path.mkdir(mode=0o700);os.chown(path,self.uid,self.gid)
        self.paths = []
        for relative in ('.upgrade-history-lock-v1','durable-binding-v2.json','current-generation-v2.json',
                'generation-records-v2/generation.json','generation-transitions-v2/transition.json',
                'generation-receipts-v2/receipt.json','lifecycle-responsibility-v2/heads/operation.json',
                'lifecycle-responsibility-v2/records/snapshot.json'):
            path = value.directory/relative;self.write(path);self.paths.append(path)
        policy = self.enterContext(patch('native_root_lifecycle.private_directory',
            side_effect=lambda path,uid,gid:(self.identity(path),())))
        value.root_custody = policy(root,self.uid,self.gid)
        value._identity(value.directory);value.usable = True
        value.lock = value._open(value.lock_path,os.O_RDONLY)
        self.value = value;self.addCleanup(value.__exit__,None,None,None)
        lifecycle = value.directory/'lifecycle-responsibility-v2'
        fields = ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_uid','st_mode','st_nlink')
        self.snapshot = {'directories':{str(path.relative_to(value.directory)):value._directory_metadata(path.stat())
                for path in (value.directory,value.store,value.directory/'generation-transitions-v2',
                    value.directory/'generation-receipts-v2',lifecycle,lifecycle/'heads',lifecycle/'records')},
            'generation':{'files':{str(path.relative_to(value.directory)):
                tuple(getattr(path.stat(),field) for field in fields) for path in self.paths if not path.is_relative_to(lifecycle)}},
            'lifecycle_files':{'directories':{role:(*self.directory_identity(path),path.stat().st_mtime_ns,path.stat().st_ctime_ns)
                for role,path in (('lifecycle',lifecycle),('heads',lifecycle/'heads'),('records',lifecycle/'records'))},
                'files':{str(path.relative_to(lifecycle)):value._file(path.stat()) for path in self.paths if path.is_relative_to(lifecycle)}}}

    def identity(self,path):
        info = path.stat();return {'device':info.st_dev,'inode':info.st_ino,'uid':info.st_uid}

    @staticmethod
    def directory_identity(path):
        return tuple(getattr(path.stat(),field) for field in ('st_dev','st_ino','st_uid','st_gid','st_mode'))

    def write(self,path,raw=b'{"fixture":true}'):
        path.write_bytes(raw);path.chmod(0o600);os.chown(path,self.uid,self.gid)

    def pin(self):self.value._pin_snapshot(self.snapshot)

    def test_original_descriptors_and_bytes_are_retained_without_replaying_or_writing(self):
        before = {path:(path.stat().st_ino,path.read_bytes(),path.stat().st_mode) for path in self.paths}
        self.pin()
        with patch.object(self.value,'_records',side_effect=AssertionError('Replay')):
            for _ in range(3):self.value.check()
        self.assertEqual(set(self.value.retained),set(self.paths))
        self.assertTrue(all(os.fstat(fd).st_uid == self.uid for fd in self.value.retained.values()))
        self.value.__exit__(None,None,None)
        self.assertEqual(self.value.retained,{})
        self.assertEqual({path:(path.stat().st_ino,path.read_bytes(),path.stat().st_mode) for path in self.paths},before)

    def test_same_bytes_generation_replacement_retains_original_but_refuses(self):
        self.pin();path = self.paths[3];raw = path.read_bytes()
        retained = path.with_name('retained-original.json');path.rename(retained);self.write(path,raw)
        with self.assertRaises(RootLifecycleRefused):self.value.check()
        self.assertEqual(retained.read_bytes(),raw);self.assertEqual(path.read_bytes(),raw)

    def test_in_place_lifecycle_rewrite_with_restored_mtime_refuses(self):
        self.pin();path = self.paths[-1];before = path.stat()
        path.write_bytes(b'{"fixture":fals}');os.utime(path,ns=(before.st_atime_ns,before.st_mtime_ns))
        with self.assertRaises(RootLifecycleRefused):self.value.check()

    def test_generation_mode_change_refuses_without_a_content_change(self):
        self.pin();self.paths[3].chmod(0o400)
        with self.assertRaises(RootLifecycleRefused):self.value.check()

    def test_new_hardlink_refuses_even_outside_the_recorded_history(self):
        self.pin();os.link(self.paths[-1],self.value.root/'external-link')
        with self.assertRaises(RootLifecycleRefused):self.value.check()

    def test_additional_generation_entry_refuses_even_when_original_files_are_unchanged(self):
        self.pin();self.write(self.value.store/'unknown.json')
        with self.assertRaises(RootLifecycleRefused):self.value.check()

    def test_transient_lifecycle_entry_refuses_after_name_set_is_restored(self):
        self.pin();path = self.paths[-1].with_name('.partial-interrupted')
        self.write(path);path.unlink()
        with self.assertRaises(RootLifecycleRefused):self.value.check()

    def test_transient_generation_entry_between_replay_and_pinning_refuses(self):
        path = self.value.store/'.partial-interrupted';self.write(path);path.unlink()
        with self.assertRaises(RootLifecycleRefused):self.pin()

    def test_rebound_original_file_descriptor_refuses(self):
        self.pin();fd = self.value.retained[self.paths[3]]
        other = os.open(self.paths[4],os.O_RDONLY)
        try:os.dup2(other,fd)
        finally:os.close(other)
        with self.assertRaises(RootLifecycleRefused):self.value.check()

    def test_lost_descriptor_poisons_public_view_and_closes_other_owned_observers(self):
        self.pin();descriptors = list(self.value.retained.values())
        os.close(descriptors[0])
        public = RootOriginalViewTest().view();public.owner = self.value.owner
        public.history = SimpleNamespace(custody=self.value,close=self.value.__exit__)
        with patch('native_root_lifecycle.root_owner',return_value=public.owner):
            with self.assertRaises(RootLifecycleRefused):public.check()
            with self.assertRaises(RootLifecycleRefused):public.check()
        self.assertFalse(public.usable);self.assertFalse(self.value.usable)
        for fd in descriptors:
            with self.assertRaises(OSError):os.fstat(fd)
        self.assertTrue(all(path.exists() for path in self.paths))

    def test_same_bytes_history_directory_replacement_refuses(self):
        self.pin();directory = self.value.store;directory.rename(directory.with_name('retained-store'))
        directory.mkdir(mode=0o700);os.chown(directory,self.uid,self.gid);self.write(directory/'generation.json')
        with self.assertRaises(RootLifecycleRefused):self.value.check()

    def test_changed_metadata_between_replay_and_pinning_refuses(self):
        self.paths[-1].chmod(0o400)
        with self.assertRaises(RootLifecycleRefused):self.pin()

    def test_same_bytes_generation_rewrite_between_replay_and_pinning_refuses(self):
        path = self.paths[3];before = path.stat();path.write_bytes(path.read_bytes())
        os.utime(path,ns=(before.st_atime_ns,before.st_mtime_ns))
        with self.assertRaises(RootLifecycleRefused):self.pin()

    def test_pinning_interruption_closes_only_owned_original_descriptors(self):
        original_open = self.value._open;calls = []
        def interrupted(path,flags):
            if len(calls) == 2:raise KeyboardInterrupt('Fixture interruption')
            fd = original_open(path,flags);calls.append(fd);return fd
        with patch.object(self.value,'_open',side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):self.pin()
        self.value.__exit__(None,None,None)
        for fd in calls:
            with self.assertRaises(OSError):os.fstat(fd)
        self.assertTrue(all(path.exists() for path in self.paths))


@unittest.skipUnless(sys.platform == 'linux' and os.getuid() == 0,'Actual isolated Root input descriptors')
class RootPrivateInputDescriptorTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)/'inputs';self.directory.mkdir(mode=0o700)
        self.uid,self.gid = 65503,1000
        os.chown(self.directory,self.uid,self.gid)
        self.seal,_,self.request,self.payloads = input_fixture.fixture()
        self.seal.update(uid=self.uid,gid=self.gid)
        self.seal['directory_identity'] = self.identity(self.directory)
        for name,raw in self.payloads.items():
            path = self.directory/name;path.write_bytes(raw);path.chmod(0o600);os.chown(path,self.uid,self.gid)
            self.seal['files'][name] = file_record(file_identity(path.stat(),self.uid,self.gid,131072),raw)

    @staticmethod
    def identity(path):
        info = path.stat();return {'device':info.st_dev,'inode':info.st_ino,'uid':info.st_uid}

    def view(self):
        # The test scratch ancestor policy is a stand-in; actual files belong
        # to an ordinary UID and are captured through real Root descriptors.
        with patch('native_root_lifecycle.private_directory',
                side_effect=lambda path,uid,gid:(self.identity(path),())):
            value = _RootPrivateInputs(self.directory,self.uid,self.gid,self.seal)
        self.addCleanup(value.close)
        return value

    def test_actual_root_read_preserves_ordinary_input_bytes_modes_and_inode_identities(self):
        before = {name:(path.stat().st_ino,path.read_bytes(),path.stat().st_mode) for name in self.payloads
            for path in (self.directory/name,)}
        value = self.view()
        with patch('native_root_lifecycle.private_directory',
                side_effect=lambda path,uid,gid:(self.identity(path),())):
            self.assertEqual(value.check(),self.payloads)
            self.assertEqual(parse_request(value.check()['request.json'],self.seal),self.request)
        self.assertEqual(os.getuid(),0)
        self.assertTrue(all(os.fstat(fd).st_uid == self.uid for fd in value.files.values()))
        self.assertEqual({name:(path.stat().st_ino,path.read_bytes(),path.stat().st_mode) for name in self.payloads
            for path in (self.directory/name,)},before)
        value.close();self.assertEqual(value.files,{})
        self.assertTrue(all((self.directory/name).exists() for name in self.payloads))

    def test_same_bytes_replacement_refuses_and_retains_both_original_and_new_input(self):
        value = self.view();path = self.directory/'inputs.json';raw = path.read_bytes()
        retained = self.directory/'retained-original-input.json';path.rename(retained)
        path.write_bytes(raw);path.chmod(0o600);os.chown(path,self.uid,self.gid)
        with patch('native_root_lifecycle.private_directory',
                side_effect=lambda path,uid,gid:(self.identity(path),())):
            with self.assertRaises((RootLifecycleRefused,OperationInputsRefused)):value.check()
        value.close()
        self.assertEqual(retained.read_bytes(),raw);self.assertEqual(path.read_bytes(),raw)


if __name__ == '__main__':unittest.main()
