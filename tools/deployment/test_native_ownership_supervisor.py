"""Actual OTP/BEAM exit boundaries, not native service/database admission proof."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[2] / 'apps/forge/lib/gitgood/native_ownership_supervisor.ex'
SCRIPT = r'''
Code.require_file(System.fetch_env!("GITGOOD_SUPERVISOR_SOURCE"))
defmodule OwnershipBoundaryWorker do
  use GenServer
  def start_link({name, root}), do: GenServer.start_link(__MODULE__, {name, root}, name: name)
  def init({name, root}) do
    path = Path.join(root, Atom.to_string(name) <> ".starts")
    File.write!(path, "started\n", [:append])
    if name == :held_session and System.get_env("GITGOOD_BOUNDARY_STARTUP_REFUSAL") == "true",
      do: {:stop, :held_session_unavailable}, else: {:ok, %{root: root}}
  end
end
defmodule OwnershipBoundaryApplication do
  use Application
  def start(_, root) do
    Gitgood.NativeOwnershipSupervisor.start_link([
      Supervisor.child_spec({OwnershipBoundaryWorker, {:captured_monitor, root}}, id: :captured_monitor),
      Supervisor.child_spec({OwnershipBoundaryWorker, {:held_session, root}}, id: :held_session),
      Supervisor.child_spec({OwnershipBoundaryWorker, {:mutation_worker, root}}, id: :mutation_worker)
    ])
  end
end
root = System.fetch_env!("GITGOOD_SUPERVISOR_BOUNDARY_ROOT")
spec = {:application, :gitgood_ownership_boundary,
        [vsn: ~c"1", description: ~c"Private ownership exit boundary",
         modules: [OwnershipBoundaryApplication, OwnershipBoundaryWorker, Gitgood.NativeOwnershipSupervisor],
         registered: [], applications: [:kernel, :stdlib, :elixir, :logger],
         mod: {OwnershipBoundaryApplication, root}]}
:ok = :application.load(spec)
:ok = Application.start(:gitgood_ownership_boundary, :permanent)
File.write!(Path.join(root, "owner-ready"), System.pid())
IO.puts("owner-ready")
case IO.gets("") do
  "monitor-kill\n" -> Process.exit(Process.whereis(:captured_monitor), :kill)
  "session-kill\n" -> Process.exit(Process.whereis(:held_session), :kill)
  "session-normal\n" -> GenServer.stop(:held_session, :normal)
end
Process.sleep(:infinity)
'''


@unittest.skipUnless(sys.platform == 'linux' and shutil.which('elixir'), 'actual Linux Elixir/OTP runtime')
class NativeOwnershipSupervisorProcessTest(unittest.TestCase):
    def test_captured_monitor_kill_exits_whole_beam_without_recapture(self):
        self.run_loss('monitor-kill')

    def test_held_session_kill_exits_whole_beam_without_reacquisition(self):
        self.run_loss('session-kill')

    def test_normal_held_session_stop_is_still_owner_loss(self):
        self.run_loss('session-normal')

    def test_ownership_startup_refusal_prevents_mutation_worker_start(self):
        self.run_loss('session-kill', startup_refused=True)

    def run_loss(self, command, startup_refused=False):
        with tempfile.TemporaryDirectory(prefix='gitgood-native-supervisor-') as temporary:
            root = Path(temporary)
            script = root / 'boundary.exs'; script.write_text(SCRIPT)
            environment = {**os.environ, 'GITGOOD_SUPERVISOR_SOURCE':str(SOURCE),
                           'GITGOOD_SUPERVISOR_BOUNDARY_ROOT':str(root),
                           'GITGOOD_BOUNDARY_STARTUP_REFUSAL':str(startup_refused).lower(),
                           'ERL_CRASH_DUMP':str(root / 'private-crash.dump'), 'ERL_CRASH_DUMP_BYTES':'65536'}
            with subprocess.Popen(['elixir','--erl','+S 2:2 +SDcpu 1 +SDio 1',str(script)],
                                  env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True) as child:
                try:
                    # A single bounded communicate includes initialization, the
                    # exact loss request and whole OS-process exit. No fixture
                    # timeout or caller kill can satisfy the passing assertion.
                    output, _ = child.communicate(command + '\n', timeout=15)
                except subprocess.TimeoutExpired:
                    child.kill(); child.communicate()
                    self.fail('Whole BEAM did not exit after captured ownership loss')
                if startup_refused:
                    self.assertNotIn('owner-ready', output)
                    self.assertFalse((root / 'owner-ready').exists())
                    self.assertIn('held_session_unavailable', output)
                else:
                    self.assertIn('owner-ready', output)
                    self.assertEqual(int((root / 'owner-ready').read_text()), child.pid)
                self.assertNotEqual(child.returncode, 0)
            for name in ['captured_monitor','held_session','mutation_worker']:
                if startup_refused and name == 'mutation_worker':
                    self.assertFalse((root / (name + '.starts')).exists())
                    continue
                self.assertEqual((root / (name + '.starts')).read_text(), 'started\n')


if __name__ == '__main__':
    unittest.main()
