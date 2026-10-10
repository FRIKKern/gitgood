import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from native_durable_database import (DatabaseRefused, observe_durable_database, query_identity,
                                     validate_database)
from native_inventory import database_environment


URL = "postgresql://ordinary:private-fixture@127.0.0.1:55432/owned_fixture"
GOOD = {"cluster": "1234567890", "database": "owned_fixture", "database_oid": 10,
        "owner_oid": 20, "role": "ordinary", "session_role": "ordinary", "role_oid": 20,
        "encoding": "UTF8", "version": "18.4", "address": "127.0.0.1", "port": 55432,
        "can_login": True, "superuser": False, "create_database": False, "create_role": False,
        "replication": False, "bypass_rls": False, "memberships": 0}


class DurableDatabaseBoundaryTest(unittest.TestCase):
    def test_exact_ordinary_identity(self):
        with patch("native_durable_database.query_identity", return_value=json.dumps(GOOD).encode()) as query:
            self.assertEqual(observe_durable_database("/trusted/psql", URL), GOOD)
        environment = query.call_args.args[1]
        self.assertEqual(environment["PGPASSWORD"], "private-fixture")
        self.assertIn("default_transaction_read_only=on", environment["PGOPTIONS"])
        self.assertNotIn("PGSERVICE", environment)
        self.assertEqual(environment["PGPASSFILE"], "/dev/null")

    def test_any_admin_privilege_or_membership_refuses(self):
        for field, value in [(name, True) for name in ["superuser", "create_database", "create_role", "replication", "bypass_rls"]] + [("memberships", 1), ("can_login", False)]:
            with self.subTest(field=field), self.assertRaises(DatabaseRefused):
                validate_database({**GOOD, field: value}, database_environment(URL))

    def test_foreign_database_role_session_cluster_and_owner_refuse(self):
        for field, value in [("database", "other"), ("role", "other"), ("session_role", "other"),
                             ("owner_oid", 21), ("cluster", "0"), ("cluster", "01"),
                             ("cluster", str(2**64)), ("address", "192.0.2.1"),
                             ("port", 55433), ("version", "18.5"), ("encoding", "LATIN1")]:
            with self.subTest(field=field), self.assertRaises(DatabaseRefused):
                validate_database({**GOOD, field: value}, database_environment(URL))

    def test_types_bounds_and_closed_fields(self):
        changes = [("database_oid", True), ("database_oid", 0), ("database_oid", 2**32),
                   ("role_oid", True), ("owner_oid", True), ("port", True),
                   ("memberships", False), ("can_login", 1), ("superuser", 0)]
        for field, value in changes:
            with self.subTest(field=field), self.assertRaises(DatabaseRefused):
                validate_database({**GOOD, field: value}, database_environment(URL))
        for value in [None, [], {**GOOD, "password": "private"}, {k: v for k, v in GOOD.items() if k != "cluster"}]:
            with self.assertRaises(DatabaseRefused):
                validate_database(value, database_environment(URL))

    def test_aliases_options_and_missing_pins_refuse_before_process(self):
        for executable, url in [("psql", URL), (None, URL), ("/trusted/psql", URL + "?options=unsafe"),
                                ("/trusted/psql", URL.replace("127.0.0.1", "foreign.invalid"))]:
            with patch("native_durable_database.query_identity") as query, self.assertRaises(DatabaseRefused):
                observe_durable_database(executable, url)
            query.assert_not_called()

    def test_duplicate_invalid_and_nonfinite_json_refuse(self):
        for raw in [b'{"cluster":"123","cluster":"456"}', b'[]', b'null', b'\xff',
                    b'{' + b'"port":NaN}', b'[[[[[[[[', b'']:
            with patch("native_durable_database.query_identity", return_value=raw), self.assertRaises(DatabaseRefused):
                observe_durable_database("/trusted/psql", URL)

    def test_environment_never_inherits_connection_or_tool_overrides(self):
        with patch.dict(os.environ, {"PGSERVICE": "other", "PGOPTIONS": "unsafe", "PGPASSWORD": "other", "PGPASSFILE": "/untrusted/passwords", "LD_PRELOAD": "other"}), patch("native_durable_database.query_identity", return_value=json.dumps(GOOD).encode()) as query:
            observe_durable_database("/trusted/psql", URL)
        environment = query.call_args.args[1]
        self.assertEqual(environment["PGPASSWORD"], "private-fixture")
        self.assertNotIn("LD_PRELOAD", environment)
        self.assertNotIn("PGSERVICE", environment)
        self.assertEqual(environment["PGPASSFILE"], "/dev/null")


@unittest.skipUnless(sys.platform == "linux", "Bounded pipe observation requires Linux selectors")
class ActualDatabasePipeBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.executable = Path(self.scratch.name) / "fixed-fixture"

    def executable_code(self, code):
        self.executable.write_text("#!/usr/bin/python3\n" + code + "\n")
        self.executable.chmod(0o700)

    def test_actual_pipe_preserves_fixed_arguments_and_private_environment(self):
        self.executable_code("import json,os,sys\nprint(json.dumps({'arguments':sys.argv[1:], 'environment':dict(os.environ)}))")
        environment = database_environment(URL)
        result = json.loads(query_identity(str(self.executable), environment))
        self.assertEqual(result["arguments"][:4], ["--no-psqlrc", "--tuples-only", "--no-align", "--set=ON_ERROR_STOP=1"])
        self.assertEqual(result["arguments"][-2], "--command")
        self.assertNotIn("private-fixture", str(result["arguments"]))
        self.assertEqual(result["environment"]["PGPASSWORD"], "private-fixture")

    def test_actual_oversized_output_and_failed_exit_refuse(self):
        for code in ["print('x'*20000)", "import sys\nprint('partial');sys.exit(2)", "pass"]:
            self.executable_code(code)
            with self.assertRaises(DatabaseRefused):
                query_identity(str(self.executable), database_environment(URL))

    def test_actual_deadline_kills_and_reaps_only_owned_child(self):
        self.executable_code("import time\ntime.sleep(10)")
        original = subprocess.Popen
        children = []
        def track(*args, **kwargs):
            child = original(*args, **kwargs)
            children.append(child)
            return child
        with patch("native_durable_database.subprocess.Popen", side_effect=track), self.assertRaises(DatabaseRefused):
            query_identity(str(self.executable), database_environment(URL), timeout=.05)
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].returncode)


if __name__ == "__main__":
    unittest.main()
