import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import native_ownership_marker_guard as guards
from native_ownership_markers import NativeOwnershipMarkers
from native_ownership_records import OwnershipRecordRefused
from test_native_ownership_records import fixture


@unittest.skipUnless(sys.platform=='linux' and os.getuid()!=0,'ordinary Linux custody guard')
class OwnershipMarkerGuardTest(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.storage=Path(temporary.name)/'storage';self.storage.mkdir(mode=0o700)
        info=self.storage.stat();self.identity={'device':info.st_dev,'inode':info.st_ino,'uid':os.getuid()}
        self.record=fixture(os.getuid())
        self.publisher=NativeOwnershipMarkers(self.storage,self.record['installation'],self.identity)
        self.publisher.retain(self.record);self.publisher.publish(self.record)
        self.directory=self.storage/'.gitgood-ownership-v2'
        self.marker=self.storage/'.gitgood-runtime-v2.json'
        self.record_path=self.directory/(self.record['operation']+'.json')

    def capture(self):
        guard=guards.NativeOwnershipMarkerGuard(self.storage,self.record['installation'],self.identity,self.record)
        self.addCleanup(guard.close);return guard

    def preserved(self):
        return {str(path): (path.read_bytes(),path.stat().st_ino,path.stat().st_mtime_ns,path.stat().st_ctime_ns)
                for path in [self.marker,self.record_path]}

    def test_repeated_read_only_observations_preserve_custody_and_grant_no_live_authority(self):
        before=self.preserved();guard=self.capture()
        for _ in range(3):
            result=guard.check();self.assertTrue(result['ownership_marker_observed'])
            for name in ['live_owner_observed','replacement_admitted','installation_readiness_established']:
                self.assertFalse(result[name])
        self.assertEqual(self.preserved(),before)

    def test_identical_publication_retry_does_not_replace_original_guard_capture(self):
        guard=self.capture();before=self.preserved()
        self.publisher.publish(self.record);guard.check()
        self.assertEqual(self.preserved(),before)

    def test_same_bytes_marker_and_record_inode_replacement_are_terminal(self):
        for path in [self.marker,self.record_path]:
            guard=self.capture();raw=path.read_bytes();replacement=path.with_suffix('.replacement')
            replacement.write_bytes(raw);replacement.chmod(0o600);replacement.replace(path)
            with self.assertRaises(OwnershipRecordRefused):guard.check()
            self.assertEqual(path.read_bytes(),raw)
            self.assertTrue(guard.poisoned);self.assertIsNone(guard.storage_fd)
            with self.assertRaises(OwnershipRecordRefused):guard.check()

    def test_permission_loss_then_repair_cannot_recapture_original_owner(self):
        guard=self.capture();raw=self.marker.read_bytes();self.marker.chmod(0o640)
        with self.assertRaises(OwnershipRecordRefused):guard.check()
        self.marker.chmod(0o600)
        with self.assertRaises(OwnershipRecordRefused):guard.check()
        self.assertEqual(self.marker.read_bytes(),raw)

    def test_in_place_same_bytes_rewrite_changes_original_metadata_and_refuses(self):
        for path in [self.marker,self.record_path]:
            guard=self.capture();raw=path.read_bytes();inode=path.stat().st_ino
            with path.open('r+b') as stream:
                stream.write(raw);stream.flush();os.fsync(stream.fileno())
            with self.assertRaises(OwnershipRecordRefused):guard.check()
            self.assertEqual((path.read_bytes(),path.stat().st_ino),(raw,inode))

    def test_other_mode_marker_or_unknown_partial_is_preserved_and_refused(self):
        for path in [self.storage/'.gitgood-maintenance-v2.json',self.directory/'.marker-partial-unknown']:
            guard=self.capture();raw=b'uncertain responsibility';path.write_bytes(raw);path.chmod(0o600)
            with self.assertRaises(OwnershipRecordRefused):guard.check()
            self.assertEqual(path.read_bytes(),raw);path.unlink()

    def test_storage_and_ownership_directory_replacement_cannot_redirect_guard(self):
        for path in [self.directory,self.storage]:
            guard=self.capture();retained=path.with_name(path.name+'-retained')
            path.rename(retained);path.mkdir(mode=0o700)
            with self.assertRaises(OwnershipRecordRefused):guard.check()
            self.assertFalse(any(path.iterdir()))
            path.rmdir();retained.rename(path)

    def test_actual_exclusive_directory_lock_refuses_and_poison_is_permanent(self):
        guard=self.capture();descriptor=os.open(self.directory,os.O_RDONLY|os.O_DIRECTORY)
        try:
            guards.fcntl.flock(descriptor,guards.fcntl.LOCK_EX|guards.fcntl.LOCK_NB)
            with self.assertRaises(OwnershipRecordRefused):guard.check()
        finally:os.close(descriptor)
        with self.assertRaises(OwnershipRecordRefused):guard.check()

    def test_marker_replacement_during_observation_is_preserved_and_refused(self):
        guard=self.capture();raw=self.marker.read_bytes();original=guard._marker_bytes;changed=False
        def replace(descriptor,name):
            nonlocal changed
            result=original(descriptor,name)
            if not changed:
                changed=True;temporary=self.marker.with_suffix('.replacement')
                temporary.write_bytes(raw);temporary.chmod(0o600);temporary.replace(self.marker)
            return result
        with patch.object(guard,'_marker_bytes',side_effect=replace):
            with self.assertRaises(OwnershipRecordRefused):guard.check()
        self.assertEqual(self.marker.read_bytes(),raw)

    def test_missing_marker_capture_does_not_create_or_repair(self):
        self.marker.unlink()
        with self.assertRaises(OwnershipRecordRefused):self.capture()
        self.assertFalse(self.marker.exists());self.assertEqual(self.record_path.read_bytes(),self.preserved_record_bytes())

    def preserved_record_bytes(self):
        from resource_generations import canonical
        return canonical(self.record)


if __name__=='__main__':unittest.main()
