"""Publish an owned verified directory without replacing an existing destination."""
import ctypes
import os
import sys
from pathlib import Path


def publish(source, target):
    source = Path(source)
    target = Path(target)
    if source.parent.resolve() != target.parent.resolve() or source.is_symlink() or not source.is_dir():
        raise ValueError("invalid publication")
    if os.name == "nt":
        os.rename(source, target)
    elif sys.platform == "linux":
        api = ctypes.CDLL(None, use_errno=True)
        api.renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        api.renameat2.restype = ctypes.c_int
        if api.renameat2(-100, os.fsencode(source), -100, os.fsencode(target), 1) != 0:
            raise OSError(ctypes.get_errno())
        directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    else:
        raise ValueError("unsupported publication platform")


if __name__ == "__main__":
    try:
        publish(sys.argv[1], sys.argv[2])
    except Exception:
        print("refused")
        sys.exit(1)
    print("published")
