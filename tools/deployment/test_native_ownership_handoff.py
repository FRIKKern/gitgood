import copy
import os
import socket
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import native_ownership_handoff as handoff
from native_command_wire import receive_frame
from resource_generations import canonical
from test_native_ownership_records import fixture
from test_native_ownership_transition import next_record


class OwnershipHandoffWireTest(unittest.TestCase):
    def setUp(self):
        self.record=next_record();self.installation=self.record['installation']
        self.request={'protocol':4,'kind':'native_ownership_handoff','action':'admit',
            **{name:self.record[name] for name in ['installation','operation','candidate','mode']},
            'owner_pid':self.record['owner']['pid']}

    def test_closed_prepare_and_publish_preserve_exact_request(self):
        for request in [self.request,{'protocol':4,'kind':'native_ownership_handoff','action':'publish','record':self.record}]:
            self.assertEqual(handoff.decode_request(canonical(request)+b'\n',self.installation),request)

    def test_receipt_hash_or_authority_cannot_be_added_to_prepare(self):
        for key,value in [('receipt',{}),('reservation_sha256','a'*64),('controller',{}),('command','/bin/sh')]:
            with self.subTest(key=key),self.assertRaises(Exception):
                handoff.decode_request(canonical({**self.request,key:value})+b'\n',self.installation)

    def test_noncanonical_duplicate_oversized_extra_frames_and_aliases_refuse(self):
        valid=canonical(self.request)+b'\n'
        cases=[valid+valid,valid[:-1],b' '+valid,b'\n',b'x'*32769,
               canonical({**self.request,'owner_pid':True})+b'\n',
               canonical({**self.request,'protocol':True})+b'\n',
               canonical({**self.request,'candidate':'unconfigured'})+b'\n',
               b'{"protocol":4,"protocol":4}\n']
        for raw in cases:
            with self.subTest(raw=raw[:32]),self.assertRaises(Exception):handoff.decode_request(raw,self.installation)

    def test_legacy_record_does_not_silently_select_the_new_transport(self):
        request={'protocol':4,'kind':'native_ownership_handoff','action':'publish','record':fixture()}
        with self.assertRaises(Exception):handoff.decode_request(canonical(request)+b'\n',self.installation)


class OwnershipHandoffExchangeTest(unittest.TestCase):
    """Full client composition with explicit protected-file/service stand-ins."""
    def setUp(self):
        self.record=next_record();self.scope=self.record['scope'];self.events=[]
        self.captured={'admission':{'worker_observation':{'service_scope':self.scope}}}
        self.guard=SimpleNamespace(check=lambda:{'current':True})
        self.seal={'protocol':2,'kind':'native_controller_endpoint_seal','installation':self.record['installation'],
            'uid':self.scope['uid'],'gid':self.scope['gid'],'unit_sha256':self.scope['unit_definition']['sha256'],
            'directory_identity':{'device':1,'inode':2,'uid':self.scope['uid']},
            'limits':{name:self.scope['limits'][name] for name in ['cpu_quota_us','memory_bytes']}}
        self.request={'protocol':4,'kind':'native_ownership_handoff','action':'publish','record':self.record}
        self.reply={'protocol':4,'status':'refused'}
        test=self
        class Connection:
            def __enter__(self):return self
            def __exit__(self,*args):test.events.append('close')
            def settimeout(self,value):test.assertGreater(value,0);test.assertLessEqual(value,60)
            def connect(self,path):test.events.append(('connect',path))
            def sendall(self,raw):test.assertEqual(raw,canonical(test.request)+b'\n');test.events.append('send')
            def shutdown(self,how):test.assertEqual(how,socket.SHUT_WR)
            def recv(self,maximum):return canonical(test.reply)+b'\n'
        self.peer={'pid':self.scope['manager']['pid'],'uid':self.scope['uid'],'gid':self.scope['gid']}
        patches=[patch.object(handoff,'root_file',side_effect=lambda *args:({'inode':1},canonical(self.seal))),
            patch.object(handoff,'private_directory',side_effect=lambda *args:(self.seal['directory_identity'],())),
            patch.object(handoff,'_socket_identity',return_value=('fixed original socket',)),
            patch.object(handoff,'process_identity',side_effect=lambda *args:copy.deepcopy(self.scope['manager'])),
            patch.object(handoff,'_peer',side_effect=lambda *args:dict(self.peer)),
            patch.object(handoff.socket,'socket',return_value=Connection())]
        for value in patches:value.start();self.addCleanup(value.stop)

    def test_two_field_root_limits_admit_actual_four_field_service_observation(self):
        self.assertEqual(set(self.scope['limits']),{'cpu_quota_us','memory_bytes','cpu_period_us','swap_bytes'})
        self.assertEqual(handoff.exchange(self.request,self.guard,self.captured),self.reply)
        self.assertIn('send',self.events)

    def test_changed_quota_fixed_period_swap_or_extra_sealed_limit_refuses_before_connection(self):
        for name,value in [('cpu_quota_us',1),('cpu_period_us',50000),('swap_bytes',1)]:
            original=copy.deepcopy(self.scope['limits'])
            with self.subTest(name=name):
                self.scope['limits'][name]=value
                with self.assertRaises(Exception):handoff.exchange(self.request,self.guard,self.captured)
                self.assertFalse(self.events)
            self.scope['limits']=original
        self.seal['limits']['cpu_period_us']=100000
        with self.assertRaises(Exception):handoff.exchange(self.request,self.guard,self.captured)
        self.assertFalse(self.events)

    def test_wrong_actual_server_pid_or_changed_original_birth_refuses_before_send(self):
        self.peer['pid']+=1
        with self.assertRaises(Exception):handoff.exchange(self.request,self.guard,self.captured)
        self.assertNotIn('send',self.events)
        self.peer['pid']-=1;self.events.clear()
        with patch.object(handoff,'process_identity',return_value={**self.scope['manager'],'birth':'987654321'}):
            with self.assertRaises(Exception):handoff.exchange(self.request,self.guard,self.captured)
        self.assertNotIn('send',self.events)


@unittest.skipUnless(sys.platform=='linux' and os.getuid()!=0,'ordinary Linux peer credentials')
class OwnershipHandoffSocketTest(unittest.TestCase):
    def test_actual_half_closed_unix_socket_binds_kernel_peer_and_larger_closed_frame(self):
        record=next_record(uid=os.getuid());request={'protocol':4,'kind':'native_ownership_handoff','action':'publish','record':record}
        raw=canonical(request)+b'\n'
        first,second=socket.socketpair()
        try:
            first.sendall(raw);first.shutdown(socket.SHUT_WR)
            actual,peer=receive_frame(second,uid=os.getuid(),maximum=32768)
            self.assertEqual(peer,{'pid':os.getpid(),'uid':os.getuid(),'gid':os.getgid()})
            self.assertEqual(handoff.decode_request(actual,record['installation']),request)
            # Half closing requests still permits a bounded controller reply.
            second.sendall(b'{"protocol":4,"status":"refused"}\n')
            self.assertEqual(first.recv(128),b'{"protocol":4,"status":"refused"}\n')
        finally:first.close();second.close()

    def test_wrong_peer_account_closes_only_its_connection(self):
        first,second=socket.socketpair()
        try:
            with self.assertRaises(Exception):receive_frame(second,uid=os.getuid()+1,maximum=32768)
            self.assertEqual(second.fileno(),-1)
        finally:first.close();second.close()
