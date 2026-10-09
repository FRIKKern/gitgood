import copy
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

from upgrade_journal import STAGES, UpgradeJournal, UpgradeRefused


@unittest.skipUnless(sys.platform == "linux", "Native upgrade operations require Linux")
class UpgradeJournalTest(unittest.TestCase):
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
        self.evidence = {"receipt_sha256": hashlib.sha256(b"inert test observation").hexdigest()}

    def journal(self, intent=None, operation=None):
        return UpgradeJournal(self.root, operation or self.operation, intent or self.intent)

    def child(self, body, *, wait=True):
        code = "import json,sys;from pathlib import Path;from upgrade_journal import UpgradeJournal,UpgradeRefused;" + body
        environment = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                       "PYTHONPATH": str(Path(__file__).parent)}
        process = subprocess.Popen([sys.executable, "-c", code, str(self.root), self.operation,
                                    json.dumps(self.intent)], env=environment,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        return process.communicate(timeout=10) + (process.returncode,) if wait else process

    def test_fixed_stage_order_and_terminal_receipt(self):
        with self.journal() as journal:
            for stage in STAGES:
                with self.assertRaises(UpgradeRefused):
                    journal.begin("activate" if stage != "activate" else "inspect")
                journal.begin(stage)
                journal.succeed(stage, self.evidence)
            self.assertEqual(journal.status()["status"], "complete")
        with self.journal() as journal:
            self.assertEqual(journal.status()["completed"], list(STAGES))
            with self.assertRaises(UpgradeRefused):
                journal.begin("inspect")

    def test_forward_repair_preserves_failed_events_and_repeats_migration_and_probes(self):
        with self.journal() as journal:
            for stage in STAGES[:6]:
                journal.begin(stage)
                journal.succeed(stage, self.evidence)
            journal.begin("public_verify")
            journal.fail("public_probe_failed")
            journal.begin_recovery()
            journal.fail("recovery_failed")
            before = copy.deepcopy(journal.record["events"])
            evidence = {**self.evidence, "artifact_verified": True, "schema_observed": True, "completed_stages": 3}
            for field, value in [("artifact_verified", False), ("schema_observed", False), ("completed_stages", True), ("completed_stages", 6)]:
                with self.subTest(field=field), self.assertRaises(UpgradeRefused):
                    journal.forward_repair({**evidence, field: value})
                self.assertEqual(journal.record["events"], before)
            journal.forward_repair(evidence)
            self.assertEqual(journal.record["events"][:-1], before)
            self.assertEqual(journal.status()["completed"], list(STAGES[:3]))
            with self.assertRaises(UpgradeRefused):
                journal.begin("activate")
            for stage in STAGES[3:]:
                journal.begin(stage)
                journal.succeed(stage, self.evidence)
        with self.journal() as journal:
            self.assertEqual(journal.status()["status"], "complete")
            self.assertEqual(journal.status()["last_failure"], {"stage": "recover", "code": "recovery_failed"})
            with self.assertRaises(UpgradeRefused):
                journal.forward_repair(evidence)

    def test_lost_forward_repair_acknowledgement_poisoned_owner_reopens_durable_pending_migration(self):
        with self.journal() as journal:
            for stage in STAGES[:3]:
                journal.begin(stage)
                journal.succeed(stage, self.evidence)
            journal.begin("migrate")
            journal.fail("migration_failed")
            sync = os.fsync
            count = 0
            def lose_ack(descriptor):
                nonlocal count
                sync(descriptor)
                count += 1
                if count == 2:
                    raise OSError("actual directory sync completed; controlled lost acknowledgement")
            with patch("upgrade_journal.os.fsync", side_effect=lose_ack), self.assertRaises(OSError):
                journal.forward_repair({**self.evidence, "artifact_verified": True, "schema_observed": True, "completed_stages": 3})
            self.assertFalse(journal.usable)
            with self.assertRaises(UpgradeRefused):
                journal.begin("migrate")
        with self.journal() as journal:
            self.assertEqual(journal.status()["status"], "pending")
            self.assertEqual(journal.status()["completed"], list(STAGES[:3]))
            journal.begin("migrate")

    def test_changed_candidate_bindings_or_operation_never_replace_intent(self):
        with self.journal():
            pass
        before = (self.root / "upgrade-journal-v1.json").read_bytes()
        for field in ["new_candidate", "bindings_sha256", "new_artifact_sha256"]:
            changed = copy.deepcopy(self.intent)
            changed[field] = "f" * len(changed[field])
            with self.subTest(field=field), self.assertRaises(UpgradeRefused):
                with self.journal(changed):
                    pass
            self.assertEqual((self.root / "upgrade-journal-v1.json").read_bytes(), before)
        with self.assertRaises(UpgradeRefused):
            with self.journal(operation=str(uuid.uuid4())):
                pass

    def test_another_real_process_cannot_claim_active_journal(self):
        with self.journal():
            output, error, code = self.child(
                "\ntry:\n with UpgradeJournal(Path(sys.argv[1]),sys.argv[2],json.loads(sys.argv[3])): pass"
                "\nexcept UpgradeRefused: sys.exit(23)"
            )
            self.assertEqual(code, 23, error)

    def test_killed_owner_preserves_uncertain_stage_and_explicit_reconciliation(self):
        process = self.child(
            "\nwith UpgradeJournal(Path(sys.argv[1]),sys.argv[2],json.loads(sys.argv[3])) as journal:"
            "\n journal.begin('inspect');print('stage persisted',flush=True);sys.stdin.read()",
            wait=False)
        self.assertEqual(process.stdout.readline().strip(), "stage persisted")
        process.kill()  # Exact newly spawned fixture process, never a discovered foreign PID.
        os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOWAIT)
        before = (self.root / "upgrade-journal-v1.json").read_bytes()
        observed = UpgradeJournal.read_status(self.root, self.operation, self.intent)
        self.assertEqual(observed["status"], "uncertain")
        self.assertEqual(observed["recorded_status"], "running")
        self.assertFalse(observed["owner_alive"])
        self.assertEqual((self.root / "upgrade-journal-v1.json").read_bytes(), before)
        process.communicate(timeout=10)
        with self.journal() as journal:
            self.assertEqual(journal.status()["status"], "uncertain")
            with self.assertRaises(UpgradeRefused):
                journal.begin("inspect")
            with self.assertRaises(UpgradeRefused):
                journal.succeed("inspect", self.evidence)
            journal.reconcile(applied=False, evidence=self.evidence)
            journal.begin("inspect")
            journal.succeed("inspect", self.evidence)
        with self.journal() as journal:
            self.assertEqual(journal.status()["completed"], ["inspect"])

    def test_reconciled_applied_action_cannot_be_applied_twice(self):
        with self.journal() as journal:
            journal.begin("inspect")
        with self.journal() as journal:
            journal.reconcile(applied=True, evidence=self.evidence)
            with self.assertRaises(UpgradeRefused):
                journal.begin("inspect")
            journal.begin("stage")

    def test_failure_and_recovery_require_verified_public_previous_release(self):
        with self.journal() as journal:
            journal.begin("inspect")
            journal.fail("artifact_refused")
            journal.begin_recovery()
            with self.assertRaises(UpgradeRefused):
                journal.recovered(self.evidence)
            journal.recovered({**self.evidence, "previous_identity_verified": True,
                               "public_functional_probe": True})
            self.assertEqual(journal.status()["status"], "recovered")
            self.assertEqual(journal.status()["last_failure"], {"stage": "inspect", "code": "artifact_refused"})

    def test_payloads_or_missing_receipts_do_not_advance_memory_or_disk(self):
        with self.journal() as journal:
            journal.begin("inspect")
            before = (self.root / "upgrade-journal-v1.json").read_bytes()
            for evidence in [{}, {"receipt_sha256": "raw secret"},
                             {"receipt_sha256": True}, {**self.evidence, "count": -1},
                             {**self.evidence, "count": 2**63},
                             {**self.evidence, "password": "actual-private-fixture-value"}]:
                with self.assertRaises(UpgradeRefused):
                    journal.succeed("inspect", evidence)
                self.assertEqual(journal.status()["completed"], [])
                self.assertEqual((self.root / "upgrade-journal-v1.json").read_bytes(), before)

    def test_readonly_status_does_not_claim_or_mutate_a_live_operation(self):
        with self.journal() as journal:
            journal.begin("inspect")
            before = (self.root / "upgrade-journal-v1.json").read_bytes()
            for _ in range(30):
                status = UpgradeJournal.read_status(self.root, self.operation, self.intent)
                self.assertEqual(status["status"], "running")
                self.assertEqual(status["events"], 2)
            self.assertEqual((self.root / "upgrade-journal-v1.json").read_bytes(), before)

    def test_previous_boot_identity_never_identifies_a_current_process_as_owner(self):
        with self.journal() as journal:
            journal.begin("inspect")
        path = self.root / "upgrade-journal-v1.json"
        record = json.loads(path.read_text())
        record["owner"]["boot_id"] = str(uuid.uuid4())
        path.write_text(json.dumps(record))
        status = UpgradeJournal.read_status(self.root, self.operation, self.intent)
        self.assertEqual(status["status"], "uncertain")
        self.assertFalse(status["owner_alive"])

    def test_corrupted_stage_history_owner_or_failure_cannot_be_trusted(self):
        with self.journal() as journal:
            journal.begin("inspect")
        path = self.root / "upgrade-journal-v1.json"
        original = json.loads(path.read_text())
        mutations = [lambda value: value.update(status="pending"),
                     lambda value: value.update(completed=["inspect"]),
                     lambda value: value["owner"].update(pid=True),
                     lambda value: value["events"][0].update(kind="invented"),
                     lambda value: value["events"][1].update(stage="activate"),
                     lambda value: value["events"][0].update(evidence={"password": "private"})]
        for mutate in mutations:
            damaged = copy.deepcopy(original)
            mutate(damaged)
            path.write_text(json.dumps(damaged))
            before = path.read_bytes()
            with self.subTest(mutation=mutate), self.assertRaises(UpgradeRefused):
                UpgradeJournal.read_status(self.root, self.operation, self.intent)
            with self.assertRaises(UpgradeRefused):
                with self.journal():
                    pass
            self.assertEqual(path.read_bytes(), before)
        path.write_text(json.dumps(original))

    def test_lost_persist_reply_disables_owner_and_reopen_requires_reconciliation(self):
        with self.journal() as journal:
            persist = journal._persist
            def lost_reply():
                persist()
                raise OSError("simulated lost durable-write acknowledgement")
            with patch.object(journal, "_persist", lost_reply), self.assertRaises(OSError):
                journal.begin("inspect")
            with self.assertRaises(UpgradeRefused):
                journal.succeed("inspect", self.evidence)
        with self.journal() as journal:
            self.assertEqual(journal.status()["status"], "uncertain")
            journal.reconcile(applied=False, evidence=self.evidence)

    def test_event_capacity_refuses_before_changing_stage(self):
        with self.journal() as journal:
            journal.record["events"] *= 1000
            journal._save()
            before = (self.root / "upgrade-journal-v1.json").read_bytes()
            with self.assertRaises(UpgradeRefused):
                journal.begin("inspect")
            self.assertEqual(journal.status()["stage"], None)
            self.assertEqual((self.root / "upgrade-journal-v1.json").read_bytes(), before)

    def test_interrupted_recovery_requires_new_explicit_public_verification(self):
        with self.journal() as journal:
            journal.begin("inspect")
            journal.fail("artifact_refused")
            journal.begin_recovery()
        with self.journal() as journal:
            self.assertEqual(journal.status()["status"], "uncertain")
            with self.assertRaises(UpgradeRefused):
                journal.recovered({**self.evidence, "previous_identity_verified": True,
                                   "public_functional_probe": True})
            journal.begin_recovery()
            journal.recovered({**self.evidence, "previous_identity_verified": True,
                               "public_functional_probe": True})

    def test_shared_directory_symlink_and_hardlink_refuse_without_modification(self):
        self.root.chmod(0o755)
        with self.assertRaises(UpgradeRefused):
            self.journal()
        self.root.chmod(0o700)
        unrelated = self.root / "unrelated"
        unrelated.write_text("retain")
        unrelated.chmod(0o600)
        link = self.root / "upgrade-journal-v1.json"
        link.symlink_to(unrelated)
        with self.assertRaises(OSError):
            with self.journal():
                pass
        link.unlink()
        os.link(unrelated, link)
        with self.assertRaises(UpgradeRefused):
            with self.journal():
                pass
        self.assertEqual(unrelated.read_text(), "retain")


class UnsupportedJournalPlatformTest(unittest.TestCase):
    @unittest.skipIf(sys.platform == "linux", "Linux is the supported operational profile")
    def test_foreign_platform_refuses_before_creating_any_file(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(UpgradeRefused):
                UpgradeJournal(Path(root), str(uuid.uuid4()), {})
            self.assertEqual(list(Path(root).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
