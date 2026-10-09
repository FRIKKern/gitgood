"""Identify one OS process instance by numeric PID and kernel creation identity. No arguments are read."""
import ctypes
import os
import sys
from pathlib import Path


def birth(pid):
    if type(pid) is not int or not 1 <= pid <= 2147483647:
        raise ValueError("invalid process")
    if os.name == "nt":
        from ctypes import wintypes
        class FileTime(ctypes.Structure):
            _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenProcess.restype = wintypes.HANDLE
        api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        api.WaitForSingleObject.restype = wintypes.DWORD
        api.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(FileTime)] * 4
        api.GetProcessTimes.restype = wintypes.BOOL
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = api.OpenProcess(0x00100000 | 0x1000, False, pid)
        if not handle:
            if ctypes.get_last_error() == 87:
                return None
            raise PermissionError("process identity unavailable")
        try:
            wait = api.WaitForSingleObject(handle, 0)
            if wait == 0:
                return None
            if wait != 258:
                raise PermissionError("process identity unavailable")
            values = [FileTime() for _ in range(4)]
            if not api.GetProcessTimes(handle, *(ctypes.byref(value) for value in values)):
                raise PermissionError("process identity unavailable")
            return str((values[0].high << 32) | values[0].low)
        finally:
            api.CloseHandle(handle)
    if sys.platform != "linux":
        raise ValueError("unsupported process identity")
    try:
        value = Path("/proc", str(pid), "stat").read_text()
    except FileNotFoundError:
        return None
    fields = value[value.rfind(")") + 2:].split()
    if fields[0] in ("Z", "X"):
        return None
    return fields[19]


if __name__ == "__main__":
    try:
        value = birth(int(sys.argv[1]))
        if value is None:
            raise ValueError("process absent")
        print(value)
    except Exception:
        print("unavailable")
        sys.exit(1)
