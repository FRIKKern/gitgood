import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote
import uuid

from native_allocation import capture_initial_allocation, observe_empty_database, supported_platform
from native_inventory import capture_native_inventory, observe_database
from upgrade_journal import canonical, UpgradeRefused


class AllocationDatabaseBoundaryTest(unittest.TestCase):
    def test_closed_readonly_observation_keeps_credentials_out_of_commands(self):
        good = dict(relations=0, functions=0, types=0, schemas=0, extensions=0, public_writable=True)
        secret = "private-allocation-fixture"
        with patch("native_allocation.subprocess.run", return_value=subprocess.CompletedProcess([], 0, canonical(good))) as run:
            self.assertEqual(observe_empty_database("/trusted/psql", "postgresql://owner:" + secret + "@127.0.0.1:55432/owned"), good)
        args, kwargs = run.call_args
        self.assertNotIn(secret, str(args))
        self.assertEqual(kwargs["env"]["PGPASSWORD"], secret)
        self.assertIn("default_transaction_read_only=on", kwargs["env"]["PGOPTIONS"])
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
        for name in good:
            value = {**good, name: False if name == "public_writable" else 1}
            with self.subTest(name=name), patch("native_allocation.subprocess.run", return_value=subprocess.CompletedProcess([], 0, canonical(value))), self.assertRaises(UpgradeRefused):
                observe_empty_database("/trusted/psql", "postgresql://owner@127.0.0.1:55432/owned")
        for value in [{**good, "relations": False}, {**good, "commands": ["anything"]}, {**good, "public_writable": 1}]:
            with patch("native_allocation.subprocess.run", return_value=subprocess.CompletedProcess([], 0, canonical(value))), self.assertRaises(UpgradeRefused):
                observe_empty_database("/trusted/psql", "postgresql://owner@127.0.0.1:55432/owned")

    def test_unsupported_profile_refuses_before_resource_or_sql_observation(self):
        for machine, release in [("aarch64", {"ID": "ubuntu", "VERSION_ID": "24.04"}),
                                 ("x86_64", {"ID": "ubuntu", "VERSION_ID": "26.04"}),
                                 ("x86_64", {"ID": "debian", "VERSION_ID": "24.04"})]:
            with patch("native_allocation.sys.platform", "linux"), patch("native_allocation.platform.machine", return_value=machine), patch("native_allocation.platform.freedesktop_os_release", return_value=release), patch("native_allocation.capture_native_resources") as capture, self.assertRaises(UpgradeRefused):
                capture_initial_allocation("/unobserved", {})
            capture.assert_not_called()


@unittest.skipUnless(sys.platform == "linux", "Private native filesystem requires Linux")
class InitialAllocationCustodyTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.root.chmod(0o700)
        for name in ["configuration", "storage", "ssh-host", "history", "staging"]:
            (self.root / name).mkdir(mode=0o700)
        self.installation = str(uuid.uuid4())
        self.configuration = {"protocol": 1, "installation": self.installation,
                              "forge": {"GITGOOD_INSTALLATION_ID": self.installation, "DATABASE_URL": "postgresql://owner@127.0.0.1:55432/owned"},
                              "web": {"PORT": "8080", "GITGOOD_API_URL": "http://127.0.0.1:4000", "GITGOOD_PROXY_KEY": "fixture", "NODE_ENV": "production"}, "edge": {}}
        path = self.root / "configuration/installation.json"
        path.write_bytes(canonical(self.configuration));path.chmod(0o600)
        self.groups = {}
        for name in ["native", "web", "edge", "maintenance"]:
            group = self.root / "ssh-host" / name
            group.mkdir(mode=0o700)
            (group / "cgroup.events").write_text("populated 0\nfrozen 0\n")
            (group / "cgroup.procs").write_text("")
            self.groups[name] = {"path": str(group), "inode": group.stat().st_ino}
        self.observed = {"installation": self.installation, "bindings": {"cgroups": self.groups, "executables": {"psql": {"path": "/trusted/psql"}}}, "bindings_sha256": "a" * 64}
        for module, name, values in [("native_allocation", "supported_platform", {"return_value": "ubuntu-24.04-linux-x86_64"}),
                                     ("native_allocation", "capture_native_resources", {"return_value": self.observed}),
                                     ("native_allocation", "observe_empty_database", {"return_value": {"empty": True}}),
                                     ("native_allocation", "cgroup_identity", {"side_effect": lambda installation, name: self.groups[name]})]:
            adapter = patch(module + "." + name, **values);adapter.start();self.addCleanup(adapter.stop)

    def test_admission_has_no_runtime_marker_or_filesystem_mutation(self):
        before = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        result = capture_initial_allocation(self.root, {})
        self.assertEqual(result["allocation"]["installation"], self.installation)
        self.assertEqual(hashlib.sha256(canonical(result["allocation"])).hexdigest(), result["allocation_sha256"])
        self.assertEqual({p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}, before)
        self.assertFalse((self.root / "storage/.gitgood-runtime-v1.json").exists())

    def test_existing_data_history_partial_stage_or_live_groups_refuse_unchanged(self):
        for name in ["storage", "history", "staging"]:
            path = self.root / name / "retained"
            path.write_bytes(b"retain-existing-bytes");path.chmod(0o600)
            with self.subTest(name=name), self.assertRaises(UpgradeRefused):
                capture_initial_allocation(self.root, {})
            self.assertEqual(path.read_bytes(), b"retain-existing-bytes")
            path.unlink()
        for name in self.groups:
            events = Path(self.groups[name]["path"]) / "cgroup.events"
            events.write_text("populated 1\nfrozen 0\n")
            with self.subTest(group=name), self.assertRaises(UpgradeRefused):
                capture_initial_allocation(self.root, {})
            self.assertEqual(events.read_text(), "populated 1\nfrozen 0\n")
            events.write_text("populated 0\nfrozen 0\n")

    def test_unsealed_configuration_identity_and_resource_change_refuse(self):
        path = self.root / "configuration/installation.json"
        for forge in [{**self.configuration["forge"], "GITGOOD_INSTALLATION_ID": str(uuid.uuid4())},
                      {**self.configuration["forge"], "UNREQUESTED_COMMAND": "not-executed"}]:
            path.write_bytes(canonical({**self.configuration, "forge": forge}))
            with self.assertRaises(UpgradeRefused):
                capture_initial_allocation(self.root, {})
        path.write_bytes(canonical(self.configuration))
        with patch("native_allocation.capture_native_resources", side_effect=[self.observed, {**self.observed, "bindings_sha256": "b" * 64}]), self.assertRaises(UpgradeRefused):
            capture_initial_allocation(self.root, {})

    def test_enrolled_inventory_still_requires_real_runtime_marker(self):
        with patch("native_inventory.capture_native_resources", return_value={"bindings": {"cgroups": {"native": {"kernel_path": "/owned"}}}}):
            with self.assertRaises(FileNotFoundError):
                capture_native_inventory(self.root, {})


@unittest.skipUnless(sys.platform == "linux" and os.environ.get("GITGOOD_TEST_DATABASE_LOCALE") == "true", "Actual owned PostgreSQL18.4 test allocation required")
class RealInitialDatabaseTest(unittest.TestCase):
    def test_empty_database_and_existing_relations_functions_types_schemas_preserved(self):
        psql = shutil.which(os.environ.get("GITGOOD_PSQL", "psql"))
        environment = {key: os.environ[key] for key in ["PATH", "PGHOST", "PGPORT", "PGUSER", "PGPASSWORD"] if key in os.environ}
        environment.update(PGDATABASE="postgres", PGCONNECT_TIMEOUT="5", PGOPTIONS="-c statement_timeout=5000")
        name = "gitgood_initial_test_" + uuid.uuid4().hex[:16]
        def tool(executable, args, database="postgres"):
            result = subprocess.run([executable, *args], env={**environment, "PGDATABASE": database}, stdin=subprocess.DEVNULL, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, "Owned initial database fixture command failed")
            return result.stdout.decode().strip()
        def sql(statement, database=name):
            return tool(psql, ["--no-psqlrc", "--tuples-only", "--no-align", "--set=ON_ERROR_STOP=1", "--command", statement], database)
        tool("createdb", ["--template=template0", "--encoding=UTF8", "--locale=C.UTF-8", "--locale-provider=libc", name])
        url = "postgresql://" + quote(environment.get("PGUSER", "gitgood"), safe="") + ":" + quote(environment.get("PGPASSWORD", ""), safe="") + "@127.0.0.1:" + environment.get("PGPORT", "55432") + "/" + name
        expected = observe_database(psql, url)
        def cleanup():
            self.assertEqual(observe_database(psql, url), expected, "Refuse disposal of a replacement database")
            tool("dropdb", [name])
        self.addCleanup(cleanup)
        self.assertEqual(observe_empty_database(psql, url)["relations"], 0)
        for create, remove, observation in [
            ("CREATE TABLE allocation_fixture(id integer); INSERT INTO allocation_fixture VALUES(7)", "DROP TABLE allocation_fixture", "SELECT id FROM allocation_fixture"),
            ("CREATE FUNCTION allocation_fixture() RETURNS integer LANGUAGE SQL AS 'SELECT 7'", "DROP FUNCTION allocation_fixture()", "SELECT allocation_fixture()"),
            ("CREATE TYPE allocation_fixture AS ENUM ('retained')", "DROP TYPE allocation_fixture", "SELECT 'retained'::allocation_fixture"),
            ("CREATE SCHEMA allocation_fixture", "DROP SCHEMA allocation_fixture", "SELECT nspname FROM pg_namespace WHERE nspname='allocation_fixture'")]:
            with self.subTest(create=create):
                sql(create)
                before = sql(observation)
                with self.assertRaises(UpgradeRefused):
                    observe_empty_database(psql, url)
                self.assertEqual(sql(observation), before)
                self.assertEqual(observe_database(psql, url), expected)
                sql(remove)
                self.assertEqual(observe_empty_database(psql, url)["relations"], 0)
