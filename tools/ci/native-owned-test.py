#!/usr/bin/env python3
"""Pure/local fixture regressions; no root service, database, or VM effects."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("native_owned_proof", HERE / "native-owned-proof.py")
proof = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proof)


class BoundedProofTests(unittest.TestCase):
    def setUp(self):
        # Local Windows checks must not spill into a full system temp drive.
        self.scratch = HERE.parents[1] / ".gitgood/native-owned-static"
        self.scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="check-", dir=self.scratch)
        self.directory = Path(self.temporary.name).resolve()
        self.assertTrue(self.directory.is_relative_to(self.scratch.resolve()))

    def tearDown(self):
        self.assertTrue(self.directory.is_relative_to(self.scratch.resolve()))
        self.temporary.cleanup()

    def test_cleanup_failure_cannot_be_green_or_hide_other_owned_units(self):
        receipt = {"status": "passed", "scope": "publication-only-component", "cases": []}
        units = ["gitgood-installation-first.service", "gitgood-installation-second.service"]
        with patch.object(proof, "command", side_effect=[TimeoutError(), b""]) as command, \
                patch.object(proof, "write_new") as write, contextlib.redirect_stdout(io.StringIO()):
            result = proof.finalize(receipt, units, self.directory, "complete")
        self.assertEqual(result, 1)
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["cleanup_errors"], units[:1])
        self.assertEqual(command.call_count, 2)
        self.assertEqual(write.call_args.args[0], self.directory / "receipt.json")

    def test_existing_failure_is_not_erased_by_successful_cleanup(self):
        receipt = {"status": "failed", "scope": "publication-only-component", "cases": []}
        with patch.object(proof, "command", return_value=b""), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(proof.finalize(receipt, [], None, "preflight"), 1)

    def hosted_opt_fixture(self, *, uid=0, mode=0o40777):
        before = SimpleNamespace(st_dev=10, st_ino=20, st_uid=uid, st_gid=0, st_mode=mode)
        after = SimpleNamespace(st_dev=10, st_ino=20, st_uid=uid, st_gid=0, st_mode=0o40755)
        path = Mock()
        path.resolve.return_value = path
        path.lstat.side_effect = [before, after]
        operating = SimpleNamespace(geteuid=lambda: 0,
            environ={"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted"},
            O_RDONLY=0, O_DIRECTORY=1, O_NOFOLLOW=2, O_CLOEXEC=4,
            open=Mock(return_value=31), close=Mock(), fstat=Mock(side_effect=[before, after]), fchmod=Mock())
        return path, operating

    def test_hosted_opt_hardening_changes_only_original_directory_descriptor(self):
        path, operating = self.hosted_opt_fixture()
        with patch.object(proof, "os", operating), patch.object(proof, "Path", return_value=path) as constructor, \
                patch.object(proof.sys, "platform", "linux"):
            result = proof.harden_hosted_opt()
        constructor.assert_called_once_with("/opt")
        operating.open.assert_called_once_with(path, 7)
        operating.fchmod.assert_called_once_with(31, 0o755)
        operating.close.assert_called_once_with(31)
        self.assertEqual((result["before_mode"], result["after_mode"]), (0o777, 0o755))
        self.assertFalse(result["recursive_changes"])
        self.assertFalse(result["production_guards_modified"])

    def test_hosted_opt_hardening_refuses_untrusted_owner_or_non_directory(self):
        for options in [{"uid": 1001}, {"mode": 0o120777}]:
            with self.subTest(options=options):
                path, operating = self.hosted_opt_fixture(**options)
                with patch.object(proof, "os", operating), patch.object(proof, "Path", return_value=path), \
                        patch.object(proof.sys, "platform", "linux"), self.assertRaises(ValueError):
                    proof.harden_hosted_opt()
                operating.fchmod.assert_not_called()
                operating.close.assert_called_once_with(31)

    def test_runtime_inventory_refuses_escape_before_copy(self):
        source = self.directory / "source"
        source.mkdir()
        outside = self.directory / "private"
        outside.write_text("must not be copied", encoding="utf-8")
        try:
            (source / "escape").symlink_to(outside)
        except OSError:
            self.skipTest("host cannot create test symlink")
        destination = self.directory / "destination"
        with self.assertRaises(ValueError):
            proof.copy_runtime(source, destination)
        self.assertFalse(destination.exists())

    def test_runtime_inventory_enforces_combined_byte_bound(self):
        source = self.directory / "source"
        source.mkdir()
        (source / "first").write_bytes(b"1234")
        (source / "second").write_bytes(b"5678")
        with patch.object(proof, "COPY_LIMIT", 7), self.assertRaises(ValueError):
            proof.copy_inventory(source)

    def test_production_import_closure_preserves_required_components(self):
        modules = proof.module_closure(HERE.parents[1] / "tools/deployment")
        self.assertLessEqual(len(modules), 128)
        self.assertTrue({"native_generation_monitor_entry.py", "native_writer_exclusion.py",
                         "native_ownership_publication_entry.py", "native_lifecycle_worker_inputs.py"} <= set(modules))
        self.assertFalse(any(name.startswith("test_") for name in modules))

    def test_original_zombie_is_not_backend_absence(self):
        original = {"pid": 12, "birth": "123"}
        with patch.object(proof, "process", return_value={**original, "state": "Z"}):
            self.assertFalse(proof.absent(original))
        with patch.object(proof, "process", return_value={"pid": 12, "birth": "124", "state": "S"}):
            self.assertTrue(proof.absent(original))

    def test_backend_fault_targets_original_sql_birth(self):
        database = proof.Database.__new__(proof.Database)
        self.assertEqual(database.predicate({"backend_pid": 27, "backend_birth": "123456"}),
                         "pid=27 AND floor(extract(epoch FROM backend_start)*1000000)::bigint=123456")
        with self.assertRaises(ValueError):
            database.predicate({"backend_pid": 27, "backend_birth": "123456 OR true"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
