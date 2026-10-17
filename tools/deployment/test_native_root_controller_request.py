import copy
import json
import os
from pathlib import Path
import socket
import stat
import sys
import tempfile
import threading
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch

import native_root_controller_request as root
from upgrade_journal import fcntl
from resource_generations import canonical


class LockFdinfoTest(unittest.TestCase):
    identity = {'device':258,'inode':11691,'uid':1000}
    raw = b'pos:\t0\nflags:\t02000002\nmnt_id:\t19\nino:\t11691\nlock:\t1: FLOCK ADVISORY WRITE 359 01:02:11691 0 EOF\n'

    def parse(self, raw):
        # Explicit Linux device stand-ins for portable parser checks.
        with patch.object(root.os,'major',return_value=1,create=True), \
                patch.object(root.os,'minor',return_value=2,create=True):
            return root._held_lock(raw,359,self.identity)

    def test_exact_exclusive_original_descriptor_metadata_is_retained(self):
        value = self.parse(self.raw)
        self.assertEqual(dict(value)['lock'],('1:','FLOCK','ADVISORY','WRITE','359','01:02:11691','0','EOF'))

    def test_read_only_descriptor_cannot_substitute_for_controller_writer(self):
        with self.assertRaises(root.RootControllerRequestRefused):self.parse(self.raw.replace(b'02000002',b'02000000'))

    def test_only_read_write_access_is_admitted_without_optional_accmode_constant(self):
        flags = SimpleNamespace(O_WRONLY=1,O_RDWR=2,major=lambda _:1,minor=lambda _:2)
        self.assertFalse(hasattr(flags,'O_ACCMODE'))
        with patch.object(root,'os',flags):
            for extra in (0,0o2004000):
                for access in range(4):
                    raw=self.raw.replace(b'02000002',format(extra|access,'o').encode('ascii'))
                    with self.subTest(extra=extra,access=access):
                        if access == 2:self.assertEqual(dict(root._held_lock(raw,359,self.identity))['flags'],(format(extra|access,'o'),))
                        else:
                            with self.assertRaises(root.RootControllerRequestRefused):root._held_lock(raw,359,self.identity)

    def test_shared_foreign_process_or_non_whole_file_lock_refuses(self):
        for before,after in ((b'WRITE',b'READ'),(b'359',b'360'),(b'0 EOF',b'1 EOF'),(b'FLOCK',b'OFDLCK')):
            with self.subTest(after=after),self.assertRaises(root.RootControllerRequestRefused):self.parse(self.raw.replace(before,after))

    def test_foreign_device_or_inode_refuses(self):
        for before,after in ((b'01:02',b'02:02'),(b'01:02',b'01:03'),(b':11691',b':11692'),(b'ino:\t11691',b'ino:\t11692')):
            with self.subTest(after=after),self.assertRaises(root.RootControllerRequestRefused):self.parse(self.raw.replace(before,after))

    def test_duplicate_unknown_oversized_or_missing_lock_fields_refuse(self):
        for raw in (self.raw+b'ino:\t11691\n',self.raw+b'caller: authority\n',b'x'*8193,
                    self.raw.split(b'lock:')[0],self.raw.replace(b'lock:\t1:',b'lock:\t0:')):
            with self.assertRaises(root.RootControllerRequestRefused):self.parse(raw)


class RootRequestBoundaryTest(unittest.TestCase):
    def view(self):
        value = root.NativeRootControllerRequest.__new__(root.NativeRootControllerRequest)
        value.usable = True;value.owner = (os.getpid(),threading.get_ident())
        value.live = Mock();value.connection = Mock()
        value.observed = {'installation':'fixed','operation':'fixed-op','stage':'stage','recorded_status':'running'}
        value.scope = {'uid':1000,'gid':1000,'manager':{'pid':359}}
        value.peer = {'pid':359,'uid':1000,'gid':1000}
        value.descriptor = value.original_descriptor = 8
        value.socket_original = (1,2,stat.S_IFSOCK)
        value.original_lock = (('lock',('original',)),)
        value.live.check.return_value = copy.deepcopy(value.observed)
        value._socket = Mock(return_value=value.socket_original)
        value._lock = Mock(return_value=value.original_lock)
        return value

    def context(self, stack, value):
        for name in ('getuid','geteuid','getgid','getegid'):
            stack.enter_context(patch.object(root.os,name,return_value=0,create=True))
        return stack.enter_context(patch.object(root,'_peer',return_value=copy.deepcopy(value.peer)))

    def test_invalid_identifiers_or_non_root_refuse_before_live_resources_and_close_socket(self):
        installation='00000000-0000-4000-8000-000000000001'
        operation='00000000-0000-4000-8000-000000000002'
        with patch.object(root,'NativeRootLiveBindingObservation') as live:
            for invalid in (None,'../caller',True,installation):
                connection,other=socket.socketpair()
                try:
                    with self.assertRaises(root.RootControllerRequestRefused):root.NativeRootControllerRequest(invalid,installation,connection)
                    self.assertEqual(connection.fileno(),-1)
                finally:connection.close();other.close()
            connection,other=socket.socketpair()
            try:
                with patch.object(root.os,'getuid',return_value=1000,create=True),self.assertRaises(root.RootControllerRequestRefused):
                    root.NativeRootControllerRequest(installation,operation,connection)
                self.assertEqual(connection.fileno(),-1)
            finally:connection.close();other.close()
            live.assert_not_called()

    def test_peer_and_lock_are_bracketed_by_original_live_view_without_effect_grant(self):
        value=self.view()
        with ExitStack() as stack:
            peer=self.context(stack,value);observed=value.check()
            self.assertEqual(value.live.check.call_count,2);self.assertEqual(peer.call_count,2)
            value._lock.assert_called_once_with()
        self.assertTrue(observed['original_controller_peer_authenticated'])
        self.assertTrue(observed['original_controller_history_lock_observed'])
        for name in ('database_writer_exclusion_verified','lifecycle_exclusion_established','stage_effect_authorized','complete_journey_acceptance'):
            self.assertIs(observed[name],False)
        self.assertFalse({'peer','history_lock_fd','lock','scope','binding'} & set(observed))

    def test_same_account_foreign_pid_refuses_before_lock_and_permanently_poisons(self):
        value=self.view()
        with ExitStack() as stack:
            peer=self.context(stack,value);peer.return_value['pid']=360
            with self.assertRaises(root.RootControllerRequestRefused):value.check()
            value._lock.assert_not_called();value.connection.close.assert_called_once_with();value.live.close.assert_called_once_with()
            peer.return_value=value.peer
            with self.assertRaises(root.RootControllerRequestRefused):value.check()
            value._lock.assert_not_called()

    def test_observed_lock_loss_cannot_be_replaced_with_a_later_matching_lock(self):
        value=self.view()
        with ExitStack() as stack:
            self.context(stack,value);value._lock.return_value=()
            with self.assertRaises(root.RootControllerRequestRefused):value.check()
            value._lock.return_value=value.original_lock
            with self.assertRaises(root.RootControllerRequestRefused):value.check()
            self.assertEqual(value._lock.call_count,1)

    def test_live_history_change_refuses_before_peer_or_lock(self):
        value=self.view()
        with ExitStack() as stack:
            peer=self.context(stack,value);value.live.check.return_value={'changed':'history'}
            with self.assertRaises(root.RootControllerRequestRefused):value.check()
            peer.assert_not_called();value._lock.assert_not_called()

    def test_descriptor_change_or_wrong_thread_refuses_before_live_observation(self):
        for changed in ('descriptor','owner'):
            value=self.view()
            if changed=='descriptor':value.descriptor=9
            else:value.owner=(os.getpid(),threading.get_ident()+1)
            with ExitStack() as stack:
                self.context(stack,value)
                with self.assertRaises(root.RootControllerRequestRefused):value.check()
                value.live.check.assert_not_called();value._lock.assert_not_called()


class RootRequestFrameTest(unittest.TestCase):
    installation='00000000-0000-4000-8000-000000000001'
    operation='00000000-0000-4000-8000-000000000002'

    def frame(self):
        return {'protocol':2,'kind':'native_root_controller_request','installation':self.installation,
            'operation':self.operation,'history_lock_fd':8}

    def construct(self, raw):
        connection,other=socket.socketpair();self.addCleanup(connection.close);self.addCleanup(other.close)
        peer={'pid':359,'uid':1000,'gid':1000}
        live=Mock();live.scope={'uid':1000,'gid':1000,'manager':{'pid':359}}
        live.check.return_value={'installation':self.installation,'operation':self.operation,'stage':'stage'}
        with ExitStack() as stack:
            for name in ('getuid','geteuid','getgid','getegid'):
                stack.enter_context(patch.object(root.os,name,return_value=0,create=True))
            stack.enter_context(patch.object(root,'NativeRootLiveBindingObservation',return_value=live))
            stack.enter_context(patch.object(root,'_peer',return_value=peer))
            stack.enter_context(patch.object(root.NativeRootControllerRequest,'_socket',return_value=(1,2,stat.S_IFSOCK)))
            receive=stack.enter_context(patch.object(root,'receive_frame',return_value=(raw,peer)))
            observe=stack.enter_context(patch.object(root.NativeRootControllerRequest,'_lock',return_value=('original',)))
            try:value=root.NativeRootControllerRequest(self.installation,self.operation,connection)
            except root.RootControllerRequestRefused:
                self.assertEqual(connection.fileno(),-1);live.close.assert_called_once_with()
                observe.assert_not_called();raise
            receive.assert_called_once_with(connection,uid=1000,maximum=512)
            self.assertEqual(live.check.call_count,4)
            return value

    def test_only_canonical_closed_operation_reference_and_descriptor_frame_is_admitted(self):
        value=self.construct(canonical(self.frame())+b'\n')
        self.assertEqual(value.descriptor,value.original_descriptor);self.assertEqual(value.descriptor,8)
        value.close()

    def test_caller_authority_wrong_operation_boolean_descriptor_and_noncanonical_data_refuse(self):
        values=[dict(self.frame(),authority=True),dict(self.frame(),operation=self.installation),
            dict(self.frame(),protocol=True),dict(self.frame(),history_lock_fd=True),
            dict(self.frame(),history_lock_fd=2),dict(self.frame(),history_lock_fd=1048576)]
        raw=[canonical(value)+b'\n' for value in values]
        raw += [canonical(self.frame()),canonical(self.frame())+b'\n\n',json.dumps(self.frame()).encode()+b'\n']
        for frame in raw:
            with self.subTest(frame=frame),self.assertRaises(root.RootControllerRequestRefused):self.construct(frame)


@unittest.skipUnless(sys.platform=='linux' and fcntl is not None,'Actual Linux fdinfo and held flock')
class ActualLockDescriptorTest(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.path=Path(self.temporary.name)/'original-lock'
        self.fd=os.open(self.path,os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600)
        self.addCleanup(os.close,self.fd)
        fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        info=os.fstat(self.fd)
        self.identity={'device':info.st_dev,'inode':info.st_ino,'uid':info.st_uid}

    def read(self, descriptor):
        return root._held_lock((Path('/proc/self/fdinfo')/str(descriptor)).read_bytes(),os.getpid(),self.identity)

    def test_actual_exclusive_descriptor_matches_original_file_and_kernel_owner(self):
        self.assertEqual(self.read(self.fd),self.read(self.fd))

    def test_actual_unlock_removes_the_kernel_witness_without_removing_original_file(self):
        self.read(self.fd);fcntl.flock(self.fd,fcntl.LOCK_UN)
        with self.assertRaises(root.RootControllerRequestRefused):self.read(self.fd)
        self.assertTrue(self.path.exists())

    def test_separate_descriptor_of_the_same_inode_cannot_impersonate_held_flock(self):
        other=os.open(self.path,os.O_RDWR);self.addCleanup(os.close,other)
        self.assertEqual(os.fstat(other).st_ino,os.fstat(self.fd).st_ino)
        with self.assertRaises(root.RootControllerRequestRefused):self.read(other)
        self.read(self.fd)


if __name__=='__main__':unittest.main()
