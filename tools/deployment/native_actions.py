"""Fixed native lifecycle commands under an owned upgrade journal and resource bindings."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tarfile
import time

from native_inventory import cgroup_identity, private_bytes, require_native_inventory
from inspect_native_artifact import inspect_native_artifact
from upgrade_journal import canonical, owner, require, unique_object

FORGE_KEYS = {"DATABASE_URL", "SECRET_KEY_BASE", "PHX_HOST", "GITGOOD_PUBLIC_URL", "GITGOOD_WEB_ORIGIN", "GITGOOD_PROXY_KEY",
              "GITGOOD_CONNECTION_KEY", "GITGOOD_BARKPARK_ORIGIN", "GITGOOD_BARKPARK_CA", "GITGOOD_STORAGE", "PORT",
              "GITGOOD_SSH_PORT", "GITGOOD_SSH_HOST_KEY_DIRECTORY", "GITGOOD_SSH_PUBLIC_HOST", "GITGOOD_SSH_PUBLIC_PORT",
              "GITGOOD_INSTALLATION_ID"}
WEB_KEYS = {"PORT", "GITGOOD_API_URL", "GITGOOD_PROXY_KEY", "NODE_ENV"}


def verify_runtime_stage(directory, candidate, artifact_digest):
    require(sys.platform == "linux")
    directory = Path(directory)
    require(directory.is_absolute() and directory.resolve() == directory)
    value = directory.lstat()
    require(stat.S_ISDIR(value.st_mode) and value.st_uid == os.getuid() and not value.st_mode & 0o077)
    receipt = json.loads(private_bytes(directory / "receipt.json"), object_pairs_hook=unique_object)
    inventory = json.loads(private_bytes(directory / "inventory.json", 33_554_432), object_pairs_hook=unique_object)
    require(receipt.get("status") == "staged" and receipt.get("candidate") == candidate and receipt.get("artifact_sha256") == artifact_digest)
    require(isinstance(inventory, list) and 1 <= len(inventory) <= 100_000)
    require(hashlib.sha256(canonical(inventory)).hexdigest() == receipt.get("inventory_sha256"))
    code = directory / "code"
    require(code.resolve() == code)
    code_info = code.lstat()
    require(stat.S_ISDIR(code_info.st_mode) and code_info.st_uid == os.getuid() and not code_info.st_mode & 0o077)
    names = set()
    for entry in inventory:
        require(isinstance(entry, dict) and isinstance(entry.get("path"), str))
        name = entry["path"]
        require(name not in names and name.split("/")[0] in {"forge", "web"})
        require(all(part not in {"", ".", ".."} for part in name.split("/")) and "\\" not in name)
        names.add(name)
        path = code / name
        value = path.lstat()
        require(value.st_uid == os.getuid())
        if "symlink" in entry:
            require(set(entry) == {"path", "symlink"} and stat.S_ISLNK(value.st_mode) and os.readlink(path) == entry["symlink"])
            require(path.resolve().is_relative_to(code / name.split("/")[0]))
        else:
            require(set(entry) == {"path", "bytes", "sha256", "executable"})
            require(type(entry["bytes"]) is int and entry["bytes"] == value.st_size and type(entry["executable"]) is bool)
            require(stat.S_ISREG(value.st_mode) and value.st_nlink == 1 and not value.st_mode & 0o077)
            require(path.resolve() == path and bool(value.st_mode & 0o111) == entry["executable"])
            require(re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]))
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            with os.fdopen(descriptor, "rb") as source:
                before = os.fstat(source.fileno())
                require(hashlib.file_digest(source, "sha256").hexdigest() == entry["sha256"])
                after = os.fstat(source.fileno())
            require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
                    (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns))
    observed = {path.relative_to(code).as_posix() for path in code.rglob("*") if path.is_file() or path.is_symlink()}
    require(observed == names)
    # Private manifests are observations, not the independent artifact identity.
    # Bind every current code byte/link/mode back to the retained pinned archive.
    snapshot = directory / "archive.tar.gz"
    inspected = inspect_native_artifact(snapshot, artifact_digest, candidate)
    by_name = {entry["path"]: entry for entry in inventory}
    archived = set()
    descriptor = os.open(snapshot, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(descriptor, "rb") as source:
        before = os.fstat(source.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid() and before.st_nlink == 1 and not before.st_mode & 0o077)
        require(hashlib.file_digest(source, "sha256").hexdigest() == artifact_digest)
        source.seek(0)
        with tarfile.open(fileobj=source, mode="r:gz") as archive:
            for member in archive:
                if member.isdir():
                    continue
                require(member.name in by_name and member.name not in archived)
                archived.add(member.name)
                entry = by_name[member.name]
                if member.issym():
                    require(entry == {"path": member.name, "symlink": member.linkname})
                else:
                    require(member.isfile() and entry.get("bytes") == member.size and entry.get("executable") == bool(member.mode & 0o111))
                    with archive.extractfile(member) as payload:
                        require(hashlib.file_digest(payload, "sha256").hexdigest() == entry.get("sha256"))
        after = os.fstat(source.fileno())
    require(archived == names and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns))
    for path in code.rglob("*"):
        if path.is_dir() and not path.is_symlink():
            info = path.lstat()
            require(info.st_uid == os.getuid() and not info.st_mode & 0o077 and path.resolve() == path)
    required = {"forge/bin/gitgood", "web/server.mjs", "web/client-address.mjs", "web/package.json", "web/package-lock.json",
                "web/dist/build-identity.json", "web/dist/server/server.js", "web/node_modules/srvx/bin/srvx.mjs"}
    require(required <= names)
    identities = list((code / "forge/lib").glob("gitgood-*/priv/build-identity.json"))
    require(len(identities) == 1)
    native = json.loads(private_bytes(identities[0]), object_pairs_hook=unique_object)
    web = json.loads(private_bytes(code / "web/dist/build-identity.json"), object_pairs_hook=unique_object)
    require(native == web and native.get("candidate") == candidate and native.get("dirty") is False)
    require(native["migrations"] == inspected["migrations"])
    wrapper = identities[0].parent / "operations/runtime_cgroup.py"
    require(wrapper.relative_to(code).as_posix() in names)
    return {"code": code, "wrapper": wrapper, "inventory_sha256": receipt["inventory_sha256"], "migrations": native["migrations"]}


class NativeActions:
    """No arbitrary commands, inherited environment or unbound process discovery."""
    def __init__(self, root, inventory, journal):
        require(sys.platform == "linux")
        self.root = Path(root)
        self.inventory = inventory
        self.bindings = inventory["bindings"]
        require(hashlib.sha256(canonical(self.bindings)).hexdigest() == inventory["bindings_sha256"])
        self.journal = journal
        require(self.bindings["installation"] == journal.intent["installation"] and inventory["bindings_sha256"] == journal.intent["bindings_sha256"])
        self.executables = {name: value["path"] for name, value in self.bindings["executables"].items()}
        self.configuration = json.loads(private_bytes(self.root / "configuration/installation.json"), object_pairs_hook=unique_object)
        require(set(self.configuration["forge"]) <= FORGE_KEYS and set(self.configuration["web"]) == WEB_KEYS)
        self.reobserve()

    def _owned(self, stages):
        require(self.journal.lock is not None and self.journal.usable)
        require(self.journal.record["owner"] == owner() and self.journal.record["status"] == "running" and self.journal.record["stage"] in stages)
        driver = cgroup_identity(self.bindings["installation"], "driver")
        require(driver == self.bindings["cgroups"]["driver"])
        require(Path("/proc/self/cgroup").read_text().splitlines() == ["0::" + driver["kernel_path"]])

    def reobserve(self):
        return require_native_inventory(self.root, self.executables, self.inventory["bindings_sha256"])

    def stop_group(self, name):
        self._owned({"maintenance", "migrate", "verify", "activate", "public_verify", "recover"})
        require(name in {"native", "web", "edge", "maintenance"})
        # Quiescence must remain possible when the database is unavailable. Exact
        # delegated kernel resource identity, rather than a new database query,
        # governs this narrowly scoped whole-group stop.
        observed = cgroup_identity(self.bindings["installation"], name)
        require(observed == self.bindings["cgroups"][name])
        path = Path(observed["path"])
        (path / "cgroup.kill").write_text("1")
        deadline = time.monotonic() + 15
        while dict(line.split() for line in (path / "cgroup.events").read_text().splitlines()).get("populated") != "0":
            require(time.monotonic() < deadline)
            time.sleep(.05)
        require(not (path / "cgroup.procs").read_text().strip())
        return {"group_empty": True, "group_identity_sha256": hashlib.sha256(canonical(observed)).hexdigest()}

    def _environment(self, component):
        values = self.configuration[component]
        environment = {"PATH": "/usr/bin:/bin", "HOME": str(self.root), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
        environment.update(values)
        if component == "forge":
            environment.update({"GITGOOD_GIT": self.executables["git"], "GITGOOD_PYTHON": self.executables["python"], "PHX_SERVER": "true"})
        return environment

    def _stage(self, directory, previous=False):
        prefix = "old" if previous else "new"
        return verify_runtime_stage(directory, self.journal.intent[prefix + "_candidate"], self.journal.intent[prefix + "_artifact_sha256"])

    def _launch(self, name, stage, arguments, environment, cwd):
        self.reobserve()
        require(name in {"native", "web", "maintenance"})
        group = self.bindings["cgroups"][name]
        require(cgroup_identity(self.bindings["installation"], name) == group)
        require(dict(line.split() for line in (Path(group["path"]) / "cgroup.events").read_text().splitlines()).get("populated") == "0")
        log = self.journal.directory / (name + "-" + str(len(self.journal.record["events"])) + ".log")
        descriptor = self.journal._private_open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        with os.fdopen(descriptor, "wb") as output:
            return subprocess.Popen([self.executables["python"], "-I", str(stage["wrapper"]), group["path"], *arguments],
                                    cwd=cwd, env=environment, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT)

    def migrate(self, directory):
        self._owned({"migrate"})
        stage = self._stage(directory)
        environment = self._environment("forge")
        environment["PHX_SERVER"] = "false"
        process = self._launch("maintenance", stage, [str(stage["code"] / "forge/bin/gitgood"), "eval", "Gitgood.Release.migrate()"], environment, stage["code"] / "forge")
        try:
            code = process.wait(timeout=300)
        finally:
            self.stop_group("maintenance")
            process.wait(timeout=15)
        require(code == 0)
        return {"migration_command_completed": True, "inventory_sha256": stage["inventory_sha256"]}

    def start_native(self, directory, *, previous=False):
        self._owned({"recover"} if previous else {"verify", "recover"})
        stage = self._stage(directory, previous)
        return self._launch("native", stage, [str(stage["code"] / "forge/bin/gitgood"), "start"], self._environment("forge"), stage["code"] / "forge")

    def start_web(self, directory, *, previous=False):
        self._owned({"recover"} if previous else {"verify", "recover"})
        stage = self._stage(directory, previous)
        return self._launch("web", stage, [self.executables["node"], str(stage["code"] / "web/node_modules/srvx/bin/srvx.mjs"),
                                          "--prod", "-s", "dist/client", "server.mjs"], self._environment("web"), stage["code"] / "web")
