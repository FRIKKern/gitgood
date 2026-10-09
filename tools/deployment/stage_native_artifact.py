"""Copy, inspect and stage one native archive in an owned private code directory."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tarfile
import uuid

from inspect_native_artifact import inspect_native_artifact
from upgrade_journal import UpgradeRefused, canonical, require


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_directory(source, destination):
    # Atomic publication must not replace even an empty pre-existing directory.
    rename = ctypes.CDLL(None, use_errno=True).renameat2
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1) != 0:
        error = ctypes.get_errno()
        raise OSError(error, "Native staging publication refused")


def stage_native_artifact(archive_path, digest, candidate, directory, operation):
    require(sys.platform == "linux")
    directory = Path(directory)
    require(directory.is_absolute() and directory.resolve() == directory)
    info = directory.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o077)
    require(isinstance(operation, str) and str(uuid.UUID(operation)) == operation)
    # Validate supplied identities before using them in paths or changing custody.
    require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest))
    require(isinstance(candidate, str) and re.fullmatch(r"[0-9a-f]{40}", candidate))
    target = directory / ("native-" + operation)
    partial = directory / (".native-" + operation + ".partial")
    require(not target.exists() and not target.is_symlink())
    partial.mkdir(mode=0o700)  # Exact request namespace; concurrent attempts cannot share it.
    sync_directory(directory)
    snapshot = partial / "archive.tar.gz"
    descriptor = os.open(archive_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(descriptor, "rb") as source:
        before = os.fstat(source.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 < before.st_size <= 1_073_741_824)
        output = os.open(snapshot, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        observed, total = hashlib.sha256(), 0
        with os.fdopen(output, "wb") as destination:
            while data := source.read(1_048_576):
                total += len(data)
                require(total <= before.st_size)
                observed.update(data)
                destination.write(data)
            destination.flush()
            os.fsync(destination.fileno())
        after = os.fstat(source.fileno())
        require(total == before.st_size and observed.hexdigest() == digest)
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns))
    inspected = inspect_native_artifact(snapshot, digest, candidate)
    code = partial / "code"
    code.mkdir(mode=0o700)
    inventory = []
    with tarfile.open(snapshot, "r:gz") as archive:
        members = archive.getmembers()
        # The inspector has already refused child paths beneath non-directories.
        # Directories first, then regular files, then internal symlinks.
        for member in sorted((m for m in members if m.isdir()), key=lambda m: m.name.count("/")):
            (code / member.name.rstrip("/")).mkdir(mode=0o700)
        for member in members:
            if not member.isfile():
                continue
            path = code / member.name
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o700 if member.mode & 0o111 else 0o600)
            hashed, size = hashlib.sha256(), 0
            with os.fdopen(descriptor, "wb") as destination, archive.extractfile(member) as source:
                while data := source.read(1_048_576):
                    size += len(data)
                    require(size <= member.size)
                    hashed.update(data)
                    destination.write(data)
                require(size == member.size)
                destination.flush()
                os.fsync(destination.fileno())
            inventory.append({"path": member.name, "bytes": size, "sha256": hashed.hexdigest(),
                              "executable": bool(member.mode & 0o111)})
        for member in members:
            if member.issym():
                os.symlink(member.linkname, code / member.name)
                inventory.append({"path": member.name, "symlink": member.linkname})
    inventory.sort(key=lambda value: value["path"])
    receipt = {"protocol": 1, "status": "staged", "operation": operation, "candidate": candidate,
               "artifact_sha256": digest, "artifact_bytes": total,
               "inventory_sha256": hashlib.sha256(canonical(inventory)).hexdigest(),
               "files": sum("sha256" in value for value in inventory),
               "symlinks": sum("symlink" in value for value in inventory),
               "migrations": inspected["migrations"],
               "limitations": ["Staging executes no candidate code and does not establish readiness or activation."]}
    for name, value in [("inventory.json", inventory), ("receipt.json", receipt)]:
        descriptor = os.open(partial / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(canonical(value) + b"\n")
            output.flush()
            os.fsync(output.fileno())
    for path in sorted((p for p in code.rglob("*") if p.is_dir() and not p.is_symlink()),
                       key=lambda p: len(p.parts), reverse=True):
        sync_directory(path)
    sync_directory(code)
    sync_directory(partial)
    publish_directory(partial, target)
    sync_directory(directory)
    return receipt


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    for argument in ["archive", "sha256", "candidate", "directory", "operation"]:
        parser.add_argument(argument)
    args = parser.parse_args()
    try:
        print(json.dumps(stage_native_artifact(args.archive, args.sha256, args.candidate,
                                              args.directory, args.operation)))
    except Exception:
        print(json.dumps({"status": "refused", "error": "Native staging failed; retain partial custody for reconciliation"}))
        raise SystemExit(1)
