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


def exclusive_startup(data, current_owner):
    """Permit only the new BEAM and its startup descendants in a reused group.

    A wrapper joins before exec. Its own processes cannot make the previous
    marker's group literally empty; unrelated survivors must still refuse.
    No command line, environment or private process payload is inspected.
    """
    if sys.platform != "linux" or type(current_owner) is not int or not 1 <= current_owner <= 2147483647:
        return False
    expected = birth(current_owner)
    if expected is None:
        return False
    owner_root = Path("/proc", str(current_owner))
    if owner_root.stat().st_uid != os.getuid():
        return False
    if empty_cgroup(data):
        return True
    relative = data["cgroup"]
    if (owner_root / "cgroup").read_text().splitlines() != ["0::" + relative]:
        return False
    root = Path("/sys/fs/cgroup") / relative[1:]

    def members():
        result = set()
        count = 0
        for directory, children, _ in os.walk(root, followlinks=False):
            count += 1
            if count > 256 or any((Path(directory) / name).is_symlink() for name in children):
                raise ValueError("invalid startup group")
            result.update(int(value) for value in (Path(directory) / "cgroup.procs").read_text().splitlines())
            if len(result) > 4096:
                raise ValueError("startup group oversized")
        return result

    observed = members()
    if current_owner not in observed:
        return False
    for pid in observed:
        seen = set()
        for _ in range(64):
            if pid == current_owner:
                break
            if pid in seen or pid <= 1:
                return False
            seen.add(pid)
            directory = Path("/proc", str(pid))
            if directory.stat().st_uid != os.getuid():
                return False
            value = (directory / "stat").read_text()
            fields = value[value.rfind(")") + 2:].split()
            pid = int(fields[1])
        else:
            return False
    # Refuse membership changes during observation instead of assuming a new PID
    # belongs to this startup. A caller can retry the admission observation.
    return birth(current_owner) == expected and members() == observed


def status(path, require_cgroup=False, current_owner=None):
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
    if current_owner is not None and not exclusive_startup(data, current_owner):
        return "invalid"
    return "clear"


if __name__ == "__main__":
    try:
        if len(sys.argv) == 4 and sys.argv[2] == "require-exclusive-startup":
            result = status(sys.argv[1], current_owner=int(sys.argv[3]))
        elif len(sys.argv) in [2, 3] and (len(sys.argv) == 2 or sys.argv[2] == "require-empty-cgroup"):
            result = status(sys.argv[1], len(sys.argv) == 3)
        else:
            raise ValueError("invalid process observation")
    except Exception:
        result = "invalid"
    print(result)
    sys.exit(0 if result == "clear" else 1)
