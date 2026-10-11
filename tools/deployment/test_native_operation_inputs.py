import copy
import hashlib
import os
import stat
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from native_operation_inputs import (NativeOperationInputs, OperationInputsRefused,
                                    POLICIES, _PrivateInputSet, parse_request, parse_seal)
from resource_generations import canonical

INSTALLATION = 'ca3fdbb3-9d66-4469-9339-9a951a683b73'
OPERATION = '3d615319-deba-4b1a-a71f-d7cda2d24749'


def fixture(purpose='native_initial_enrollment'):
    policy = POLICIES[purpose]['files']
    payloads = {name: canonical({'protocol': 2, 'synthetic': name})
                for name in policy if name != 'request.json'}
    files = {name: {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
             for name, raw in payloads.items()}
    request = {'protocol': 2, 'kind': 'native_lifecycle_request', 'installation': INSTALLATION,
               'operation': OPERATION, 'purpose': purpose, 'durable_binding_sha256': 'a'*64,
               'files': copy.deepcopy(files)}
    raw = canonical(request)
    files['request.json'] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    payloads['request.json'] = raw
    files = {name: dict(observed, device=1, inode=index, uid=1000, gid=1000,
                       mode=stat.S_IFREG | 0o600, links=1, mtime_ns=1, ctime_ns=1)
             for index, (name, observed) in enumerate(files.items(), 3)}
    seal = {'protocol': 2, 'kind': 'native_operation_inputs_seal', 'installation': INSTALLATION,
            'operation': OPERATION, 'purpose': purpose, 'durable_binding_sha256': 'a'*64,
            'uid': 1000, 'gid': 1000, 'directory_identity': {'device': 1, 'inode': 2, 'uid': 1000},
            'files': files}
    command = {'protocol': 2, 'kind': 'native_controller_command', 'installation': INSTALLATION,
               'action': 'enroll' if purpose == 'native_initial_enrollment' else 'upgrade',
               'operation': OPERATION, 'request_sha256': files['request.json']['sha256']}
    return seal, command, request, payloads


class OperationFormatTest(unittest.TestCase):
    def test_original_request_and_recovery_actions_share_the_same_sealed_inputs(self):
        for purpose in POLICIES:
            seal, command, request, raw = fixture(purpose)
            for action in POLICIES[purpose]['actions']:
                command['action'] = action
                self.assertEqual(parse_seal(canonical(seal), command, 1000, 1000), seal)
                self.assertEqual(parse_request(raw['request.json'], seal), request)

    def test_cross_purpose_action_and_foreign_operation_installation_or_digest_refuse(self):
        seal, command, _, _ = fixture()
        for change in [{'action': 'upgrade'}, {'action': 'backup'}, {'installation': OPERATION},
                       {'operation': INSTALLATION}, {'request_sha256': 'b'*64}]:
            with self.subTest(change=change), self.assertRaises(OperationInputsRefused):
                parse_seal(canonical(seal), dict(command, **change), 1000, 1000)

    def test_legacy_unknown_fields_files_and_boolean_aliases_refuse(self):
        seal, command, _, _ = fixture()
        changes = [dict(seal, protocol=1), dict(seal, protocol=True), dict(seal, uid=True),
                   dict(seal, gid=1001), dict(seal, callback='arbitrary'),
                   dict(seal, files={'../outside': {'bytes': 1, 'sha256': 'a'*64}}),
                   dict(seal, durable_binding_sha256='A'*64),
                   dict(seal, directory_identity={'device': True, 'inode': 2, 'uid': 1000})]
        for value in changes:
            with self.subTest(value=value), self.assertRaises(OperationInputsRefused):
                parse_seal(canonical(value), command, 1000, 1000)
        for field, value in [('bytes', True), ('bytes', 0), ('bytes', 131073), ('sha256', 'A'*64)]:
            changed = copy.deepcopy(seal);changed['files']['allocation.json'][field] = value
            with self.assertRaises(OperationInputsRefused):parse_seal(canonical(changed), command, 1000, 1000)

    def test_duplicate_noncanonical_and_nonobject_seals_refuse(self):
        seal, command, _, _ = fixture()
        raw = canonical(seal)
        for invalid in [raw+b'\n', b'[]', raw.replace(b'"protocol":2', b'"protocol":2,"protocol":2')]:
            with self.assertRaises(OperationInputsRefused):parse_seal(invalid, command, 1000, 1000)

    def test_request_cannot_rebind_inputs_purpose_durable_identity_or_legacy_protocol(self):
        seal, _, request, _ = fixture()
        for change in [{'protocol': 1}, {'protocol': True}, {'operation': INSTALLATION},
                       {'purpose': 'native_upgrade_execution'}, {'durable_binding_sha256': 'b'*64},
                       {'files': {}}, {'program': 'arbitrary'}]:
            with self.assertRaises(OperationInputsRefused):parse_request(canonical(dict(request, **change)), seal)

    def test_invalid_or_unimplemented_command_refuses_before_scope_or_input_reads(self):
        _, command, _, _ = fixture()
        with patch('native_operation_inputs.NativeControllerScope') as scope, patch('native_operation_inputs.root_file') as read:
            for action in ['status', 'backup', 'restore', 'export', 'retire']:
                value = {'protocol': 2, 'kind': 'native_controller_command', 'installation': INSTALLATION, 'action': action}
                if action != 'status':value.update(operation=OPERATION, request_sha256='a'*64)
                with self.assertRaises(OperationInputsRefused):NativeOperationInputs(INSTALLATION, canonical(value)+b'\n')
            with self.assertRaises(OperationInputsRefused):NativeOperationInputs(INSTALLATION, canonical(command))
            scope.assert_not_called();read.assert_not_called()


@unittest.skipUnless(sys.platform == 'linux' and os.getuid() > 0, 'Actual ordinary Linux input descriptors')
class PrivateInputCustodyTest(unittest.TestCase):
    def setUp(self):
        self.fixture = tempfile.TemporaryDirectory();self.addCleanup(self.fixture.cleanup)
        self.directory = Path(self.fixture.name);self.directory.chmod(0o700)
        self.seal, _, _, self.raw = fixture()
        for name, value in self.raw.items():
            path = self.directory/name;path.write_bytes(value);path.chmod(0o600)
            info = path.stat()
            self.seal['files'][name] = {
                'device': info.st_dev, 'inode': info.st_ino, 'bytes': info.st_size,
                'uid': info.st_uid, 'gid': info.st_gid, 'mode': info.st_mode,
                'links': info.st_nlink, 'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns,
                'sha256': hashlib.sha256(value).hexdigest()}
        info = self.directory.stat()
        self.expected = {'device': info.st_dev, 'inode': info.st_ino, 'uid': os.getuid()}

    def reader(self, **changes):
        arguments = {'directory': self.directory, 'uid': os.getuid(), 'gid': os.getgid(),
                     'expected': self.expected, 'files': self.seal['files'],
                     'policy': POLICIES[self.seal['purpose']]['files']}
        arguments.update(changes)
        value = _PrivateInputSet(**arguments);self.addCleanup(value.close);return value

    def test_original_descriptors_and_detached_bytes_remain_current_and_close_retains_files(self):
        reader = self.reader();value = reader.check();value.clear()
        self.assertEqual(reader.check(), self.raw)
        originals = {name: (self.directory/name).stat() for name in self.raw}
        reader.close();reader.close()
        self.assertEqual(reader.descriptors, {});self.assertIsNone(reader.directory_fd)
        for name, before in originals.items():
            after = (self.directory/name).stat()
            self.assertEqual((before.st_dev, before.st_ino, before.st_ctime_ns), (after.st_dev, after.st_ino, after.st_ctime_ns))

    def test_same_bytes_inode_replacement_poison_cannot_be_revived(self):
        reader = self.reader();path = self.directory/'inputs.json'
        original = path.with_name('retained.json');path.rename(original)
        path.write_bytes(self.raw['inputs.json']);path.chmod(0o600)
        with self.assertRaises(OperationInputsRefused):reader.check()
        path.unlink();original.rename(path)
        with self.assertRaises(OperationInputsRefused):reader.check()
        self.assertEqual(path.read_bytes(), self.raw['inputs.json'])

    def test_same_inode_same_bytes_rewrite_poison(self):
        reader = self.reader();path = self.directory/'inputs.json'
        before = path.stat();path.write_bytes(self.raw['inputs.json'])
        self.assertEqual(before.st_ino, path.stat().st_ino)
        with self.assertRaises(OperationInputsRefused):reader.check()

    def test_permissions_lost_then_restored_do_not_revive(self):
        reader = self.reader();path = self.directory/'inputs.json';path.chmod(0o644)
        with self.assertRaises(OperationInputsRefused):reader.check()
        path.chmod(0o600)
        with self.assertRaises(OperationInputsRefused):reader.check()

    def test_fresh_reader_cannot_adopt_replaced_file_with_same_approved_bytes(self):
        path = self.directory/'inputs.json'
        original = self.directory.with_name(self.directory.name+'-original-input')
        path.rename(original)
        try:
            path.write_bytes(self.raw['inputs.json']);path.chmod(0o600)
            with self.assertRaises(OperationInputsRefused):self.reader()
        finally:
            path.unlink();original.rename(path)

    def test_fresh_reader_cannot_adopt_same_inode_rewrite_after_root_sealing(self):
        path = self.directory/'inputs.json';path.write_bytes(self.raw['inputs.json'])
        with self.assertRaises(OperationInputsRefused):self.reader()

    def test_symlink_hardlink_and_fifo_refuse_without_opening_other_files(self):
        path = self.directory/'inputs.json';original = path.with_name('retained.json');path.rename(original)
        for kind in ['symlink', 'hardlink', 'fifo']:
            if kind == 'symlink':path.symlink_to(original)
            elif kind == 'hardlink':os.link(original, path)
            else:os.mkfifo(path, 0o600)
            # Extra retained node also refuses; remove it from the directory
            # through a distinct fixture parent to exercise the actual file.
            external = self.directory.with_name(self.directory.name+'-retained')
            original.rename(external)
            try:
                with self.assertRaises(OperationInputsRefused):self.reader()
            finally:
                external.rename(original);path.unlink()
        original.rename(path)

    def test_digest_size_identity_and_credentials_refuse_without_file_changes(self):
        for change in [{'uid': True}, {'uid': os.getuid()+1}, {'gid': os.getgid()+1},
                       {'expected': dict(self.expected, inode=self.expected['inode']+1)}]:
            with self.assertRaises(OperationInputsRefused):self.reader(**change)
        files = copy.deepcopy(self.seal['files']);files['inputs.json']['sha256'] = 'b'*64
        with self.assertRaises(OperationInputsRefused):self.reader(files=files)
        files['inputs.json'] = dict(self.seal['files']['inputs.json'], bytes=1)
        with self.assertRaises(OperationInputsRefused):self.reader(files=files)
        self.assertEqual({name: (self.directory/name).read_bytes() for name in self.raw}, self.raw)

    def test_directory_replacement_and_fork_cannot_adopt_original_descriptors(self):
        reader = self.reader();pid = os.fork()
        if pid == 0:
            try:reader.check()
            except OperationInputsRefused:os._exit(0)
            os._exit(1)
        _, status = os.waitpid(pid, 0);self.assertEqual(os.waitstatus_to_exitcode(status), 0)
        reader.check()
        original = self.directory.with_name(self.directory.name+'-original');self.directory.rename(original)
        self.directory.mkdir(mode=0o700)
        try:
            with self.assertRaises(OperationInputsRefused):reader.check()
        finally:
            self.directory.rmdir();original.rename(self.directory)
        with self.assertRaises(OperationInputsRefused):reader.check()


if __name__ == '__main__':
    unittest.main()
