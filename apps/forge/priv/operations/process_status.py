"""Fail closed when an owned runtime/maintenance process can still exist. No process arguments are read."""
import ctypes
import json
import os
import socket
import stat
import sys
from pathlib import Path


sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from process_birth import birth


def alive(pid, expected=None):
    actual = birth(pid)
    return actual is not None and (expected is None or actual == expected)


def empty_cgroup(data):
    relative = data.get("cgroup")
    if sys.platform != "linux" or not isinstance(relative, str) or not relative.startswith("/") or relative == "/":
        return False
    root = Path("/sys/fs/cgroup")
    path = root / relative[1:]
    if path.resolve() != path or not path.is_relative_to(root):
        return False
    events = dict(line.split() for line in (path / "cgroup.events").read_text().splitlines())
    return events.get("populated") == "0" and not (path / "cgroup.procs").read_text().strip()


def status(path, require_cgroup=False):
    file = Path(path)
    info = file.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > 4096:
        return "invalid"
    data = json.loads(file.read_bytes())
    if data.get("protocol") != 1 or data.get("host", "").casefold() != socket.gethostname().casefold():
        return "invalid"
    owners = data.get("owners")
    if not isinstance(owners, list) or not 1 <= len(owners) <= 8:
        return "invalid"
    if any(type(pid) is not int or not 1 <= pid <= 2147483647 for pid in owners):
        return "invalid"
    identities = data.get("owner_births")
    if identities is not None:
        if not isinstance(identities, dict) or set(identities) != {str(pid) for pid in owners}:
            return "invalid"
        if any(not isinstance(value, str) or not value.isdecimal() or value.startswith("0") or len(value) > 20
               for value in identities.values()):
            return "invalid"
    if any(alive(pid, identities.get(str(pid)) if identities is not None else None) for pid in owners):
        return "busy"
    if require_cgroup and not empty_cgroup(data):
        return "invalid"
    return "clear"


if __name__ == "__main__":
    try:
        result = status(sys.argv[1], len(sys.argv) == 3 and sys.argv[2] == "require-empty-cgroup")
    except Exception:
        result = "invalid"
    print(result)
    sys.exit(0 if result == "clear" else 1)
