import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from retirement_retention import CONFIGURATION_FILE, RetirementRetention, retain_configuration
from retirement_snapshot import RetirementSnapshot
from upgrade_journal import UpgradeRefused
import test_retirement_snapshot


@unittest.skipUnless(sys.platform == "linux" and os.environ.get("GITGOOD_TEST_DATABASE_LOCALE") == "true", "Actual PostgreSQL18.4 and native profile required")
class RetirementRetentionTest(unittest.TestCase):
    def setUp(self):
        self.fixture = test_retirement_snapshot.RetirementSnapshotTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.configuration = self.fixture.fixture.configuration

    def test_private_configuration_retains_exact_bytes_and_repeat_identity(self):
        fixture = self.fixture
        with fixture.claim() as journal:
            journal.begin("archive_verify")
            source = fixture.root / "configuration/installation.json"
            original = source.read_bytes()
            receipt = retain_configuration(journal, fixture.resources, self.configuration)
            retained = journal.directory / CONFIGURATION_FILE
            before = retained.stat()
            self.assertEqual(retained.read_bytes(), original)
            self.assertEqual(before.st_uid, os.getuid())
            self.assertEqual(before.st_mode & 0o777, 0o600)
            self.assertEqual(before.st_nlink, 1)
            self.assertEqual(receipt, {"configuration_sha256": hashlib.sha256(original).hexdigest()})
            self.assertEqual(retain_configuration(journal, fixture.resources, self.configuration), receipt)
            self.assertEqual((retained.stat().st_dev, retained.stat().st_ino), (before.st_dev, before.st_ino))
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(journal.record["completed"], ["quiesce"])

    def test_changed_or_aliased_cache_preserves_both_source_and_witness(self):
        fixture = self.fixture
        with fixture.claim() as journal:
            journal.begin("archive_verify")
            target = journal.directory / CONFIGURATION_FILE
            witness = journal.directory / "owned-witness"
            witness.write_bytes(b"preserve different configuration")
            witness.chmod(0o600)
            original = witness.read_bytes()
            target.symlink_to(witness)
            with self.assertRaises(UpgradeRefused):
                retain_configuration(journal, fixture.resources, self.configuration)
            self.assertTrue(target.is_symlink())
            self.assertEqual(witness.read_bytes(), original)
            target.unlink()
            os.link(witness, target)
            with self.assertRaises(UpgradeRefused):
                retain_configuration(journal, fixture.resources, self.configuration)
            self.assertEqual(witness.read_bytes(), original)
            self.assertEqual(target.stat().st_nlink, 2)
            target.unlink()
            target.write_bytes(original)
            target.chmod(0o600)
            with self.assertRaises(UpgradeRefused):
                retain_configuration(journal, fixture.resources, self.configuration)
            self.assertEqual(target.read_bytes(), original)
            self.assertEqual((fixture.root / "configuration/installation.json").read_bytes(), self.configuration)

    def test_live_database_client_refuses_configuration_publication(self):
        fixture = self.fixture
        with fixture.claim() as journal:
            journal.begin("archive_verify")
            database = fixture.fixture
            client = subprocess.Popen([database.psql, "--no-psqlrc", "--command", "SELECT pg_sleep(30)"],
                                      env={**database.environment, "PGDATABASE": database.name,
                                           "PGAPPNAME": "owned retention publication test", "PGOPTIONS": ""},
                                      stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 10
                while database.sql("SELECT count(*) FROM pg_stat_activity WHERE datname='" + database.name + "' AND application_name='owned retention publication test'") != "1":
                    self.assertIsNone(client.poll())
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(.05)
                with self.assertRaises(UpgradeRefused):
                    retain_configuration(journal, fixture.resources, self.configuration)
                self.assertIsNone(client.poll(), "Publication refusal must preserve the live client")
            finally:
                if client.poll() is None:
                    client.send_signal(signal.SIGINT)
                client.communicate(timeout=10)
            self.assertFalse((journal.directory / CONFIGURATION_FILE).exists())
            self.assertEqual(journal.record["completed"], ["quiesce"])

    def test_final_profile_cannot_bypass_prior_stages_or_run_live_snapshot(self):
        fixture = self.fixture
        with fixture.claim() as journal:
            journal.begin("archive_verify")
            with self.assertRaises(UpgradeRefused):
                RetirementRetention(journal, fixture.resources, fixture.retention, fixture.expected, {})
            final = RetirementSnapshot(journal, fixture.resources, fixture.retention, fixture.expected,
                                       self.configuration, lifecycle_stage="retention_verify")
            with patch("retirement_snapshot.subprocess.Popen") as launch:
                with self.assertRaises(UpgradeRefused):
                    final._custody()
                with self.assertRaises(UpgradeRefused):
                    final.observe()
                with self.assertRaises(UpgradeRefused):
                    final._run_packaged("retirement-restore-data.mjs", "restored-data", {"phase": "restore"}, {})
                launch.assert_not_called()
            self.assertEqual(journal.record["completed"], ["quiesce"])
