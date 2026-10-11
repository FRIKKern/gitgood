import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit, urlunsplit

from native_inventory import directory_identity, observe_database
from native_retirement import INPUTS, NativeRetirement
from retirement_journal import RetirementJournal, STAGES
from upgrade_journal import canonical, UpgradeRefused
import test_retirement_snapshot
import test_retirement_restore_plan


@unittest.skipUnless(sys.platform == "linux" and os.environ.get("GITGOOD_TEST_DATABASE_LOCALE") == "true", "Actual PostgreSQL18.4/private native input profile required")
class NativeRetirementInputTest(unittest.TestCase):
    def setUp(self):
        self.fixture = test_retirement_snapshot.RetirementSnapshotTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        fixture = self.fixture
        self.history = fixture.base / "executor-history"
        self.history.mkdir(mode=0o700)
        for name in ["upgrade-history-v1.json", "current-release-v1.json"]:
            shutil.copyfile(fixture.history / name, self.history / name)
            (self.history / name).chmod(0o600)
        shutil.copytree(fixture.history / "operations", self.history / "operations")
        template = test_retirement_restore_plan.FullRestorationPlanTest()
        template.setUp()
        full = copy.deepcopy(template.value)
        full.update(protocol=3, operation=fixture.operation, installation=fixture.bindings["installation"])
        database = fixture.fixture
        name = "gitgood_retirement_restore_" + fixture.operation.replace("-", "")
        database._tool("createdb", ["--template=template0", "--encoding=UTF8", "--locale=C.UTF-8", "--locale-provider=libc", name])
        url = urlunsplit(urlsplit(database.url)._replace(path="/" + name))
        target_database = observe_database(database.psql, url)
        def cleanup_target():
            self.assertEqual(observe_database(database.psql, url), target_database)
            # Administrative fixture cleanup is not the input-refusal operation.
            # Keep the production retirement command's 10s statement/5s lock
            # bounds and this helper's 15s child bound; never force live sessions.
            cleanup_environment = {**database.environment,
                "PGOPTIONS": "-c statement_timeout=10000 -c lock_timeout=5000 -c search_path=pg_catalog"}
            database._tool("dropdb", [name], cleanup_environment)
        self.addCleanup(cleanup_target)
        target = fixture.base / name
        target.mkdir(mode=0o700)
        full["data_plan"].update(operation=fixture.operation, installation=fixture.bindings["installation"], target_database=target_database)
        full["materialization"].update(operation=fixture.operation, installation=fixture.bindings["installation"], candidate=fixture.plan["candidate"],
            ciphertext_sha256=fixture.plan["archive_sha256"], source=fixture.retention["archive"]["path"], key_path=fixture.retention["key"]["path"],
            scratch_directory=fixture.retention["scratch"]["path"], target_database=target_database, target_root=directory_identity(target, private=True))
        target_installation = full["materialization"]["target_installation"]
        for role, group in full["target_groups"].items():
            group["path"] = "/sys/fs/cgroup/gitgood-installation-" + full["installation"] + "/retirement-" + fixture.operation + "/" + target_installation + "/" + role
            group["kernel_path"] = group["path"][len("/sys/fs/cgroup"):]
        full["outsider_probe_directory"] = {**full["probe_directory"], "path": "/retained/outsider-probes", "inode": 110}
        full["outsider_probe_sha256"] = "e" * 64
        self.plan = {**fixture.plan, "restore_sha256": hashlib.sha256(canonical(full)).hexdigest()}
        self.digest = hashlib.sha256(canonical(self.plan)).hexdigest()
        self.directory = fixture.base / "executor-inputs"
        self.directory.mkdir(mode=0o700)
        values = {"plan": self.plan, "resources": fixture.resources, "retention": fixture.retention, "checkpoint": fixture.expected, "restoration": full}
        for key, (filename, maximum) in INPUTS.items():
            path = self.directory / filename
            path.write_bytes(canonical(values[key]) + b"\n")
            path.chmod(0o600)
        # Kernel groups/artifact/archive are controlled inputs in this component;
        # private files, actual database identities, OS locks and CLI are real.
        # No component fixture grants actual installed execution acceptance.

    def action(self):
        return NativeRetirement(self.history, self.directory, self.digest)

    def files(self):
        return {str(p): (p.stat().st_dev, p.stat().st_ino, p.stat().st_mode, p.read_bytes())
                for p in self.history.rglob("*") if p.is_file()}

    def test_changed_input_refuses_before_new_responsibility_or_source_changes(self):
        action = self.action()
        source = (self.fixture.root / "configuration/installation.json").read_bytes()
        path = self.directory / "retention.json"
        path.write_bytes(path.read_bytes().replace(b'"protocol":1', b'"protocol":2'))
        before = self.files()
        with self.assertRaises(UpgradeRefused):
            action.run()
        self.assertEqual(self.files(), before)
        self.assertEqual((self.fixture.root / "configuration/installation.json").read_bytes(), source)
        self.assertFalse((self.history / "retirement-journal-v1.json").exists())

    def test_same_bytes_replacement_alias_and_open_modes_are_refused(self):
        action = self.action()
        path = self.directory / "checkpoint.json"
        replacement = self.directory / "owned-replacement"
        replacement.write_bytes(path.read_bytes())
        replacement.chmod(0o600)
        os.replace(replacement, path)
        with self.assertRaises(UpgradeRefused):
            action._inputs_unchanged()
        path.chmod(0o644)
        with self.assertRaises(UpgradeRefused):
            self.action()
        path.chmod(0o600)
        replacement.write_bytes(path.read_bytes())
        replacement.chmod(0o600)
        path.unlink()
        path.symlink_to(replacement)
        with self.assertRaises(UpgradeRefused):
            self.action()
        self.assertTrue(path.is_symlink())

    def test_resealed_command_field_is_not_an_execution_escape(self):
        value = {**self.plan, "command": "private-test-input-must-not-execute"}
        (self.directory / "plan.json").write_bytes(canonical(value))
        with self.assertRaises(UpgradeRefused):
            NativeRetirement(self.history, self.directory, hashlib.sha256(canonical(value)).hexdigest())
        self.assertFalse((self.history / "retirement-journal-v1.json").exists())

    def test_real_competing_owner_refuses_without_changing_held_responsibility(self):
        action = self.action()
        with RetirementJournal(self.history, self.plan, self.digest):
            before = self.files()
            with patch("native_retirement.cgroup_identity", return_value=self.fixture.bindings["cgroups"]["driver"]):
                with self.assertRaises(UpgradeRefused):
                    action.run()
            self.assertEqual(self.files(), before)

    def test_terminal_same_intent_reports_only_inert_record_and_preserves_files(self):
        # Inert journal authority deliberately tests metadata-only behavior:
        # source still exists and no actual function or deletion is inferred.
        inert = {"receipt_sha256": "f" * 64, "archive_identity_verified": True, "restore_function_verified": True,
                 "current_snapshot_verified": True, "writer_exclusion_verified": True, "resource_reobserved": True,
                 "desired_state_verified": True, "retained_archive_usable": True, "owned_resources_absent": True}
        with RetirementJournal(self.history, self.plan, self.digest) as journal:
            for stage in STAGES:
                journal.begin(stage)
                journal.succeed(inert)
        before = self.files()
        for number in range(2):
            result = self.action().run()
            self.assertEqual(result["outcome"], "recorded_complete")
            self.assertNotIn("retained_archive_usable", result)
            self.assertEqual(self.files(), before)
        self.assertTrue((self.fixture.root / "configuration/installation.json").exists())

    def test_cli_private_invalid_input_has_fixed_refusal_and_no_echo(self):
        private = "private_test_input_never_echo"
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("native_operator.py")), "retire",
            "--history-directory", str(self.history), "--plan-directory", str(self.directory), "--plan-sha256", private],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stderr), {"status": "refused", "code": "native_operator_retirement_invalid"})
        self.assertNotIn(private.encode(), result.stdout + result.stderr)
        self.assertFalse((self.history / "retirement-journal-v1.json").exists())


@unittest.skipUnless(sys.platform != "linux", "Foreign-platform early refusal")
class UnsupportedNativeRetirementTest(unittest.TestCase):
    def test_foreign_platform_cannot_open_private_inputs_or_publish_intent(self):
        with self.assertRaises(UpgradeRefused):
            NativeRetirement("unavailable", "unavailable", "f" * 64)
