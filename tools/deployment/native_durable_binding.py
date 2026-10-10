"""Read-only protocol-2 persistent identity; no generation is published here."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid

from native_actions import FORGE_KEYS, WEB_KEYS
from native_durable_database import DatabaseRefused, observe_durable_database
from native_service_scope import ServiceRefused, observe_service, root_file
from resource_generations import GenerationRefused, canonical, identifier, validate_scope


class BindingRefused(Exception):
    pass


def require(value):
    if not value:
        raise BindingRefused("Native durable installation identity unavailable or changed")


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def directory(path, uid):
    path = Path(path)
    require(path.is_absolute() and path.resolve(strict=True) == path)
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == uid and stat.S_IMODE(info.st_mode) == 0o700)
    return {"path": str(path), "device": info.st_dev, "inode": info.st_ino, "uid": uid}


def private_file(path, uid, maximum=131072):
    path = Path(path)
    require(path.is_absolute() and path.resolve(strict=True) == path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        before = os.fstat(source.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == uid and before.st_nlink == 1)
        require(stat.S_IMODE(before.st_mode) == 0o600 and 0 < before.st_size <= maximum)
        raw = source.read(maximum + 1)
        after = os.fstat(source.fileno())
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_uid", "st_mode", "st_nlink")
    require(len(raw) == before.st_size and all(getattr(before, field) == getattr(after, field) for field in fields))
    return {"path": str(path), "device": before.st_dev, "inode": before.st_ino, "uid": uid,
            "bytes": before.st_size, "sha256": hashlib.sha256(raw).hexdigest()}, raw


def configuration(root, installation, uid):
    root = Path(root)
    record, raw = private_file(root / "configuration/installation.json", uid)
    value = json.loads(raw, object_pairs_hook=unique)
    require(type(value) is dict and set(value) == {"protocol", "installation", "forge", "web", "edge"})
    # Retain the established configuration format; no legacy journal conversion.
    require(type(value["protocol"]) is int and value["protocol"] == 1 and value["installation"] == installation)
    forge, web, edge = value["forge"], value["web"], value["edge"]
    require(type(forge) is dict and set(forge) <= FORGE_KEYS and type(web) is dict and set(web) == WEB_KEYS)
    require(all(type(item) is str and 0 < len(item) <= 8192 and "\0" not in item for env in [forge, web] for item in env.values()))
    require(forge.get("GITGOOD_INSTALLATION_ID") == installation)
    require(forge.get("GITGOOD_STORAGE") == str(root / "storage"))
    require(forge.get("GITGOOD_SSH_HOST_KEY_DIRECTORY") == str(root / "ssh-host"))
    require(web.get("NODE_ENV") == "production" and web.get("GITGOOD_PROXY_KEY") == forge.get("GITGOOD_PROXY_KEY"))
    expected = {"tls_certificate": "tls-certificate.pem", "tls_key": "tls-key.pem"}
    if "GITGOOD_BARKPARK_CA" in forge:
        expected["source_ca"] = "source-ca.pem"
        require(forge["GITGOOD_BARKPARK_CA"] == str(root / "configuration/source-ca.pem"))
    require(type(edge) is dict and edge == expected)
    files = {"installation.json": record}
    for name in edge.values():
        files[name] = private_file(root / "configuration" / name, uid)[0]
    require({item.name for item in (root / "configuration").iterdir()} == set(files))
    return files, forge.get("DATABASE_URL")


def executable(path):
    """Hash a bounded root-controlled binary without loading it into memory."""
    require(type(path) is str and Path(path).is_absolute())
    path = Path(path).resolve(strict=True)
    for parent in path.parents:
        info = parent.lstat()
        require(parent.resolve(strict=True) == parent and stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        before = os.fstat(source.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1)
        require(before.st_mode & 0o111 and not before.st_mode & 0o022 and 0 < before.st_size <= 268435456)
        digest = hashlib.file_digest(source, "sha256").hexdigest()
        after = os.fstat(source.fileno())
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_uid", "st_mode", "st_nlink")
    require(all(getattr(before, field) == getattr(after, field) for field in fields))
    return {"path": str(path), "device": before.st_dev, "inode": before.st_ino,
            "bytes": before.st_size, "sha256": digest}


def persistent_identity(root, scope, executables):
    """Observe allocated persistent resources; service admission is separate."""
    validate_scope(scope)
    uid = scope["uid"]
    require(os.getuid() == os.geteuid() == uid and os.getgid() == os.getegid() == scope["gid"])
    root = Path(root)
    require(root == Path("/var/lib/gitgood/installations") / scope["installation"])
    for parent in root.parents:
        info = parent.lstat()
        require(parent.resolve(strict=True) == parent and stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022)
    resources = {"root": directory(root, uid)}
    for name in ["configuration", "storage", "ssh-host", "history", "staging"]:
        resources[name] = directory(root / name, uid)
    require({item.name for item in root.iterdir()} == set(resources) - {"root"})
    require(len({(item["device"], item["inode"]) for item in resources.values()}) == 6)
    _, machine = root_file("/etc/machine-id", 64)
    require(re.fullmatch(b"[0-9a-f]{32}\n?", machine) and machine.strip() != b"0" * 32)
    release, _ = root_file(Path("/etc/os-release").resolve(strict=True), 4096)
    files, database_url = configuration(root, scope["installation"], uid)
    keys = {name: private_file(root / "ssh-host" / name, uid)[0] for name in ["ssh_host_ed25519_key", "ssh_host_ed25519_key.pub"]}
    require({item.name for item in (root / "ssh-host").iterdir()} == set(keys))
    require(type(executables) is dict and set(executables) == {"python", "node", "git", "psql", "caddy"})
    binaries = {}
    for name, path in executables.items():
        binaries[name] = executable(path)
    require(len({(item["device"], item["inode"]) for item in binaries.values()}) == 5)
    database = observe_durable_database(binaries["psql"]["path"], database_url)
    return {"protocol": 2, "kind": "durable_installation_binding", "installation": scope["installation"],
            "host": {"machine_id": machine.decode("ascii").strip(), "profile": "ubuntu-24.04-linux-x86_64", "os_release": release},
            "account": {"name": "gg_" + base64.b32encode(uuid.UUID(scope["installation"]).bytes).decode("ascii").lower().rstrip("="), "uid": uid, "gid": scope["gid"]}, "resources": resources,
            "configuration": files, "ssh_host_keys": keys, "executables": binaries, "database": database}


def observe_durable_binding(root, installation, unit_sha256, executables, *, cpu_quota_us, memory_bytes):
    """Bracket two persistent observations with exact actual service admission.

    Observations remain transient; callers must separately establish custody,
    installation locking, database writer exclusion and stage reconciliation.
    """
    try:
        identifier(installation)
        require(type(root) is str and root == "/var/lib/gitgood/installations/" + installation)
        require(type(executables) is dict and set(executables) == {"python", "node", "git", "psql", "caddy"})
        require(all(type(path) is str and 0 < len(path) <= 4096 and path.startswith("/") and "\0" not in path for path in executables.values()))
        options = {"cpu_quota_us": cpu_quota_us, "memory_bytes": memory_bytes}
        before = observe_service(installation, unit_sha256, **options)
        binding = persistent_identity(root, before, executables)
        require(persistent_identity(root, before, executables) == binding)
        require(observe_service(installation, unit_sha256, **options) == before)
        return {"binding": binding, "binding_sha256": hashlib.sha256(canonical(binding)).hexdigest(),
                "scope": before, "installation_readiness_established": False,
                "generation_publication_established": False}
    except BindingRefused:
        raise
    except (ServiceRefused, DatabaseRefused, GenerationRefused, OSError, ValueError, UnicodeError, RecursionError):
        raise BindingRefused("Native durable installation identity unavailable or changed") from None
