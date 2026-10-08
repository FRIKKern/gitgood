"""Atomically move a verified regular file without replacing a destination."""
import ctypes
import os
import stat
import sys
from pathlib import Path


def publish(source, target):
    source = Path(source)
    target = Path(target)
    information = source.lstat()
    if sys.platform != "linux" or not stat.S_ISREG(information.st_mode) or information.st_nlink != 1:
        raise ValueError("invalid source")
    if source.parent.resolve() != source.parent or target.parent.resolve() != target.parent:
        raise ValueError("invalid parent")
    if source.parent.stat().st_dev != target.parent.stat().st_dev:
        raise ValueError("cross-device publication")
    api = ctypes.CDLL(None, use_errno=True)
    api.renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    api.renameat2.restype = ctypes.c_int
    if api.renameat2(-100, os.fsencode(source), -100, os.fsencode(target), 1) != 0:
        raise OSError(ctypes.get_errno())
    for parent in {source.parent, target.parent}:
        directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


if __name__ == "__main__":
    try:
        publish(sys.argv[1], sys.argv[2])
    except Exception:
        print("refused")
        sys.exit(1)
    print("published")
