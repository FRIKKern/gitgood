#!/usr/bin/env python3
"""Ordinary real systemd MainPID for the isolated hosted ownership proof.

Production publication/admission/claim code is used unchanged. This manager is
fixture orchestration, not the unfinished product lifecycle controller.
"""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, "/opt/gitgood/native/v2")
from generation_publication import GenerationPublication
from native_durable_binding import observe_durable_binding
from native_service_scope import group_identity
from resource_generations import canonical


def write(path, value):
    raw = canonical(value)
    if len(raw) > 65536:
        raise ValueError("fixture receipt limit")
    with path.with_suffix(".partial").open("xb") as target:
        target.write(raw)
    os.chmod(path.with_suffix(".partial"), 0o600)
    os.rename(path.with_suffix(".partial"), path)


def wait(path, deadline):
    while not path.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("fixture handshake deadline")
        time.sleep(.1)
    return json.loads(path.read_bytes())


def launch(arguments, leaf, *, environment, output):
    def enter():
        (leaf / "cgroup.procs").write_text(str(os.getpid()))
    return subprocess.Popen(arguments, env=environment, stdin=subprocess.DEVNULL,
                            stdout=output, stderr=subprocess.STDOUT, preexec_fn=enter)


def main(seed_path):
    seed = json.loads(Path(seed_path).read_bytes())
    run = Path(seed["run"])
    root = Path(seed["root"])
    deadline = time.monotonic() + 300
    phase = "delegation"
    os.umask(0o077)
    try:
        assert os.getuid() == os.geteuid() == seed["uid"] > 0
        assert os.getgid() == os.getegid() == seed["gid"] > 0
        assert not (run / "observed.json").exists()  # a restart cannot replay this fixture
        for path in [root / "history/lifecycle-responsibility-v2",
                     Path(seed["seal_directory"]) / "lifecycle-worker-admission-v2.json"]:
            assert not path.exists() and not path.is_symlink()

        parent = Path("/sys/fs/cgroup/system.slice") / seed["unit"]
        assert os.getxattr(parent, "user.delegate") == b"1"
        assert not (parent / "cgroup.procs").read_text().strip()
        (parent / "cgroup.subtree_control").write_text("+cpu +memory")
        for name in ["native", "web", "edge", "maintenance"]:
            (parent / name).mkdir()

        # Publication is performed by the real MainPID, under production file
        # custody and SQL writer exclusion, with all workload leaves empty.
        phase = "observe-real-binding"
        observed = observe_durable_binding(seed["root"], seed["installation"],
                                           seed["unit_sha256"], seed["executables"], **seed["limits"])
        write(run / "observed.json", observed)
        phase = "await-root-seal"
        expected = wait(Path(seed["seal_directory"]) / "generation-admission-v2.json", deadline)
        assert expected["binding_sha256"] == observed["binding_sha256"]
        phase = "publish-generation"
        published = GenerationPublication(
            seed["root"], seed["installation"], expected["binding_sha256"],
            expected["history_identity"], expected["lock_identity"], seed["unit_sha256"],
            seed["executables"], **seed["limits"]
        ).publish(operation=seed["generation_operation"], generation=seed["generation"],
                  created_at=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))
        write(run / "published.json", published)
        phase = "await-root-start"
        wait(Path(seed["seal_directory"]) / "fixture-start.json", deadline)

        environment = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
                       "HOME": str(run), "ERL_CRASH_DUMP": "/dev/null", "ERL_CRASH_DUMP_SECONDS": "0",
                       "RELEASE_TMP": str(run), "RELEASE_DISTRIBUTION": "none",
                       "ERL_FLAGS": "+S 2:2 +SDio 1 +SDcpu 1"}
        configuration = json.loads((root / "configuration/installation.json").read_bytes())
        environment.update(configuration["forge"])
        environment.update({"GITGOOD_SUPERVISION_PROFILE": "systemd-v2", "PHX_SERVER": "true",
                            "GITGOOD_GIT": seed["executables"]["git"],
                            "GITGOOD_PYTHON": seed["executables"]["python"],
                            "GITGOOD_OWNED_PROOF_DIRECTORY": str(run)})
        phase = "start-original-owner"
        native = parent / "native"
        native_identity = group_identity(native, seed["uid"])
        with (run / "worker.private.log").open("xb") as output:
            beam = launch([seed["release"] + "/bin/gitgood", "eval",
                           'Code.eval_file("' + seed["worker"] + '")'], native,
                          environment=environment, output=output)
            # A sibling sentinel checks that bounded native cleanup does not
            # target other delegated leaves before final fixture unit shutdown.
            sentinel = launch(["/usr/bin/sleep", "300"], parent / "web",
                              environment={"PATH": "/usr/bin:/bin"}, output=subprocess.DEVNULL)
            write(run / "launched.json", {"launcher_pid": beam.pid, "sentinel_pid": sentinel.pid})
            phase = "await-original-owner-exit"
            while beam.poll() is None:
                if time.monotonic() >= deadline:
                    raise TimeoutError("original owner fixture deadline")
                time.sleep(.1)
            write(run / "owner-exited.json", {"exit_code": beam.returncode,
                                              "fixture_signalled_beam": False})
            # The root observer first proves the BEAM and original SQL/kernel
            # backend gone. Only then does this fixture quiesce residual children.
            phase = "await-cleanup-observer"
            wait(Path(seed["seal_directory"]) / "fixture-cleanup.json", deadline)
            assert group_identity(native, seed["uid"]) == native_identity
            assert sentinel.poll() is None
            (native / "cgroup.kill").write_text("1")
            until = time.monotonic() + 10
            while "populated 0" not in (native / "cgroup.events").read_text():
                if time.monotonic() >= until:
                    raise TimeoutError("native descendants remain")
                time.sleep(.1)
            assert group_identity(native, seed["uid"]) == native_identity
            assert sentinel.poll() is None
            write(run / "quiescent.json", {"native_empty": True, "sibling_preserved": True,
                                           "cleanup_actor": "fixture-manager", "product_controller_verified": False})
            phase = "await-root-stop"
            while time.monotonic() < deadline:
                time.sleep(.25)
            raise TimeoutError("fixture was not stopped")
    except Exception as error:
        write(run / "manager-failed.json", {"phase": phase, "error_type": type(error).__name__})
        # No automatic Restart=on-failure retry over retained responsibility.
        # Leave this MainPID present until the bounded root cleanup stops it.
        while time.monotonic() < deadline:
            time.sleep(.25)
        # The observed failure is in the retained receipt. Exiting normally
        # prevents the required Restart=on-failure policy from replaying a
        # disposable fixture after its outer observer has disappeared.
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
