import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import uuid

from native_operator import read_status
from upgrade_journal import canonical, UpgradeRefused
import test_retirement_journal


@unittest.skipUnless(sys.platform == "linux", "Native operator custody requires Linux")
class NativeOperatorStatusTest(unittest.TestCase):
    def setUp(self):
        self.fixture = test_retirement_journal.RetirementJournalTest()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.root = self.fixture.root
        self.program = Path(__file__).with_name("native_operator.py")

    def files(self):
        return {str(path): (path.stat().st_ino, path.stat().st_mode, path.read_bytes())
                for path in self.root.rglob("*") if path.is_file()}

    def cli(self, installation=None):
        return subprocess.run([sys.executable, str(self.program), "status", "--history-directory", str(self.root),
                               "--installation", installation or self.fixture.installation], stdin=subprocess.DEVNULL,
                              capture_output=True, timeout=10)

    def test_cli_observes_live_owner_without_claiming_or_changing_records(self):
        with self.fixture.claim() as journal:
            journal.begin("quiesce")
            before = self.files()
            result = self.cli()
            self.assertEqual(result.returncode, 0)
            value = json.loads(result.stdout)
            self.assertEqual(value["activation_record"]["candidate"], "b" * 40)
            self.assertEqual(value["upgrades"][-1]["status"], "complete")
            self.assertEqual(value["retirement"]["status"], "running")
            self.assertTrue(value["retirement"]["owner_alive"])
            self.assertEqual(len(value["limitations"]), 3)
            self.assertEqual(self.files(), before)

    def test_real_killed_owner_is_observed_as_uncertain_without_reconciliation(self):
        plan_path = self.root / "test-retirement-status-plan.json"
        plan_path.write_bytes(canonical(self.fixture.plan))
        plan_path.chmod(0o600)
        code = "import hashlib,json,sys;from pathlib import Path;from retirement_journal import RetirementJournal;from upgrade_journal import canonical;plan=json.loads(Path(sys.argv[2]).read_bytes());\nwith RetirementJournal(sys.argv[1],plan,hashlib.sha256(canonical(plan)).hexdigest()) as journal:\n journal.begin('quiesce');print('owned',flush=True);sys.stdin.read()\n"
        child = subprocess.Popen([sys.executable, "-c", code, str(self.root), str(plan_path)],
                                 cwd=self.program.parent, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            self.assertEqual(child.stdout.readline(), b"owned\n")
            child.kill()
            child.wait(timeout=5)
            before = self.files()
            result = self.cli()
            self.assertEqual(result.returncode, 0)
            value = json.loads(result.stdout)
            self.assertEqual(value["retirement"]["status"], "uncertain")
            self.assertFalse(value["retirement"]["owner_alive"])
            self.assertEqual(json.loads((self.root / "retirement-journal-v1.json").read_bytes())["status"], "running")
            self.assertEqual(self.files(), before)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
            child.stdin.close()
            child.stdout.close()

    def test_wrong_installation_and_private_alias_refuse_without_detail_or_changes(self):
        before = self.files()
        result = self.cli(str(uuid.uuid4()))
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(json.loads(result.stderr), {"status": "refused", "code": "native_operator_status_invalid"})
        self.assertEqual(self.files(), before)
        (self.root / "current-release-v1.json").chmod(0o644)
        before = self.files()
        self.assertEqual(self.cli().returncode, 2)
        self.assertEqual(self.files(), before)
        pointer = self.root / "current-release-v1.json"
        pointer.chmod(0o600)
        (self.root / "current-release-alias").hardlink_to(pointer)
        before = self.files()
        self.assertEqual(self.cli().returncode, 2)
        self.assertEqual(self.files(), before)

    def test_concurrent_record_change_refuses_instead_of_reporting_a_mixed_snapshot(self):
        with self.fixture.claim() as journal:
            journal.begin("quiesce")
            original = (self.root / "retirement-journal-v1.json").read_bytes()
            from upgrade_history import UpgradeHistory
            actual = UpgradeHistory.read_history
            def changed(*args):
                result = actual(*args)
                journal.fail("quiescence_failed")
                return result
            with patch("native_operator.UpgradeHistory.read_history", side_effect=changed):
                with self.assertRaises(UpgradeRefused):
                    read_status(self.root, self.fixture.installation)
            self.assertNotEqual((self.root / "retirement-journal-v1.json").read_bytes(), original)
            self.assertEqual(read_status(self.root, self.fixture.installation)["retirement"]["status"], "failed")

    def test_activation_record_must_agree_with_terminal_upgrade_identity(self):
        pointer = self.root / "current-release-v1.json"
        original = pointer.read_bytes()
        value = json.loads(original)
        value.update(candidate="a" * 40, artifact_sha256="c" * 64)
        pointer.write_bytes(canonical(value) + b"\n")
        before = self.files()
        self.assertEqual(self.cli().returncode, 2)
        self.assertEqual(self.files(), before)
        pointer.write_bytes(original)
        self.assertEqual(self.cli().returncode, 0)

    def test_enrollment_refusal_reveals_no_private_input_path_and_changes_no_existing_history(self):
        before = self.files()
        for action in ["enroll", "enroll-resume"]:
            result = subprocess.run([sys.executable,str(self.program),action,"--inputs-directory",
                                    str(self.root / "private-bootstrap-material"),"--request-sha256","0" * 64],
                                   stdin=subprocess.DEVNULL,capture_output=True,timeout=10)
            self.assertEqual(result.returncode,2)
            self.assertEqual(result.stdout,b"")
            self.assertEqual(json.loads(result.stderr),{"status":"refused","code":"native_operator_enrollment_invalid"})
            self.assertNotIn(b"private-bootstrap-material",result.stderr)
            self.assertEqual(self.files(),before)
