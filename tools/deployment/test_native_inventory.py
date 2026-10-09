import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from native_inventory import database_environment, directory_identity, observe_database, private_bytes
from upgrade_journal import UpgradeRefused


class DatabaseResourceTest(unittest.TestCase):
    def test_database_credentials_stay_in_environment_and_query_is_fixed_readonly(self):
        secret = "fixture-private-password"
        observed = {"cluster": "1234567890", "database": "owned_fixture", "database_oid": 10,
                    "owner_oid": 20, "role_oid": 20, "encoding": "UTF8", "version": "18.4", "address": "127.0.0.1", "port": 55432}
        with patch("native_inventory.subprocess.run", return_value=subprocess.CompletedProcess([], 0, json.dumps(observed).encode())) as run:
            self.assertEqual(observe_database("/trusted/psql", "postgresql://owner:" + secret + "@127.0.0.1:55432/owned_fixture"), observed)
        args, kwargs = run.call_args
        self.assertNotIn(secret, str(args))
        self.assertNotIn("shell", kwargs)
        self.assertEqual(kwargs["env"]["PGPASSWORD"], secret)
        self.assertIn("default_transaction_read_only=on", kwargs["env"]["PGOPTIONS"])
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
        self.assertNotIn("PGSERVICE", kwargs["env"])

    def test_foreign_servers_options_and_ambiguous_database_names_refuse_before_sql(self):
        for value in ["postgresql://owner@foreign.invalid:55432/owned", "postgresql://owner@127.0.0.1:55432/owned?options=unsafe",
                      "postgresql://owner@127.0.0.1:55432/owned#other", "postgresql://owner@127.0.0.1/owned",
                      "postgresql://owner@127.0.0.1:55432/owned%2Fother", "postgresql://owner@127.0.0.1:55432/owned%00",
                      "postgresql://owner@127.0.0.1:55432/postgres;DROP", "https://owner@127.0.0.1:55432/owned"]:
            with self.subTest(value=value), patch("native_inventory.subprocess.run") as run, self.assertRaises(UpgradeRefused):
                observe_database("/trusted/psql", value)
            run.assert_not_called()

    def test_wrong_database_owner_cluster_version_or_response_refuses(self):
        good = {"cluster": "123", "database": "owned", "database_oid": 10, "owner_oid": 20, "role_oid": 20,
                "encoding": "UTF8", "version": "18.4", "address": "127.0.0.1", "port": 55432}
        for field, value in [("database", "other"), ("cluster", True), ("database_oid", True), ("owner_oid", 21),
                             ("version", "18.6"), ("address", "192.0.2.1"), ("port", 55433), ("encoding", "LATIN1")]:
            with self.subTest(field=field), patch("native_inventory.subprocess.run", return_value=subprocess.CompletedProcess([], 0, json.dumps({**good, field: value}).encode())), self.assertRaises(UpgradeRefused):
                observe_database("/trusted/psql", "postgresql://owner@127.0.0.1:55432/owned")
        with patch("native_inventory.subprocess.run", return_value=subprocess.CompletedProcess([], 1, b"private error")), self.assertRaises(UpgradeRefused):
            observe_database("/trusted/psql", "postgresql://owner@127.0.0.1:55432/owned")


@unittest.skipUnless(sys.platform == "linux", "Native resource custody requires Linux")
class NativeResourceCustodyTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.root.chmod(0o700)

    def test_private_custody_does_not_follow_aliases_or_shared_files(self):
        value = self.root / "private.json"
        value.write_bytes(b"private fixture")
        value.chmod(0o600)
        self.assertEqual(private_bytes(value), b"private fixture")
        alias = self.root / "alias"
        alias.symlink_to(value)
        with self.assertRaises(UpgradeRefused):
            private_bytes(alias)
        alias.unlink()
        os.link(value, alias)
        with self.assertRaises(UpgradeRefused):
            private_bytes(value)
        alias.unlink()
        value.chmod(0o644)
        with self.assertRaises(UpgradeRefused):
            private_bytes(value)

    def test_replaced_directory_has_a_different_binding_without_changing_retained_data(self):
        directory = self.root / "storage"
        directory.mkdir(mode=0o700)
        before = directory_identity(directory)
        retained = self.root / "retained-storage"
        directory.rename(retained)
        directory.mkdir(mode=0o700)
        self.assertNotEqual(directory_identity(directory)["inode"], before["inode"])
        self.assertEqual(retained.stat().st_ino, before["inode"])
