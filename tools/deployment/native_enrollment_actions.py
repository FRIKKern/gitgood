"""Fixed first-install commands under sealed inputs and installation-wide custody."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid

from enrollment_journal import STAGES
from inspect_native_artifact import inspect_native_artifact
from native_actions import NativeActions, FORGE_KEYS, WEB_KEYS, verify_runtime_stage
from native_allocation import observe_empty_database, supported_platform
from native_inventory import capture_native_resources, cgroup_identity, private_bytes
from native_probes import SCHEMA_SQL
from stage_native_artifact import stage_native_artifact
from upgrade_journal import canonical, require, unique_object


class NativeEnrollmentActions:
    """No prior-release fiction, arbitrary commands, callbacks or inherited environment."""
    def __init__(self, custody):
        self.custody = custody
        self.inputs = custody.inputs
        self.journal = custody.journal
        self.root = self.inputs.root
        self.bindings = self.inputs.allocation["bindings"]
        self.executables = {name: value["path"] for name, value in self.bindings["executables"].items()}
        self.configuration = json.loads(private_bytes(self.root / "configuration/installation.json"), object_pairs_hook=unique_object)
        require(set(self.configuration["forge"]) <= FORGE_KEYS and set(self.configuration["web"]) == WEB_KEYS)
        require(self.configuration["forge"].get("GITGOOD_INSTALLATION_ID") == self.inputs.intent["installation"])
        self.directory = self.root / "staging" / ("native-" + self.journal.operation)
        self.reobserve()

    def _custody(self):
        self.custody.check()
        driver = cgroup_identity(self.bindings["installation"], "driver")
        require(driver == self.bindings["cgroups"]["driver"])
        require(Path("/proc/self/cgroup").read_text().splitlines() == ["0::" + driver["kernel_path"]])

    def _owned(self, stages):
        self.custody.owned(stages)
        self._custody()

    def reobserve(self):
        self._custody()
        supported_platform()
        observed = capture_native_resources(self.root, self.executables)
        require(observed["bindings"] == self.bindings and
                observed["bindings_sha256"] == self.inputs.allocation["bindings_sha256"])
        return observed

    def _empty(self, names):
        for name in names:
            group = self.bindings["cgroups"][name]
            require(cgroup_identity(self.bindings["installation"], name) == group)
            path = Path(group["path"])
            require(dict(line.split() for line in (path / "cgroup.events").read_text().splitlines())["populated"] == "0")
            require(not (path / "cgroup.procs").read_text().strip())

    def runtime_profile(self, *, observation=False):
        self.custody.owned({"inspect"},observation=observation); self.reobserve()
        versions = {}
        for name, arguments in [("python", ["--version"]), ("node", ["--version"]),
                                ("git", ["--version"]), ("psql", ["--version"]), ("caddy", ["version"])]:
            result = subprocess.run([self.executables[name], *arguments],
                                    env={"PATH":"/usr/bin:/bin", "LANG":"C.UTF-8", "LC_ALL":"C.UTF-8"},
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)
            require(result.returncode == 0 and 0 < len(result.stdout) <= 8192)
            versions[name] = result.stdout.decode("ascii").strip()
        require(re.fullmatch(r"Python 3\.12\.[0-9]+", versions["python"]))
        require(versions["node"] == "v22.23.3" and versions["psql"] == "psql (PostgreSQL) 18.4")
        git = re.fullmatch(r"git version 2\.([0-9]+)\.[0-9]+", versions["git"])
        require(git and int(git[1]) >= 43)
        require(re.fullmatch(r"v2\.11\.7(?: [^\r\n]+)?", versions["caddy"]))
        self.reobserve()
        return versions

    def inspect(self, *, observation=False):
        self.custody.owned({"inspect"},observation=observation); self.reobserve()
        self._empty(["native", "web", "edge", "maintenance"])
        require(not list((self.root / "storage").iterdir()) and not list((self.root / "staging").iterdir()))
        empty = observe_empty_database(self.executables["psql"], self.configuration["forge"]["DATABASE_URL"])
        require(empty == self.inputs.allocation["empty_database"])
        versions = self.runtime_profile(observation=observation)
        inspected = inspect_native_artifact(self.inputs.inputs["plan"]["archive"]["path"],
                                           self.inputs.intent["artifact_sha256"], self.inputs.intent["candidate"])
        self.reobserve(); self._empty(["native", "web", "edge", "maintenance"])
        return {"artifact": inspected, "runtime": versions, "empty_database": empty}

    def stage(self):
        self._owned({"stage"}); self.reobserve()
        self._empty(["native", "web", "edge", "maintenance"])
        result = stage_native_artifact(self.inputs.inputs["plan"]["archive"]["path"],
                                       self.inputs.intent["artifact_sha256"], self.inputs.intent["candidate"],
                                       self.root / "staging", self.journal.operation)
        self._stage(self.directory)
        return result

    def _stage(self, directory):
        require(Path(directory) == self.directory)
        return verify_runtime_stage(directory, self.inputs.intent["candidate"], self.inputs.intent["artifact_sha256"])

    _environment = NativeActions._environment

    def _launch(self, name, stage, arguments, environment, cwd):
        self.reobserve()
        require(name in {"native", "web", "maintenance"})
        self._empty([name])
        group = self.bindings["cgroups"][name]
        log = self.journal.directory / (name + "-" + str(len(self.journal.record["events"])) + "-" + str(uuid.uuid4()) + ".log")
        with os.fdopen(self.journal._open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL), "wb") as output:
            process = subprocess.Popen([self.executables["python"], "-I", str(stage["wrapper"]), group["path"], *arguments],
                                       cwd=cwd, env=environment, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                                       start_new_session=True, umask=0o077)
        process.gitgood_log = log
        return process

    def stop_group(self, name, *, observation=False):
        self.custody.owned(set(STAGES), observation=observation); self._custody()
        require(name in {"native", "web", "edge", "maintenance"})
        observed = cgroup_identity(self.bindings["installation"], name)
        require(observed == self.bindings["cgroups"][name])
        path = Path(observed["path"])
        groups = [path, *[child for child in path.rglob("*") if child.is_dir()]]
        require(len(groups) <= 256)
        pids = {int(pid) for group in groups for pid in (group / "cgroup.procs").read_text().split()}
        require(len(pids) <= 4096)
        members = [member for pid in sorted(pids) if (member := NativeActions._process_birth(pid)) is not None]
        (path / "cgroup.kill").write_text("1")
        deadline = time.monotonic() + 15
        while dict(line.split() for line in (path / "cgroup.events").read_text().splitlines())["populated"] != "0":
            require(time.monotonic() < deadline); time.sleep(.05)
        self._empty([name]); NativeActions._reap_owned(members)
        return {"group_empty": True, "group_identity_sha256": hashlib.sha256(canonical(observed)).hexdigest()}

    def migrate(self, *, resume=False):
        require(type(resume) is bool)
        self._owned({"migrate"}); self._empty(["native", "web", "edge", "maintenance"])
        self.reobserve()
        stage = self._stage(self.directory)
        if resume:
            before = self.initial_schema()
            require(stage["migrations"][:len(before)] == before)
        else:
            observe_empty_database(self.executables["psql"], self.configuration["forge"]["DATABASE_URL"])
            require(not list((self.root / "storage").iterdir()))
            before = []
        environment = self._environment("forge"); environment["PHX_SERVER"] = "false"
        process = self._launch("maintenance", stage, [str(stage["code"] / "forge/bin/gitgood"), "eval", "Gitgood.Release.migrate()"], environment, stage["code"] / "forge")
        try: code = process.wait(timeout=300)
        finally:
            self.stop_group("maintenance"); process.wait(timeout=15)
        require(code == 0)
        after = self.schema()
        require(after == stage["migrations"])
        return {"migration_command_completed": True, "before_schema":before, "schema": after, "inventory_sha256": stage["inventory_sha256"]}

    def schema(self, *, observation=False, allow_empty=False):
        require(type(allow_empty) is bool)
        self.custody.owned({"migrate", "bootstrap", "verify", "activate", "enroll"}, observation=observation)
        self.reobserve()
        from native_inventory import database_environment
        result = subprocess.run([self.executables["psql"], "--no-psqlrc", "--tuples-only", "--no-align",
                                 "--set=ON_ERROR_STOP=1", "--command", SCHEMA_SQL],
                                env=database_environment(self.configuration["forge"]["DATABASE_URL"]),
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)
        require(result.returncode == 0 and 0 < len(result.stdout) <= 8192)
        value = json.loads(result.stdout, object_pairs_hook=unique_object)
        require(isinstance(value, list) and (0 if allow_empty else 1) <= len(value) <= 256 and value == sorted(set(value)))
        require(all(isinstance(version, str) and re.fullmatch(r"[0-9]{14}", version) for version in value))
        return value

    def initial_schema(self, *, observation=False):
        self.custody.owned({"migrate"},observation=observation); self.reobserve()
        self._empty(["native","web","edge","maintenance"])
        from native_inventory import database_environment
        result = subprocess.run([self.executables["psql"],"--no-psqlrc","--tuples-only","--no-align",
                                 "--set=ON_ERROR_STOP=1","--command","SELECT coalesce(to_regclass('public.schema_migrations')::text,'absent')"],
                                env=database_environment(self.configuration["forge"]["DATABASE_URL"]),
                                stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=10)
        require(result.returncode == 0 and result.stdout.strip() in {b"absent",b"public.schema_migrations"})
        if result.stdout.strip() == b"absent":
            observe_empty_database(self.executables["psql"],self.configuration["forge"]["DATABASE_URL"])
            return []
        return self.schema(observation=observation,allow_empty=True)

    def bootstrap(self, *, observe=False):
        require(type(observe) is bool)
        self.custody.owned({"bootstrap"}, observation=observe)
        self._empty(["native", "web", "maintenance"])
        stage = self._stage(self.directory)
        require(self.schema(observation=observe) == stage["migrations"])
        environment = self._environment("forge"); environment["PHX_SERVER"] = "false"
        bootstrap = self.inputs.inputs["bootstrap"]
        environment.update({"GITGOOD_BOOTSTRAP_"+key.upper():value for key,value in bootstrap.items()})
        environment["GITGOOD_BOOTSTRAP_REQUEST_SHA256"] = self.inputs.inputs["plan"]["bootstrap_request_sha256"]
        command = ("Gitgood.Release.observe_bootstrap_owner(); if Process.whereis(Gitgood.Supervisor) != nil or Process.whereis(Gitgood.InstallationLease) != nil, do: raise(\"Observation started runtime\")"
                   if observe else "Gitgood.Release.bootstrap_owner()")
        name = "maintenance" if observe else "native"
        process = self._launch(name, stage, [str(stage["code"] / "forge/bin/gitgood"), "eval", command], environment, stage["code"] / "forge")
        try: code = process.wait(timeout=60)
        finally:
            self.stop_group(name, observation=observe); process.wait(timeout=15)
        require(code == 0)
        raw = private_bytes(process.gitgood_log, 131_072)
        require(bootstrap["password"].encode() not in raw)
        records = []
        for line in raw.splitlines():
            if line.startswith(b"{"):
                record = json.loads(line, object_pairs_hook=unique_object)
                if record.get("purpose") == "installation_owner_bootstrap": records.append(record)
        require(len(records) == 1)
        record = records[0]
        require(set(record) == {"protocol", "purpose", "outcome", "installation", "request", "username", "team", "user_id", "role_at_creation", "limitations"})
        require(type(record["protocol"]) is int and record["protocol"] == 1 and
                all(record[key] == bootstrap[key] for key in ["installation", "request", "username", "team"]))
        require(record["outcome"] in ({"absent", "recorded"} if observe else {"created", "recorded"}))
        if record["outcome"] == "absent": require(record["user_id"] is None and record["role_at_creation"] is None)
        else: require(type(record["user_id"]) is int and record["user_id"] > 0 and record["role_at_creation"] == "owner")
        return record

    def start_native(self):
        self._owned({"verify","activate","enroll"}); stage = self._stage(self.directory)
        return self._launch("native", stage, [str(stage["code"] / "forge/bin/gitgood"), "start"], self._environment("forge"), stage["code"] / "forge")

    def start_web(self):
        self._owned({"verify","activate","enroll"}); stage = self._stage(self.directory)
        return self._launch("web", stage, [self.executables["node"], str(stage["code"] / "web/node_modules/srvx/bin/srvx.mjs"),
                                          "--prod", "-s", "dist/client", "server.mjs"], self._environment("web"), stage["code"] / "web")
