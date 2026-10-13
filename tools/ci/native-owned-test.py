#!/usr/bin/env python3
"""Pure/local fixture regressions; no root service, database, or VM effects."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
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

    def test_startup_diagnostics_accept_only_closed_events_and_numeric_exit(self):
        (self.directory / "startup-events.txt").write_text("bootstrap:observed\nmonitor:entered\nmonitor:refused\n", encoding="ascii")
        (self.directory / "owner-exited.json").write_text(json.dumps({"exit_code": 1, "fixture_signalled_beam": False}))
        self.assertEqual(proof.startup_diagnostics(self.directory), {
            "status": "observed", "events": ["bootstrap:observed", "monitor:entered", "monitor:refused"],
            "original_exit_code": 1})

    def test_startup_diagnostics_never_forward_unknown_or_excess_output(self):
        path = self.directory / "startup-events.txt"
        for raw in [b"configuration:secret-value\n", b"bootstrap:observed\n" * 65, b"x" * 4097, b"\xff"]:
            with self.subTest(raw_size=len(raw)):
                path.write_bytes(raw)
                self.assertEqual(proof.startup_diagnostics(self.directory), {"status": "invalid"})
        path.write_bytes(b"bootstrap:observed\n")
        (self.directory / "owner-exited.json").write_text(json.dumps({
            "exit_code": 1, "fixture_signalled_beam": False, "private": "secret-value"}))
        self.assertEqual(proof.startup_diagnostics(self.directory), {"status": "invalid"})

    def test_vm_trace_reduces_actual_messages_to_fixed_tags(self):
        # Exercise the real fixture tracer with explicitly fake startup modules;
        # this checks trace grammar/redaction, never production startup admission.
        executable = shutil.which("elixir")
        if not executable:
            self.skipTest("Elixir is required for the small VM tracer check")
        source = (HERE / "native-owned-worker.exs").read_text(encoding="utf-8")
        diagnostics = source.split("defmodule GitgoodOwnedProof.Witness", 1)[0]
        script = '''
calls = [
  {Gitgood.InstallationProfile, :resolve, 3},
  {Gitgood.InstallationGenerationMonitor, :start_link, 1},
  {Gitgood.InstallationGenerationMonitor, :admission, 1},
  {Gitgood.NativeOwnershipInputs, :read_application, 2},
  {Gitgood.NativeOwnershipStartup, :validate_artifact, 2},
  {Gitgood.NativeApplicationConfiguration, :check, 3},
  {Gitgood.NativeDatabaseLease, :start_link, 1},
  {Gitgood.NativeOwnershipFence, :start_link, 2},
  {Gitgood.NativeOwnershipClaim, :claim, 4},
  {Gitgood.InstallationGenerationMonitor, :attach_ownership, 3}
]
for {module, entries} <- Enum.group_by(calls, &elem(&1, 0)) do
  definitions = for {_, function, arity} <- entries do
    arguments = for i <- 1..arity, do: Macro.var(String.to_atom("_input#{i}"), nil)
    body = case function do
      :check -> quote do: {:error, "synthetic-private-return"}
      :read_application -> quote do: raise("synthetic-private-exception")
      _ -> quote do: {:ok, "synthetic-private-return"}
    end
    quote do
      def unquote(function)(unquote_splicing(arguments)), do: unquote(body)
    end
  end
  Module.create(module, {:__block__, [], definitions}, Macro.Env.location(__ENV__))
end
'''
        script += diagnostics + '''
GitgoodOwnedProof.Diagnostics.start()
GitgoodOwnedProof.Diagnostics.mark("bootstrap")
for {module, function, arity} <- calls do
  try do
    apply(module, function, List.duplicate("synthetic-private-argument", arity))
  rescue
    _ -> :ok
  end
end
path = Path.join(System.fetch_env!("GITGOOD_OWNED_PROOF_DIRECTORY"), "startup-events.txt")
until = System.monotonic_time(:millisecond) + 2_000
wait = fn recurse ->
  if length(String.split(File.read!(path), "\\n", trim: true)) < 21 do
    true = System.monotonic_time(:millisecond) < until
    Process.sleep(10)
    recurse.(recurse)
  end
end
wait.(wait)
'''
        environment = {**os.environ, "GITGOOD_OWNED_PROOF_DIRECTORY": str(self.directory),
                       "ERL_FLAGS": "+S 2:2 +SDio 1 +SDcpu 1"}
        result = subprocess.run([executable, "-e", "Code.eval_string(IO.read(:stdio, :all))"],
                                input=script, text=True, capture_output=True, timeout=20, env=environment)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        detail = proof.startup_diagnostics(self.directory)
        self.assertEqual(detail["status"], "observed")
        self.assertEqual(len(detail["events"]), 21)
        self.assertIn("configuration:refused", detail["events"])
        self.assertIn("inputs:exception", detail["events"])
        self.assertNotIn("synthetic-private", (self.directory / "startup-events.txt").read_text())

    def test_diagnostic_read_has_a_real_byte_bound_and_refuses_changed_identity(self):
        path = self.directory / "startup-events.txt"
        path.write_bytes(b"bootstrap:observed\n")
        actual_read = os.read
        with patch.object(proof.os, "read", wraps=actual_read) as read:
            self.assertEqual(proof.bounded_diagnostic_read(path), b"bootstrap:observed\n")
            self.assertEqual(read.call_args.args[1], 4097)
        def changed_read(descriptor, maximum):
            raw = actual_read(descriptor, maximum)
            path.write_bytes(b"bootstrap:observed\n" * 2)
            return raw
        with patch.object(proof.os, "read", side_effect=changed_read), self.assertRaises(ValueError):
            proof.bounded_diagnostic_read(path)

    def test_actual_fixture_application_spec_uses_supported_otp_loader(self):
        executable = shutil.which("elixir")
        if not executable:
            self.skipTest("Elixir is required for the small application specification check")
        script = '''
{:__block__, _, expressions} =
  System.fetch_env!("GITGOOD_OWNED_WORKER_SOURCE") |> File.read!() |> Code.string_to_quoted!()
[loader] = Enum.filter(expressions, fn expression ->
  Macro.prewalk(expression, false, fn
    {{:., _, [_, :load]}, _, [{:{}, _, [:application, :gitgood_owned_proof, _]}]} = node, _ -> {node, true}
    node, found -> {node, found}
  end) |> elem(1)
end)
{:ok, _} = Code.eval_quoted(loader)
{:ok, properties} = :application.get_all_key(:gitgood_owned_proof)
{GitgoodOwnedProof.Application, []} = Keyword.fetch!(properties, :mod)
[:kernel, :stdlib, :elixir, :logger, :postgrex, :jason] = Keyword.fetch!(properties, :applications)
IO.puts("fixture-application-spec-loaded")
'''
        environment = {**os.environ, "GITGOOD_OWNED_WORKER_SOURCE": str(HERE / "native-owned-worker.exs"),
                       "ERL_FLAGS": "+S 2:2 +SDio 1 +SDcpu 1"}
        result = subprocess.run([executable, "-e", "Code.eval_string(IO.read(:stdio, :all))"],
                                input=script, text=True, capture_output=True, timeout=20, env=environment)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), "fixture-application-spec-loaded", result.stderr)

    @unittest.skipUnless(sys.platform == "linux", "real Linux JIT file-limit check runs on the hosted runner")
    def test_real_beam_jit_boots_with_the_finite_fixture_file_limit(self):
        import resource
        executable = shutil.which("erl")
        self.assertIsNotNone(executable, "the pinned hosted OTP runtime is required")
        seed = {"account": "fixture", "seal_directory": str(self.directory), "run": str(self.directory)}
        unit = proof.unit_text(seed, self.directory / "manager.py").decode()
        file_limit = int(next(line.split("=", 1)[1] for line in unit.splitlines() if line.startswith("LimitFSIZE=")))
        self.assertIn("LimitCORE=0\n", unit)
        self.assertLessEqual(file_limit, 64 * 1024**2)
        environment = {"PATH": os.environ["PATH"], "LANG": "C.UTF-8", "HOME": str(self.directory),
                       "TMPDIR": str(self.directory), "ERL_CRASH_DUMP": "/dev/null", "ERL_CRASH_DUMP_SECONDS": "0",
                       "ERL_FLAGS": "+S 2:2 +SDio 1 +SDcpu 1"}
        for limit, expected in [(16 * 1024**2, -signal.SIGXFSZ), (file_limit, 0)]:
            with self.subTest(limit=limit):
                def constrain():
                    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
                    resource.setrlimit(resource.RLIMIT_FSIZE, (limit, limit))
                result = subprocess.run([executable, "-noshell", "-eval",
                    'jit = erlang:system_info(emu_flavor), io:format("native-beam-limit-ok~n"), halt().'],
                    env=environment, capture_output=True, timeout=15, preexec_fn=constrain)
                self.assertEqual(result.returncode, expected)
                if expected == 0:
                    self.assertEqual(result.stdout, b"native-beam-limit-ok\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
