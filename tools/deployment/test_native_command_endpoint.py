import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from native_command_endpoint import CommandEndpointRefused, NativeCommandEndpoint, _OwnedCommandEndpoint
from native_command_wire import CommandWireRefused, receive_command
from native_controller_scope import ControllerScopeRefused, NativeControllerScope

INSTALLATION = 'f053c00f-1076-43ea-b510-2c6aabbbf79b'


def frame(action='status'):
    value = {'protocol': 2, 'kind': 'native_controller_command', 'installation': INSTALLATION, 'action': action}
    if action != 'status':
        value.update(operation='a61c988b-633a-4d6e-969b-6940399b08fe', request_sha256='a'*64)
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode() + b'\n'


class UnsupportedEndpointTest(unittest.TestCase):
    def test_unsupported_platform_refuses_before_seal_or_socket(self):
        with patch('native_controller_scope.sys.platform', 'win32'), patch('native_controller_scope.root_file') as read, patch('native_command_endpoint.socket.socket') as create:
            with self.assertRaises(CommandEndpointRefused):
                NativeCommandEndpoint(INSTALLATION)
            read.assert_not_called()
            create.assert_not_called()

    def test_invalid_identifier_refuses_without_private_input_or_socket(self):
        with patch('native_controller_scope.root_file') as read, patch('native_command_endpoint.socket.socket') as create:
            for identity in [True, None, '../outside', INSTALLATION.upper(), '00000000-0000-0000-0000-000000000000']:
                with self.assertRaises(CommandEndpointRefused):
                    NativeCommandEndpoint(identity)
            read.assert_not_called()
            create.assert_not_called()


@unittest.skipUnless(sys.platform == 'linux' and os.getuid() > 0, 'Actual ordinary Linux pathname listener')
class OwnedEndpointTest(unittest.TestCase):
    def setUp(self):
        self.fixture = tempfile.TemporaryDirectory()
        self.addCleanup(self.fixture.cleanup)
        self.directory = Path(self.fixture.name)
        self.directory.chmod(0o700)
        info = self.directory.stat()
        self.expected = {'device': info.st_dev, 'inode': info.st_ino, 'uid': os.getuid()}

    def endpoint(self):
        value = _OwnedCommandEndpoint(self.directory, INSTALLATION, os.getuid(), os.getgid(), self.expected)
        self.addCleanup(value.close)
        return value

    def client(self, raw=None):
        value = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(value.close)
        value.connect(str(self.directory/'controller.sock'))
        value.sendall(frame() if raw is None else raw)
        value.shutdown(socket.SHUT_WR)
        return value

    def test_actual_listener_directory_descriptor_peer_and_retained_close(self):
        endpoint = self.endpoint()
        before = (self.directory/'controller.sock').lstat()
        self.assertEqual(before.st_mode & 0o777, 0o600)
        self.client(frame('backup'))
        with endpoint.accept(.25) as connection:
            value = receive_command(connection, installation=INSTALLATION, uid=os.getuid())
        self.assertEqual(value['peer'], {'pid': os.getpid(), 'uid': os.getuid(), 'gid': os.getgid()})
        self.assertEqual(value['request']['action'], 'backup')
        endpoint.check()
        endpoint.close()
        after = (self.directory/'controller.sock').lstat()
        self.assertEqual((before.st_dev, before.st_ino, before.st_ctime_ns), (after.st_dev, after.st_ino, after.st_ctime_ns))
        with self.assertRaises(CommandEndpointRefused):
            endpoint.check()

    def test_stale_node_refuses_without_unlink_or_chmod(self):
        old = self.directory/'controller.sock'
        old.write_bytes(b'retained original stale fixture')
        old.chmod(0o600)
        before = old.stat()
        with self.assertRaises(CommandEndpointRefused):
            self.endpoint()
        after = old.stat()
        self.assertEqual(old.read_bytes(), b'retained original stale fixture')
        self.assertEqual((before.st_dev, before.st_ino, before.st_ctime_ns, before.st_mode), (after.st_dev, after.st_ino, after.st_ctime_ns, after.st_mode))

    def test_replaced_socket_poison_preserves_original_and_foreign_listener(self):
        endpoint = self.endpoint()
        original = self.directory/'original.sock'
        (self.directory/'controller.sock').rename(original)
        replacement = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(replacement.close)
        replacement.bind(str(self.directory/'controller.sock'))
        (self.directory/'controller.sock').chmod(0o600)
        replacement.listen(1)
        before = (self.directory/'controller.sock').lstat()
        with self.assertRaises(CommandEndpointRefused):
            endpoint.accept(.25)
        self.assertTrue(original.exists())
        self.assertEqual(replacement.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN), 1)
        after = (self.directory/'controller.sock').lstat()
        self.assertEqual((before.st_dev, before.st_ino, before.st_ctime_ns), (after.st_dev, after.st_ino, after.st_ctime_ns))
        # Removing the replacement in this private fixture cannot revive the
        # endpoint. Product code never performs these reconciliation effects.
        (self.directory/'controller.sock').unlink()
        original.rename(self.directory/'controller.sock')
        with self.assertRaises(CommandEndpointRefused):
            endpoint.check()

    def test_replaced_directory_and_symlink_refuse_without_adopting(self):
        endpoint = self.endpoint()
        original = self.directory.with_name(self.directory.name+'-original')
        self.directory.rename(original)
        self.addCleanup(lambda: original.rename(self.directory))
        self.directory.symlink_to(original, target_is_directory=True)
        self.addCleanup(self.directory.unlink)
        with self.assertRaises(CommandEndpointRefused):
            endpoint.check()
        self.assertTrue((original/'controller.sock').exists())

    def test_permission_loss_poison_remains_after_restore(self):
        for target in ['socket', 'directory']:
            with self.subTest(target=target), tempfile.TemporaryDirectory() as folder:
                directory = Path(folder);directory.chmod(0o700);info=directory.stat()
                endpoint = _OwnedCommandEndpoint(directory, INSTALLATION, os.getuid(), os.getgid(), {'device':info.st_dev,'inode':info.st_ino,'uid':os.getuid()})
                self.addCleanup(endpoint.close)
                path=directory/'controller.sock' if target=='socket' else directory
                path.chmod(0o644 if target=='socket' else 0o755)
                with self.assertRaises(CommandEndpointRefused):endpoint.check()
                path.chmod(0o600 if target=='socket' else 0o700)
                with self.assertRaises(CommandEndpointRefused):endpoint.check()

    def test_malformed_client_closes_only_connection_and_accepts_next(self):
        endpoint = self.endpoint()
        self.client(frame()+frame())
        with endpoint.accept(.25) as connection:
            with self.assertRaises(CommandWireRefused):
                receive_command(connection, installation=INSTALLATION, uid=os.getuid())
            self.assertEqual(connection.fileno(), -1)
        endpoint.check()
        self.client()
        with endpoint.accept(.25) as connection:
            self.assertEqual(receive_command(connection, installation=INSTALLATION, uid=os.getuid())['request']['action'], 'status')

    def test_accept_deadline_bounds_and_no_connection_leave_listener_current(self):
        endpoint = self.endpoint()
        for timeout in [True, None, 0, -1, float('inf'), float('nan'), 2.01]:
            with self.assertRaises(CommandEndpointRefused):endpoint.accept(timeout)
        self.assertIsNone(endpoint.accept(.01))
        endpoint.check()

    def test_fork_cannot_borrow_controller_descriptor_custody(self):
        endpoint=self.endpoint()
        pid=os.fork()
        if pid==0:
            try:endpoint.check()
            except CommandEndpointRefused:os._exit(0)
            os._exit(1)
        _,status=os.waitpid(pid,0)
        self.assertEqual(os.waitstatus_to_exitcode(status),0)
        endpoint.check()

    def test_wrong_directory_identity_or_credentials_refuse_before_binding(self):
        for expected,uid,gid in [(dict(self.expected,inode=self.expected['inode']+1),os.getuid(),os.getgid()),(self.expected,True,os.getgid()),(self.expected,os.getuid()+1,os.getgid()),(self.expected,os.getuid(),os.getgid()+1)]:
            with self.assertRaises(CommandEndpointRefused):
                _OwnedCommandEndpoint(self.directory,INSTALLATION,uid,gid,expected)
            self.assertFalse((self.directory/'controller.sock').exists())


if __name__=='__main__':
    unittest.main()
