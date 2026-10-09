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

from retirement_journal import DIGESTS, RetirementJournal, STAGES
from upgrade_history import UpgradeHistory
from upgrade_journal import canonical, STAGES as UPGRADE_STAGES, UpgradeRefused


@unittest.skipUnless(sys.platform == "linux", "Retirement custody requires Linux")
class RetirementJournalTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.root.chmod(0o700)
        self.upgrade = str(uuid.uuid4())
        self.installation = str(uuid.uuid4())
        self.intent = {"installation": self.installation, "old_candidate": "a" * 40,
                       "new_candidate": "b" * 40, "old_artifact_sha256": "c" * 64,
                       "new_artifact_sha256": "d" * 64, "bindings_sha256": "e" * 64,
                       "rollback_policy": "same_schema_only"}
        self.receipt = {"receipt_sha256": hashlib.sha256(b"inert journal fixture; no actions").hexdigest()}
        with UpgradeHistory(self.root, self.upgrade, self.intent) as journal:
            for stage in UPGRADE_STAGES:
                journal.begin(stage)
                journal.succeed(stage, self.receipt)
        self.pointer = self.root / "current-release-v1.json"
        self.pointer.write_text('{"inert_fixture":true}\n')
        self.pointer.chmod(0o600)
        self.plan = {"protocol": 1, "operation": str(uuid.uuid4()), "installation": self.installation,
                     "candidate": "b" * 40, **{key: "f" * 64 for key in DIGESTS},
                     "bindings_sha256": "e" * 64, "artifact_sha256": "d" * 64,
                     "current_sha256": hashlib.sha256(self.pointer.read_bytes()).hexdigest()}

    def claim(self, plan=None):
        plan = plan or self.plan
        return RetirementJournal(self.root, plan, hashlib.sha256(canonical(plan)).hexdigest())

    def status(self):
        return RetirementJournal.read_status(self.root, self.plan, hashlib.sha256(canonical(self.plan)).hexdigest())

    def evidence(self, stage):
        return {**self.receipt, **({"archive_identity_verified": True, "restore_function_verified": True,
                "current_snapshot_verified": True, "writer_exclusion_verified": True} if stage == "archive_verify" else
                {"resource_reobserved": True, "desired_state_verified": True} if stage in {"database_remove", "stores_remove"} else
                {"retained_archive_usable": True, "owned_resources_absent": True} if stage == "retention_verify" else {})}

    def test_fixed_order_complete_and_repeat_retain_history_without_any_resource_actions(self):
        prior = (self.root / "operations" / self.upgrade / "upgrade-journal-v1.json").read_bytes()
        with self.claim() as journal:
            with self.assertRaises(UpgradeRefused):
                journal.begin("database_remove")
            for stage in STAGES:
                journal.begin(stage)
                journal.succeed(self.evidence(stage))
            self.assertEqual(journal.record["status"], "complete")
            retained = list(journal.record["events"])
        with self.claim() as journal:
            self.assertEqual(journal.record["events"][:-1], retained)
            with self.assertRaises(UpgradeRefused):
                journal.begin("quiesce")
        self.assertEqual((self.root / "operations" / self.upgrade / "upgrade-journal-v1.json").read_bytes(), prior)
        self.assertTrue(self.pointer.exists())

    def test_same_kernel_lock_and_retained_retirement_intent_exclude_upgrade(self):
        with UpgradeHistory(self.root, self.upgrade, self.intent):
            with self.assertRaises(UpgradeRefused):
                with self.claim():
                    pass
        self.assertFalse((self.root / "retirement-journal-v1.json").exists())
        with self.claim():
            with self.assertRaises(UpgradeRefused):
                with UpgradeHistory(self.root, self.upgrade, self.intent):
                    pass
        with self.assertRaises(UpgradeRefused):
            with UpgradeHistory(self.root, self.upgrade, self.intent):
                pass

    def test_independent_plan_pointer_and_previous_release_identity_refuse_changes(self):
        for key, changed in [("candidate", "9" * 40), ("artifact_sha256", "9" * 64), ("installation", str(uuid.uuid4()))]:
            with self.assertRaises(UpgradeRefused):
                with self.claim({**self.plan, key: changed}):
                    pass
            self.assertFalse((self.root / "retirement-journal-v1.json").exists())
        self.pointer.write_text('{"changed_pointer":true}\n')
        with self.assertRaises(UpgradeRefused):
            with self.claim():
                pass

    def test_real_competing_process_refuses_same_and_changed_intent(self):
        code = "import json,sys;from retirement_journal import RetirementJournal;from upgrade_journal import UpgradeRefused\ntry:\n with RetirementJournal(sys.argv[1],json.loads(sys.argv[2]),sys.argv[3]):pass\nexcept UpgradeRefused:sys.exit(23)"
        with self.claim():
            for plan in [self.plan, {**self.plan, "operation": str(uuid.uuid4())}]:
                result = subprocess.run([sys.executable, "-c", code, str(self.root), json.dumps(plan), hashlib.sha256(canonical(plan)).hexdigest()],
                                        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(Path(__file__).parent)}, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 23, result.stderr)

    def test_pending_prior_upgrade_and_independent_plan_digest_refuse_before_retirement(self):
        with self.assertRaises(UpgradeRefused):
            RetirementJournal(self.root, self.plan, "0" * 64)
        next_intent = {**self.intent, "old_candidate": "b" * 40, "old_artifact_sha256": "d" * 64,
                       "new_candidate": "9" * 40, "new_artifact_sha256": "9" * 64}
        with UpgradeHistory(self.root, str(uuid.uuid4()), next_intent) as journal:
            journal.begin("inspect")
        prior = (self.root / "upgrade-history-v1.json").read_bytes()
        with self.assertRaises(UpgradeRefused):
            with self.claim():
                pass
        self.assertFalse((self.root / "retirement-journal-v1.json").exists())
        self.assertEqual((self.root / "upgrade-history-v1.json").read_bytes(), prior)

    def test_reclaim_cannot_replace_retained_plan_or_operation(self):
        with self.claim():
            pass
        retained = (self.root / "retirement-journal-v1.json").read_bytes()
        for patch in [{"operation": str(uuid.uuid4())}, {"archive_sha256": "9" * 64}]:
            with self.assertRaises(UpgradeRefused):
                with self.claim({**self.plan, **patch}):
                    pass
            self.assertEqual((self.root / "retirement-journal-v1.json").read_bytes(), retained)

    def test_real_killed_owner_retains_uncertainty_until_explicit_observed_reconciliation(self):
        code = "import json,sys;from retirement_journal import RetirementJournal\nwith RetirementJournal(sys.argv[1],json.loads(sys.argv[2]),sys.argv[3]) as journal:\n journal.begin('quiesce');print('persisted',flush=True);sys.stdin.read()"
        process = subprocess.Popen([sys.executable, "-c", code, str(self.root), json.dumps(self.plan), hashlib.sha256(canonical(self.plan)).hexdigest()],
                                   env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(Path(__file__).parent)}, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), "persisted")
            process.kill()
            process.communicate(timeout=10)
            retained = (self.root / "retirement-journal-v1.json").read_bytes()
            self.assertEqual(self.status()["status"], "uncertain")
            self.assertEqual((self.root / "retirement-journal-v1.json").read_bytes(), retained)
            with self.claim() as journal:
                self.assertEqual(journal.record["status"], "uncertain")
                with self.assertRaises(UpgradeRefused):
                    journal.begin("quiesce")
                journal.reconcile(applied=False, evidence={**self.receipt, "unapplied_verified": True})
                journal.begin("quiesce")
                journal.succeed(self.receipt)
                self.assertTrue(any(event["kind"] == "interrupted" for event in journal.record["events"]))
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)

    def test_failed_action_does_not_retry_or_acknowledge_without_required_observations(self):
        with self.claim() as journal:
            journal.begin("quiesce")
            journal.succeed(self.receipt)
            journal.begin("archive_verify")
            with self.assertRaises(UpgradeRefused):
                journal.succeed(self.receipt)
            journal.fail("archive_refused")
            with self.assertRaises(UpgradeRefused):
                journal.begin("archive_verify")
            with self.assertRaises(UpgradeRefused):
                journal.reconcile(applied=True, evidence=self.receipt)
            journal.reconcile(applied=False, evidence={**self.receipt, "unapplied_verified": True})
            journal.begin("archive_verify")
            journal.succeed(self.evidence("archive_verify"))
            journal.begin("database_remove")
            journal.fail("database_remove_failed")
            journal.reconcile(applied=True, evidence=self.evidence("database_remove"))
            self.assertEqual(journal.record["completed"], list(STAGES[:3]))

    def test_forged_terminal_state_and_changed_plan_refuse(self):
        with self.claim() as journal:
            journal.begin("quiesce")
        path = self.root / "retirement-journal-v1.json"
        record = json.loads(path.read_text())
        record["status"] = "complete"
        path.write_text(json.dumps(record))
        with self.assertRaises(UpgradeRefused):
            self.status()
        with self.assertRaises(UpgradeRefused):
            with self.claim():
                pass

    def test_directory_fsync_failure_requires_reopen_and_retains_uncertain_running_action(self):
        with self.claim() as journal:
            real_sync = os.fsync
            calls = 0
            def fail_second(descriptor):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("inert fsync fault")
                return real_sync(descriptor)
            with patch("retirement_journal.os.fsync", fail_second), self.assertRaises(OSError):
                journal.begin("quiesce")
            with self.assertRaises(UpgradeRefused):
                journal.succeed(self.receipt)
        with self.claim() as journal:
            self.assertEqual(journal.record["status"], "uncertain")
            journal.reconcile(applied=False, evidence={**self.receipt, "unapplied_verified": True})

    def test_alias_and_nonprivate_journal_refuse_without_truncating_original(self):
        with self.claim():
            pass
        path = self.root / "retirement-journal-v1.json"
        before = path.read_bytes()
        path.chmod(0o644)
        with self.assertRaises(UpgradeRefused):
            with self.claim():
                pass
        self.assertEqual(path.read_bytes(), before)
        path.chmod(0o600)
        original = self.root / "retained-original"
        path.rename(original)
        path.symlink_to(original)
        with self.assertRaises(UpgradeRefused):
            with self.claim():
                pass
        self.assertEqual(original.read_bytes(), before)
