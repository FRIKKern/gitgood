import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch
import uuid

from native_inventory import executable_identity
from retirement_fence import RetirementFence
from retirement_journal import RetirementJournal, DIGESTS
from retirement_snapshot import RetirementSnapshot, capture_retention_inputs
from retirement_stores import capture_store_plan
from upgrade_history import UpgradeHistory
from upgrade_journal import canonical, STAGES, UpgradeRefused
import test_retirement_database


@unittest.skipUnless(sys.platform == "linux" and os.environ.get("GITGOOD_TEST_DATABASE_LOCALE") == "true", "Actual PostgreSQL18.4 and native node profile required")
class RetirementSnapshotTest(unittest.TestCase):
    def setUp(self):
        self.fixture = test_retirement_database.RetirementDatabaseTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.fixture.root
        self.base = self.fixture.fixture.base
        self.history = self.base / "snapshot-history"
        self.history.mkdir(mode=0o700)
        node, git = shutil.which("node"), shutil.which("git")
        self.bindings = {**self.fixture.bindings, "executables": {**self.fixture.bindings["executables"],
                         "node": executable_identity(node), "git": executable_identity(git)}}
        digest = hashlib.sha256(canonical(self.bindings)).hexdigest()
        self.operation = str(uuid.uuid4())
        self.resources = capture_store_plan(self.root, {"bindings": self.bindings, "bindings_sha256": digest}, self.operation)
        archive, key = self.fixture.fixture.archive, self.fixture.fixture.key
        archive.chmod(0o600)
        key.write_bytes(os.urandom(32))
        key.chmod(0o600)
        tools = Path(self.fixture.psql).parent
        self.retention = capture_retention_inputs(self.operation, self.bindings["installation"], archive, key,
                                                 str(tools / "pg_dump"), str(tools / "pg_restore"))
        self.expected = {"protocol": 1, "purpose": "retirement_checkpoint", "status": "complete", "candidate": "b" * 40,
                         "installation": self.bindings["installation"], "ciphertext_sha256": self.retention["archive"]["sha256"],
                         "recovery_point": "2026-10-09T00:00:00.000Z", "database_fingerprint": "f" * 64,
                         "resource_fingerprints": {name: "e" * 64 for name in ["git", "ssh", "configuration"]},
                         "checks": ["inert boundary fixture"] * 3, "limitations": ["no actual checkpoint proof"] * 3}
        upgrade = str(uuid.uuid4())
        intent = {"installation": self.bindings["installation"], "old_candidate": "a" * 40, "new_candidate": "b" * 40,
                  "old_artifact_sha256": "c" * 64, "new_artifact_sha256": "d" * 64, "bindings_sha256": digest, "rollback_policy": "same_schema_only"}
        with UpgradeHistory(self.history, upgrade, intent) as journal:
            for stage in STAGES:
                journal.begin(stage)
                journal.succeed(stage, self.fixture.fixture.receipt)
        pointer = {"protocol": 1, "installation": self.bindings["installation"], "operation": upgrade, "candidate": "b" * 40,
                   "artifact_sha256": "d" * 64, "bindings_sha256": digest, "stage": self.bindings["resources"]["root"],
                   "stage_inventory_sha256": "f" * 64, "schema": ["20261007000000"], "public_probe_sha256": "f" * 64}
        current = self.history / "current-release-v1.json"
        current.write_bytes(canonical(pointer) + b"\n")
        current.chmod(0o600)
        self.plan = {"protocol": 1, "operation": self.operation, "installation": self.bindings["installation"], "candidate": "b" * 40,
                     **{name: "f" * 64 for name in DIGESTS}, "bindings_sha256": digest, "artifact_sha256": "d" * 64,
                     "current_sha256": hashlib.sha256(current.read_bytes()).hexdigest(), "resource_plan_sha256": hashlib.sha256(canonical(self.resources)).hexdigest(),
                     "retention_sha256": hashlib.sha256(canonical(self.retention)).hexdigest(), "checkpoint_sha256": hashlib.sha256(canonical(self.expected)).hexdigest(),
                     "archive_sha256": self.retention["archive"]["sha256"]}
        self.configure_plan()
        self.plan_digest = hashlib.sha256(canonical(self.plan)).hexdigest()
        # Kernel identities and immutable artifact/observer result are controlled;
        # filesystem ownership, journal locks, real PG identity and actual node
        # child custody are exercised. This fixture proves no archive/restore.
        for module in ["retirement_fence", "retirement_quiescence"]:
            adapter = patch(module + ".cgroup_identity", side_effect=lambda installation, name: self.bindings["cgroups"][name])
            adapter.start()
            self.addCleanup(adapter.stop)
        code = self.base / "controlled-code"
        self.module = code / "forge/lib/gitgood-fixture/priv/operations/retirement-snapshot.mjs"
        self.module.parent.mkdir(parents=True)
        self.observed = {**self.expected, "purpose": "retirement_snapshot", "status": "observed", "limitations": ["controlled artifact boundary"] * 2}
        self.module.write_text("console.log(" + json.dumps(json.dumps(self.observed)) + ")\n")
        self.verified = {"code": code, "inventory_sha256": "f" * 64, "migrations": ["20261007000000"]}
        adapter = patch("retirement_snapshot.verify_runtime_stage", return_value=self.verified)
        adapter.start()
        self.addCleanup(adapter.stop)
        with self.claim() as journal:
            journal.begin("quiesce")
            journal.succeed(RetirementFence(journal, self.resources).install())

    def claim(self):
        return RetirementJournal(self.history, self.plan, self.plan_digest)

    def configure_plan(self):
        """Allow composed fixtures to seal their independently allocated target."""

    def action(self, journal):
        return RetirementSnapshot(journal, self.resources, self.retention, self.expected, self.fixture.configuration)

    def test_observation_cannot_acknowledge_archive_stage_without_actual_restoration(self):
        with self.claim() as journal:
            journal.begin("archive_verify")
            receipt = self.action(journal).observe()
            self.assertTrue(receipt["current_snapshot_verified"])
            self.assertNotIn("restore_function_verified", receipt)
            with self.assertRaises(UpgradeRefused):
                journal.succeed(receipt)
            self.assertEqual(journal.record["stage"], "archive_verify")
            self.assertEqual(journal.record["status"], "running")
        self.assertEqual(self.fixture.sql("SELECT oid::text FROM pg_database WHERE datname='" + self.fixture.name + "'"), str(self.fixture.expected["database_oid"]))

    def test_wrong_stage_and_changed_retained_key_refuse_before_child_execution(self):
        with self.claim() as journal:
            with patch("retirement_snapshot.subprocess.Popen") as launch:
                with self.assertRaises(UpgradeRefused):
                    self.action(journal).observe()
                launch.assert_not_called()
            journal.begin("archive_verify")
            Path(self.retention["key"]["path"]).write_bytes(os.urandom(32))
            with patch("retirement_snapshot.subprocess.Popen") as launch:
                with self.assertRaises(UpgradeRefused):
                    self.action(journal).observe()
                launch.assert_not_called()

    def test_runtime_writer_appearing_during_child_read_refuses_without_acknowledgement(self):
        events = Path(self.bindings["cgroups"]["native"]["path"]) / "cgroup.events"
        self.module.write_text("import {writeFileSync} from 'node:fs';writeFileSync(" + json.dumps(str(events)) + ",'populated 1\\n');setTimeout(()=>{},5000)\n")
        with self.claim() as journal:
            journal.begin("archive_verify")
            with self.assertRaises(UpgradeRefused):
                self.action(journal).observe()
            self.assertEqual(journal.record["completed"], ["quiesce"])
            self.assertEqual(journal.record["status"], "running")
        self.assertTrue(Path(self.retention["archive"]["path"]).exists())
        self.assertTrue((self.root / "configuration/installation.json").exists())

    def test_changed_observer_result_refuses_without_advancing_or_removing_resources(self):
        altered = {**self.observed, "database_fingerprint": "0" * 64}
        self.module.write_text("console.log(" + json.dumps(json.dumps(altered)) + ")\n")
        with self.claim() as journal:
            journal.begin("archive_verify")
            with self.assertRaises(UpgradeRefused):
                self.action(journal).observe()
            self.assertEqual(journal.record["completed"], ["quiesce"])
        self.assertTrue((self.root / "storage/objects/object").exists())
