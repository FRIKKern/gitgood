import hashlib
from contextlib import ExitStack
import json
import io
import os
from pathlib import Path
import stat
import sys
import tarfile
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from native_protected_artifact import (MAX_ARCHIVE, MAX_EXPANDED, RESERVE, NativeProtectedArtifactStage,
    ProtectedArtifactRefused, _BoundedTarHeaders, fingerprint, parse_policy)
from resource_generations import canonical
import test_inspect_native_artifact as archive_fixture

INSTALLATION = 'f053c00f-1076-43ea-b510-2c6aabbbf79b'
OPERATION = 'a61c988b-633a-4d6e-969b-6940399b08fe'


def policy():
    request = {'protocol':2, 'kind':'native_lifecycle_request', 'installation':INSTALLATION,
        'operation':OPERATION, 'purpose':'native_initial_enrollment', 'durable_binding_sha256':'a'*64,
        'files':{name:{'bytes':4,'sha256':'b'*64} for name in ('allocation.json','inputs.json')}}
    identity = {'device':1,'inode':2,'uid':1000}
    return {'protocol':2, 'kind':'native_protected_artifact_stage_seal', 'installation':INSTALLATION,
        'operation':OPERATION, 'candidate':'c'*40, 'scope_sha256':'d'*64, 'request':request,
        'request_sha256':hashlib.sha256(canonical(request)).hexdigest(), 'snapshot_sha256':'e'*64,
        'archive':{'device':1,'inode':3,'bytes':100,'mtime_ns':1,'ctime_ns':2,'sha256':'f'*64},
        'destination':{'device':1,'inode':4,'uid':0}, 'directories':{name:dict(identity) for name in
            ('installation','history_container','history','records','heads')}}


class ProtectedPolicyTest(unittest.TestCase):
    def test_closed_original_policy_and_request_hash_parse_without_effects(self):
        value = policy()
        self.assertEqual(parse_policy(canonical(value), INSTALLATION, OPERATION), value)

    def test_wrong_identity_candidate_unknown_authority_and_boolean_aliases_refuse(self):
        for change in ({'protocol':True}, {'candidate':'C'*40}, {'installation':OPERATION},
            {'operation':INSTALLATION}, {'scope_sha256':'short'}, {'request_sha256':'0'*64},
            {'path':'/caller/archive'}, {'program':'/caller/command'}, {'callback':'caller'}):
            value = dict(policy(), **change)
            with self.subTest(change=change), self.assertRaises(Exception):
                parse_policy(canonical(value), INSTALLATION, OPERATION)
        for field, item in (('bytes',True), ('bytes',MAX_ARCHIVE+1), ('inode',0), ('device',True)):
            value = policy();value['archive'][field] = item
            with self.subTest(field=field), self.assertRaises(ProtectedArtifactRefused):
                parse_policy(canonical(value), INSTALLATION, OPERATION)

    def test_duplicate_noncanonical_missing_directory_and_unbound_requests_refuse(self):
        value = policy();raw = canonical(value)
        for invalid in (raw+b'\n', raw.replace(b'"protocol":2',b'"protocol":2,"protocol":2',1)):
            with self.assertRaises(ProtectedArtifactRefused):parse_policy(invalid, INSTALLATION, OPERATION)
        value['directories'].pop('history_container')
        with self.assertRaises(ProtectedArtifactRefused):parse_policy(canonical(value), INSTALLATION, OPERATION)
        value = policy();value['request']['operation'] = INSTALLATION
        with self.assertRaises(Exception):parse_policy(canonical(value), INSTALLATION, OPERATION)

    def test_invalid_identifier_and_non_root_refuse_before_original_controller_or_root_files(self):
        with patch('native_protected_artifact.NativeRootControllerObservation') as controller, \
             patch('native_protected_artifact.root_file') as read:
            for identity in (True, None, '../outside', INSTALLATION.upper()):
                with self.assertRaises(ProtectedArtifactRefused):NativeProtectedArtifactStage(identity, OPERATION)
            with patch('native_protected_artifact.os.getuid', return_value=1000, create=True):
                with self.assertRaises(ProtectedArtifactRefused):NativeProtectedArtifactStage(INSTALLATION, OPERATION)
            controller.assert_not_called();read.assert_not_called()

    def test_constructor_initializes_ready_before_its_first_current_check(self):
        # Explicit filesystem/controller stand-ins exercise constructor order.
        scope = {'uid':1000,'gid':1000}
        sealed = policy();sealed['scope_sha256'] = hashlib.sha256(canonical(scope)).hexdigest()
        info = SimpleNamespace(**{name:1 for name in ('st_dev','st_ino','st_uid','st_gid',
            'st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')})
        info.st_ino = 4;info.st_uid = 0
        def ready(value):
            self.assertTrue(value.usable);self.assertEqual(value.state,'ready')
        with ExitStack() as stack:
            for name in ('getuid','geteuid','getgid','getegid'):
                stack.enter_context(patch('native_protected_artifact.os.'+name,return_value=0,create=True))
            for name in ('O_DIRECTORY','O_NOFOLLOW','O_CLOEXEC','O_NONBLOCK'):
                stack.enter_context(patch('native_protected_artifact.os.'+name,0,create=True))
            controller = stack.enter_context(patch('native_protected_artifact.NativeRootControllerObservation'))
            controller.return_value.check.return_value = scope
            stack.enter_context(patch('native_protected_artifact.root_file',return_value=({},canonical(sealed))))
            stack.enter_context(patch('native_protected_artifact._CapturedRootFiles._fingerprint',return_value=()))
            stack.enter_context(patch('native_protected_artifact.directory',return_value=sealed['destination']))
            stack.enter_context(patch('native_protected_artifact.os.open',side_effect=[13,14]))
            stack.enter_context(patch('native_protected_artifact.os.fstat',return_value=info))
            close = stack.enter_context(patch('native_protected_artifact.os.close'))
            stack.enter_context(patch.object(NativeProtectedArtifactStage,'_private',return_value=((),b'fixture')))
            stack.enter_context(patch.object(NativeProtectedArtifactStage,'_validate_stage'))
            checked = stack.enter_context(patch.object(NativeProtectedArtifactStage,'check',autospec=True,side_effect=ready))
            stage = NativeProtectedArtifactStage(INSTALLATION,OPERATION)
            checked.assert_called_once_with(stage)
            stage.close()
            self.assertEqual([item.args[0] for item in close.call_args_list],[14,13])

    def test_destination_descriptor_opened_after_replacement_refuses_before_input_read(self):
        scope = {'uid':1000,'gid':1000}
        sealed = policy();sealed['scope_sha256'] = hashlib.sha256(canonical(scope)).hexdigest()
        with ExitStack() as stack:
            for name in ('getuid','geteuid','getgid','getegid'):
                stack.enter_context(patch('native_protected_artifact.os.'+name,return_value=0,create=True))
            for name in ('O_DIRECTORY','O_NOFOLLOW','O_CLOEXEC','O_NONBLOCK'):
                stack.enter_context(patch('native_protected_artifact.os.'+name,0,create=True))
            controller = stack.enter_context(patch('native_protected_artifact.NativeRootControllerObservation'))
            controller.return_value.check.return_value = scope
            stack.enter_context(patch('native_protected_artifact.root_file',return_value=({},canonical(sealed))))
            stack.enter_context(patch('native_protected_artifact._CapturedRootFiles._fingerprint',return_value=()))
            stack.enter_context(patch('native_protected_artifact.directory',return_value=sealed['destination']))
            opened = stack.enter_context(patch('native_protected_artifact.os.open',return_value=13))
            stack.enter_context(patch('native_protected_artifact.os.fstat',
                return_value=SimpleNamespace(st_dev=1,st_ino=999,st_uid=0)))
            close = stack.enter_context(patch('native_protected_artifact.os.close'))
            with self.assertRaises(ProtectedArtifactRefused):NativeProtectedArtifactStage(INSTALLATION,OPERATION)
            self.assertEqual(opened.call_count,1)
            close.assert_called_once_with(13)


class CurrentOutputGuardTest(unittest.TestCase):
    def test_changed_published_output_poisons_check_and_cannot_be_revived(self):
        # Authority/metadata observations are stand-ins; exercise the public
        # check path and permanent refusal, rather than invoking its guard alone.
        stage = NativeProtectedArtifactStage.__new__(NativeProtectedArtifactStage)
        stage.usable = True;stage.owner = (os.getpid(),threading.get_ident());stage.state = 'staged'
        stage.scope = {'uid':1000,'gid':1000};stage.controller = Mock()
        stage.controller.check.return_value = stage.scope
        stage.policy = policy();stage.raw = canonical(stage.policy)
        stage.policy_path = Mock();stage.policy_fingerprint = ();stage.policy_identity = {}
        stage.parent = Mock();stage.parent.parents = [];stage.parent_fd = 13
        stage.code_fd = None;stage.work_fd = None;stage.snapshot_fd = None;stage.archive_fd = 14
        directory_info = SimpleNamespace(st_dev=1,st_ino=4,st_uid=0,st_gid=0,
            st_mode=stat.S_IFDIR|0o700,st_nlink=2,st_size=0,st_mtime_ns=1,st_ctime_ns=2)
        archive_info = SimpleNamespace(st_dev=1,st_ino=3,st_uid=0,st_gid=0,
            st_mode=stat.S_IFREG|0o444,st_nlink=1,st_size=100,st_mtime_ns=1,st_ctime_ns=2)
        stage.parent_original = fingerprint(directory_info)[:5]
        stage.archive_original = fingerprint(archive_info)
        stage.source = Mock();stage.source.parents = [];stage.source.lstat.return_value = archive_info
        stage.journal_paths = {};stage.head_path = Mock();stage.snapshot_path = Mock()
        stage.head_original = ();stage.snapshot_original = ();stage.head_raw = b'fixture';stage.snapshot_raw = b'fixture'
        stage._private = Mock(return_value=((),b'fixture'))
        stage._check_output = Mock(side_effect=ProtectedArtifactRefused('changed output'))
        with ExitStack() as stack:
            for name in ('getuid','geteuid','getgid','getegid'):
                stack.enter_context(patch('native_protected_artifact.os.'+name,return_value=0,create=True))
            stack.enter_context(patch('native_protected_artifact.root_file',return_value=({},stage.raw)))
            stack.enter_context(patch('native_protected_artifact._CapturedRootFiles._fingerprint',return_value=()))
            stack.enter_context(patch('native_protected_artifact.directory',return_value=stage.policy['destination']))
            stack.enter_context(patch('native_protected_artifact.os.fstat',side_effect=[directory_info,archive_info]))
            close = stack.enter_context(patch('native_protected_artifact.os.close'))
            with self.assertRaises(ProtectedArtifactRefused):stage.check()
            stage._check_output.assert_called_once_with()
            self.assertFalse(stage.usable)
            self.assertEqual([item.args[0] for item in close.call_args_list],[14,13])
            stage._check_output.side_effect = None
            with self.assertRaises(ProtectedArtifactRefused):stage.check()
            self.assertEqual(stage._check_output.call_count,1)
            self.assertEqual(stage.controller.check.call_count,1)


class AllocationBudgetTest(unittest.TestCase):
    def test_budget_includes_system_and_output_reserves_and_releases_owned_observation_fd(self):
        stage = NativeProtectedArtifactStage.__new__(NativeProtectedArtifactStage)
        stage.parent_fd = 12
        maximum = SimpleNamespace(f_bavail=RESERVE+100, f_frsize=1)
        with patch('native_protected_artifact.os.O_DIRECTORY',0,create=True), \
             patch('native_protected_artifact.os.O_NOFOLLOW',0,create=True), \
             patch('native_protected_artifact.os.O_CLOEXEC',0,create=True), \
             patch('native_protected_artifact.os.open',return_value=11), \
             patch('native_protected_artifact.os.close') as close, \
             patch('native_protected_artifact.os.fstatvfs',return_value=maximum,create=True) as capacity:
            stage._budget(100)
            self.assertEqual([call.args[0] for call in capacity.call_args_list],[11,12])
            close.assert_called_once_with(11)
        for capacities in ((RESERVE+99,RESERVE+100),(RESERVE+100,RESERVE+99)):
            with patch('native_protected_artifact.os.O_DIRECTORY',0,create=True), \
                 patch('native_protected_artifact.os.O_NOFOLLOW',0,create=True), \
                 patch('native_protected_artifact.os.O_CLOEXEC',0,create=True), \
                 patch('native_protected_artifact.os.open',return_value=11), \
                 patch('native_protected_artifact.os.close') as close, \
                 patch('native_protected_artifact.os.fstatvfs',create=True,
                    side_effect=[SimpleNamespace(f_bavail=value,f_frsize=1) for value in capacities]):
                with self.assertRaises(ProtectedArtifactRefused):stage._budget(100)
                close.assert_called_once_with(11)
        with patch('native_protected_artifact.os.open') as opened:
            for amount in (True,0,-1,10**20):
                with self.assertRaises(ProtectedArtifactRefused):stage._budget(amount)
            opened.assert_not_called()


class BoundedArchiveHeadersTest(unittest.TestCase):
    def test_unbounded_reads_and_expansion_offsets_refuse_before_reader_access(self):
        source = Mock();source.tell.return_value = 0
        reader = _BoundedTarHeaders(source)
        for amount in (-1,True,8193):
            with self.assertRaises(ProtectedArtifactRefused):reader.read(amount)
        for offset,whence in ((-1,0),(MAX_EXPANDED+1,0),(0,2),(True,0)):
            with self.assertRaises(ProtectedArtifactRefused):reader.seek(offset,whence)
        source.read.assert_not_called();source.seek.assert_not_called()
        source.tell.return_value = MAX_EXPANDED
        with self.assertRaises(ProtectedArtifactRefused):reader.read(1)
        source.read.assert_not_called()

    def test_actual_small_archive_preflight_and_oversized_compressed_pax_refusal(self):
        fixture = archive_fixture.ArtifactInspectionTest();fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.archive()
        def preflight():
            stage = NativeProtectedArtifactStage.__new__(NativeProtectedArtifactStage)
            stage.check = Mock()
            stage.archive_fd = os.open(fixture.path,os.O_RDONLY)
            try:stage._preflight_archive()
            finally:os.close(stage.archive_fd)
        preflight()
        # A few compressed bytes must not authorize an oversized metadata read.
        with tarfile.open(fixture.path,'w:gz',format=tarfile.PAX_FORMAT) as archive:
            member = tarfile.TarInfo('forge/metadata')
            member.pax_headers = {'comment':'x'*9000}
            archive.addfile(member,io.BytesIO(b''))
        self.assertLess(fixture.path.stat().st_size,1024)
        with self.assertRaises(ProtectedArtifactRefused):preflight()

    def test_declared_oversized_member_refuses_before_expansion_seek(self):
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch)/'header.tar.gz'
            with tarfile.open(path,'w:gz') as archive:
                member = tarfile.TarInfo('forge/oversized');member.size = 128*1024**2+1
                archive.addfile(member)
            stage = NativeProtectedArtifactStage.__new__(NativeProtectedArtifactStage)
            stage.check = Mock();stage.archive_fd = os.open(path,os.O_RDONLY)
            try:
                with self.assertRaises(ProtectedArtifactRefused):stage._preflight_archive()
            finally:os.close(stage.archive_fd)


class HeldCodeDirectoryTest(unittest.TestCase):
    def test_traversal_uses_held_fds_and_refuses_replaced_original_directory(self):
        stage = NativeProtectedArtifactStage.__new__(NativeProtectedArtifactStage)
        stage.code_fd = 10
        stage.code_directories = {'':{'device':1,'inode':100,'uid':0},
            'forge':{'device':1,'inode':101,'uid':0}, 'forge/lib':{'device':1,'inode':102,'uid':0}}
        def info(inode):
            return SimpleNamespace(st_dev=1,st_ino=inode,st_uid=0,st_mode=stat.S_IFDIR|0o700)
        with patch('native_protected_artifact.os.O_DIRECTORY',0,create=True), \
             patch('native_protected_artifact.os.O_NOFOLLOW',0,create=True), \
             patch('native_protected_artifact.os.O_CLOEXEC',0,create=True), \
             patch('native_protected_artifact.os.dup',return_value=11), \
             patch('native_protected_artifact.os.open',side_effect=[12,13]) as opened, \
             patch('native_protected_artifact.os.close') as close, \
             patch('native_protected_artifact.os.fstat',side_effect=[info(100),info(101),info(999)]):
            with self.assertRaises(ProtectedArtifactRefused):stage._code_directory('forge/lib')
            self.assertEqual([call.kwargs['dir_fd'] for call in opened.call_args_list],[11,12])
            self.assertEqual([call.args[0] for call in close.call_args_list],[11,12,13])


@unittest.skipUnless(sys.platform == 'linux' and os.getuid() == 0, 'Actual isolated Root extraction')
class RootExtractionTest(unittest.TestCase):
    def setUp(self):
        self.fixture = archive_fixture.ArtifactInspectionTest();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.digest = self.fixture.archive();self.fixture.path.chmod(0o444)
        self.scratch = tempfile.TemporaryDirectory();self.addCleanup(self.scratch.cleanup)
        self.parent = Path(self.scratch.name);self.parent.chmod(0o700)

    def stage(self):
        # Explicit admission/budget stand-ins; real Root descriptors, extraction,
        # permissions, atomic no-replace publication and metadata guards.
        value = NativeProtectedArtifactStage.__new__(NativeProtectedArtifactStage)
        value.installation = INSTALLATION;value.operation = OPERATION
        value.parent = self.parent;value.source = self.fixture.path
        value.parent_fd = os.open(self.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        value.archive_fd = os.open(self.fixture.path,os.O_RDONLY|os.O_NOFOLLOW)
        value.work_fd = None;value.code_fd = None;value.snapshot_fd = None;value.controller = None
        value.code_directories = {};value.output_files = {};value.state = 'ready';value.usable = True
        value.policy = dict(policy(),candidate=self.fixture.candidate)
        value.policy['archive'] = {'sha256':self.digest}
        value.check = Mock(return_value={'original_controller_and_running_stage_observed':True})
        value._budget = Mock()
        self.addCleanup(value.close)
        return value

    def test_actual_root_files_are_readonly_and_exact_original_output_is_guarded(self):
        stage = self.stage();before = self.fixture.path.read_bytes()
        original_umask = os.umask(0o077)
        try:receipt = stage.stage()
        finally:os.umask(original_umask)
        target = self.parent/('native-'+OPERATION)
        self.assertTrue(receipt['root_controlled_code'])
        self.assertEqual(self.fixture.path.read_bytes(),before)
        self.assertFalse((self.parent/('.native-'+OPERATION+'.partial')).exists())
        for name in ('archive.tar.gz','inventory.json','receipt.json'):
            info=(target/name).stat()
            self.assertEqual((info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode)),(0,0,0o444))
        inventory = json.loads((target/'inventory.json').read_bytes())
        self.assertEqual(hashlib.sha256(canonical(inventory)).hexdigest(),receipt['inventory_sha256'])
        for item in inventory:
            path = target/'code'/item['path']
            self.assertEqual(path.stat().st_uid,0)
            self.assertEqual(path.stat().st_mode & 0o222,0)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o555 if item['executable'] else 0o444)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),item['sha256'])
        stage._check_output()
        file = target/'code/web/package.json'
        file.chmod(0o644);file.write_bytes(b'changed');file.chmod(0o444)
        with self.assertRaises(ProtectedArtifactRefused):stage._check_output()

    def test_existing_foreign_destination_is_preserved_without_partial_allocation(self):
        target = self.parent/('native-'+OPERATION);target.mkdir(mode=0o700)
        sentinel = target/'retain';sentinel.write_bytes(b'foreign owned fixture')
        with self.assertRaises(ProtectedArtifactRefused):self.stage().stage()
        self.assertEqual(sentinel.read_bytes(),b'foreign owned fixture')
        self.assertFalse((self.parent/('.native-'+OPERATION+'.partial')).exists())

    def test_destination_created_during_staging_is_not_replaced(self):
        stage = self.stage();target = self.parent/('native-'+OPERATION)
        original_fchmod = os.fchmod
        def race(descriptor,mode):
            original_fchmod(descriptor,mode)
            if descriptor == stage.work_fd:
                target.mkdir(mode=0o700)
                (target/'retain').write_bytes(b'foreign created before publication')
        with patch('native_protected_artifact.os.fchmod',side_effect=race):
            with self.assertRaises(ProtectedArtifactRefused):stage.stage()
        self.assertEqual((target/'retain').read_bytes(),b'foreign created before publication')
        partial = self.parent/('.native-'+OPERATION+'.partial')
        self.assertTrue((partial/'receipt.json').is_file())
        self.assertFalse(stage.usable)
        self.assertTrue(all(getattr(stage,name) is None for name in
            ('parent_fd','archive_fd','work_fd','code_fd','snapshot_fd')))

    def test_interruption_retains_source_and_partial_and_closes_owned_descriptors(self):
        stage = self.stage();source_before = self.fixture.path.read_bytes()
        partial = self.parent/('.native-'+OPERATION+'.partial')
        def interrupted():
            if (partial/'archive.tar.gz').exists():raise KeyboardInterrupt('fixture interruption')
        stage.check.side_effect = interrupted
        with self.assertRaises(ProtectedArtifactRefused):stage.stage()
        self.assertEqual(self.fixture.path.read_bytes(),source_before)
        self.assertTrue((partial/'archive.tar.gz').is_file())
        self.assertFalse((self.parent/('native-'+OPERATION)).exists())
        self.assertFalse(stage.usable)
        self.assertTrue(all(getattr(stage,name) is None for name in
            ('parent_fd','archive_fd','work_fd','code_fd','snapshot_fd')))


if __name__ == '__main__':
    unittest.main()
