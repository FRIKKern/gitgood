import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from native_inventory import observe_database
from retirement_restore_data import RetirementRestoreData
from upgrade_journal import canonical, UpgradeRefused
import test_retirement_snapshot


@unittest.skipUnless(sys.platform == "linux" and os.environ.get("GITGOOD_TEST_DATABASE_LOCALE") == "true", "Actual PostgreSQL18.4 and native node profile required")
class RetirementRestoreDataTest(unittest.TestCase):
    def setUp(self):
        self.fixture = test_retirement_snapshot.RetirementSnapshotTest()
        self.fixture.configure_plan = self.configure_plan
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.module = self.fixture.module.with_name("retirement-restore-data.mjs")
        self.observed = {**self.fixture.expected, "purpose": "retirement_restore_data", "status": "verified",
                         "operation": self.fixture.operation, "target_database": self.target, "phase": "restore",
                         "checks": ["controlled result boundary"] * 4, "limitations": ["no actual archive or functional restoration"] * 3}
        self.write_result(self.observed)

    def configure_plan(self):
        fixture = self.fixture
        database = fixture.fixture
        self.name = "gitgood_retirement_restore_" + fixture.operation.replace("-", "")
        database._tool("createdb", ["--template=template0", "--encoding=UTF8", "--locale=C.UTF-8", "--locale-provider=libc", self.name])
        url = database.url.rsplit("/", 1)[0] + "/" + self.name
        self.target = observe_database(database.psql, url)
        fixture.addCleanup(self.cleanup_target)
        self.restoration = {"protocol": 1, "purpose": "retirement_restore_data_plan", "operation": fixture.operation,
                            "installation": fixture.bindings["installation"], "target_database": self.target}
        fixture.plan["restore_sha256"] = hashlib.sha256(canonical(self.restoration)).hexdigest()

    def cleanup_target(self):
        database = self.fixture.fixture
        actual = observe_database(database.psql, database.url.rsplit("/", 1)[0] + "/" + self.name)
        self.assertEqual(actual, self.target, "Unknown replacement target must be retained")
        self.assertEqual(database.sql("SELECT count(*) FROM pg_stat_activity WHERE datname='" + self.name + "'"), "0")
        database._tool("dropdb", [self.name])

    def write_result(self, observed):
        self.module.write_text("console.log(" + json.dumps(json.dumps(observed)) + ")\n")

    def action(self, journal, restoration=None):
        fixture = self.fixture
        return RetirementRestoreData(journal, fixture.resources, fixture.retention, fixture.expected,
                                     restoration or self.restoration, fixture.fixture.configuration)

    def test_bound_result_stays_separate_from_functional_restoration(self):
        with self.fixture.claim() as journal:
            journal.begin("archive_verify")
            receipt = self.action(journal).verify("restore")
            self.assertTrue(receipt["restored_data_verified"])
            self.assertNotIn("restore_function_verified", receipt)
            with self.assertRaises(UpgradeRefused):
                journal.succeed(receipt)
            self.assertEqual(journal.record["completed"], ["quiesce"])
            self.assertTrue((self.fixture.root / "storage/objects/object").exists())

    def test_observe_phase_uses_the_original_target_without_readmitting_import(self):
        self.write_result({**self.observed, "phase": "observe"})
        with self.fixture.claim() as journal:
            journal.begin("archive_verify")
            self.assertTrue(self.action(journal).verify("observe")["restored_data_verified"])
            with self.assertRaises(UpgradeRefused):
                self.action(journal).verify("restore")
            with patch("retirement_snapshot.subprocess.Popen") as launch:
                with self.assertRaises(UpgradeRefused):
                    self.action(journal).verify("invented")
                launch.assert_not_called()

    def test_changed_target_plan_refuses_before_any_child(self):
        with self.fixture.claim() as journal:
            journal.begin("archive_verify")
            changed = {**self.restoration, "target_database": {**self.target, "database_oid": self.target["database_oid"] + 1}}
            with patch("retirement_snapshot.subprocess.Popen") as launch:
                with self.assertRaises(UpgradeRefused):
                    self.action(journal, changed)
                launch.assert_not_called()

    def test_changed_result_or_target_cannot_authorize_removal(self):
        with self.fixture.claim() as journal:
            journal.begin("archive_verify")
            for change in [{"target_database": {**self.target, "database_oid": self.target["database_oid"] + 1}},
                           {"database_fingerprint": "0" * 64}, {"operation": "00000000-0000-0000-0000-000000000000"}]:
                self.write_result({**self.observed, **change})
                with self.assertRaises(UpgradeRefused):
                    self.action(journal).verify("restore")
            self.assertEqual(journal.record["completed"], ["quiesce"])

    def test_writer_appearing_during_child_read_retains_target_and_source(self):
        events = Path(self.fixture.bindings["cgroups"]["native"]["path"]) / "cgroup.events"
        self.module.write_text("import {writeFileSync} from 'node:fs';writeFileSync(" + json.dumps(str(events)) + ",'populated 1\\n');setTimeout(()=>{},5000)\n")
        with self.fixture.claim() as journal:
            journal.begin("archive_verify")
            with self.assertRaises(UpgradeRefused):
                self.action(journal).verify("restore")
            self.assertEqual(journal.record["completed"], ["quiesce"])
        self.assertTrue(Path(self.fixture.retention["archive"]["path"]).exists())
        self.assertTrue((self.fixture.root / "configuration/installation.json").exists())
