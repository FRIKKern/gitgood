import json
import os
import socket
import sys
import threading
import time
import unittest

from native_command_wire import (CommandWireRefused, MAXIMUM, MUTATIONS,
                                 decode_command, receive_command)

INSTALLATION = 'f053c00f-1076-43ea-b510-2c6aabbbf79b'
OPERATION = 'a61c988b-633a-4d6e-969b-6940399b08fe'


def command(action='status'):
    value = {'protocol': 2, 'kind': 'native_controller_command',
             'installation': INSTALLATION, 'action': action}
    if action != 'status':
        value.update(operation=OPERATION, request_sha256='a'*64)
    return value


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode() + b'\n'


class CommandDecoderTest(unittest.TestCase):
    def test_all_fixed_actions_and_detached_request(self):
        for action in MUTATIONS | {'status'}:
            original = command(action)
            decoded = decode_command(encode(original), INSTALLATION)
            self.assertEqual(decoded, original)
            decoded['action'] = 'changed'
            self.assertEqual(original['action'], action)

    def test_unknown_action_paths_programs_and_environment_refuse(self):
        cases = [dict(command(), action=action) for action in ['shell', 'bash', 'provider', 'restart', '../retire']]
        cases += [dict(command('upgrade'), **{name: '/untrusted'}) for name in ['path', 'program', 'env', 'inputs', 'argv']]
        for value in cases:
            with self.assertRaises(CommandWireRefused):
                decode_command(encode(value), INSTALLATION)

    def test_mutation_requires_exact_original_operation_and_digest(self):
        for name in ['operation', 'request_sha256']:
            value = command('upgrade'); del value[name]
            with self.assertRaises(CommandWireRefused):
                decode_command(encode(value), INSTALLATION)
        for value in [True, 0, None, '', 'A'*64, 'a'*63, 'a'*65]:
            with self.assertRaises(CommandWireRefused):
                decode_command(encode(dict(command('upgrade'), request_sha256=value)), INSTALLATION)

    def test_uuid_aliases_and_cross_installation_refuse(self):
        for value in ['0'*32, INSTALLATION.upper(), INSTALLATION.replace('-', ''), True, None]:
            with self.assertRaises(CommandWireRefused):
                decode_command(encode(dict(command(), installation=value)), INSTALLATION)
        for value in ['00000000-0000-0000-0000-000000000000', OPERATION.upper(), True, None]:
            with self.assertRaises(CommandWireRefused):
                decode_command(encode(dict(command('retire'), operation=value)), INSTALLATION)

    def test_type_aliases_unknown_fields_and_duplicate_keys_refuse(self):
        cases = [encode(dict(command(), protocol=value)) for value in [True, 2.0, '2']]
        cases += [encode(dict(command(), kind='other')), encode(dict(command(), operation=OPERATION))]
        cases += [encode(command()).replace(b'"protocol":2', b'"protocol":2,"protocol":2')]
        for raw in cases:
            with self.assertRaises(CommandWireRefused):
                decode_command(raw, INSTALLATION)

    def test_noncanonical_incomplete_multiple_and_overlong_frames_refuse(self):
        valid = encode(command())
        cases = [valid[:-1], valid+b'\n', valid+valid, valid.replace(b'\n', b'\r\n'),
                 b' '+valid, valid.replace(b'"action":', b'"action": '), b'\0'+valid,
                 b'\xff\n', b'{}\n', b'[]\n', b'x'*(MAXIMUM+1), valid.decode()]
        for raw in cases:
            with self.assertRaises(CommandWireRefused):
                decode_command(raw, INSTALLATION)


@unittest.skipUnless(sys.platform == 'linux' and os.getuid() > 0, 'Actual ordinary Linux peer credentials')
class KernelCommandWireTest(unittest.TestCase):
    def pair(self):
        server, client = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(server.close); self.addCleanup(client.close)
        return server, client

    def test_actual_peer_credentials_and_original_timeout(self):
        server, client = self.pair(); server.settimeout(0.75)
        client.sendall(encode(command('backup'))); client.shutdown(socket.SHUT_WR)
        result = receive_command(server, installation=INSTALLATION, uid=os.getuid())
        self.assertEqual(result['request'], command('backup'))
        self.assertEqual(result['peer'], {'pid': os.getpid(), 'uid': os.getuid(), 'gid': os.getgid()})
        self.assertEqual(server.gettimeout(), 0.75)
        self.assertGreaterEqual(server.fileno(), 0)

    def test_actual_wrong_peer_uid_root_and_boolean_expected_uid_refuse(self):
        for uid in [os.getuid()+1, 0, True]:
            server, client = self.pair()
            client.sendall(encode(command())); client.shutdown(socket.SHUT_WR)
            with self.assertRaises(CommandWireRefused):
                receive_command(server, installation=INSTALLATION, uid=uid)
            self.assertEqual(server.fileno(), -1)

    def test_segmented_frame_is_read_through_eof(self):
        server, client = self.pair(); raw = encode(command('restore'))
        client.sendall(raw[:17])
        def finish():
            time.sleep(0.02)
            client.sendall(raw[17:]); client.shutdown(socket.SHUT_WR)
        writer = threading.Thread(target=finish); writer.start()
        self.addCleanup(writer.join, 3)
        result = receive_command(server, installation=INSTALLATION, uid=os.getuid())
        self.assertEqual(result['request'], command('restore'))

    def test_incremental_input_cannot_renew_absolute_deadline(self):
        server, client = self.pair(); raw = encode(command())
        client.sendall(raw[:1])
        def continue_input():
            time.sleep(1)
            try: client.sendall(raw[1:])
            except OSError: pass
        writer = threading.Thread(target=continue_input); writer.start()
        self.addCleanup(writer.join, 3)
        started = time.monotonic()
        with self.assertRaises(CommandWireRefused):
            receive_command(server, installation=INSTALLATION, uid=os.getuid())
        elapsed = time.monotonic()-started
        self.assertGreaterEqual(elapsed, 1.8)
        self.assertLess(elapsed, 2.8)
        self.assertEqual(server.fileno(), -1)

    def test_no_half_close_times_out_and_poisons_original_connection(self):
        server, client = self.pair(); client.sendall(encode(command()))
        started = time.monotonic()
        with self.assertRaises(CommandWireRefused):
            receive_command(server, installation=INSTALLATION, uid=os.getuid())
        self.assertGreaterEqual(time.monotonic()-started, 1.8)
        self.assertEqual(server.fileno(), -1)

    def test_multiple_frames_empty_eof_and_oversize_poison_connection(self):
        for raw in [encode(command())*2, b'', b'x'*(MAXIMUM+1)]:
            server, client = self.pair(); client.sendall(raw); client.shutdown(socket.SHUT_WR)
            with self.assertRaises(CommandWireRefused):
                receive_command(server, installation=INSTALLATION, uid=os.getuid())
            self.assertEqual(server.fileno(), -1)

    def test_actual_datagram_and_inet_socket_refuse(self):
        server, client = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.addCleanup(server.close); self.addCleanup(client.close)
        inet = socket.socket(socket.AF_INET, socket.SOCK_STREAM); self.addCleanup(inet.close)
        for connection in [server, inet]:
            with self.assertRaises(CommandWireRefused):
                receive_command(connection, installation=INSTALLATION, uid=os.getuid())
            self.assertEqual(connection.fileno(), -1)


if __name__ == '__main__':
    unittest.main()
