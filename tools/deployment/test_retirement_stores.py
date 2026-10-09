import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

from native_inventory import directory_identity
from retirement_journal import DIGESTS, RetirementJournal
from retirement_stores import RetirementStores, STORES, capture_store_plan
from upgrade_history import UpgradeHistory
from upgrade_journal import canonical, STAGES, UpgradeRefused


@unittest.skipUnless(sys.platform == "linux", "Descriptor-bound native removal requires Linux")
class RetirementStoresTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.base = Path(self.scratch.name)
        self.base.chmod(0o700)
        self.root = self.base / "installation"
        self.history = self.base / "history"
        for path in [self.root, self.history]:
            path.mkdir(mode=0o700)
        for name in STORES:
            (self.root / name).mkdir(mode=0o700)
        (self.root / "storage/objects").mkdir(mode=0o700)
        for name, value in [("storage/objects/object", b"inert private Git store fixture"), ("configuration/installation.json", b"inert private configuration"), ("ssh-host/host-key", b"inert private host material")]:
            path = self.root / name
            path.write_bytes(value)
            path.chmod(0o600)
        self.archive = self.base / "retained-archive"
        self.archive.write_bytes(b"inert archive fixture; not a recovery proof")
        self.key = self.base / "retained-key"
        self.key.write_bytes(b"inert external key fixture")
        self.unrelated = self.root / "unrelated"
        self.unrelated.write_bytes(b"retain unrelated operator data")
        installation = str(uuid.uuid4())
        groups = {}
        kernel = self.base / "controlled-kernel-fixture"
        kernel.mkdir(mode=0o700)
        self.kernel_path = Path("/proc/self/cgroup").read_text().strip().removeprefix("0::")
        for name in ["native", "web", "edge", "maintenance", "driver"]:
            group = kernel / name
            group.mkdir(mode=0o700)
            (group / "cgroup.events").write_text("populated 0\n")
            (group / "cgroup.procs").write_text("")
            groups[name] = {"path": str(group), "kernel_path": self.kernel_path,
                            "device": group.stat().st_dev, "inode": group.stat().st_ino, "delegated_uid": os.getuid()}
        self.bindings = {"protocol": 1, "installation": installation, "host": socket.gethostname(), "uid": os.getuid(),
                         "platform": "linux-x86_64", "resources": {name: directory_identity(self.root if name == "root" else self.root / name, private=True) for name in ["root", *STORES]},
                         "cgroups": groups, "configuration_sha256": {}, "ssh_host_key_sha256": {}, "executables": {}, "database": {}}
        digest = hashlib.sha256(canonical(self.bindings)).hexdigest()
        self.inventory = {"bindings": self.bindings, "bindings_sha256": digest}
        self.operation = str(uuid.uuid4())
        self.resource_plan = capture_store_plan(self.root, self.inventory, self.operation)
        upgrade = str(uuid.uuid4())
        intent = {"installation": installation, "old_candidate": "a" * 40, "new_candidate": "b" * 40,
                  "old_artifact_sha256": "c" * 64, "new_artifact_sha256": "d" * 64, "bindings_sha256": digest,
                  "rollback_policy": "same_schema_only"}
        self.receipt = {"receipt_sha256": hashlib.sha256(b"inert journal observations; no database action or restore").hexdigest()}
        with UpgradeHistory(self.history, upgrade, intent) as journal:
            for stage in STAGES:
                journal.begin(stage)
                journal.succeed(stage, self.receipt)
        pointer = {"protocol": 1, "installation": installation, "operation": upgrade, "candidate": "b" * 40,
                   "artifact_sha256": "d" * 64, "bindings_sha256": digest, "stage": self.bindings["resources"]["root"],
                   "stage_inventory_sha256": "f" * 64, "schema": ["20261007000000"], "public_probe_sha256": "f" * 64}
        path = self.history / "current-release-v1.json"
        path.write_bytes(canonical(pointer) + b"\n")
        path.chmod(0o600)
        self.plan = {"protocol": 1, "operation": self.operation, "installation": installation, "candidate": "b" * 40,
                     **{key: "f" * 64 for key in DIGESTS}, "bindings_sha256": digest, "artifact_sha256": "d" * 64,
                     "current_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                     "resource_plan_sha256": hashlib.sha256(canonical(self.resource_plan)).hexdigest()}
        self.plan_digest = hashlib.sha256(canonical(self.plan)).hexdigest()
        # Only the kernel observation boundary is controlled here. File operations,
        # OS ownership, descriptors, locks, child death and private journal IO are real.
        self.kernel_patch = patch("retirement_stores.cgroup_identity", side_effect=lambda installation, name: self.bindings["cgroups"][name])
        self.kernel_patch.start()
        self.addCleanup(self.kernel_patch.stop)
        with self.claim() as journal:
            journal.begin("quiesce")
            journal.succeed(self.receipt)
            journal.begin("archive_verify")
            journal.succeed({**self.receipt, "archive_identity_verified": True, "restore_function_verified": True,
                             "current_snapshot_verified": True, "writer_exclusion_verified": True})
            journal.begin("database_remove")
            journal.succeed({**self.receipt, "resource_reobserved": True, "desired_state_verified": True})

    def claim(self):
        return RetirementJournal(self.history, self.plan, self.plan_digest)

    def assert_retained(self):
        self.assertEqual(self.archive.read_bytes(), b"inert archive fixture; not a recovery proof")
        self.assertEqual(self.key.read_bytes(), b"inert external key fixture")
        self.assertEqual(self.unrelated.read_bytes(), b"retain unrelated operator data")
        self.assertTrue((self.history / "current-release-v1.json").exists())

    def test_actual_owned_store_removal_and_repeat_preserve_retained_and_unrelated_material(self):
        with self.claim() as journal:
            journal.begin("stores_remove")
            action = RetirementStores(journal, self.resource_plan)
            receipt = action.remove()
            self.assertTrue(receipt["desired_state_verified"])
            self.assertEqual(receipt["remaining"], 0)
            self.assertEqual(action.remove(), receipt)
            journal.succeed(receipt)
            journal.begin("retention_verify")
            self.assertEqual(action.observe(), receipt)
            with self.assertRaises(UpgradeRefused):
                action.remove()
        for name in STORES:
            self.assertFalse((self.root / name).exists())
        self.assert_retained()

    def test_extra_entry_refuses_before_any_deletion(self):
        unexpected = self.root / "storage/unplanned"
        unexpected.write_bytes(b"preserve unplanned store entry")
        unexpected.chmod(0o600)
        with self.claim() as journal:
            journal.begin("stores_remove")
            with self.assertRaises(UpgradeRefused):
                RetirementStores(journal, self.resource_plan).remove()
        self.assertTrue((self.root / "configuration/installation.json").exists())
        self.assertEqual(unexpected.read_bytes(), b"preserve unplanned store entry")
        self.assert_retained()

    def test_replacement_directory_refuses_and_preserves_both_resources(self):
        retained = self.root / "retained-original-storage"
        (self.root / "storage").rename(retained)
        (self.root / "storage").mkdir(mode=0o700)
        replacement = self.root / "storage/replacement"
        replacement.write_bytes(b"unrelated replacement")
        replacement.chmod(0o600)
        with self.claim() as journal:
            journal.begin("stores_remove")
            with self.assertRaises(UpgradeRefused):
                RetirementStores(journal, self.resource_plan).remove()
        self.assertTrue((retained / "objects/object").exists())
        self.assertEqual(replacement.read_bytes(), b"unrelated replacement")
        self.assert_retained()

    def test_same_size_changed_file_and_replacement_inode_refuse(self):
        path = self.root / "configuration/installation.json"
        before = path.read_bytes()
        path.write_bytes(b"x" * len(before))
        with self.claim() as journal:
            journal.begin("stores_remove")
            with self.assertRaises(UpgradeRefused):
                RetirementStores(journal, self.resource_plan).remove()
        path.write_bytes(before)
        retained = self.root / "retained-original-configuration"
        path.rename(retained)
        path.write_bytes(before)
        path.chmod(0o600)
        with self.claim() as journal:
            action = RetirementStores(journal, self.resource_plan)
            with self.assertRaises(UpgradeRefused):
                action.observe()
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(retained.read_bytes(), before)

    def test_phase_binding_and_live_group_refuse(self):
        with self.claim() as journal:
            action = RetirementStores(journal, self.resource_plan)
            with self.assertRaises(UpgradeRefused):
                action.remove()
            journal.begin("stores_remove")
            (Path(self.bindings["cgroups"]["native"]["path"]) / "cgroup.events").write_text("populated 1\n")
            with self.assertRaises(UpgradeRefused):
                action.remove()
        self.assertTrue((self.root / "configuration/installation.json").exists())
        self.assert_retained()

    def test_partial_unlink_and_sync_failure_resume_remaining_original_entries(self):
        with self.claim() as journal:
            journal.begin("stores_remove")
            action = RetirementStores(journal, self.resource_plan)
            with patch("retirement_stores.os.fsync", side_effect=OSError("inert directory-sync fault")), self.assertRaises(OSError):
                action.remove()
            observed = action.observe()
            self.assertGreater(observed["removed"], 0)
            self.assertGreater(observed["remaining"], 0)
            journal.fail("store_remove_failed")
        with self.claim() as journal:
            action = RetirementStores(journal, self.resource_plan)
            observed = action.observe()
            journal.reconcile(applied=False, evidence={**observed, "unapplied_verified": True, "partial": True})
            journal.begin("stores_remove")
            journal.succeed(action.remove())
        self.assert_retained()

    def test_real_killed_owner_after_all_unlinks_reconciles_without_repeating_deletion(self):
        code = """import json,os,signal,sys
from unittest.mock import patch
from retirement_journal import RetirementJournal
from retirement_stores import RetirementStores
plan=json.loads(sys.argv[2]);resources=json.loads(sys.argv[4])
with patch('retirement_stores.cgroup_identity',side_effect=lambda installation,name: resources['bindings']['cgroups'][name]):
 with RetirementJournal(sys.argv[1],plan,sys.argv[3]) as journal:
  journal.begin('stores_remove')
  RetirementStores(journal,resources).remove()
  print('removed-before-acknowledgement',flush=True)
  os.kill(os.getpid(),signal.SIGKILL)
"""
        process = subprocess.Popen([sys.executable, "-c", code, str(self.history), json.dumps(self.plan), self.plan_digest, json.dumps(self.resource_plan)],
                                   env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(Path(__file__).parent)}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), "removed-before-acknowledgement")
            process.communicate(timeout=10)
            self.assertEqual(process.returncode, -9)
            self.assertEqual(RetirementJournal.read_status(self.history, self.plan, self.plan_digest)["status"], "uncertain")
            with self.claim() as journal:
                action = RetirementStores(journal, self.resource_plan)
                observed = action.observe()
                self.assertTrue(observed["desired_state_verified"])
                journal.reconcile(applied=True, evidence=observed)
                self.assertEqual(journal.record["completed"][-1], "stores_remove")
                with self.assertRaises(UpgradeRefused):
                    action.remove()
            self.assert_retained()
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)

    def test_hardlink_and_symlink_refuse_without_touching_alias_target(self):
        target = self.root / "storage/objects/object"
        alias = self.base / "unrelated-hardlink"
        os.link(target, alias)
        with self.claim() as journal:
            journal.begin("stores_remove")
            action = RetirementStores(journal, self.resource_plan)
            with self.assertRaises(UpgradeRefused):
                action.remove()
            alias.unlink()
            (self.root / "storage/outside-alias").symlink_to(self.archive)
            with self.assertRaises(UpgradeRefused):
                action.remove()
        self.assertTrue(target.exists())
        self.assert_retained()
