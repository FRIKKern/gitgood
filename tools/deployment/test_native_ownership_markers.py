import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

import native_ownership_markers as markers
from native_ownership_records import NativeOwnershipRecords, OwnershipRecordRefused
from resource_generations import canonical
from test_native_ownership_records import fixture


@unittest.skipUnless(sys.platform=='linux' and os.getuid()!=0, 'ordinary Linux marker custody')
class OwnershipMarkerCustodyTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.storage = Path(temporary.name)/'storage'
        self.storage.mkdir(mode=0o700)
        info = self.storage.stat()
        self.identity = {'device':info.st_dev,'inode':info.st_ino,'uid':os.getuid()}
        self.record = fixture(os.getuid())
        self.records = NativeOwnershipRecords(self.storage,self.record['installation'],self.identity)
        self.subject = markers.NativeOwnershipMarkers(self.storage,self.record['installation'],self.identity)
        self.records.retain(self.record)
        self.directory = self.storage/'.gitgood-ownership-v2'
        self.target = self.storage/'.gitgood-runtime-v2.json'

    def test_marker_references_retained_record_and_identical_retry_preserves_inode(self):
        result = self.subject.publish(self.record)
        raw, inode = self.target.read_bytes(),self.target.stat().st_ino
        value = json.loads(raw)
        self.assertEqual(value['record_sha256'],hashlib.sha256(canonical(self.record)).hexdigest())
        self.assertEqual(value['operation'],self.record['operation'])
        self.assertEqual(value['kind'],'native_application_marker')
        self.assertEqual(raw,canonical(value))
        self.assertFalse(result['replacement_admitted'])
        self.assertFalse(result['installation_readiness_established'])
        self.assertEqual(self.subject.publish(self.record),result)
        self.assertEqual((self.target.read_bytes(),self.target.stat().st_ino),(raw,inode))
        self.assertEqual(self.target.stat().st_mode&0o777,0o600)
        self.assertEqual(self.target.stat().st_nlink,1)

    def test_marker_requires_exact_previously_retained_record(self):
        changed = copy.deepcopy(self.record)
        changed['operation'] = str(uuid.uuid4())
        with self.assertRaises(OwnershipRecordRefused): self.subject.publish(changed)
        self.assertFalse(self.target.exists())
        self.assertEqual(len(list(self.directory.iterdir())),1)

    def test_changed_same_mode_and_other_mode_markers_preserved_without_new_partials(self):
        for name in ['.gitgood-runtime-v2.json','.gitgood-maintenance-v2.json']:
            path = self.storage/name
            raw = b'unknown retained marker'
            path.write_bytes(raw);path.chmod(0o600)
            with self.assertRaises(OwnershipRecordRefused): self.subject.publish(self.record)
            self.assertEqual(path.read_bytes(),raw)
            self.assertFalse(any(item.name.startswith('.marker-partial-') for item in self.directory.iterdir()))
            path.unlink()

    def test_actual_directory_lock_refuses_competing_publication(self):
        descriptor = os.open(self.directory,os.O_RDONLY|os.O_DIRECTORY)
        try:
            markers.fcntl.flock(descriptor,markers.fcntl.LOCK_EX|markers.fcntl.LOCK_NB)
            with self.assertRaises(OwnershipRecordRefused): self.subject.publish(self.record)
            self.assertFalse(self.target.exists())
        finally:
            os.close(descriptor)
        self.subject.publish(self.record)

    def test_interruption_before_link_retains_partial_and_refuses_retry(self):
        with patch.object(markers.os,'link',side_effect=OSError('private interruption')):
            with self.assertRaises(OwnershipRecordRefused): self.subject.publish(self.record)
        self.assertFalse(self.target.exists())
        partials = [path for path in self.directory.iterdir() if path.name.startswith('.marker-partial-')]
        self.assertEqual(len(partials),1)
        raw = partials[0].read_bytes()
        with self.assertRaises(OwnershipRecordRefused): self.subject.publish(self.record)
        self.assertEqual(partials[0].read_bytes(),raw)

    def test_interruption_after_link_retains_hard_link_and_refuses_retry(self):
        with patch.object(markers.os,'unlink',side_effect=OSError('private interruption')):
            with self.assertRaises(OwnershipRecordRefused): self.subject.publish(self.record)
        self.assertTrue(self.target.exists())
        self.assertEqual(self.target.stat().st_nlink,2)
        raw,inode = self.target.read_bytes(),self.target.stat().st_ino
        with self.assertRaises(OwnershipRecordRefused): self.subject.publish(self.record)
        self.assertEqual((self.target.read_bytes(),self.target.stat().st_ino),(raw,inode))

    def test_storage_replacement_cannot_redirect_descriptor_based_marker(self):
        actual = markers.os.link
        moved = self.storage.parent/'original-storage'
        def replace(source,destination,**options):
            self.storage.rename(moved);self.storage.mkdir(mode=0o700)
            return actual(source,destination,**options)
        with patch.object(markers.os,'link',side_effect=replace):
            with self.assertRaises(OwnershipRecordRefused): self.subject.publish(self.record)
        self.assertFalse(self.target.exists())
        self.assertTrue((moved/self.target.name).exists())

    def test_identical_byte_marker_replacement_during_retry_refuses(self):
        self.subject.publish(self.record)
        actual = markers.os.fsync
        done = False
        def replace(descriptor):
            nonlocal done
            if not done:
                done = True
                replacement = self.storage/'private-replacement'
                replacement.write_bytes(self.target.read_bytes());replacement.chmod(0o600)
                replacement.replace(self.target)
            return actual(descriptor)
        with patch.object(markers.os,'fsync',side_effect=replace):
            with self.assertRaises(OwnershipRecordRefused): self.subject.publish(self.record)

    def test_concurrent_other_mode_marker_during_link_refuses_and_retains_effect(self):
        actual = markers.os.link
        other = self.storage/'.gitgood-maintenance-v2.json'
        def compete(source,destination,**options):
            other.write_bytes(b'unknown retained responsibility');other.chmod(0o600)
            return actual(source,destination,**options)
        with patch.object(markers.os,'link',side_effect=compete):
            with self.assertRaises(OwnershipRecordRefused): self.subject.publish(self.record)
        self.assertTrue(self.target.exists())
        self.assertEqual(other.read_bytes(),b'unknown retained responsibility')

    def test_maintenance_marker_references_exact_mode_and_does_not_replace_another_mode(self):
        backup = copy.deepcopy(self.record)
        backup['operation'] = str(uuid.uuid4());backup['mode'] = 'backup'
        backup['guard']['scope_sha256'] = hashlib.sha256(canonical({'scope':backup['scope'],'owner':backup['owner'],'worker':'maintenance'})).hexdigest()
        self.records.retain(backup)
        self.subject.publish(backup)
        target = self.storage/'.gitgood-maintenance-v2.json'
        raw,inode = target.read_bytes(),target.stat().st_ino
        self.assertEqual(json.loads(raw)['mode'],'backup')
        migrate = copy.deepcopy(backup)
        migrate['operation'] = str(uuid.uuid4());migrate['mode'] = 'migrate'
        self.records.retain(migrate)
        with self.assertRaises(OwnershipRecordRefused): self.subject.publish(migrate)
        with self.assertRaises(OwnershipRecordRefused): self.subject.publish(self.record)
        self.assertEqual((target.read_bytes(),target.stat().st_ino),(raw,inode))
        self.assertFalse(self.target.exists())

    def test_marker_symlink_hard_link_and_writable_file_refuse_without_repair(self):
        source = self.storage/'private-original'
        source.write_bytes(canonical(self.subject._marker(self.record)));source.chmod(0o600)
        for kind in ['symlink','hard-link','writable']:
            with self.subTest(kind=kind):
                if kind=='symlink': self.target.symlink_to(source)
                elif kind=='hard-link': os.link(source,self.target)
                else:
                    self.target.write_bytes(source.read_bytes());self.target.chmod(0o644)
                inode = self.target.lstat().st_ino
                with self.assertRaises(OwnershipRecordRefused): self.subject.publish(self.record)
                self.assertEqual(self.target.lstat().st_ino,inode)
                self.target.unlink()
        self.assertEqual(source.stat().st_nlink,1)

    def test_record_replacement_during_marker_publication_refuses_and_retains_marker(self):
        actual = markers.os.link
        path = self.directory/(self.record['operation']+'.json')
        def replace(source,destination,**options):
            result = actual(source,destination,**options)
            changed = copy.deepcopy(self.record);changed['candidate'] = 'b'*40
            temporary = self.directory/'replacement'
            temporary.write_bytes(canonical(changed));temporary.chmod(0o600)
            temporary.replace(path)
            return result
        with patch.object(markers.os,'link',side_effect=replace):
            with self.assertRaises(OwnershipRecordRefused): self.subject.publish(self.record)
        self.assertTrue(self.target.exists())
        self.assertEqual(json.loads(path.read_bytes())['candidate'],'b'*40)

    def test_identical_byte_record_inode_replacement_during_link_refuses(self):
        actual = markers.os.link
        path = self.directory/(self.record['operation']+'.json')
        original = path.stat().st_ino
        def replace(source,destination,**options):
            result = actual(source,destination,**options)
            temporary = self.directory/'replacement'
            temporary.write_bytes(path.read_bytes());temporary.chmod(0o600)
            temporary.replace(path)
            return result
        with patch.object(markers.os,'link',side_effect=replace):
            with self.assertRaises(OwnershipRecordRefused): self.subject.publish(self.record)
        self.assertNotEqual(path.stat().st_ino,original)
        self.assertTrue(self.target.exists())

    def test_failed_pointer_directory_sync_retains_hard_link_responsibility(self):
        actual = markers.os.fsync
        def fail(descriptor):
            info = os.fstat(descriptor)
            if (info.st_dev,info.st_ino)==(self.identity['device'],self.identity['inode']):
                raise OSError('private directory synchronization failure')
            return actual(descriptor)
        with patch.object(markers.os,'fsync',side_effect=fail):
            with self.assertRaises(OwnershipRecordRefused): self.subject.publish(self.record)
        self.assertTrue(self.target.exists())
        self.assertEqual(self.target.stat().st_nlink,2)
        with self.assertRaises(OwnershipRecordRefused): self.subject.publish(self.record)
