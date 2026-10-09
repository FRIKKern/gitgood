import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
from urllib.parse import quote
import uuid

from native_inventory import executable_identity, observe_database
from retirement_database import RetirementDatabase
from retirement_journal import DIGESTS, RetirementJournal
from retirement_stores import capture_store_plan
import test_retirement_stores
from upgrade_history import UpgradeHistory
from upgrade_journal import canonical, STAGES, UpgradeRefused


@unittest.skipUnless(sys.platform == "linux" and os.environ.get("GITGOOD_TEST_DATABASE_LOCALE") == "true", "Real native PostgreSQL18.4 profile required")
class RetirementDatabaseTest(unittest.TestCase):
    def setUp(self):
        self.fixture = test_retirement_stores.RetirementStoresTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.environment = {key: os.environ[key] for key in ["PATH", "PGHOST", "PGPORT", "PGUSER", "PGPASSWORD"] if key in os.environ}
        self.environment.update(PGDATABASE="postgres", PGCONNECT_TIMEOUT="5", PGOPTIONS="-c statement_timeout=5000")
        self.psql = os.environ.get("GITGOOD_PSQL", "psql")
        if not Path(self.psql).is_absolute():
            import shutil
            self.psql = shutil.which(self.psql)
        self.name = "gitgood_retire_test_" + uuid.uuid4().hex[:16]
        self._tool("createdb", ["--template=template0", "--encoding=UTF8", "--locale=C.UTF-8", "--locale-provider=libc", self.name])
        self.url = "postgresql://" + quote(self.environment.get("PGUSER", "gitgood"), safe="") + ":" + quote(self.environment.get("PGPASSWORD", ""), safe="") + "@127.0.0.1:" + self.environment.get("PGPORT", "55432") + "/" + self.name
        self.expected = observe_database(self.psql, self.url)
        self.owned_oids = {self.expected["database_oid"]}
        self.addCleanup(self._cleanup_database)
        installation = self.fixture.bindings["installation"]
        self.configuration = canonical({"protocol": 1, "installation": installation,
                                        "forge": {"DATABASE_URL": self.url}, "web": {}, "edge": {}}) + b"\n"
        path = self.fixture.root / "configuration/installation.json"
        path.write_bytes(self.configuration)
        self.bindings = {**self.fixture.bindings, "configuration_sha256": {"installation.json": hashlib.sha256(self.configuration).hexdigest()},
                         "executables": {"psql": executable_identity(self.psql)}, "database": self.expected}
        digest = hashlib.sha256(canonical(self.bindings)).hexdigest()
        self.operation = str(uuid.uuid4())
        self.resource_plan = capture_store_plan(self.fixture.root, {"bindings": self.bindings, "bindings_sha256": digest}, self.operation)
        self.history = self.fixture.base / "database-history"
        self.history.mkdir(mode=0o700)
        upgrade = str(uuid.uuid4())
        intent = {"installation": installation, "old_candidate": "a" * 40, "new_candidate": "b" * 40,
                  "old_artifact_sha256": "c" * 64, "new_artifact_sha256": "d" * 64, "bindings_sha256": digest, "rollback_policy": "same_schema_only"}
        with UpgradeHistory(self.history, upgrade, intent) as journal:
            for stage in STAGES:
                journal.begin(stage)
                journal.succeed(stage, self.fixture.receipt)
        pointer = {"protocol": 1, "installation": installation, "operation": upgrade, "candidate": "b" * 40,
                   "artifact_sha256": "d" * 64, "bindings_sha256": digest, "stage": self.bindings["resources"]["root"],
                   "stage_inventory_sha256": "f" * 64, "schema": ["20261007000000"], "public_probe_sha256": "f" * 64}
        current = self.history / "current-release-v1.json"
        current.write_bytes(canonical(pointer) + b"\n")
        current.chmod(0o600)
        self.plan = {"protocol": 1, "operation": self.operation, "installation": installation, "candidate": "b" * 40,
                     **{key: "f" * 64 for key in DIGESTS}, "bindings_sha256": digest, "artifact_sha256": "d" * 64,
                     "current_sha256": hashlib.sha256(current.read_bytes()).hexdigest(), "resource_plan_sha256": hashlib.sha256(canonical(self.resource_plan)).hexdigest()}
        self.plan_digest = hashlib.sha256(canonical(self.plan)).hexdigest()
        adapter = patch("retirement_database.cgroup_identity", side_effect=lambda installation, name: self.bindings["cgroups"][name])
        adapter.start()
        self.addCleanup(adapter.stop)
        with self.claim() as journal:
            journal.begin("quiesce")
            journal.succeed(self.fixture.receipt)
            journal.begin("archive_verify")
            journal.succeed({**self.fixture.receipt, "archive_identity_verified": True, "restore_function_verified": True,
                             "current_snapshot_verified": True, "writer_exclusion_verified": True})

    def _tool(self, tool, arguments, environment=None):
        result = subprocess.run([tool, *arguments], env=environment or self.environment, stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, "Owned disposable database fixture command failed")
        return result.stdout.decode().strip()

    def sql(self, statement, database="postgres"):
        return self._tool(self.psql, ["--no-psqlrc", "--tuples-only", "--no-align", "--set=ON_ERROR_STOP=1", "--command", statement], {**self.environment, "PGDATABASE": database})

    def _cleanup_database(self):
        oid = self.sql("SELECT oid::text FROM pg_database WHERE datname='" + self.name + "'")
        if oid:
            self.assertIn(int(oid), self.owned_oids, "Refuse cleanup of an unknown replacement database")
            self.assertEqual(self.sql("SELECT system_identifier::text FROM pg_control_system()"), self.expected["cluster"])
            self._tool("dropdb", [self.name])

    def claim(self):
        return RetirementJournal(self.history, self.plan, self.plan_digest)

    def action(self, journal):
        return RetirementDatabase(journal, self.resource_plan, self.configuration)

    def test_real_database_drop_and_repeat_keep_shared_role_and_unrelated_database(self):
        keep = "gitgood_retire_keep_" + uuid.uuid4().hex[:16]
        self._tool("createdb", [keep])
        keep_oid = self.sql("SELECT oid::text FROM pg_database WHERE datname='" + keep + "'")
        def cleanup_keep():
            self.assertEqual(self.sql("SELECT oid::text FROM pg_database WHERE datname='" + keep + "'"), keep_oid)
            self._tool("dropdb", [keep])
        self.addCleanup(cleanup_keep)
        with self.claim() as journal:
            journal.begin("database_remove")
            action = self.action(journal)
            receipt = action.remove()
            self.assertTrue(receipt["desired_state_verified"])
            self.assertEqual(action.remove(), receipt)
            journal.succeed(receipt)
        self.assertEqual(self.sql("SELECT oid::text FROM pg_database WHERE datname='" + keep + "'"), keep_oid)
        self.assertEqual(self.sql("SELECT oid::text FROM pg_roles WHERE rolname=current_user"), str(self.expected["role_oid"]))
        self.fixture.assert_retained()

    def test_replacement_database_with_same_name_refuses_before_drop(self):
        self._tool("dropdb", [self.name])
        self._tool("createdb", ["--template=template0", "--encoding=UTF8", "--locale=C.UTF-8", "--locale-provider=libc", self.name])
        replacement = observe_database(self.psql, self.url)
        self.owned_oids.add(replacement["database_oid"])
        self.assertNotEqual(replacement["database_oid"], self.expected["database_oid"])
        self.sql("CREATE TABLE replacement_fixture(id integer PRIMARY KEY); INSERT INTO replacement_fixture VALUES(7)", self.name)
        with self.claim() as journal:
            journal.begin("database_remove")
            with self.assertRaises(UpgradeRefused):
                self.action(journal).remove()
        self.assertEqual(self.sql("SELECT id FROM replacement_fixture", self.name), "7")

    def test_other_live_client_refuses_without_forcing_disconnect_then_can_reconcile(self):
        client = subprocess.Popen([self.psql, "--no-psqlrc", "--command", "SELECT pg_sleep(30)"],
                                  env={**self.environment, "PGDATABASE": self.name, "PGAPPNAME": "owned retirement fixture client", "PGOPTIONS": ""},
                                  stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 10
            while self.sql("SELECT count(*) FROM pg_stat_activity WHERE datname='" + self.name + "' AND application_name='owned retirement fixture client'") != "1":
                self.assertIsNone(client.poll())
                self.assertLess(time.monotonic(), deadline)
                time.sleep(.05)
            with self.claim() as journal:
                journal.begin("database_remove")
                action = self.action(journal)
                with self.assertRaises(UpgradeRefused):
                    action.remove()
                self.assertIsNone(client.poll(), "Removal must not terminate the unrelated-to-action client")
                journal.fail("database_remove_failed")
            client.send_signal(signal.SIGINT)
            client.communicate(timeout=10)
            with self.claim() as journal:
                action = self.action(journal)
                observed = action.observe()
                self.assertTrue(observed["original_present_verified"])
                self.assertEqual(observed["connected_clients"], 0)
                journal.reconcile(applied=False, evidence={**observed, "unapplied_verified": True})
                journal.begin("database_remove")
                journal.succeed(action.remove())
        finally:
            if client.poll() is None:
                client.kill()
                client.communicate(timeout=10)

    def test_real_killed_owner_after_drop_reconciles_exact_absence(self):
        code = """import json,os,signal,sys
from unittest.mock import patch
from native_inventory import private_bytes
from retirement_journal import RetirementJournal
from retirement_database import RetirementDatabase
plan=json.loads(sys.argv[2]);resources=json.loads(sys.argv[4])
with patch('retirement_database.cgroup_identity',side_effect=lambda installation,name: resources['bindings']['cgroups'][name]):
 with RetirementJournal(sys.argv[1],plan,sys.argv[3]) as journal:
  journal.begin('database_remove')
  RetirementDatabase(journal,resources,private_bytes(sys.argv[5])).remove()
  print('database-removed-before-acknowledgement',flush=True)
  os.kill(os.getpid(),signal.SIGKILL)
"""
        client = subprocess.Popen([sys.executable, "-c", code, str(self.history), json.dumps(self.plan), self.plan_digest,
                                   json.dumps(self.resource_plan), str(self.fixture.root / "configuration/installation.json")],
                                  env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(Path(__file__).parent)}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(client.stdout.readline().strip(), "database-removed-before-acknowledgement")
            client.communicate(timeout=10)
            self.assertEqual(client.returncode, -9)
            with self.claim() as journal:
                action = self.action(journal)
                observed = action.observe()
                self.assertTrue(observed["desired_state_verified"])
                journal.reconcile(applied=True, evidence=observed)
                with self.assertRaises(UpgradeRefused):
                    action.remove()
            self.fixture.assert_retained()
        finally:
            if client.poll() is None:
                client.kill()
                client.communicate(timeout=10)

    def test_changed_private_configuration_refuses_without_query_or_mutation(self):
        with self.claim() as journal:
            journal.begin("database_remove")
            with self.assertRaises(UpgradeRefused):
                RetirementDatabase(journal, self.resource_plan, b"different private configuration")
        self.assertEqual(observe_database(self.psql, self.url), self.expected)
