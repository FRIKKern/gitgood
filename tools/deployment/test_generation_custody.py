import copy
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import generation_custody as custody
from resource_generations import canonical, make_generation
import test_resource_generations as fixtures


@unittest.skipUnless(sys.platform == "linux" and os.getuid() != 0, "ordinary Linux filesystem custody")
class GenerationCustodyTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.root.chmod(0o700)
        fixture = fixtures.ResourceGenerationRecordTest()
        fixture.setUp()
        self.installation, self.first, self.second = fixture.installation, fixture.first, fixture.second
        info = self.root.stat()
        self.identity = {"device": info.st_dev, "inode": info.st_ino, "uid": info.st_uid}
        lock = self.root / ".upgrade-history-lock-v1"
        lock.write_bytes(b"")
        lock.chmod(0o600)
        info = lock.stat()
        self.lock_identity = {"device": info.st_dev, "inode": info.st_ino, "uid": info.st_uid}

    def open(self):
        return custody.GenerationRecordCustody(self.root, self.installation, self.identity, self.lock_identity)

    def write(self, name, raw):
        path = self.root / "generation-records-v2" / name
        path.write_bytes(raw)
        path.chmod(0o600)
        return path

    def test_exact_records_and_replay_preserve_original_bytes_and_inode(self):
        with self.open() as store:
            result = store.retain(self.first)
            path = store.store / (result["sha256"] + ".json")
            original = (path.stat().st_ino, path.read_bytes())
            self.assertFalse(result["generation_published"])
            self.assertTrue(store.retain(self.first)["replayed"])
            self.assertFalse(store.retain(self.second)["replayed"])
            self.assertEqual((path.stat().st_ino, path.read_bytes()), original)
            self.assertEqual(len(store._records()), 2)

    def test_missing_predecessor_foreign_installation_and_second_genesis_refuse(self):
        with self.open() as store:
            with self.assertRaises(custody.CustodyRefused):
                store.retain(self.second)
            store.retain(self.first)
            foreign = copy.deepcopy(self.first)
            foreign["installation"] = "00000000-0000-4000-8000-000000000099"
            with self.assertRaises(custody.CustodyRefused):
                store.retain(foreign)
            another = copy.deepcopy(self.first)
            another["generation"] = self.second["generation"]
            with self.assertRaises(custody.CustodyRefused):
                store.retain(another)

    def test_generation_identity_cannot_be_reused_later_in_the_chain(self):
        with self.open() as store:
            store.retain(self.first)
            store.retain(self.second)
            next_scope = copy.deepcopy(self.first["scope"])
            third = make_generation(next_scope, "b" * 64, generation=self.first["generation"],
                                    created_at="2026-10-10T05:02:00.000000Z", previous=self.second)
            with self.assertRaises(custody.CustodyRefused):
                store.retain(third)
            self.assertEqual(len(store._records()), 2)

    def test_competing_process_refuses_and_can_acquire_after_release(self):
        code = "import sys;from pathlib import Path;from generation_custody import GenerationRecordCustody,CustodyRefused;p=Path(sys.argv[1]);s=p.stat();l=(p/'.upgrade-history-lock-v1').stat();\ntry:\n with GenerationRecordCustody(p,sys.argv[2],{'device':s.st_dev,'inode':s.st_ino,'uid':s.st_uid},{'device':l.st_dev,'inode':l.st_ino,'uid':l.st_uid}):pass\nexcept CustodyRefused:sys.exit(7)"
        with self.open():
            result = subprocess.run([sys.executable, "-c", code, str(self.root), self.installation],
                                    cwd=Path(__file__).parent, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 7, result.stderr)
        result = subprocess.run([sys.executable, "-c", code, str(self.root), self.installation],
                                cwd=Path(__file__).parent, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_replaced_lock_and_replaced_history_never_grant_ownership(self):
        with self.open() as store:
            store.lock_path.rename(self.root / "retained-lock")
            store.lock_path.write_bytes(b"")
            store.lock_path.chmod(0o600)
            with self.assertRaises(custody.CustodyRefused):
                store.retain(self.first)
        retained = self.root.with_name(self.root.name + "-retained")
        self.root.rename(retained)
        self.addCleanup(lambda: retained.rename(self.root) if not self.root.exists() else None)
        self.root.mkdir(mode=0o700)
        with self.assertRaises(custody.CustodyRefused):
            self.open()
        self.root.rmdir()

    def test_lock_fifo_hardlink_and_shared_mode_refuse_before_waiting(self):
        lock = self.root / ".upgrade-history-lock-v1"
        lock.rename(self.root / "retained-original-lock")
        os.mkfifo(lock, 0o600)
        with self.assertRaises((OSError, custody.CustodyRefused)):
            with self.open():
                pass
        lock.rename(self.root / "retained-fifo")
        lock.write_bytes(b"")
        lock.chmod(0o600)
        os.link(lock, self.root / "retained-link")
        with self.assertRaises(custody.CustodyRefused):
            with self.open():
                pass
        (self.root / "retained-link").unlink()
        lock.chmod(0o640)
        with self.assertRaises(custody.CustodyRefused):
            with self.open():
                pass

    def test_unknown_aliased_and_noncanonical_record_files_refuse(self):
        with self.open() as store:
            result = store.retain(self.first)
            path = store.store / (result["sha256"] + ".json")
            original = path.read_bytes()
            path.write_bytes(original + b"\n")
            with self.assertRaises(custody.CustodyRefused):
                store.retain(self.second)
            path.write_bytes(original)
            path.rename(self.root / "retained-record")
            path.symlink_to(self.root / "retained-record")
            with self.assertRaises((OSError, custody.CustodyRefused)):
                store.retain(self.second)

    def test_pre_rename_failure_retains_partial_and_retry_does_not_adopt_it(self):
        with self.open() as store:
            with patch.object(custody, "publish_directory", side_effect=OSError("injected")):
                with self.assertRaises(OSError):
                    store.retain(self.first)
            partial = next(store.store.glob(".partial-*"))
            original = (partial.stat().st_ino, partial.read_bytes())
            self.assertFalse(store.retain(self.first)["replayed"])
            self.assertEqual((partial.stat().st_ino, partial.read_bytes()), original)

    def test_lost_sync_ack_reobserves_exact_record_and_resynchronizes(self):
        with self.open() as store:
            with patch.object(custody, "sync_directory", side_effect=OSError("lost sync acknowledgement")):
                with self.assertRaises(OSError):
                    store.retain(self.first)
            path = store.store / (hashlib.sha256(canonical(self.first)).hexdigest() + ".json")
            original = (path.stat().st_ino, path.read_bytes())
        with self.open() as store:
            self.assertTrue(store.retain(self.first)["replayed"])
            self.assertEqual((path.stat().st_ino, path.read_bytes()), original)

    def test_changed_store_identity_and_invalid_expected_identity_refuse(self):
        invalid = dict(self.identity, inode=True)
        with self.assertRaises(custody.CustodyRefused):
            custody.GenerationRecordCustody(self.root, self.installation, invalid, self.lock_identity)
        with self.open() as store:
            store.store.rename(self.root / "retained-store")
            store.store.mkdir(mode=0o700)
            with self.assertRaises(custody.CustodyRefused):
                store.retain(self.first)

    def test_replaced_lock_before_entry_refuses_the_independent_identity(self):
        path = self.root / ".upgrade-history-lock-v1"
        path.rename(self.root / "retained-original-lock")
        path.write_bytes(b"")
        path.chmod(0o600)
        with self.assertRaises(custody.CustodyRefused):
            with self.open():
                pass
