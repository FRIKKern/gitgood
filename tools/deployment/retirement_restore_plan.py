"""Closed full-restoration inputs; parsing never grants functional success."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import uuid

from upgrade_journal import canonical, require

GROUPS = {"native", "web", "edge", "maintenance"}
ROOT_KEYS = {"path", "device", "inode", "uid"}
FILE_KEYS = {"path", "device", "inode", "uid", "mode", "bytes", "sha256"}
TARGET_KEYS = {"address", "cluster", "database", "database_oid", "encoding", "owner_oid", "port", "role_oid", "version"}
MATERIALIZATION_KEYS = {"protocol", "operation", "installation", "candidate", "ciphertext_sha256", "source", "key_path",
                        "scratch_directory", "target_database", "target_installation", "target_root", "ports"}


def _uuid(value):
    require(isinstance(value, str))
    try:
        require(str(uuid.UUID(value)) == value)
    except ValueError:
        require(False)


def _digest(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value))


def _path(value):
    require(isinstance(value, str) and 0 < len(value) <= 4096 and "\0" not in value)
    require(Path(value).is_absolute() and str(Path(value)) == value and ".." not in Path(value).parts)


def _root(value):
    require(isinstance(value, dict) and set(value) == ROOT_KEYS)
    _path(value["path"])
    for key in ["device", "inode", "uid"]:
        require(type(value[key]) is int and 0 <= value[key] < 2**53)
    require(value["uid"] == os.getuid())


def target_group_path(installation, operation, target_installation, name):
    for value in [installation, operation, target_installation]:
        _uuid(value)
    require(installation != target_installation and name in GROUPS)
    return Path("/sys/fs/cgroup") / ("gitgood-installation-" + installation) / ("retirement-" + operation) / target_installation / name


def observe_target_group(installation, operation, target_installation, name):
    """Observe only the operation's subtree inside the original delegation."""
    require(sys.platform == "linux")
    path = target_group_path(installation, operation, target_installation, name)
    mount = Path("/sys/fs/cgroup")
    require(any(" - cgroup2 " in line and line.split()[4] == str(mount)
                for line in Path("/proc/self/mountinfo").read_text().splitlines()))
    device = mount.stat().st_dev
    for directory in [path, path.parent, path.parent.parent, path.parent.parent.parent]:
        require(directory.resolve() == directory)
        info = directory.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid in {0, os.getuid()} and info.st_dev == device)
        control = (directory / "cgroup.procs").lstat()
        require(stat.S_ISREG(control.st_mode) and control.st_uid == os.getuid())
    kill = (path / "cgroup.kill").lstat()
    require(stat.S_ISREG(kill.st_mode) and kill.st_uid == os.getuid())
    require("populated" in (path / "cgroup.events").read_text())
    info = path.lstat()
    return {"path": str(path), "kernel_path": "/" + path.relative_to(mount).as_posix(),
            "device": info.st_dev, "inode": info.st_ino, "delegated_uid": os.getuid()}


def validate_full_restore_plan(journal, value):
    require(sys.platform == "linux")
    require(isinstance(value, dict) and set(value) == {"protocol", "purpose", "operation", "installation", "data_plan",
            "materialization", "target_groups", "probe_directory", "probe_sha256", "outsider_token"})
    require(type(value["protocol"]) is int and value["protocol"] == 2 and value["purpose"] == "retirement_functional_restore_plan")
    require(value["operation"] == journal.operation and value["installation"] == journal.plan["installation"])
    require(hashlib.sha256(canonical(value)).hexdigest() == journal.plan["restore_sha256"])
    data = value["data_plan"]
    require(isinstance(data, dict) and set(data) == {"protocol", "purpose", "operation", "installation", "target_database"})
    require(type(data["protocol"]) is int and data["protocol"] == 1 and data["purpose"] == "retirement_restore_data_plan")
    require(data["operation"] == journal.operation and data["installation"] == journal.plan["installation"])
    database = data["target_database"]
    require(isinstance(database, dict) and set(database) == TARGET_KEYS)
    require(database["database"] == "gitgood_retirement_restore_" + journal.operation.replace("-", ""))
    require(isinstance(database["cluster"], str) and re.fullmatch(r"[0-9]+", database["cluster"]))
    require(database["version"] == "18.4" and database["encoding"] == "UTF8" and database["address"] == "127.0.0.1")
    for name in ["database_oid", "owner_oid", "role_oid", "port"]:
        require(type(database[name]) is int and 0 < database[name] < 2**53)
    require(database["owner_oid"] == database["role_oid"] and 1024 <= database["port"] <= 65535)
    materialization = value["materialization"]
    require(isinstance(materialization, dict) and set(materialization) == MATERIALIZATION_KEYS)
    require(type(materialization["protocol"]) is int and materialization["protocol"] == 1)
    for key in ["operation", "installation", "candidate"]:
        require(materialization[key] == journal.plan[key])
    require(materialization["ciphertext_sha256"] == journal.plan["archive_sha256"])
    require(materialization["target_database"] == data["target_database"])
    installation = materialization["target_installation"]
    _uuid(installation)
    require(installation != journal.plan["installation"])
    _root(materialization["target_root"])
    require(Path(materialization["target_root"]["path"]).name == "gitgood_retirement_restore_" + journal.operation.replace("-", ""))
    for key in ["source", "key_path", "scratch_directory"]:
        _path(materialization[key])
    ports = materialization["ports"]
    require(isinstance(ports, dict) and set(ports) == {"forge", "web", "native_ssh", "https", "ssh"})
    require(all(type(port) is int and 1024 <= port <= 65535 for port in ports.values()) and len(set(ports.values())) == 5)
    groups = value["target_groups"]
    require(isinstance(groups, dict) and set(groups) == GROUPS)
    for name, group in groups.items():
        require(isinstance(group, dict) and set(group) == {"path", "kernel_path", "device", "inode", "delegated_uid"})
        expected = str(target_group_path(journal.plan["installation"], journal.operation, installation, name))
        require(group["path"] == expected and group["kernel_path"] == expected[len("/sys/fs/cgroup"):])
        require(type(group["delegated_uid"]) is int and group["delegated_uid"] == os.getuid())
        for key in ["device", "inode"]:
            require(type(group[key]) is int and 0 < group[key] < 2**63)
    _root(value["probe_directory"])
    _digest(value["probe_sha256"])
    token = value["outsider_token"]
    require(isinstance(token, dict) and set(token) == FILE_KEYS)
    _path(token["path"])
    for key in ["device", "inode", "uid", "mode", "bytes"]:
        require(type(token[key]) is int and 0 <= token[key] < 2**53)
    require(token["uid"] == os.getuid() and token["mode"] == 0o600 and 32 <= token["bytes"] <= 128)
    _digest(token["sha256"])
    target = Path(materialization["target_root"]["path"])
    for path in [value["probe_directory"]["path"], token["path"], materialization["source"], materialization["key_path"]]:
        require(not Path(path).is_relative_to(target) and not target.is_relative_to(Path(path)))
    return json.loads(canonical(value))
