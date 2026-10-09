"""Join a pre-provisioned empty Linux cgroup before exec; never inspect process arguments."""
import os
import sys
from pathlib import Path


def group(path):
    root = Path("/sys/fs/cgroup")
    value = Path(path)
    if sys.platform != "linux" or value == root or value.resolve() != value or not value.is_relative_to(root):
        raise ValueError("invalid runtime group")
    events = dict(line.split() for line in (value / "cgroup.events").read_text().splitlines())
    if events.get("populated") != "0":
        raise ValueError("runtime group busy")
    return value


if __name__ == "__main__":
    try:
        target = group(sys.argv[1])
        (target / "cgroup.procs").write_text(str(os.getpid()))
        os.execve(sys.argv[2], sys.argv[2:], os.environ)
    except Exception:
        print("runtime group refused", file=sys.stderr)
        sys.exit(1)
