import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import unittest
from unittest.mock import patch
import uuid

import test_native_enrollment_inputs as fixtures
from enrollment_journal import EnrollmentRefused, STAGES
from native_enrollment_custody import NativeEnrollmentCustody
from upgrade_history import UpgradeHistory
from upgrade_journal import canonical, UpgradeRefused


@unittest.skipUnless(sys.platform == "linux", "Exclusive native installation custody requires Linux")
class InitialLifecycleCustodyTest(unittest.TestCase):
    def setUp(self):
        # Reuse sealed-input data, not an executable allocation capability.
        fixtures.EnrollmentInputCustodyTest.setUp(self)
        self.scope = patch("native_enrollment_custody.scope_identity", return_value=self.allocation["scope"])
        self.scope.start(); self.addCleanup(self.scope.stop)
        self.value = fixtures.EnrollmentInputCustodyTest.value(self)
        self.history = self.root / "history"
        self.evidence = {"receipt_sha256": hashlib.sha256(b"inert custody receipt").hexdigest()}

    save = fixtures.EnrollmentInputCustodyTest.save

    def custody(self):
        return NativeEnrollmentCustody(self.value)

    def upgrade(self):
        intent = {"installation": self.installation, "old_candidate": "a" * 40,
                  "new_candidate": "b" * 40, "old_artifact_sha256": "c" * 64,
                  "new_artifact_sha256": "d" * 64, "bindings_sha256": "e" * 64,
                  "rollback_policy": "same_schema_only"}
        return UpgradeHistory(self.history, str(uuid.uuid4()), intent)

    def child(self, body):
        script = """import json,sys
from pathlib import Path
from unittest.mock import patch
from native_enrollment_inputs import NativeEnrollmentInputs
from native_enrollment_custody import NativeEnrollmentCustody
from upgrade_journal import UpgradeRefused
from enrollment_journal import EnrollmentRefused
directory,digest,scope=sys.argv[1:]
with patch('native_enrollment_inputs.supported_platform',return_value='ubuntu-24.04-linux-x86_64'):
 inputs=NativeEnrollmentInputs(Path(directory),digest)
scope_patch=patch('native_enrollment_custody.scope_identity',return_value=json.loads(scope));scope_patch.start()
custody=NativeEnrollmentCustody(inputs)
""" + body
        process = subprocess.Popen([sys.executable, "-c", script, str(self.directory), self.digest,
                                    json.dumps(self.allocation["scope"])],
                                   env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                                        "PYTHONPATH": str(Path(__file__).parent)},
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        def cleanup():
            if process.poll() is None: process.kill()
            process.wait(timeout=10)
            for stream in [process.stdin, process.stdout, process.stderr]: stream.close()
        self.addCleanup(cleanup)
        return process

    def test_actual_competing_controller_and_upgrade_refuse_without_history_changes(self):
        with self.custody() as current:
            current.journal.begin("inspect"); current.owned({"inspect"})
            before = {p.name: p.read_bytes() for p in self.history.iterdir()}
            child = self.child("""try:
 with custody: pass
except UpgradeRefused: print('shared lifecycle refused')
else: raise AssertionError('competing installation owner admitted')
""")
            out, error = child.communicate(timeout=10)
            self.assertEqual(child.returncode, 0, error)
            self.assertEqual(out.strip(), "shared lifecycle refused")
            with self.assertRaises(UpgradeRefused):
                with self.upgrade(): pass
            self.assertEqual({p.name: p.read_bytes() for p in self.history.iterdir()}, before)

    def test_actual_killed_owner_reclaims_uncertainty_and_still_excludes_upgrades(self):
        child = self.child("""with custody:
 custody.journal.begin('inspect')
 print('owned',flush=True)
 sys.stdin.read()
""")
        self.assertEqual(child.stdout.readline().strip(), "owned")
        os.kill(child.pid, signal.SIGKILL)
        self.assertEqual(child.wait(timeout=10), -signal.SIGKILL)
        before = (self.history / "initial-enrollment-v1.json").read_bytes()
        with self.assertRaises(UpgradeRefused):
            with self.upgrade(): pass
        self.assertEqual((self.history / "initial-enrollment-v1.json").read_bytes(), before)
        with self.custody() as resumed:
            self.assertEqual(resumed.journal.record["status"], "uncertain")
            with self.assertRaises(UpgradeRefused): resumed.owned({"inspect"})
            resumed.owned({"inspect"}, observation=True)
            resumed.journal.reconcile(applied=False, evidence=self.evidence)
            resumed.journal.begin("inspect"); resumed.owned({"inspect"})
            self.assertEqual(resumed.journal.record["epoch"], 2)

    def test_reservation_survives_lost_first_journal_acknowledgement(self):
        with patch("enrollment_journal.EnrollmentJournal.__enter__", side_effect=OSError("inert first journal acknowledgement loss")):
            with self.assertRaises(OSError):
                with self.custody(): pass
        self.assertTrue((self.history / "initial-lifecycle-anchor-v1.json").is_file())
        self.assertFalse((self.history / "initial-enrollment-v1.json").exists())
        with self.assertRaises(UpgradeRefused):
            with self.upgrade(): pass
        self.assertFalse((self.history / "operations").exists())
        with self.custody() as resumed:
            self.assertEqual(resumed.journal.record["epoch"], 1)

    def test_named_shared_lock_replacement_refuses_current_and_next_owner(self):
        with self.custody() as current:
            current.journal.begin("inspect")
            named = self.history / ".upgrade-history-lock-v1"
            named.rename(self.history / "retained-original-shared-lock")
            named.write_bytes(b""); named.chmod(0o600)
            with self.assertRaises(UpgradeRefused): current.owned({"inspect"})
            with self.assertRaises(UpgradeRefused):
                with self.custody(): pass
            with self.assertRaises(UpgradeRefused):
                with self.upgrade(): pass
        self.assertTrue((self.history / "retained-original-shared-lock").is_file())

    def test_anchor_replacement_scope_change_and_boolean_alias_refuse(self):
        with self.custody() as current:
            current.journal.begin("inspect")
            with patch("native_enrollment_custody.scope_identity", return_value={**self.allocation["scope"], "boot_id":str(uuid.uuid4())}):
                with self.assertRaises(UpgradeRefused): current.owned({"inspect"})
            anchor = current.path; raw = anchor.read_bytes()
            other = self.history / "replacement-anchor"; other.write_bytes(raw); other.chmod(0o600)
            os.replace(other, anchor)
            with self.assertRaises(UpgradeRefused): current.owned({"inspect"})
        value = json.loads(raw); value["protocol"] = True
        anchor.write_bytes(canonical(value) + b"\n")
        with self.assertRaises(UpgradeRefused):
            with self.custody(): pass

    def test_no_terminal_replay_or_initial_receipt_fabricates_an_upgrade(self):
        with self.custody() as current:
            for stage in STAGES:
                current.journal.begin(stage); current.owned({stage})
                current.journal.succeed(stage, self.evidence)
        before = {p.name:p.read_bytes() for p in self.history.iterdir()}
        with self.custody() as replay:
            self.assertEqual(replay.journal.record["status"], "complete")
        self.assertEqual({p.name:p.read_bytes() for p in self.history.iterdir()}, before)
        with self.assertRaises(UpgradeRefused):
            with self.upgrade(): pass
        self.assertFalse((self.history / "upgrade-history-v1.json").exists())
        self.assertFalse((self.history / "operations").exists())

    def test_existing_retirement_or_upgrade_intent_refuses_before_initial_claim(self):
        for name in ["retirement-journal-v1.json", "upgrade-history-v1.json"]:
            path = self.history / name; path.write_bytes(b"retained foreign lifecycle intent"); path.chmod(0o600)
            with self.subTest(name=name), self.assertRaises(UpgradeRefused):
                with self.custody(): pass
            self.assertEqual(path.read_bytes(), b"retained foreign lifecycle intent")
            self.assertFalse((self.history / "initial-enrollment-v1.json").exists())
            path.unlink()
