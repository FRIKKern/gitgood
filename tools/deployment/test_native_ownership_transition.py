"""Actual ordinary Linux custody checks; live admission is tested separately."""
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

import native_ownership_transition as transition
from native_ownership_markers import NativeOwnershipMarkers
from native_ownership_marker_guard import NativeOwnershipMarkerGuard
from native_ownership_records import NativeOwnershipRecords, OwnershipRecordRefused, record_name, validate_record
from resource_generations import canonical
from test_native_ownership_records import fixture


def next_record(previous=None, *, mode='runtime', uid=None):
    value=copy.deepcopy(previous) if previous is not None else fixture(uid)
    value.update(protocol=4,claim=str(uuid.uuid4()),predecessor_sha256=transition.sha(previous) if previous else None,
                 reservation_sha256='9'*64,mode=mode)
    value['owner']['pid']+=10;value['owner']['birth']=str(int(value['owner']['birth'])+10)
    value['database_session']['backend_pid']+=10
    value['database_session']['backend_birth']=str(int(value['database_session']['backend_birth'])+10)
    value['backend_kernel']['database_session']=copy.deepcopy(value['database_session'])
    value['backend_kernel']['kernel_birth']=str(int(value['backend_kernel']['kernel_birth'])+10)
    value['guard']['scope_sha256']=transition.sha({'scope':value['scope'],'owner':value['owner'],
                                                 'worker':'native' if mode=='runtime' else 'maintenance'})
    return value


class VersionFourGrammarTest(unittest.TestCase):
    def test_claim_names_allow_distinct_owners_of_one_stable_operation(self):
        first=next_record();second=next_record(first,mode='migrate')
        for value in [first,second]:self.assertEqual(validate_record(value),value)
        self.assertEqual(first['operation'],second['operation'])
        self.assertNotEqual(record_name(first),record_name(second))
        self.assertEqual(second['predecessor_sha256'],transition.sha(first))

    def test_original_version_three_bytes_and_name_are_unchanged(self):
        original=fixture();raw=canonical(original)
        self.assertEqual(record_name(original),original['operation']+'.json')
        next_record(original)
        self.assertEqual(canonical(original),raw)

    def test_type_aliases_added_authority_missing_references_and_colliding_claims_refuse(self):
        value=next_record()
        for name,changed in [('claim',value['operation']),('claim',value['pointer']['operation']),
                             ('claim',value['installation']),('claim',False),('protocol',True),
                             ('predecessor_sha256','unknown'),('reservation_sha256',None),('receipt',{})]:
            with self.subTest(name=name),self.assertRaises(Exception):validate_record({**value,name:changed})
        for name in ['claim','predecessor_sha256','reservation_sha256']:
            changed=copy.deepcopy(value);del changed[name]
            with self.subTest(missing=name),self.assertRaises(Exception):validate_record(changed)


@unittest.skipUnless(sys.platform=='linux' and os.getuid()!=0,'ordinary Linux successor custody')
class OwnershipTransitionCustodyTest(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.storage=Path(temporary.name)/'storage';self.storage.mkdir(mode=0o700)
        info=self.storage.stat();self.identity={'device':info.st_dev,'inode':info.st_ino,'uid':info.st_uid}
        self.previous=fixture(os.getuid())
        NativeOwnershipRecords(self.storage,self.previous['installation'],self.identity).retain(self.previous)
        markers=NativeOwnershipMarkers(self.storage,self.previous['installation'],self.identity);markers.publish(self.previous)
        self.store=transition.OwnershipTransitionStore(self.storage,self.previous['installation'],self.identity)
        self.addCleanup(self.store.close)
        self.marker=self.store.current_marker(self.previous)
        self.record=next_record(self.previous,mode='migrate')

    def publish(self):
        return self.store.publish(self.record,self.previous,self.marker,self.store.check)

    def test_successor_preserves_original_record_and_marker_inode_and_retries_identically(self):
        original=(self.storage/'.gitgood-ownership-v2'/record_name(self.previous)).read_bytes()
        before_inode=self.marker[1][1][1]
        first=self.publish();current=self.store.current_marker(self.record)
        self.assertEqual(self.publish(),first)
        self.assertEqual(self.store.current_marker(self.record),current)
        archived=self.store.read('receipts',self.record['claim']+'.old-marker.json')
        self.assertEqual(archived[0],self.marker[1][0]);self.assertEqual(archived[1][1],before_inode)
        self.assertEqual((self.storage/'.gitgood-ownership-v2'/record_name(self.previous)).read_bytes(),original)
        self.assertEqual(len(self.store.records()),2)
        self.assertFalse(first['replacement_admitted']);self.assertFalse(first['installation_readiness_established'])
        guard=NativeOwnershipMarkerGuard(self.storage,self.record['installation'],self.identity,self.record)
        try:self.assertEqual(guard.check()['record_sha256'],transition.sha(self.record))
        finally:guard.close()

    def test_initial_v4_uses_same_journal_without_inventing_a_predecessor(self):
        other=self.storage.parent/'initial';other.mkdir(mode=0o700);info=other.stat()
        record=next_record(uid=os.getuid())
        subject=transition.OwnershipTransitionStore(other,record['installation'],{'device':info.st_dev,'inode':info.st_ino,'uid':info.st_uid})
        try:
            result=subject.publish(record,None,None,subject.check)
            self.assertEqual(result['claim'],record['claim'])
            self.assertFalse(any(name.endswith('.old-marker.json') for name in subject._names('receipts')))
            self.assertEqual(subject.current_marker(record)[1][0]['claim'],record['claim'])
        finally:subject.close()

    def test_complete_partial_keeps_original_inode_across_retry(self):
        name=self.record['claim']+'.reservation.json';value={'retained':'synthetic bytes'}
        with patch.object(transition,'publish_directory',side_effect=OSError('interrupted before rename')):
            with self.assertRaises(OSError):self.store.put('receipts',name,value)
        partial=self.storage/'.gitgood-successors-v4'/('.partial-'+name);inode=partial.stat().st_ino
        self.store.put('receipts',name,value)
        self.assertEqual((self.storage/'.gitgood-successors-v4'/name).stat().st_ino,inode)
        self.assertFalse(partial.exists())

    def test_identical_byte_partial_replacement_cannot_resume(self):
        name=self.record['claim']+'.reservation.json';value={'retained':'synthetic bytes'}
        with patch.object(transition,'publish_directory',side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):self.store.put('receipts',name,value)
        partial=self.storage/'.gitgood-successors-v4'/('.partial-'+name)
        replacement=self.storage/'substitution';replacement.write_bytes(partial.read_bytes());replacement.chmod(0o600)
        replacement.replace(partial);inode=partial.stat().st_ino
        with self.assertRaises(OwnershipRecordRefused):self.store.put('receipts',name,value)
        self.assertEqual(partial.stat().st_ino,inode)
        self.assertFalse((self.storage/'.gitgood-successors-v4'/name).exists())

    def test_every_atomic_move_can_lose_acknowledgement_and_resume_exact_bytes(self):
        real=transition.publish_directory
        # Each fresh fixture exercises a different immutable receipt/record or
        # marker rename, including the gap between archiving old and moving new.
        for target in range(1,7):
            with self.subTest(move=target):
                self.tearDown();self.setUp();calls=0
                def interrupt(source,destination):
                    nonlocal calls
                    calls+=1;real(source,destination)
                    if calls==target:raise OSError('lost rename acknowledgement')
                with patch.object(transition,'publish_directory',side_effect=interrupt):
                    with self.assertRaises(OSError):self.publish()
                self.publish()
                self.assertEqual(self.store.current_marker(self.record)[1][0],self.store._marker(self.record))
                self.assertEqual(self.store.read('receipts',self.record['claim']+'.old-marker.json')[1][1],self.marker[1][1][1])

    def test_every_file_and_directory_sync_can_lose_acknowledgement_and_resume_original_inodes(self):
        real=transition.os.fsync
        with patch.object(transition.os,'fsync',wraps=real) as observed:self.publish()
        count=observed.call_count;self.assertGreater(count,10)
        for target in range(1,count+1):
            with self.subTest(sync=target):
                self.store.close();self.setUp();calls=0
                def interrupt(descriptor):
                    nonlocal calls
                    calls+=1;real(descriptor)
                    if calls==target:raise OSError('lost synchronization acknowledgement')
                with patch.object(transition.os,'fsync',side_effect=interrupt):
                    with self.assertRaises(OSError):self.publish()
                before={str(path.relative_to(self.storage)):path.stat().st_ino
                        for path in self.storage.rglob('*') if path.is_file()}
                self.publish()
                self.assertEqual(self.store.current_marker(self.record)[1][0],self.store._marker(self.record))
                self.assertEqual(self.store.read('receipts',self.record['claim']+'.old-marker.json')[1][1],self.marker[1][1][1])
                for name,inode in before.items():
                    path=self.storage/name
                    if path.exists():self.assertEqual(path.stat().st_ino,inode)

    def test_full_record_store_refuses_a_new_record_without_a_partial(self):
        directory=self.storage/'.gitgood-ownership-v2'
        self.store.close()
        for _ in range(127):
            value=next_record(self.previous,uid=os.getuid());path=directory/record_name(value)
            path.write_bytes(canonical(value));path.chmod(0o600)
        self.store=transition.OwnershipTransitionStore(self.storage,self.previous['installation'],self.identity)
        self.addCleanup(self.store.close)
        names={path.name for path in directory.iterdir()}
        with self.assertRaises(OwnershipRecordRefused):self.store.put('records',record_name(self.record),self.record)
        self.assertEqual({path.name for path in directory.iterdir()},names)
        self.assertFalse(self.store._names('receipts'))

    def test_changed_old_marker_is_retained_and_never_overwritten(self):
        path=self.storage/self.marker[0];raw=b'{"unknown":"responsibility"}'
        path.write_bytes(raw);path.chmod(0o600)
        with self.assertRaises(Exception):self.publish()
        self.assertEqual(path.read_bytes(),raw)
        self.assertFalse((self.storage/'.gitgood-maintenance-v2.json').exists())

    def test_partial_recovery_requires_fresh_live_admission_before_any_progress(self):
        real=transition.publish_directory
        def interrupt(source,destination):
            real(source,destination);raise OSError('interrupted')
        with patch.object(transition,'publish_directory',side_effect=interrupt):
            with self.assertRaises(OSError):self.publish()
        before={str(path.relative_to(self.storage)):path.read_bytes() for path in self.storage.rglob('*') if path.is_file()}
        def lost():raise ValueError('original absence or lease unavailable')
        with self.assertRaises(ValueError):self.store.publish(self.record,self.previous,self.marker,lost)
        self.assertEqual({str(path.relative_to(self.storage)):path.read_bytes() for path in self.storage.rglob('*') if path.is_file()},before)

    def test_competing_marker_lock_refuses_before_journal_changes(self):
        descriptor=os.open(self.storage/'.gitgood-ownership-v2',os.O_RDONLY|os.O_DIRECTORY)
        try:
            transition.fcntl.flock(descriptor,transition.fcntl.LOCK_EX|transition.fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):self.publish()
            self.assertFalse(self.store._names('receipts'))
        finally:os.close(descriptor)
