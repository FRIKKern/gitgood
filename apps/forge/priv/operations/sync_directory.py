"""Durably record the final removal of the incomplete restore gate."""
import os
import sys
from pathlib import Path


if __name__ == "__main__":
    try:
        directory = Path(sys.argv[1])
        if sys.platform != "linux" or directory.resolve() != directory:
            raise ValueError("invalid directory")
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except Exception:
        print("refused")
        sys.exit(1)
    print("synced")
