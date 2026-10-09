"""Fixed temporary application launches under original retirement custody."""
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time
import uuid

from native_actions import FORGE_KEYS, WEB_KEYS, NativeActions, verify_runtime_stage
from native_edge import routing_profile, verification_caddy_source
from native_inventory import directory_identity, executable_identity, private_bytes
from retirement_restore_data import RetirementRestoreData
from retirement_restore_plan import observe_target_group
from retirement_snapshot import CORE, retained_file_identity
from upgrade_journal import canonical, require, unique_object, validate_time


class RetirementRuntime:
    def __init__(self, journal, resource_plan, retention, checkpoint, restoration, configuration_bytes, *, lifecycle_stage="archive_verify"):
        self.data = RetirementRestoreData(journal, resource_plan, retention, checkpoint, restoration, configuration_bytes,
                                          lifecycle_stage=lifecycle_stage)
        require(self.data.full_restoration is not None)
        self.snapshot, self.journal = self.data.snapshot, journal
        self.full = self.data.full_restoration
        self.target = self.full["materialization"]
        self.root = Path(self.target["target_root"]["path"])
        self.bindings = self.snapshot.bindings
        self.executables = {key: item["path"] for key, item in self.bindings["executables"].items()}
        require({"python", "node", "git", "psql", "caddy"} <= set(self.executables))
        self.configuration = None
        self.configuration_sha256 = None
        self.directory = None
        self.processes = {}
        self.reservations = {}

    def _custody(self, *, stopping=False):
        stage = self.snapshot._core_custody() if stopping else self.snapshot._custody()
        if not stopping:
            self.snapshot._retained()
            self.snapshot._original_database()
            for value in self.bindings["executables"].values():
                require(executable_identity(value["path"]) == value)
        return stage

    def _group(self, name, *, empty=False):
        require(name in {"native", "web", "edge", "maintenance"})
        observed = observe_target_group(self.journal.plan["installation"], self.journal.operation,
                                        self.target["target_installation"], name)
        require(observed == self.full["target_groups"][name])
        if empty:
            path = Path(observed["path"])
            require(dict(line.split() for line in (path / "cgroup.events").read_text().splitlines()).get("populated") == "0")
            require(not (path / "cgroup.procs").read_text().strip())
        return observed

    def empty(self):
        self._custody(stopping=True)
        for name in self.full["target_groups"]:
            self._group(name, empty=True)

    def reobserve(self):
        stage = self._custody()
        require(directory_identity(self.root, private=True) == self.target["target_root"])
        if self.configuration_sha256 is not None:
            require(hashlib.sha256(private_bytes(self.root / "configuration/installation.json")).hexdigest() == self.configuration_sha256)
        for name in self.full["target_groups"]:
            self._group(name)
        if self.directory is not None:
            directory_identity(self.directory, private=True)
        return verify_runtime_stage(stage, self.journal.plan["candidate"], self.journal.plan["artifact_sha256"])

    def materialization(self, *, marker=None):
        self.empty()
        require(directory_identity(self.root, private=True) == self.target["target_root"])
        request = json.loads(canonical(self.target))
        existing = bool(list(self.root.iterdir()))
        require(self.snapshot.lifecycle_stage == "archive_verify" or existing and marker is not None)
        require(existing or marker is None)
        if existing:
            request.update(protocol=3 if marker is not None else 2, phase="observe")
        if marker is not None:
            request.update(runtime_marker=marker, native_group=self.full["target_groups"]["native"])
        environment = {**self.snapshot.database.environment, "PGDATABASE": self.data.target["database"]}
        value = self.snapshot._run_packaged("retirement-restore-materialize.mjs", "materialization", request,
                                            environment, restoration=self.full)
        keys = {"protocol", "purpose", "status", "operation", *CORE, "target_installation", "target_root", "target_database",
                "target_resource_fingerprints", "configuration_sha256", "ports", "checks", "limitations"}
        if existing:
            keys.add("phase")
        if marker is not None:
            keys.update({"runtime_marker", "native_group"})
        require(isinstance(value, dict) and set(value) == keys)
        require(type(value["protocol"]) is int and value["protocol"] == request["protocol"])
        require(value["purpose"] == "retirement_restore_materialization" and value["status"] == ("observed" if existing else "materialized"))
        require(not existing or value["phase"] == "observe")
        require(value["operation"] == self.journal.operation and all(value[key] == self.snapshot.expected[key] for key in CORE))
        for key in ["target_installation", "target_root", "target_database", "ports"]:
            require(value[key] == self.target[key])
        if marker is not None:
            require(value["runtime_marker"] == marker and value["native_group"] == self.full["target_groups"]["native"])
        require(isinstance(value["target_resource_fingerprints"], dict) and set(value["target_resource_fingerprints"]) == {"git", "ssh", "configuration"})
        require(all(isinstance(item, str) and re.fullmatch(r"[0-9a-f]{64}", item) for item in value["target_resource_fingerprints"].values()))
        require(isinstance(value["configuration_sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", value["configuration_sha256"]))
        require(isinstance(value["checks"], list) and len(value["checks"]) == 4 and isinstance(value["limitations"], list) and len(value["limitations"]) == 3)
        self.configuration_sha256 = value["configuration_sha256"]
        raw = private_bytes(self.root / "configuration/installation.json")
        require(hashlib.sha256(raw).hexdigest() == self.configuration_sha256)
        self.configuration = json.loads(raw, object_pairs_hook=unique_object)
        require(self.configuration["installation"] == self.target["target_installation"])
        require(set(self.configuration["forge"]) <= FORGE_KEYS and set(self.configuration["web"]) == WEB_KEYS)
        require("GITGOOD_BARKPARK_ORIGIN" not in self.configuration["forge"])
        profile = routing_profile(self.configuration)
        require(profile["hostname"] == "127.0.0.1" and profile["ports"] == self.target["ports"])
        require(self.configuration["forge"]["GITGOOD_STORAGE"] == str(self.root / "git"))
        require(self.configuration["forge"]["GITGOOD_SSH_HOST_KEY_DIRECTORY"] == str(self.root / "ssh"))
        self.reobserve()
        return value

    def _write(self, path, raw):
        descriptor = self.journal._private_open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        with os.fdopen(descriptor, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())

    def _reserve(self):
        require(not self.reservations)
        try:
            for name, port in self.target["ports"].items():
                connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    connection.bind(("127.0.0.1", port))
                    connection.listen(1)
                except BaseException:
                    connection.close()
                    raise
                self.reservations[name] = connection
            connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                connection.bind(("127.0.0.1", self.target["ports"]["https"]))
            except BaseException:
                connection.close()
                raise
            self.reservations["https_udp"] = connection
        except BaseException:
            self.close_reservations()
            raise

    def close_reservations(self):
        for connection in self.reservations.values():
            connection.close()
        self.reservations.clear()

    def _release(self, names):
        for name in names:
            self.reservations.pop(name).close()

    def _environment(self, component):
        require(self.configuration is not None and self.directory is not None)
        environment = {"PATH": ":".join([str(Path(self.executables[name]).parent) for name in ["node", "psql"]] + ["/usr/bin", "/bin"]),
                       "HOME": str(self.directory), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
        environment.update(self.configuration[component])
        if component == "forge":
            temporary = self.directory / "native-private"
            temporary.mkdir(mode=0o700)
            environment.update(GITGOOD_GIT=self.executables["git"], GITGOOD_PYTHON=self.executables["python"], PHX_SERVER="true",
                               RELEASE_TMP=str(temporary), ERL_CRASH_DUMP=str(temporary / "erl-crash.dump"),
                               GITGOOD_RECOVERY_VERIFY_ONLY="true", GITGOOD_RECOVERY_VERIFY_OPERATION=self.journal.operation)
        return environment

    def _launch(self, name, arguments, environment, cwd):
        stage = self.reobserve()
        group = self._group(name, empty=True)
        require(self.directory is not None)
        log = self.directory / (name + "-" + str(uuid.uuid4()) + ".log")
        descriptor = self.journal._private_open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        with os.fdopen(descriptor, "wb") as output:
            process = subprocess.Popen([self.executables["python"], "-I", str(stage["wrapper"]), group["path"], *arguments],
                                       env=environment, cwd=cwd, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, umask=0o077)
        process.gitgood_log = log
        self.processes[name] = process
        return process

    def start(self):
        require(self.configuration is not None and self.directory is None)
        self.empty()
        stage = self.reobserve()
        self.directory = self.journal.directory / ("retirement-runtime-" + str(uuid.uuid4()))
        self.directory.mkdir(mode=0o700)
        self._reserve()
        try:
            self._release(["forge", "native_ssh"])
            self._launch("native", [str(stage["code"] / "forge/bin/gitgood"), "start"], self._environment("forge"), stage["code"] / "forge")
            self._release(["web"])
            self._launch("web", [self.executables["node"], str(stage["code"] / "web/node_modules/srvx/bin/srvx.mjs"),
                                 "--prod", "-s", "dist/client", "server.mjs"], self._environment("web"), stage["code"] / "web")
            edge = self.directory / "edge"
            edge.mkdir(mode=0o700)
            source = verification_caddy_source(self.root, self.configuration).encode()
            self._write(edge / "Caddyfile", source)
            module = Path(__file__).resolve().with_name("retirement_edge.py")
            plan = {"protocol": 1, "installation": self.journal.plan["installation"], "operation": self.journal.operation,
                    "target_installation": self.target["target_installation"], "root": self.target["target_root"],
                    "group": self.full["target_groups"]["edge"], "configuration_sha256": self.configuration_sha256,
                    "caddy": self.bindings["executables"]["caddy"], "module_sha256": hashlib.sha256(private_bytes(module)).hexdigest(),
                    "edge_module_sha256": hashlib.sha256(private_bytes(module.with_name("native_edge.py"))).hexdigest(),
                    "caddyfile_sha256": hashlib.sha256(source).hexdigest()}
            raw = canonical(plan) + b"\n"
            self._write(edge / "edge-plan.json", raw)
            self._release(["https", "https_udp", "ssh"])
            self._launch("edge", [self.executables["python"], "-I", str(module), str(edge / "edge-plan.json"), hashlib.sha256(raw).hexdigest()],
                         {"PATH": "/usr/bin:/bin", "HOME": str(edge), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}, edge)
        finally:
            self.close_reservations()

    def runtime_marker(self):
        self.reobserve()
        path = self.root / "git/.gitgood-runtime-v1.json"
        raw = private_bytes(path, 4096)
        value = json.loads(raw, object_pairs_hook=unique_object)
        require(set(value) == {"protocol", "host", "owners", "owner_births", "mode", "candidate", "created_at", "cgroup"})
        require(type(value["protocol"]) is int and value["protocol"] == 1 and value["mode"] == "runtime")
        require(value["host"] == socket.gethostname() and value["candidate"] == self.journal.plan["candidate"])
        require(value["cgroup"] == self._group("native")["kernel_path"])
        validate_time(value["created_at"])
        require(isinstance(value["owners"], list) and 1 <= len(value["owners"]) <= 8)
        require(isinstance(value["owner_births"], dict) and set(value["owner_births"]) == {str(pid) for pid in value["owners"]})
        for pid in value["owners"]:
            require(type(pid) is int and 0 < pid <= 2147483647)
            current = NativeActions._process_birth(pid)
            require(current is not None and current["birth"] == value["owner_births"][str(pid)] and current["state"] not in {"Z", "X"})
            require(Path("/proc", str(pid)).stat().st_uid == os.getuid())
            require(Path("/proc", str(pid), "cgroup").read_text().splitlines() == ["0::" + value["cgroup"]])
        identity = retained_file_identity(path, 4096)
        require(identity["sha256"] == hashlib.sha256(raw).hexdigest())
        self._write(self.directory / "runtime-marker-observation.json", canonical({"identity": identity, "record": value}) + b"\n")
        return identity

    def stop_group(self, name):
        self._custody(stopping=True)
        group = self._group(name)
        path = Path(group["path"])
        descendants = [path, *[item for item in path.rglob("*") if item.is_dir()]]
        require(len(descendants) <= 256)
        pids = {int(pid) for item in descendants for pid in (item / "cgroup.procs").read_text().split()}
        require(len(pids) <= 4096)
        members = [item for pid in pids if (item := NativeActions._process_birth(pid)) is not None]
        (path / "cgroup.kill").write_text("1")
        deadline = time.monotonic() + 15
        while dict(line.split() for line in (path / "cgroup.events").read_text().splitlines()).get("populated") != "0":
            require(time.monotonic() < deadline)
            self._custody(stopping=True)
            self._group(name)
            time.sleep(.05)
        self._group(name, empty=True)
        NativeActions._reap_owned(members)
        if name in self.processes:
            self.processes[name].wait(timeout=15)

    def stop(self):
        self.close_reservations()
        for name in ["edge", "native", "web", "maintenance"]:
            self.stop_group(name)
        self.empty()
