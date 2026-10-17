"""Closed netlink framing tests and actual Linux loopback/descriptor checks."""
import os
from pathlib import Path
import socket
import struct
import sys
import time
import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock,patch

import native_ownership_database as database
from native_durable_database import DatabaseRefused


def reply(sequence=9,port_id=123,uid=1000,client=23456,server=54321,inode=345):
    loopback=socket.inet_pton(socket.AF_INET,'127.0.0.1')+bytes(12)
    identity=struct.pack('!HH',client,server)+loopback+loopback+struct.pack('=III',0,1,2)
    body=struct.pack('=BBBB',socket.AF_INET,1,0,0)+identity+struct.pack('=IIIII',0,0,0,uid,inode)
    return struct.pack('=IHHII',88,20,0,sequence,port_id)+body


class TcpSocketReplyTest(unittest.TestCase):
    def decode(self,raw):
        return database._tcp_socket_reply(raw,9,123,1000,23456,54321)

    def test_exact_kernel_identity_and_bounded_unknown_attributes(self):
        raw=reply();self.assertEqual(self.decode(raw),'345')
        extra=struct.pack('=HHI',8,99,1234)
        changed=struct.pack('=I',len(raw)+len(extra))+raw[4:]+extra
        self.assertEqual(self.decode(changed),'345')

    def test_wrong_sequence_recipient_uid_ports_or_absent_inode_refuse(self):
        for raw in [reply(sequence=10),reply(port_id=124),reply(uid=1001),reply(client=23457),
                reply(server=54322),reply(inode=0)]:
            with self.subTest(raw=raw),self.assertRaises(DatabaseRefused):self.decode(raw)

    def test_foreign_family_state_addresses_or_bound_device_refuse(self):
        for offset,data in [(16,bytes([socket.AF_INET6])),(17,b'\x08'),
                (24,b'\x7f\x00\x00\x02'),(40,b'\x7f\x00\x00\x02'),(56,struct.pack('=I',2))]:
            raw=bytearray(reply());raw[offset:offset+len(data)]=data
            with self.subTest(offset=offset),self.assertRaises(DatabaseRefused):self.decode(bytes(raw))

    def test_error_dump_multipart_truncation_excess_and_trailing_messages_refuse(self):
        for raw in [b'',reply()[:87],reply()+reply(),reply()+b'\x00',reply()+bytes(4096),
                reply()[:4]+struct.pack('=HH',2,0)+reply()[8:],
                reply()[:6]+struct.pack('=H',2)+reply()[8:]]:
            with self.subTest(length=len(raw)),self.assertRaises(DatabaseRefused):self.decode(raw)

    def test_attribute_framing_duplicate_bounds_and_padding_refuse(self):
        for extra in [b'x',struct.pack('=HH',3,8),struct.pack('=HH',8,8),
                struct.pack('=HHI',8,8,0)*2,
                struct.pack('=HHB',5,8,0)+b'\x01\x00\x00',
                b''.join(struct.pack('=HH',4,index) for index in range(1,66))]:
            raw=reply();raw=struct.pack('=I',len(raw)+len(extra))+raw[4:]+extra
            with self.subTest(length=len(extra)),self.assertRaises(DatabaseRefused):self.decode(raw)


class TcpSocketTransportTest(unittest.TestCase):
    """Explicit transport stand-in; kernel authentication needs Linux cases."""
    def observer(self):
        view=MagicMock();view.__enter__.return_value=view
        view.getsockname.return_value=(123,0);view.sendto.side_effect=lambda raw,_:len(raw)
        view.recvmsg.return_value=(reply(),[],0,(0,0))
        return view

    def query(self,view):
        with patch.object(database.socket,'AF_NETLINK',16,create=True), \
                patch.object(database.socket,'socket',return_value=view), \
                patch.object(database.os,'urandom',return_value=struct.pack('=I',9)):
            return database._tcp_socket_inode(1000,23456,54321)

    def test_read_only_exact_tuple_request_has_no_dump_or_destroy_and_closes_transport(self):
        view=self.observer();self.assertEqual(self.query(view),'345')
        raw,address=view.sendto.call_args.args
        self.assertEqual(address,(0,0));self.assertEqual(len(raw),72)
        self.assertEqual(struct.unpack_from('=IHHII',raw),(72,20,1,9,123))
        self.assertEqual(struct.unpack_from('=BBBBI',raw,16),(socket.AF_INET,socket.IPPROTO_TCP,0,0,2))
        self.assertEqual(struct.unpack_from('!HH',raw,24),(23456,54321))
        self.assertEqual(struct.unpack_from('=III',raw,60),(0,2**32-1,2**32-1))
        view.bind.assert_called_once_with((0,0));view.settimeout.assert_called_once_with(2)
        view.recvmsg.assert_called_once_with(4096);view.__exit__.assert_called_once()

    def test_non_kernel_sender_ancillary_or_truncated_transport_never_returns_identity(self):
        for received in [(reply(),[],0,(999,0)),(reply(),[],0,(0,1)),
                (reply(),[('foreign','private')],0,(0,0)),(reply(),[],socket.MSG_TRUNC,(0,0))]:
            view=self.observer();view.recvmsg.return_value=received
            with self.subTest(received=received),self.assertRaises(DatabaseRefused):self.query(view)
            view.__exit__.assert_called_once()

    def test_short_send_timeout_or_missing_reply_cannot_fall_back_to_table_scan(self):
        for stage in ('send','timeout','empty'):
            view=self.observer()
            if stage=='send':view.sendto.side_effect=None;view.sendto.return_value=71
            elif stage=='timeout':view.recvmsg.side_effect=TimeoutError('transport stand-in')
            else:view.recvmsg.return_value=(b'',[],0,(0,0))
            with self.subTest(stage=stage),self.assertRaises((DatabaseRefused,TimeoutError)):self.query(view)
            view.__exit__.assert_called_once()

    def test_invalid_tuple_refuses_before_transport_creation(self):
        for uid,client,server in [(True,23456,54321),(-1,23456,54321),(1000,True,54321),
                (1000,0,54321),(1000,23456,65536)]:
            with patch.object(database.socket,'socket') as create,self.subTest(uid=uid,client=client,server=server):
                with self.assertRaises(DatabaseRefused):database._tcp_socket_inode(uid,client,server)
                create.assert_not_called()


@unittest.skipUnless(sys.platform=='linux' and hasattr(socket,'AF_NETLINK'),'Actual Linux SOCK_DIAG and procfs descriptors')
class ActualTcpSocketObservationTest(unittest.TestCase):
    def connection(self):
        stack=ExitStack();self.addCleanup(stack.close)
        listener=stack.enter_context(socket.socket(socket.AF_INET,socket.SOCK_STREAM))
        listener.bind(('127.0.0.1',0));listener.listen(1);listener.settimeout(2)
        client=stack.enter_context(socket.socket(socket.AF_INET,socket.SOCK_STREAM))
        client.settimeout(2);client.connect(listener.getsockname())
        server,_=listener.accept();stack.enter_context(server)
        return client,client.getsockname()[1],listener.getsockname()[1]

    def observe(self,client_port,server_port):
        return database._socket_for_process(Path('/proc')/str(os.getpid()),
            os.readlink('/proc/self/ns/net'),os.getuid(),client_port,server_port)

    def test_fresh_kernel_queries_match_original_actual_socket_descriptor(self):
        client,client_port,server_port=self.connection()
        original={'network_namespace':os.readlink('/proc/self/ns/net'),
            'socket_inode':str(os.fstat(client.fileno()).st_ino),'descriptor':str(client.fileno()),
            'client_port':client_port,'server_port':server_port}
        started=time.monotonic()
        with patch.object(database,'_tcp_socket_inode',wraps=database._tcp_socket_inode) as query:
            for _ in range(20):self.assertEqual(self.observe(client_port,server_port),original)
            self.assertEqual(query.call_count,20)
        print('actual_tcp_socket_observation_queries=20 elapsed_ms='+str(int((time.monotonic()-started)*1000)))

    def test_original_socket_closure_refuses_instead_of_returning_cached_identity(self):
        client,client_port,server_port=self.connection();self.observe(client_port,server_port);client.close()
        with self.assertRaises((DatabaseRefused,OSError)):self.observe(client_port,server_port)

    def test_duplicate_original_descriptor_refuses_ambiguous_process_ownership(self):
        client,client_port,server_port=self.connection();duplicate=os.dup(client.fileno())
        try:
            with self.assertRaises(DatabaseRefused):self.observe(client_port,server_port)
        finally:os.close(duplicate)
        self.assertEqual(self.observe(client_port,server_port)['descriptor'],str(client.fileno()))

    def test_wrong_uid_or_endpoint_cannot_be_adopted(self):
        _,client_port,server_port=self.connection()
        with self.assertRaises(DatabaseRefused):database._tcp_socket_inode(os.getuid()+1,client_port,server_port)
        with self.assertRaises(DatabaseRefused):database._tcp_socket_inode(os.getuid(),client_port,0 if server_port==65535 else server_port+1)

    def test_foreign_namespace_refuses_before_kernel_query(self):
        _,client_port,server_port=self.connection()
        with patch.object(database,'_tcp_socket_inode') as query,self.assertRaises(DatabaseRefused):
            database._socket_for_process(Path('/proc')/str(os.getpid()),'net:[foreign]',os.getuid(),client_port,server_port)
        query.assert_not_called()


if __name__=='__main__':unittest.main()
