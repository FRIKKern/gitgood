import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from native_inventory import directory_identity
from native_upgrade_command import NativeUpgradeCommand
from upgrade_history import UpgradeHistory
from upgrade_journal import canonical, STAGES, UpgradeRefused
import test_native_upgrade


@unittest.skipUnless(sys.platform == "linux", "Private native input and real lifecycle-lock profile")
class UpgradeCommandInputTest(unittest.TestCase):
    def setUp(self):
        self.fixture = test_native_upgrade.PlanCustodyTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        fixture = self.fixture
        resources = {"root": directory_identity(fixture.root, private=True)}
        for name in ["storage", "ssh-host", "configuration"]:
            path = fixture.root / name
            path.mkdir(mode=0o700)
            resources[name] = directory_identity(path, private=True)
        self.driver = {"path": "/controlled/driver", "kernel_path": Path("/proc/self/cgroup").read_text().strip()[3:],
                       "device": 7, "inode": 8, "delegated_uid": os.getuid()}
        installation = fixture.intent["installation"]
        bindings = {"protocol": 1, "installation": installation, "host": "controlled", "uid": os.getuid(),
                    "platform": "linux-x86_64", "resources": resources, "configuration_sha256": {},
                    "ssh_host_key_sha256": {}, "executables": {}, "cgroups": {"driver": self.driver}, "database": {}}
        digest = hashlib.sha256(canonical(bindings)).hexdigest()
        fixture.inventory = {"protocol": 1, "installation": installation, "bindings": bindings, "bindings_sha256": digest,
                             "observed_runtime_candidate": fixture.intent["old_candidate"], "limitations": ["Controlled kernel/artifact/data; input files, OS locks and CLI are real."]}
        fixture.intent["bindings_sha256"] = digest
        fixture.plan["intent_sha256"] = hashlib.sha256(canonical(fixture.intent)).hexdigest()
        self.directory = fixture.root / "inputs"
        self.directory.mkdir(mode=0o700)
        self.request = {"protocol": 1, "purpose": "native_upgrade_execution", "operation": fixture.operation,
                        "installation": installation, "root": resources["root"], "history": directory_identity(fixture.history, private=True),
                        "inventory_sha256": hashlib.sha256(canonical(fixture.inventory)).hexdigest(),
                        "intent_sha256": hashlib.sha256(canonical(fixture.intent)).hexdigest(), "plan_sha256": fixture.save()}
        self.save()

    def save(self):
        self.digest = hashlib.sha256(canonical(self.request)).hexdigest()
        for name, value in [("request", self.request), ("intent", self.fixture.intent), ("inventory", self.fixture.inventory)]:
            path = self.directory / (name + ".json")
            path.write_bytes(canonical(value) + b"\n")
            path.chmod(0o600)

    def action(self):
        return NativeUpgradeCommand(self.fixture.history, self.directory, self.digest)

    def history_files(self):
        return {str(p): (p.stat().st_dev, p.stat().st_ino, p.stat().st_mode, p.read_bytes())
                for p in self.fixture.history.rglob("*") if p.is_file()}

    def test_wrong_digest_or_changed_input_refuses_before_new_responsibility(self):
        before = self.history_files()
        with self.assertRaises(UpgradeRefused):
            NativeUpgradeCommand(self.fixture.history, self.directory, "0" * 64)
        action = self.action()
        path = self.directory / "intent.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaises(UpgradeRefused):
            action.run("upgrade")
        self.assertEqual(self.history_files(), before)
        self.assertFalse((self.fixture.history / "upgrade-history-v1.json").exists())

    def test_same_byte_replacement_alias_and_shared_permissions_refuse(self):
        action = self.action()
        path = self.directory / "inventory.json"
        other = self.directory / "replacement"
        other.write_bytes(path.read_bytes())
        other.chmod(0o600)
        os.replace(other, path)
        with self.assertRaises(UpgradeRefused):
            action.observe_inputs()
        path.chmod(0o644)
        with self.assertRaises(UpgradeRefused):
            self.action()
        path.chmod(0o600)
        other.write_bytes(path.read_bytes())
        other.chmod(0o600)
        path.unlink()
        path.symlink_to(other)
        with self.assertRaises(UpgradeRefused):
            self.action()
        self.assertTrue(path.is_symlink())

    def test_resealed_request_command_and_inventory_escape_refuse(self):
        self.request["command"] = "must_never_execute"
        self.save()
        with self.assertRaises(UpgradeRefused):
            self.action()
        del self.request["command"]
        self.fixture.inventory["command"] = "must_never_execute"
        self.request["inventory_sha256"] = hashlib.sha256(canonical(self.fixture.inventory)).hexdigest()
        self.save()
        with self.assertRaises(UpgradeRefused):
            self.action()
        self.assertFalse((self.fixture.history / "operations").exists())

    def test_actual_competing_lifecycle_lock_preserves_held_record(self):
        action = self.action()
        with UpgradeHistory(self.fixture.history, self.fixture.operation, self.fixture.intent):
            before = self.history_files()
            with patch("native_upgrade_command.cgroup_identity", return_value=self.driver):
                with self.assertRaises(UpgradeRefused):
                    action.run("upgrade")
            self.assertEqual(self.history_files(), before)

    def terminal(self, recovered):
        # Inert terminal receipts test historical metadata only. Actual installed
        # function, artifact/schema, database and kernel authority are unproved.
        receipt = {"receipt_sha256": "f" * 64}
        with UpgradeHistory(self.fixture.history, self.fixture.operation, self.fixture.intent) as journal:
            if recovered:
                journal.begin("inspect")
                journal.fail("artifact_refused")
                journal.begin_recovery()
                journal.recovered({**receipt, "previous_identity_verified": True, "public_functional_probe": True})
            else:
                for stage in STAGES:
                    journal.begin(stage)
                    journal.succeed(stage, receipt)
        before = self.history_files()
        for command in ["upgrade", "upgrade-recover", "upgrade-resume"]:
            for number in range(2):
                value = self.action().run(command)
                self.assertEqual(value["outcome"], "recorded_recovered" if recovered else "recorded_complete")
                self.assertNotIn("observations", value)
                self.assertEqual(self.history_files(), before)

    def test_inert_complete_terminal_preserves_history_without_claim_or_live_probe(self):
        self.terminal(False)

    def test_inert_recovered_terminal_preserves_failed_events_without_new_claim(self):
        self.terminal(True)

    def test_cli_invalid_private_digest_has_fixed_refusal_without_echo(self):
        private = "private_input_never_echo"
        before = self.history_files()
        for command in ["upgrade", "upgrade-recover", "upgrade-resume"]:
            value = subprocess.run([sys.executable, str(Path(__file__).with_name("native_operator.py")), command,
                "--history-directory", str(self.fixture.history), "--inputs-directory", str(self.directory),
                "--request-sha256", private], capture_output=True, stdin=subprocess.DEVNULL, timeout=10)
            self.assertEqual(value.returncode, 2)
            self.assertEqual(json.loads(value.stderr), {"status": "refused", "code": "native_operator_upgrade_invalid"})
            self.assertNotIn(private.encode(), value.stdout + value.stderr)
            self.assertEqual(self.history_files(), before)

    def test_probe_summary_omits_private_extras_and_refuses_wrong_identity(self):
        action = self.action()
        candidate = self.fixture.intent["new_candidate"]
        private = "private_remote_value_never_report"
        probes = {}
        for name, services in [("internal", ["gitgood", "gitgood-web"]), ("public", ["gitgood-web"])]:
            observation = {"candidate": candidate, "commit": "f" * 40, "anonymous_refused": True,
                           "https_ref_sha256": "e" * 64, "private_body": private,
                           "ready": [{"candidate": candidate, "service": service, "ready": True, "private_body": private} for service in services]}
            if name == "public":
                observation["ssh_ref_sha256"] = "e" * 64
            probes[name] = {"observations": observation, "private_body": private}
        result = {"outcome": "activated", "observations": {**probes, "before": ["20261001000000"], "after": ["20261001000000"], "pointer_sha256": "a" * 64}}
        self.assertNotIn(private, json.dumps(action.verification(result)))
        probes["public"]["observations"]["candidate"] = "0" * 40
        with self.assertRaises(UpgradeRefused):
            action.verification(result)


@unittest.skipIf(sys.platform == "linux", "Foreign-platform early refusal")
class UnsupportedUpgradeCommandTest(unittest.TestCase):
    def test_foreign_platform_refuses_before_private_input_reads(self):
        with self.assertRaises(UpgradeRefused):
            NativeUpgradeCommand(None, None, "f" * 64)
