"""Read-only admission for the separately allocated protocol-2 systemd profile.

An observation is transient evidence, never permission to signal a later process
or reuse a cgroup path. No installation, journal or database is changed here.
"""
import base64
import hashlib
import os
from pathlib import Path
import platform
import pwd
import re
import selectors
import stat
import subprocess
import time
import uuid


class ServiceRefused(Exception):
    """The expected ordinary service boundary could not be established."""


def require(value):
    if not value:
        raise ServiceRefused("Native service scope unavailable or changed")


GROUPS = ("driver", "native", "web", "edge", "maintenance")
PROPERTIES = ("Id", "LoadState", "ActiveState", "SubState", "User", "Group",
              "MainPID", "ControlGroup", "Delegate", "DelegateSubgroup",
              "DelegateControllers", "FragmentPath", "DropInPaths", "KillMode", "Restart")


def read_bytes(path, maximum=16384):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as source:
        value = source.read(maximum + 1)
    require(len(value) <= maximum)
    return value


def root_file(path, maximum=16777216, *, executable=False):
    path = Path(path)
    require(path.is_absolute() and path.resolve(strict=True) == path)
    for parent in path.parents:
        value = parent.lstat()
        require(stat.S_ISDIR(value.st_mode) and value.st_uid == 0 and not value.st_mode & 0o022)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as source:
        before = os.fstat(source.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1)
        require(not before.st_mode & 0o022 and 0 < before.st_size <= maximum)
        require(not executable or before.st_mode & 0o111)
        raw = source.read(maximum + 1)
        after = os.fstat(source.fileno())
    require(len(raw) == before.st_size)
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_uid", "st_mode", "st_nlink")
    require(all(getattr(before, f) == getattr(after, f) for f in fields))
    return {"path": str(path), "device": before.st_dev, "inode": before.st_ino,
            "bytes": before.st_size, "sha256": hashlib.sha256(raw).hexdigest()}, raw


def bounded_command(arguments, timeout=5, maximum=16384):
    environment = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C", "LC_ALL": "C",
                   "SYSTEMD_COLORS": "0", "SYSTEMD_PAGER": "cat"}
    with subprocess.Popen(arguments, env=environment, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as child:
        output = bytearray()
        try:
            deadline = time.monotonic() + timeout
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    require(remaining > 0)
                    require(selector.select(remaining))
                    block = os.read(child.stdout.fileno(), min(4096, maximum + 1 - len(output)))
                    if not block:
                        break
                    output.extend(block)
                    require(len(output) <= maximum)
            require(child.wait(timeout=max(.01, deadline - time.monotonic())) == 0)
            return bytes(output)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()


def parse_properties(raw):
    require(isinstance(raw, bytes) and 0 < len(raw) <= 16384 and b"\0" not in raw)
    result = {}
    for line in raw.decode("ascii", errors="strict").splitlines():
        key, separator, value = line.partition("=")
        require(separator and key in PROPERTIES and key not in result)
        result[key] = value
    require(set(result) == set(PROPERTIES))
    return result


def process_security(status, gid):
    require(type(gid) is int and 0 < gid < 2**32)
    def field(name):
        values = [line.partition(":")[2].split() for line in status.splitlines() if line.startswith(name + ":")]
        require(len(values) == 1)
        return values[0]
    require(field("Gid") == [str(gid)] * 4)
    groups = field("Groups")
    require(len(groups) <= 64 and all(re.fullmatch(r"[0-9]{1,10}", group) for group in groups))
    require(set(int(group) for group in groups) <= {gid})
    capabilities = ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
    require(all(field(name) == ["0000000000000000"] for name in capabilities))
    require(field("NoNewPrivs") == ["1"])
    return {"gid": gid, "supplementary_groups": sorted(set(int(group) for group in groups)),
            "capabilities": {name: 0 for name in capabilities}, "no_new_privileges": True}


def process_identity(pid, uid, gid, group):
    require(type(pid) is int and 0 < pid < 2147483648)
    path = Path("/proc") / str(pid)
    raw = read_bytes(path / "stat").decode("ascii")
    parts = raw[raw.rfind(")") + 2:].split()
    require(len(parts) >= 20 and parts[0] not in {"Z", "X"} and path.stat().st_uid == uid)
    status = read_bytes(path / "status").decode("ascii")
    for field in ("Uid", "Gid"):
        values = [line.partition(":")[2].split() for line in status.splitlines() if line.startswith(field + ":")]
        require(len(values) == 1 and len(values[0]) == 4 and len(set(values[0])) == 1)
        if field == "Uid":
            require(values[0][0] == str(uid))
    require(read_bytes(path / "cgroup").decode("ascii").splitlines() == ["0::" + group])
    return {"pid": pid, "birth": parts[19], "uid": uid, "security": process_security(status, gid),
            "mount_namespace": os.readlink(path / "ns/mnt"),
            "cgroup_namespace": os.readlink(path / "ns/cgroup")}


def group_identity(path, uid):
    path = Path(path)
    require(path.resolve(strict=True) == path)
    value = path.lstat()
    require(stat.S_ISDIR(value.st_mode) and value.st_uid == uid and not value.st_mode & 0o022)
    return {"path": str(path), "device": value.st_dev, "inode": value.st_ino, "uid": uid}


def members(path):
    raw = read_bytes(Path(path) / "cgroup.procs", 16384).decode("ascii").split()
    require(len(raw) <= 1024 and all(re.fullmatch(r"[1-9][0-9]{0,9}", item) for item in raw))
    return {int(item) for item in raw}


def observe_service(installation, unit_sha256, *, cpu_quota_us, memory_bytes):
    """Observe the caller's exact allocated service; refuse unsupported boundaries.

    The allocator supplies the independently retained unit digest and limits.
    This function neither allocates resources nor establishes durable continuity.
    """
    try:
        return _observe_service(installation, unit_sha256, cpu_quota_us, memory_bytes)
    except ServiceRefused:
        raise
    except (OSError, ValueError, UnicodeError, KeyError, subprocess.SubprocessError):
        raise ServiceRefused("Native service scope unavailable or changed") from None


def _observe_service(installation, unit_sha256, cpu_quota_us, memory_bytes):
    require(isinstance(installation, str) and str(uuid.UUID(installation)) == installation)
    require(isinstance(unit_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", unit_sha256))
    require(type(cpu_quota_us) is int and 1000 <= cpu_quota_us <= 6400000)
    require(type(memory_bytes) is int and 134217728 <= memory_bytes <= 68719476736)
    require(platform.system() == "Linux" and platform.machine() == "x86_64" and os.getuid() > 0)
    # A remapped user namespace must not manufacture apparently root-owned trust.
    initial_mapping = ["0", "0", "4294967295"]
    require(read_bytes("/proc/1/uid_map", 256).decode("ascii").split() == initial_mapping)
    require(read_bytes("/proc/self/uid_map", 256).decode("ascii").split() == initial_mapping)
    account_name = "gg_" + base64.b32encode(uuid.UUID(installation).bytes).decode("ascii").lower().rstrip("=")
    account = pwd.getpwnam(account_name)
    require(account.pw_uid == os.getuid() == os.geteuid() and account.pw_gid > 0 and account.pw_gid == os.getgid() == os.getegid())
    boot = read_bytes("/proc/sys/kernel/random/boot_id", 64).decode("ascii").strip()
    require(str(uuid.UUID(boot)) == boot)
    _, release = root_file(Path("/etc/os-release").resolve(strict=True), 4096)
    require(b'ID=ubuntu\n' in release and b'VERSION_ID="24.04"\n' in release)
    require(Path("/proc/1").stat().st_uid == 0 and read_bytes("/proc/1/comm", 64) == b"systemd\n")
    # Linux denies ordinary users /proc/1/exe. Authenticate the manager through
    # its root-controlled system bus path and verify the installed binary.
    root_file(Path("/usr/lib/systemd/systemd").resolve(strict=True), executable=True)
    bus = Path("/run/dbus/system_bus_socket")
    require(bus.resolve(strict=True) == bus)
    for parent in bus.parents:
        value = parent.lstat()
        require(stat.S_ISDIR(value.st_mode) and value.st_uid == 0 and not value.st_mode & 0o022)
    value = bus.lstat()
    require(stat.S_ISSOCK(value.st_mode) and value.st_uid == 0)
    systemctl = Path("/usr/bin/systemctl")
    executable, _ = root_file(systemctl, executable=True)
    require(re.match(rb"systemd 255(?:\s|\.)", bounded_command([str(systemctl), "--version"])))
    require(re.match(rb"255(?:\s|\.)", bounded_command([str(systemctl), "--system", "--no-pager", "show", "--property=Version", "--value"])))
    unit = "gitgood-installation-" + installation + ".service"
    definition = Path("/etc/systemd/system") / unit
    unit_before, _ = root_file(definition, 16384)
    require(unit_before["sha256"] == unit_sha256)
    arguments = [str(systemctl), "--system", "--no-pager", "show", unit,
                 "--property=" + ",".join(PROPERTIES)]
    properties = parse_properties(bounded_command(arguments))
    expected = {"Id": unit, "LoadState": "loaded", "ActiveState": "active", "SubState": "running",
                "User": account_name, "Group": account_name, "Delegate": "yes", "DelegateSubgroup": "driver",
                "FragmentPath": str(definition), "DropInPaths": "", "KillMode": "control-group", "Restart": "on-failure"}
    require(all(properties[k] == v for k, v in expected.items()))
    require(set(properties["DelegateControllers"].split()) == {"cpu", "memory"})
    require(re.fullmatch(r"[1-9][0-9]{0,9}", properties["MainPID"]))
    relative = "/system.slice/" + unit
    require(properties["ControlGroup"] == relative)
    parent = Path("/sys/fs/cgroup" + relative)
    parent_before = group_identity(parent, account.pw_uid)
    require(os.getxattr(parent, "user.delegate", follow_symlinks=False) == b"1")
    require(not members(parent))
    require(set(read_bytes(parent / "cgroup.subtree_control").decode("ascii").split()) == {"cpu", "memory"})
    require(read_bytes(parent / "cpu.max").decode("ascii").strip() == str(cpu_quota_us) + " 100000")
    require(read_bytes(parent / "memory.max").decode("ascii").strip() == str(memory_bytes))
    require(read_bytes(parent / "memory.swap.max").strip() == b"0")
    groups = {}
    for name in GROUPS:
        path = parent / name
        groups[name] = group_identity(path, account.pw_uid)
        for control in ("cgroup.procs", "cgroup.kill", "cgroup.subtree_control"):
            value = (path / control).lstat()
            require(stat.S_ISREG(value.st_mode) and value.st_uid == account.pw_uid and value.st_mode & 0o200 and not value.st_mode & 0o022)
    driver = relative + "/driver"
    manager = process_identity(int(properties["MainPID"]), account.pw_uid, account.pw_gid, driver)
    caller = process_identity(os.getpid(), account.pw_uid, account.pw_gid, driver)
    require(manager["mount_namespace"] == caller["mount_namespace"] and manager["cgroup_namespace"] == caller["cgroup_namespace"])
    require({manager["pid"], caller["pid"]}.issubset(members(parent / "driver")))
    require(process_identity(manager["pid"], account.pw_uid, account.pw_gid, driver) == manager)
    require(parse_properties(bounded_command(arguments)) == properties)
    require(root_file(definition, 16384)[0] == unit_before and root_file(systemctl, executable=True)[0] == executable)
    require(group_identity(parent, account.pw_uid) == parent_before)
    require(all(group_identity(parent / name, account.pw_uid) == value for name, value in groups.items()))
    require(read_bytes("/proc/sys/kernel/random/boot_id", 64).decode("ascii").strip() == boot)
    return {"protocol": 2, "profile": "systemd", "installation": installation, "boot_id": boot,
            "uid": account.pw_uid, "gid": account.pw_gid, "unit": unit, "unit_definition": unit_before,
            "manager": manager, "parent": parent_before, "groups": groups,
            "limits": {"cpu_quota_us": cpu_quota_us, "cpu_period_us": 100000, "memory_bytes": memory_bytes, "swap_bytes": 0},
            "service_scope_observed": True, "installation_readiness_established": False}
