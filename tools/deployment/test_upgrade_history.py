import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

from upgrade_history import UpgradeHistory
from upgrade_journal import STAGES, UpgradeRefused


@unittest.skipUnless(sys.platform == "linux", "Native upgrade history requires Linux")
class UpgradeHistoryTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.root.chmod(0o700)
        self.operation = str(uuid.uuid4())
        self.intent = {"installation": str(uuid.uuid4()), "old_candidate": "a" * 40,
                       "new_candidate": "b" * 40, "old_artifact_sha256": "c" * 64,
                       "new_artifact_sha256": "d" * 64, "bindings_sha256": "e" * 64,
                       "rollback_policy": "same_schema_only"}
        self.receipt = {"receipt_sha256": hashlib.sha256(b"inert fixture receipt").hexdigest()}

    def claim(self, operation=None, intent=None):
        return UpgradeHistory(self.root, operation or self.operation, intent or self.intent)

    def finish(self, operation=None, intent=None):
        with self.claim(operation, intent) as journal:
            for stage in STAGES:
                journal.begin(stage)
                journal.succeed(stage, self.receipt)

    def next_intent(self):
        return {**self.intent, "old_candidate": self.intent["new_candidate"], "old_artifact_sha256": self.intent["new_artifact_sha256"],
                "new_candidate": "f" * 40, "new_artifact_sha256": "9" * 64}

    def test_success_then_recovered_attempt_then_another_upgrade_preserve_all_history(self):
        self.finish()
        first = self.root / "operations" / self.operation / "upgrade-journal-v1.json"
        before = first.read_bytes()
        second, third = str(uuid.uuid4()), str(uuid.uuid4())
        intent = self.next_intent()
        with self.claim(second, intent) as journal:
            journal.begin("inspect")
            journal.fail("artifact_refused")
            journal.begin_recovery()
            journal.recovered({**self.receipt, "previous_identity_verified": True, "public_functional_probe": True})
        retained = (self.root / "operations" / second / "upgrade-journal-v1.json").read_bytes()
        self.finish(third, intent)
        status = UpgradeHistory.read_history(self.root, third, intent)
        self.assertEqual([x["status"] for x in status["operations"]], ["complete", "recovered", "complete"])
        self.assertEqual(status["operations"][1]["last_failure"], {"stage": "inspect", "code": "artifact_refused"})
        self.assertEqual(first.read_bytes(), before)
        self.assertEqual((self.root / "operations" / second / "upgrade-journal-v1.json").read_bytes(), retained)
        with self.assertRaises(UpgradeRefused):
            with self.claim():
                pass

    def test_real_competing_process_cannot_claim_a_different_operation(self):
        with self.claim():
            code = "import json,sys;from upgrade_history import UpgradeHistory;from upgrade_journal import UpgradeRefused\ntry:\n with UpgradeHistory(sys.argv[1],sys.argv[2],json.loads(sys.argv[3])):pass\nexcept UpgradeRefused:sys.exit(23)"
            result = subprocess.run([sys.executable, "-c", code, str(self.root), str(uuid.uuid4()), json.dumps(self.intent)],
                                    env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONPATH": str(Path(__file__).parent)},
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 23, result.stderr)

    def test_interrupted_operation_blocks_new_request_and_retains_same_request_for_reconciliation(self):
        with self.claim() as journal:
            journal.begin("inspect")
        with self.assertRaises(UpgradeRefused):
            with self.claim(str(uuid.uuid4())):
                pass
        with self.claim() as journal:
            self.assertEqual(journal.status()["status"], "uncertain")
            journal.reconcile(applied=False, evidence=self.receipt)
            journal.begin("inspect")
            journal.fail("artifact_refused")
        with self.assertRaises(UpgradeRefused):
            with self.claim(str(uuid.uuid4())):
                pass

    def test_killed_owner_releases_history_lock_without_erasing_running_stage(self):
        code = "import json,sys;from upgrade_history import UpgradeHistory\nwith UpgradeHistory(sys.argv[1],sys.argv[2],json.loads(sys.argv[3])) as journal:\n journal.begin('inspect');print('persisted',flush=True);sys.stdin.read()"
        process = subprocess.Popen([sys.executable, "-c", code, str(self.root), self.operation, json.dumps(self.intent)],
                                   env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONPATH": str(Path(__file__).parent)},
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), "persisted")
            process.kill()
            process.communicate(timeout=10)
            observed = UpgradeHistory.read_history(self.root, self.operation, self.intent)
            self.assertEqual(observed["operations"][0]["status"], "uncertain")
            with self.claim() as journal:
                self.assertEqual(journal.status()["status"], "uncertain")
                journal.reconcile(applied=False, evidence=self.receipt)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)
    def test_changed_installation_bindings_previous_release_or_reused_operation_refuse_before_changes(self):
        self.finish()
        before = (self.root / "upgrade-history-v1.json").read_bytes()
        for field, value in [("installation", str(uuid.uuid4())), ("bindings_sha256", "1" * 64),
                             ("old_candidate", "2" * 40), ("old_artifact_sha256", "3" * 64)]:
            changed = self.next_intent()
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(UpgradeRefused):
                with self.claim(str(uuid.uuid4()), changed):
                    pass
            self.assertEqual((self.root / "upgrade-history-v1.json").read_bytes(), before)
        with self.assertRaises(UpgradeRefused):
            with self.claim(intent=self.next_intent()):
                pass

    def test_sealed_journal_tampering_or_alias_refuses_read_and_subsequent_claim(self):
        self.finish()
        second = str(uuid.uuid4())
        intent = self.next_intent()
        with self.claim(second, intent):
            pass
        first = self.root / "operations" / self.operation / "upgrade-journal-v1.json"
        data = first.read_bytes()
        first.write_bytes(data + b"\n")
        for action in [lambda: UpgradeHistory.read_history(self.root, second, intent), lambda: self.claim(second, intent).__enter__()]:
            with self.assertRaises(UpgradeRefused):
                action()
        first.write_bytes(data)
        directory = first.parent
        original = self.root / "retained-journal"
        directory.rename(original)
        directory.symlink_to(original, target_is_directory=True)
        with self.assertRaises(UpgradeRefused):
            UpgradeHistory.read_history(self.root, second, intent)

    def test_lost_history_acknowledgement_exposes_reserved_intent_without_started_stage(self):
        original = UpgradeHistory._save
        def lost(history, value):
            original(history, value)
            raise OSError("lost fixture acknowledgement")
        with patch.object(UpgradeHistory, "_save", lost), self.assertRaises(OSError):
            with self.claim():
                self.fail("No action may start after lost acknowledgement")
        observed = UpgradeHistory.read_history(self.root, self.operation, self.intent)
        self.assertEqual(observed["operations"][0]["status"], "reserved")
        with self.assertRaises(UpgradeRefused):
            with self.claim(str(uuid.uuid4())):
                pass
        with self.claim() as journal:
            self.assertEqual(journal.status()["status"], "pending")
            self.assertEqual(journal.status()["completed"], [])
        self.assertEqual(len(json.loads((self.root / "upgrade-history-v1.json").read_bytes())["operations"]), 1)

    def test_history_bound_is_checked_before_creating_another_operation(self):
        self.finish()
        with patch("upgrade_history.MAX_OPERATIONS", 1), self.assertRaises(UpgradeRefused):
            with self.claim(str(uuid.uuid4()), self.next_intent()):
                pass
        self.assertEqual({p.name for p in (self.root / "operations").iterdir()}, {self.operation})

    def test_history_hardlink_shared_permissions_and_orphan_operation_refuse(self):
        with self.claim():
            pass
        path = self.root / "upgrade-history-v1.json"
        os.link(path, self.root / "alias")
        with self.assertRaises(UpgradeRefused):
            UpgradeHistory.read_history(self.root, self.operation, self.intent)
        (self.root / "alias").unlink()
        path.chmod(0o644)
        with self.assertRaises(UpgradeRefused):
            with self.claim():
                pass
        path.chmod(0o600)
        (self.root / "operations" / str(uuid.uuid4())).mkdir(mode=0o700)
        with self.assertRaises(UpgradeRefused):
            with self.claim():
                pass


@unittest.skipIf(sys.platform == "linux", "Foreign-platform early refusal")
class UnsupportedHistoryTest(unittest.TestCase):
    def test_history_refuses_before_touching_resources(self):
        with self.assertRaises(UpgradeRefused):
            UpgradeHistory("unowned-path", str(uuid.uuid4()), {})
