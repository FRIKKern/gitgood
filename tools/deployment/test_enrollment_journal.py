import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

from enrollment_journal import EnrollmentJournal, EnrollmentRefused, STAGES, canonical


@unittest.skipUnless(sys.platform == "linux", "Initial native enrollment requires Linux")
class EnrollmentJournalTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.directory = Path(self.scratch.name)
        self.directory.chmod(0o700)
        self.operation = str(uuid.uuid4())
        self.intent = {"installation": str(uuid.uuid4()), "candidate": "a" * 40,
                       "artifact_sha256": "b" * 64, "allocation_sha256": "c" * 64,
                       "inputs_sha256": "d" * 64}
        self.request = {"protocol": 1, "purpose": "native_initial_enrollment",
                        "operation": self.operation, "intent": self.intent}
        self.request_sha256 = hashlib.sha256(canonical(self.request)).hexdigest()
        self.evidence = {"receipt_sha256": hashlib.sha256(b"inert component observation").hexdigest()}
        self.path = self.directory / "initial-enrollment-v1.json"

    def journal(self, intent=None, digest=None):
        return EnrollmentJournal(self.directory, self.operation, intent or self.intent,
                                 digest or self.request_sha256)

    def child(self, body):
        script = """import json,sys
from pathlib import Path
from enrollment_journal import EnrollmentJournal,EnrollmentRefused,STAGES
directory,operation,intent,digest=sys.argv[1:]
journal=EnrollmentJournal(Path(directory),operation,json.loads(intent),digest)
""" + body
        process = subprocess.Popen([sys.executable, "-c", script, str(self.directory), self.operation,
                                    json.dumps(self.intent), self.request_sha256],
                                   env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                                        "PYTHONPATH": str(Path(__file__).parent)},
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        def cleanup():
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
            for stream in [process.stdin, process.stdout, process.stderr]:
                if stream is not None:
                    stream.close()
        self.addCleanup(cleanup)
        return process

    def test_fixed_order_and_unchanged_terminal_replays(self):
        with self.journal() as journal:
            for stage in STAGES:
                before = self.path.read_bytes()
                with self.assertRaises(EnrollmentRefused):
                    journal.begin("enroll" if stage != "enroll" else "inspect")
                self.assertEqual(self.path.read_bytes(), before)
                journal.begin(stage)
                journal.succeed(stage, self.evidence)
            self.assertEqual(journal.status()["status"], "complete")
        before = self.path.read_bytes()
        for _ in range(3):
            with self.journal() as journal:
                self.assertEqual(journal.status()["completed"], list(STAGES))
                with self.assertRaises(EnrollmentRefused):
                    journal.begin("inspect")
            self.assertEqual(self.path.read_bytes(), before)
            self.assertEqual(EnrollmentJournal.read_status(self.directory, self.operation, self.intent,
                             self.request_sha256)["status"], "complete")
            self.assertEqual(self.path.read_bytes(), before)

    def test_real_competing_controller_refuses_and_status_does_not_claim(self):
        with self.journal() as journal:
            journal.begin("inspect")
            before = self.path.read_bytes()
            child = self.child("""try:
 with journal: pass
except EnrollmentRefused:
 print('exclusive lock refused')
else: raise AssertionError('another controller admitted')
""")
            out, error = child.communicate(timeout=10)
            self.assertEqual(child.returncode, 0, error)
            self.assertEqual(out.strip(), "exclusive lock refused")
            for _ in range(3):
                value = EnrollmentJournal.read_status(self.directory, self.operation, self.intent, self.request_sha256)
                self.assertEqual(value["status"], "running")
                self.assertEqual(value["epoch"], 1)
            self.assertEqual(self.path.read_bytes(), before)

    def test_actual_killed_owner_requires_observation_without_repeating_effect(self):
        child = self.child("""with journal:
 journal.begin('inspect')
 Path(directory,'observed-effect').write_text('one synthetic effect')
 print('effect applied',flush=True)
 sys.stdin.read()
""")
        self.assertEqual(child.stdout.readline().strip(), "effect applied")
        original = json.loads(self.path.read_text())
        os.kill(child.pid, signal.SIGKILL)
        self.assertEqual(child.wait(timeout=10), -signal.SIGKILL)
        before = self.path.read_bytes()
        status = EnrollmentJournal.read_status(self.directory, self.operation, self.intent, self.request_sha256)
        self.assertEqual(status["status"], "uncertain")
        self.assertFalse(status["owner_alive"])
        self.assertEqual(self.path.read_bytes(), before)
        with self.journal() as resumed:
            self.assertEqual(resumed.status()["epoch"], 2)
            self.assertEqual(resumed.record["events"][:len(original["events"])], original["events"])
            with self.assertRaises(EnrollmentRefused):
                resumed.begin("inspect")
            self.assertEqual((self.directory / "observed-effect").read_text(), "one synthetic effect")
            resumed.reconcile(applied=True, evidence=self.evidence)
            self.assertEqual(resumed.status()["completed"], ["inspect"])
            resumed.begin("stage")
        # This proves the journal/OS boundary only, not a real migration or owner bootstrap.

    def test_absent_effect_reconciliation_permits_only_same_next_stage(self):
        with self.journal() as journal:
            journal.begin("inspect")
        with self.journal() as journal:
            before = self.path.read_bytes()
            with self.assertRaises(EnrollmentRefused):
                journal.reconcile(applied=1, evidence=self.evidence)
            self.assertEqual(self.path.read_bytes(), before)
            journal.reconcile(applied=False, evidence=self.evidence)
            with self.assertRaises(EnrollmentRefused):
                journal.begin("stage")
            journal.begin("inspect")
            journal.succeed("inspect", self.evidence)

    def test_changed_sealed_request_and_unknown_fields_refuse_unchanged_record(self):
        with self.journal():
            pass
        before = self.path.read_bytes()
        changed = {**self.intent, "candidate": "e" * 40}
        resealed = hashlib.sha256(canonical({**self.request, "intent": changed})).hexdigest()
        with self.assertRaises(EnrollmentRefused):
            with self.journal(changed, resealed):
                pass
        for intent, digest in [({**self.intent, "command": "arbitrary"}, self.request_sha256),
                               (self.intent, "0" * 64)]:
            with self.assertRaises(EnrollmentRefused):
                self.journal(intent, digest)
        self.assertEqual(self.path.read_bytes(), before)

    def test_private_payloads_and_missing_receipts_refuse_before_mutation(self):
        with self.journal() as journal:
            journal.begin("inspect")
            before = self.path.read_bytes()
            for evidence in [{}, {"receipt_sha256": "private text"},
                             {**self.evidence, "password": "private fixture"}]:
                with self.assertRaises(EnrollmentRefused):
                    journal.succeed("inspect", evidence)
                self.assertEqual(self.path.read_bytes(), before)
            output = json.dumps(journal.status())
            self.assertNotIn("inputs_sha256", output)
            self.assertNotIn(self.intent["inputs_sha256"], output)

    def test_lost_begin_persistence_acknowledgement_poisoned_controller(self):
        with self.journal() as journal:
            persist = journal._persist
            def lost_reply():
                persist()
                raise OSError("lost durable acknowledgement")
            with patch.object(journal, "_persist", lost_reply), self.assertRaises(OSError):
                journal.begin("inspect")
            with self.assertRaises(EnrollmentRefused):
                journal.succeed("inspect", self.evidence)
        with self.journal() as journal:
            self.assertEqual(journal.status()["status"], "uncertain")
            journal.reconcile(applied=False, evidence=self.evidence)

    def test_lost_terminal_acknowledgement_reopens_without_claim_or_reexecution(self):
        with self.journal() as journal:
            for stage in STAGES[:-1]:
                journal.begin(stage)
                journal.succeed(stage, self.evidence)
            journal.begin(STAGES[-1])
            persist = journal._persist
            def lost_reply():
                persist()
                raise OSError("lost terminal acknowledgement")
            with patch.object(journal, "_persist", lost_reply), self.assertRaises(OSError):
                journal.succeed(STAGES[-1], self.evidence)
        before = self.path.read_bytes()
        with self.journal() as recorded:
            self.assertEqual(recorded.status()["status"], "complete")
        self.assertEqual(self.path.read_bytes(), before)

    def test_failed_publication_preserves_previous_record_and_poisoned_owner(self):
        with self.journal() as journal:
            before = self.path.read_bytes()
            with patch("enrollment_journal.os.replace", side_effect=OSError("publication refused")), self.assertRaises(OSError):
                journal.begin("inspect")
            self.assertEqual(self.path.read_bytes(), before)
            with self.assertRaises(EnrollmentRefused):
                journal.succeed("inspect", self.evidence)
            partials = list(self.directory.glob(".initial-enrollment-*.partial"))
            self.assertEqual(len(partials), 1)
            self.assertEqual(partials[0].stat().st_mode & 0o777, 0o600)
        with self.journal() as reopened:
            self.assertEqual(reopened.status()["status"], "pending")
            self.assertIsNone(reopened.status()["stage"])
            reopened.begin("inspect")

    def test_failure_reason_is_bound_to_current_stage_and_retry_keeps_events(self):
        with self.journal() as journal:
            journal.begin("inspect")
            before = self.path.read_bytes()
            with self.assertRaises(EnrollmentRefused):
                journal.fail("bootstrap_failed")
            self.assertEqual(self.path.read_bytes(), before)
            journal.fail("artifact_refused")
            previous = copy.deepcopy(journal.record["events"])
            journal.begin("inspect")
            journal.succeed("inspect", self.evidence)
            self.assertEqual(journal.record["events"][:len(previous)], previous)

    def test_tampered_history_or_epoch_refuses_without_repairing_record(self):
        with self.journal() as journal:
            journal.begin("inspect")
        original = json.loads(self.path.read_text())
        for change in [lambda v: v.update(status="pending"), lambda v: v.update(epoch=True),
                       lambda v: v["events"][1].update(stage="enroll"),
                       lambda v: v["events"][0].update(evidence={"password": "private"}),
                       lambda v: v.update(completed=["inspect"])]:
            value = copy.deepcopy(original)
            change(value)
            self.path.write_text(json.dumps(value))
            before = self.path.read_bytes()
            with self.assertRaises(EnrollmentRefused):
                EnrollmentJournal.read_status(self.directory, self.operation, self.intent, self.request_sha256)
            with self.assertRaises(EnrollmentRefused):
                with self.journal():
                    pass
            self.assertEqual(self.path.read_bytes(), before)
        self.path.write_text(json.dumps(original))

    def test_replaced_lock_or_record_refuses_live_controller_without_stage_change(self):
        with self.journal() as journal:
            before = self.path.read_bytes()
            old_lock = self.directory / "retained-original-lock"
            journal.lock_path.rename(old_lock)
            journal.lock_path.write_text("")
            journal.lock_path.chmod(0o600)
            with self.assertRaises(EnrollmentRefused):
                journal.begin("inspect")
            with self.assertRaises(EnrollmentRefused):
                with self.journal():
                    pass
            self.assertEqual(self.path.read_bytes(), before)
            journal.lock_path.unlink()
            old_lock.rename(journal.lock_path)
        with self.journal() as journal:
            value = json.loads(self.path.read_text())
            value["created_at"] = "2026-10-01T00:00:00+00:00"
            self.path.write_text(json.dumps(value))
            before = self.path.read_bytes()
            with self.assertRaises(EnrollmentRefused):
                journal.begin("inspect")
            self.assertEqual(self.path.read_bytes(), before)

    def test_other_namespace_cannot_be_reported_as_current_process_owner(self):
        with self.journal() as journal:
            journal.begin("inspect")
        record = json.loads(self.path.read_text())
        record["owner"]["mount_namespace"] = "mnt:[1]"
        record["events"][0]["owner"]["mount_namespace"] = "mnt:[1]"
        record["events"][1]["owner"]["mount_namespace"] = "mnt:[1]"
        self.path.write_text(json.dumps(record))
        before = self.path.read_bytes()
        status = EnrollmentJournal.read_status(self.directory, self.operation, self.intent, self.request_sha256)
        self.assertEqual(status["status"], "uncertain")
        self.assertFalse(status["owner_alive"])
        self.assertEqual(self.path.read_bytes(), before)

    def test_symlink_hardlink_and_shared_directory_refuse_retaining_unrelated_bytes(self):
        unrelated = self.directory / "unrelated"
        unrelated.write_bytes(b"retain unrelated fixture")
        unrelated.chmod(0o600)
        self.path.symlink_to(unrelated)
        with self.assertRaises(OSError):
            with self.journal():
                pass
        self.path.unlink()
        os.link(unrelated, self.path)
        with self.assertRaises(EnrollmentRefused):
            with self.journal():
                pass
        self.path.unlink()
        self.directory.chmod(0o755)
        with self.assertRaises(EnrollmentRefused):
            self.journal()
        self.directory.chmod(0o700)
        self.assertEqual(unrelated.read_bytes(), b"retain unrelated fixture")


if __name__ == "__main__":
    unittest.main()
