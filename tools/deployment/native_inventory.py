"""Observe exact owned resources for the initial single-host native operator profile."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import socket
import stat
import subprocess
import sys
from urllib.parse import unquote, urlsplit
import uuid

from upgrade_journal import canonical, require, unique_object

EXECUTABLES = {"python", "node", "git", "psql", "caddy"}
SQL = """SELECT json_build_object(
 'cluster', (SELECT system_identifier::text FROM pg_control_system()),
 'database', d.datname, 'database_oid', d.oid::bigint, 'owner_oid', d.datdba::bigint,
 'role_oid', r.oid::bigint, 'encoding', pg_encoding_to_char(d.encoding),
 'version', current_setting('server_version'),
 'address', host(inet_server_addr()), 'port', inet_server_port())
 FROM pg_database d JOIN pg_roles r ON r.rolname=current_user
 WHERE d.datname=current_database() AND d.datdba=r.oid"""


def directory_identity(path, *, private=False):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path)
    value = path.lstat()
    require(stat.S_ISDIR(value.st_mode) and value.st_uid == os.getuid())
    require(not value.st_mode & (0o077 if private else 0o022))
    return {"path": str(path), "device": value.st_dev, "inode": value.st_ino, "uid": value.st_uid}


def private_bytes(path, maximum=131_072):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(descriptor, "rb") as source:
        value = os.fstat(source.fileno())
        require(stat.S_ISREG(value.st_mode) and value.st_uid == os.getuid() and value.st_nlink == 1)
        require(not value.st_mode & 0o077 and 0 < value.st_size <= maximum)
        data = source.read(maximum + 1)
        after = os.fstat(source.fileno())
    require(len(data) == value.st_size and (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns))
    return data


def executable_identity(path):
    # Resolve trusted installed-runtime aliases once; retain the actual file identity.
    path = Path(path)
    require(path.is_absolute())
    path = path.resolve(strict=True)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(descriptor, "rb") as source:
        value = os.fstat(source.fileno())
        require(stat.S_ISREG(value.st_mode) and value.st_uid in {0, os.getuid()})
        require(value.st_mode & 0o111 and not value.st_mode & 0o022 and 0 < value.st_size <= 268_435_456)
        digest = hashlib.file_digest(source, "sha256").hexdigest()
        after = os.fstat(source.fileno())
    require((value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns))
    return {"path": str(path), "device": value.st_dev, "inode": value.st_ino, "uid": value.st_uid,
            "bytes": value.st_size, "sha256": digest}


def database_environment(value):
    require(isinstance(value, str) and len(value) <= 8192 and "\0" not in value)
    url = urlsplit(value)
    require(url.scheme in {"postgres", "postgresql"} and url.hostname in {"127.0.0.1", "localhost"})
    require(not url.query and not url.fragment and url.port is not None and 1 <= url.port <= 65535)
    database, actor = unquote(url.path.removeprefix("/")), unquote(url.username or "")
    require(re.fullmatch(r"[a-z][a-z0-9_]{0,62}", database) and re.fullmatch(r"[a-z][a-z0-9_]{0,62}", actor))
    password = unquote(url.password or "")
    require("\0" not in password and len(password) <= 8192)
    return {"PGHOST": "127.0.0.1", "PGPORT": str(url.port), "PGDATABASE": database, "PGUSER": actor,
            "PGPASSWORD": password, "PGCONNECT_TIMEOUT": "5", "PGAPPNAME": "gitgood native resource observation",
            "PGOPTIONS": "-c statement_timeout=5000 -c default_transaction_read_only=on -c search_path=pg_catalog",
            "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}


def observe_database(psql, database_url):
    environment = database_environment(database_url)
    result = subprocess.run([psql, "--no-psqlrc", "--tuples-only", "--no-align", "--set=ON_ERROR_STOP=1", "--command", SQL],
                            env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, timeout=10)
    require(result.returncode == 0 and 0 < len(result.stdout) <= 8192)
    value = json.loads(result.stdout, object_pairs_hook=unique_object)
    require(isinstance(value, dict) and set(value) == {"cluster", "database", "database_oid", "owner_oid", "role_oid", "encoding", "version", "address", "port"})
    require(isinstance(value["cluster"], str) and re.fullmatch(r"[0-9]{1,20}", value["cluster"]))
    require(value["database"] == environment["PGDATABASE"] and value["version"] == "18.4")
    require(value["address"] == "127.0.0.1" and value["port"] == int(environment["PGPORT"]) and value["encoding"] == "UTF8")
    require(all(type(value[field]) is int and 0 < value[field] < 2**32 for field in ["database_oid", "owner_oid", "role_oid"]))
    require(value["owner_oid"] == value["role_oid"])
    return value


def cgroup_identity(installation, name):
    path = Path("/sys/fs/cgroup") / ("gitgood-installation-" + installation) / name
    require(path.resolve() == path)
    value = path.lstat()
    require(stat.S_ISDIR(value.st_mode) and value.st_uid in {0, os.getuid()} and value.st_dev == Path("/sys/fs/cgroup").stat().st_dev)
    for control in ["cgroup.procs", "cgroup.kill"]:
        info = (path / control).lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid())
    require((path.parent / "cgroup.procs").lstat().st_uid == os.getuid())
    require("populated" in (path / "cgroup.events").read_text())
    require(any(" - cgroup2 " in line and line.split()[4] == "/sys/fs/cgroup" for line in Path("/proc/self/mountinfo").read_text().splitlines()))
    return {"path": str(path), "kernel_path": "/" + path.relative_to("/sys/fs/cgroup").as_posix(),
            "device": value.st_dev, "inode": value.st_ino, "delegated_uid": os.getuid()}


def capture_native_inventory(root, executables):
    require(sys.platform == "linux" and platform.machine() == "x86_64")
    root = Path(root)
    resources = {"root": directory_identity(root, private=True)}
    configuration = root / "configuration"
    resources["configuration"] = directory_identity(configuration, private=True)
    configuration_bytes = private_bytes(configuration / "installation.json")
    config = json.loads(configuration_bytes, object_pairs_hook=unique_object)
    require(isinstance(config, dict) and set(config) == {"protocol", "installation", "forge", "web", "edge"})
    require(type(config["protocol"]) is int and config["protocol"] == 1)
    installation = config["installation"]
    require(isinstance(installation, str) and str(uuid.UUID(installation)) == installation)
    forge, web, edge = config["forge"], config["web"], config["edge"]
    require(isinstance(forge, dict) and isinstance(web, dict) and isinstance(edge, dict))
    require(all(isinstance(value, str) and 0 < len(value) <= 8192 and "\0" not in value for env in [forge, web] for value in env.values()))
    require(forge.get("GITGOOD_STORAGE") == str(root / "storage") and forge.get("GITGOOD_SSH_HOST_KEY_DIRECTORY") == str(root / "ssh-host"))
    require(web.get("NODE_ENV") == "production" and web.get("GITGOOD_PROXY_KEY") == forge.get("GITGOOD_PROXY_KEY"))
    require(set(edge) == ({"tls_certificate", "tls_key", "source_ca"} if "GITGOOD_BARKPARK_CA" in forge else {"tls_certificate", "tls_key"}))
    expected = {"tls_certificate": "tls-certificate.pem", "tls_key": "tls-key.pem", "source_ca": "source-ca.pem"}
    require(all(value == expected[name] for name, value in edge.items()))
    if "GITGOOD_BARKPARK_CA" in forge:
        require(forge["GITGOOD_BARKPARK_CA"] == str(configuration / "source-ca.pem"))
    resources.update({name: directory_identity(root / name) for name in ["storage", "ssh-host"]})
    private_files = {name: hashlib.sha256(private_bytes(configuration / name)).hexdigest() for name in ["installation.json", *edge.values()]}
    require({path.name for path in configuration.iterdir()} == set(private_files))
    require({path.name for path in (root / "ssh-host").iterdir()} == {"ssh_host_ed25519_key", "ssh_host_ed25519_key.pub"})
    host_keys = {name: hashlib.sha256(private_bytes(root / "ssh-host" / name)).hexdigest()
                 for name in ["ssh_host_ed25519_key", "ssh_host_ed25519_key.pub"]}
    require(set(executables) == EXECUTABLES)
    binaries = {name: executable_identity(path) for name, path in executables.items()}
    groups = {name: cgroup_identity(installation, name) for name in ["native", "web", "edge", "maintenance", "driver"]}
    require(Path("/proc/self/cgroup").read_text().splitlines() == ["0::" + groups["driver"]["kernel_path"]])
    runtime = json.loads(private_bytes(root / "storage/.gitgood-runtime-v1.json", 8192), object_pairs_hook=unique_object)
    require(type(runtime.get("protocol")) is int and runtime["protocol"] == 1 and runtime.get("mode") == "runtime" and runtime.get("host") == socket.gethostname())
    require(runtime.get("cgroup") == groups["native"]["kernel_path"])
    require(isinstance(runtime.get("candidate"), str) and re.fullmatch(r"[0-9a-f]{40}", runtime["candidate"]))
    database = observe_database(binaries["psql"]["path"], forge.get("DATABASE_URL"))
    bindings = {"protocol": 1, "installation": installation, "host": socket.gethostname(), "uid": os.getuid(),
                "platform": "linux-x86_64", "resources": resources, "configuration_sha256": private_files,
                "ssh_host_key_sha256": host_keys, "executables": binaries, "cgroups": groups, "database": database}
    return {"protocol": 1, "installation": installation, "bindings": bindings,
            "bindings_sha256": hashlib.sha256(canonical(bindings)).hexdigest(),
            "observed_runtime_candidate": runtime["candidate"],
            "limitations": ["Observation does not establish artifact readiness, active routing or an installed upgrade.",
                            "Initial local PostgreSQL18.4 profile requires database ownership and permission to read pg_control_system().",
                            "These same-host resource bindings are distinct from replacement-host resource enrollment."]}


def require_native_inventory(root, executables, expected_digest):
    require(isinstance(expected_digest, str) and re.fullmatch(r"[0-9a-f]{64}", expected_digest))
    observed = capture_native_inventory(root, executables)
    require(observed["bindings_sha256"] == expected_digest)
    return observed


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    for name in sorted(EXECUTABLES):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--bindings-sha256")
    args = parser.parse_args()
    try:
        executables = {name: getattr(args, name) for name in EXECUTABLES}
        result = (require_native_inventory(args.root, executables, args.bindings_sha256) if args.bindings_sha256
                  else capture_native_inventory(args.root, executables))
        print(json.dumps(result))
    except Exception:
        print(json.dumps({"status": "refused", "error": "Native installation resource observation refused"}))
        raise SystemExit(1)
