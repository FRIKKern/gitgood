"""Fail closed when an owned runtime/maintenance process can still exist. No process arguments are read."""
import ctypes
import json
import os
import socket
import stat
import sys
from pathlib import Path


def alive(pid):
    if os.name == "nt":
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        api.OpenProcess.restype = ctypes.c_void_p
        api.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        api.WaitForSingleObject.restype = ctypes.c_ulong
        api.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = api.OpenProcess(0x00100000, 0, pid)
        if not handle:
            return ctypes.get_last_error() != 87
        try:
            return api.WaitForSingleObject(handle, 0) != 0
        finally:
            api.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


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
    if any(alive(pid) for pid in owners):
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
