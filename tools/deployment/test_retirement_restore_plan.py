import copy
import hashlib
import os
import sys
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import patch

from retirement_restore_plan import validate_full_restore_plan
from upgrade_journal import canonical, UpgradeRefused


@unittest.skipUnless(sys.platform == "linux", "Linux restoration plan profile")
class FullRestorationPlanTest(unittest.TestCase):
    def setUp(self):
        operation, installation, target = [str(uuid.uuid4()) for _ in range(3)]
        database = {"address": "127.0.0.1", "cluster": "7694734359310268359", "database": "gitgood_retirement_restore_" + operation.replace("-", ""),
                    "database_oid": 1001, "encoding": "UTF8", "owner_oid": 17, "port": 55432, "role_oid": 17, "version": "18.4"}
        self.value = {"protocol": 2, "purpose": "retirement_functional_restore_plan", "operation": operation, "installation": installation,
                      "data_plan": {"protocol": 1, "purpose": "retirement_restore_data_plan", "operation": operation,
                                    "installation": installation, "target_database": database},
                      "materialization": {"protocol": 1, "operation": operation, "installation": installation, "candidate": "a" * 40,
                            "ciphertext_sha256": "b" * 64, "source": "/retained/archive.ggbackup", "key_path": "/retained/key.bin",
                            "scratch_directory": "/retained", "target_database": database, "target_installation": target,
                            "target_root": {"path": "/targets/" + database["database"], "device": 17, "inode": 101, "uid": os.getuid()},
                            "ports": dict(zip(["forge", "web", "native_ssh", "https", "ssh"], range(27000, 27005)))},
                      "target_groups": {name: {"path": "/sys/fs/cgroup/gitgood-installation-" + installation + "/retirement-" + operation + "/" + target + "/" + name,
                            "kernel_path": "/gitgood-installation-" + installation + "/retirement-" + operation + "/" + target + "/" + name, "device": 29, "inode": 100 + index,
                            "delegated_uid": os.getuid()} for index, name in enumerate(["native", "web", "edge", "maintenance"])},
                      "probe_directory": {"path": "/retained/probes", "device": 17, "inode": 103, "uid": os.getuid()}, "probe_sha256": "c" * 64,
                      "outsider_token": {"path": "/retained/outsider-token", "device": 17, "inode": 104, "uid": os.getuid(), "mode": 0o600, "bytes": 43, "sha256": "d" * 64}}
        self.journal = SimpleNamespace(operation=operation, plan={"operation": operation, "installation": installation,
                "candidate": "a" * 40, "archive_sha256": "b" * 64, "restore_sha256": hashlib.sha256(canonical(self.value)).hexdigest()})

    def sealed(self, value):
        self.journal.plan["restore_sha256"] = hashlib.sha256(canonical(value)).hexdigest()
        return validate_full_restore_plan(self.journal, value)

    def test_parsing_returns_independent_inputs_without_granting_success(self):
        before = canonical(self.value)
        parsed = validate_full_restore_plan(self.journal, self.value)
        self.assertEqual(canonical(parsed), before)
        self.assertNotIn("restore_function_verified", parsed)
        parsed["materialization"]["ports"]["forge"] += 1
        self.assertEqual(canonical(self.value), before)

    def test_resealed_foreign_or_original_installation_groups_refuse(self):
        for substitute in [self.value["installation"], str(uuid.uuid4())]:
            changed = copy.deepcopy(self.value)
            changed["target_groups"]["maintenance"]["path"] = "/sys/fs/cgroup/gitgood-installation-" + substitute + "/maintenance"
            with self.assertRaises(UpgradeRefused):
                self.sealed(changed)
        changed = copy.deepcopy(self.value)
        changed["materialization"]["target_installation"] = changed["installation"]
        with self.assertRaises(UpgradeRefused):
            self.sealed(changed)

    def test_resealed_mixed_database_targets_and_claimed_success_refuse(self):
        changed = copy.deepcopy(self.value)
        # Keep separately supplied bindings independent rather than sharing the
        # fixture's reference, just as a serialized plan would.
        changed["materialization"]["target_database"] = {**changed["materialization"]["target_database"], "database_oid": 1002}
        with self.assertRaises(UpgradeRefused):
            self.sealed(changed)
        changed = {**self.value, "restore_function_verified": True}
        with self.assertRaises(UpgradeRefused):
            self.sealed(changed)

    def test_changed_inputs_require_the_original_independent_digest(self):
        changed = copy.deepcopy(self.value)
        changed["probe_sha256"] = "e" * 64
        with self.assertRaises(UpgradeRefused):
            validate_full_restore_plan(self.journal, changed)

    def test_resealed_wrong_retirement_slot_and_kernel_alias_refuse(self):
        original = self.value["target_groups"]["maintenance"]["path"]
        for path in [original.replace(self.value["operation"], str(uuid.uuid4())),
                     original.replace("/retirement-", "/unrelated-"),
                     original + "/../maintenance"]:
            changed = copy.deepcopy(self.value)
            changed["target_groups"]["maintenance"]["path"] = path
            changed["target_groups"]["maintenance"]["kernel_path"] = path[len("/sys/fs/cgroup"):]
            with self.assertRaises(UpgradeRefused):
                self.sealed(changed)
        changed = copy.deepcopy(self.value)
        changed["target_groups"]["maintenance"]["kernel_path"] += "/descendant"
        with self.assertRaises(UpgradeRefused):
            self.sealed(changed)

    def test_full_actor_version_binds_distinct_private_outsider_inputs(self):
        changed = {**self.value, "protocol": 3, "outsider_probe_directory": {"path": "/retained/outsider-probes", "device": 17,
                   "inode": 111, "uid": os.getuid()}, "outsider_probe_sha256": "e" * 64}
        self.assertEqual(self.sealed(changed)["protocol"], 3)
        for path in [self.value["probe_directory"]["path"], self.value["probe_directory"]["path"] + "/nested",
                     self.value["materialization"]["target_root"]["path"] + "/outsider"]:
            altered = copy.deepcopy(changed)
            altered["outsider_probe_directory"]["path"] = path
            with self.assertRaises(UpgradeRefused):
                self.sealed(altered)
        with self.assertRaises(UpgradeRefused):
            self.sealed({**changed, "protocol": 2})
        altered = {**changed, "outsider_probe_sha256": "f" * 64}
        self.sealed(changed)
        with self.assertRaises(UpgradeRefused):
            validate_full_restore_plan(self.journal, altered)

    def test_resealed_private_identity_aliases_and_malformed_ports_refuse(self):
        changes = [("probe_directory", "path", self.value["materialization"]["target_root"]["path"] + "/probes"),
                   ("probe_directory", "path", "/retained/../foreign/probes"),
                   ("probe_directory", "uid", os.getuid() + 1), ("outsider_token", "mode", 0o644)]
        for section, key, value in changes:
            changed = copy.deepcopy(self.value)
            changed[section][key] = value
            with self.assertRaises(UpgradeRefused):
                self.sealed(changed)
        for port in [True, 443, 65536, "27000"]:
            changed = copy.deepcopy(self.value)
            changed["materialization"]["ports"]["forge"] = port
            with self.assertRaises(UpgradeRefused):
                self.sealed(changed)


@unittest.skipUnless(sys.platform != "linux", "Foreign-platform early refusal")
class UnsupportedRestorationPlanTest(unittest.TestCase):
    def test_foreign_profile_refuses_before_path_or_journal_access(self):
        with patch("retirement_restore_plan.Path", side_effect=AssertionError("No filesystem access permitted")):
            with self.assertRaises(UpgradeRefused):
                validate_full_restore_plan(None, {})
