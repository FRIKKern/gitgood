"""Read-only admission for the separately allocated protocol-2 systemd profile.

An observation is transient evidence, never permission to signal a later process
or reuse a cgroup path. No installation, journal or database is changed here.
"""
import base64
from functools import lru_cache
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


def _root_file_path(path):
    """Canonical POSIX spelling; ancestor/leaf lstat checks reject links."""
    path = Path(path)
    require(path.is_absolute() and path.anchor == '/' and '..' not in path.parts)
    return path


@lru_cache(maxsize=64)
def _root_file_parent_plan(path):
    """Only immutable lexical paths/names; no observations or validation."""
    return tuple((parent, str(parent)) for parent in path.parents)


def _root_file_parents(path):
    # Bound retained lexical structure. Longer paths keep the original lazy
    # walk, with no new admission limit and no filesystem result retained.
    if len(str(path)) <= 1024 and len(path.parts) <= 64:
        return _root_file_parent_plan(path)
    return ((parent, str(parent)) for parent in path.parents)


def root_file(path, maximum=16777216, *, executable=False):
    path = _root_file_path(path)
    for parent, _ in _root_file_parents(path):
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


class _CapturedRootFiles:
    """One observer's content validation, bound to unchanging root file metadata.

    No live manager reply is cached. Installed CLI version depends on the same
    validated executable. Any replacement or metadata change poisons this object.
    """
    def __init__(self):
        self.files = {}
        self.version = None
        self.frozen = False
        self.usable = True
        self.systemd = None

    def systemd_properties(self):
        try:
            require(self.usable)
            if self.systemd is None:
                require(not self.frozen)
                from native_systemd_properties import ReadOnlySystemdProperties
                self.systemd = ReadOnlySystemdProperties()
            require(self.systemd.usable)
            return self.systemd
        except BaseException:
            self.close()
            raise

    def close(self):
        self.usable = False
        if self.systemd is not None:
            self.systemd.close()

    @staticmethod
    def _fingerprint(path, maximum, executable):
        # No identity or ancestor result is cached. Every named parent is
        # lstat-checked below, so a separate resolving walk repeats that work.
        path = _root_file_path(path)
        parents = []
        for parent, name in _root_file_parents(path):
            info = parent.lstat()
            require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022)
            parents.append((name, info.st_dev, info.st_ino, info.st_uid, info.st_mode))
        info = path.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1)
        require(not info.st_mode & 0o022 and 0 < info.st_size <= maximum)
        require(not executable or info.st_mode & 0o111)
        fields = ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_uid','st_mode','st_nlink')
        return tuple(getattr(info, field) for field in fields), tuple(parents)

    def read(self, path, maximum=16777216, *, executable=False):
        try:
            require(self.usable)
            path = Path(path)
            fingerprint = self._fingerprint(path, maximum, executable)
            contract = (maximum, executable)
            if path not in self.files:
                require(not self.frozen and len(self.files) < 4)
                value = root_file(path, maximum, executable=executable)
                identity = value[0]
                require((identity['device'], identity['inode'], identity['bytes']) == fingerprint[0][:3])
                require(self._fingerprint(path, maximum, executable) == fingerprint)
                self.files[path] = (contract, fingerprint, value)
            original_contract, original, value = self.files[path]
            require(contract == original_contract and fingerprint == original)
            return dict(value[0]), value[1]
        except BaseException:
            self.usable = False
            raise

    def installed_version(self, path):
        try:
            self.read(path, executable=True)
            if self.version is None:
                require(not self.frozen)
                version = bounded_command([str(path), '--version'])
                require(re.match(rb'systemd 255(?:\s|\.)', version))
                self.read(path, executable=True)
                self.version = version
            return self.version
        except BaseException:
            self.usable = False
            raise

    def freeze(self):
        require(self.usable and len(self.files) == 4 and self.version is not None)
        for path, (contract, _, _) in self.files.items():
            self.read(path, contract[0], executable=contract[1])
        self.frozen = True


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


def _process_status_fields(status):
    """Parse one fresh status read; retain duplicates for the original checks."""
    names = {'Uid', 'Gid', 'Groups', 'CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb', 'NoNewPrivs'}
    fields = {}
    for line in status.splitlines():
        name, separator, value = line.partition(':')
        if separator and name in names:
            fields.setdefault(name, []).append(value.split())
    return fields


def _process_security_fields(fields, gid):
    require(type(gid) is int and 0 < gid < 2**32)
    def field(name):
        values = fields.get(name, [])
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


def process_security(status, gid):
    require(type(gid) is int and 0 < gid < 2**32)
    return _process_security_fields(_process_status_fields(status), gid)


def process_identity(pid, uid, gid, group):
    require(type(pid) is int and 0 < pid < 2147483648)
    path = Path("/proc") / str(pid)
    raw = read_bytes(path / "stat").decode("ascii")
    parts = raw[raw.rfind(")") + 2:].split()
    require(len(parts) >= 20 and parts[0] not in {"Z", "X"} and path.stat().st_uid == uid)
    status = read_bytes(path / "status").decode("ascii")
    fields = _process_status_fields(status)
    for field in ("Uid", "Gid"):
        values = fields.get(field, [])
        require(len(values) == 1 and len(values[0]) == 4 and len(set(values[0])) == 1)
        if field == "Uid":
            require(values[0][0] == str(uid))
    require(read_bytes(path / "cgroup").decode("ascii").splitlines() == ["0::" + group])
    return {"pid": pid, "birth": parts[19], "uid": uid, "security": _process_security_fields(fields, gid),
            "mount_namespace": os.readlink(path / "ns/mnt"),
            "cgroup_namespace": os.readlink(path / "ns/cgroup")}


def group_identity(path, uid, *, _parent=None):
    path = Path(path)
    if _parent is None:
        require(path.resolve(strict=True) == path)
    else:
        # The service parent is fully canonicalized before and after its fixed
        # leaves. Rewalking every root prefix for every leaf adds no authority.
        require(str(path.parent) == _parent['path'] and path.name in GROUPS)
        parent = path.parent.lstat()
        require(stat.S_ISDIR(parent.st_mode) and not parent.st_mode & 0o022)
        require((parent.st_dev, parent.st_ino, parent.st_uid) ==
                (_parent['device'], _parent['inode'], _parent['uid']))
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


def _observe_service(installation, unit_sha256, cpu_quota_us, memory_bytes, *, caller_group="driver", _root_files=None):
    return _observe_allocated_service(installation, unit_sha256, cpu_quota_us, memory_bytes,
        caller_group=caller_group, root_observer=False, _root_files=_root_files)


def _observe_root_controller(installation, unit_sha256, cpu_quota_us, memory_bytes, *, _root_files):
    """Read-only Root observation; the selected MainPID remains ordinary.

    This is separate from caller admission. Only the fixed protected observer
    supplies independently read Root policy; no caller process is impersonated.
    """
    return _observe_allocated_service(installation, unit_sha256, cpu_quota_us, memory_bytes,
        caller_group="driver", root_observer=True, _root_files=_root_files)


def _observe_allocated_service(installation, unit_sha256, cpu_quota_us, memory_bytes,
                               *, caller_group, root_observer, _root_files):
    require(caller_group in {"driver", "native", "maintenance"})
    require(isinstance(installation, str) and str(uuid.UUID(installation)) == installation)
    require(isinstance(unit_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", unit_sha256))
    require(type(cpu_quota_us) is int and 1000 <= cpu_quota_us <= 6400000)
    require(type(memory_bytes) is int and 134217728 <= memory_bytes <= 68719476736)
    require(platform.system() == "Linux" and platform.machine() == "x86_64")
    if root_observer:
        require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0)
    else:
        require(os.getuid() > 0)
    # A remapped user namespace must not manufacture apparently root-owned trust.
    initial_mapping = ["0", "0", "4294967295"]
    require(read_bytes("/proc/1/uid_map", 256).decode("ascii").split() == initial_mapping)
    require(read_bytes("/proc/self/uid_map", 256).decode("ascii").split() == initial_mapping)
    account_name = "gg_" + base64.b32encode(uuid.UUID(installation).bytes).decode("ascii").lower().rstrip("=")
    account = pwd.getpwnam(account_name)
    require(account.pw_uid > 0 and account.pw_gid > 0)
    if not root_observer:
        require(account.pw_uid == os.getuid() == os.geteuid() and account.pw_gid == os.getgid() == os.getegid())
    boot = read_bytes("/proc/sys/kernel/random/boot_id", 64).decode("ascii").strip()
    require(str(uuid.UUID(boot)) == boot)
    read_root = root_file if _root_files is None else _root_files.read
    _, release = read_root(Path("/etc/os-release").resolve(strict=True), 4096)
    require(b'ID=ubuntu\n' in release and b'VERSION_ID="24.04"\n' in release)
    require(Path("/proc/1").stat().st_uid == 0 and read_bytes("/proc/1/comm", 64) == b"systemd\n")
    # Linux denies ordinary users /proc/1/exe. Authenticate the manager through
    # its root-controlled system bus path and verify the installed binary.
    read_root(Path("/usr/lib/systemd/systemd").resolve(strict=True), executable=True)
    bus = Path("/run/dbus/system_bus_socket")
    require(bus.resolve(strict=True) == bus)
    for parent in bus.parents:
        value = parent.lstat()
        require(stat.S_ISDIR(value.st_mode) and value.st_uid == 0 and not value.st_mode & 0o022)
    value = bus.lstat()
    require(stat.S_ISSOCK(value.st_mode) and value.st_uid == 0)
    systemctl = Path("/usr/bin/systemctl")
    executable, _ = read_root(systemctl, executable=True)
    installed = (bounded_command([str(systemctl), '--version']) if _root_files is None
                 else _root_files.installed_version(systemctl))
    require(re.match(rb"systemd 255(?:\s|\.)", installed))
    properties_reader = None if _root_files is None else _root_files.systemd_properties()
    manager_version = (bounded_command([str(systemctl), "--system", "--no-pager", "show", "--property=Version", "--value"])
                       if properties_reader is None else properties_reader.manager_version().encode('ascii'))
    require(re.match(rb"255(?:\s|\.)", manager_version))
    unit = "gitgood-installation-" + installation + ".service"
    definition = Path("/etc/systemd/system") / unit
    unit_before, _ = read_root(definition, 16384)
    require(unit_before["sha256"] == unit_sha256)
    arguments = [str(systemctl), "--system", "--no-pager", "show", unit,
                 "--property=" + ",".join(PROPERTIES)]
    properties = (parse_properties(bounded_command(arguments)) if properties_reader is None
                  else properties_reader.unit_properties(unit))
    require(set(properties) == set(PROPERTIES))
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
        groups[name] = group_identity(path, account.pw_uid, _parent=parent_before)
        for control in ("cgroup.procs", "cgroup.kill", "cgroup.subtree_control"):
            value = (path / control).lstat()
            require(stat.S_ISREG(value.st_mode) and value.st_uid == account.pw_uid and value.st_mode & 0o200 and not value.st_mode & 0o022)
    driver = relative + "/driver"
    manager = process_identity(int(properties["MainPID"]), account.pw_uid, account.pw_gid, driver)
    if root_observer:
        # Root observes the actual MainPID in the same host namespaces. Root is
        # not an ordinary installation worker and gains no worker admission.
        for name, namespace in (("mount_namespace", "mnt"), ("cgroup_namespace", "cgroup")):
            require(manager[name] == os.readlink("/proc/self/ns/" + namespace))
    else:
        caller_relative = relative + "/" + caller_group
        caller = process_identity(os.getpid(), account.pw_uid, account.pw_gid, caller_relative)
        require(manager["mount_namespace"] == caller["mount_namespace"] and manager["cgroup_namespace"] == caller["cgroup_namespace"])
        require(caller["pid"] in members(parent / caller_group))
    require(manager["pid"] in members(parent / "driver"))
    require(process_identity(manager["pid"], account.pw_uid, account.pw_gid, driver) == manager)
    repeated = (parse_properties(bounded_command(arguments)) if properties_reader is None
                else properties_reader.unit_properties(unit))
    require(repeated == properties)
    require(read_root(definition, 16384)[0] == unit_before and read_root(systemctl, executable=True)[0] == executable)
    require(group_identity(parent, account.pw_uid) == parent_before)
    require(all(group_identity(parent / name, account.pw_uid, _parent=parent_before) == value for name, value in groups.items()))
    require(read_bytes("/proc/sys/kernel/random/boot_id", 64).decode("ascii").strip() == boot)
    return {"protocol": 2, "profile": "systemd", "installation": installation, "boot_id": boot,
            "uid": account.pw_uid, "gid": account.pw_gid, "unit": unit, "unit_definition": unit_before,
            "manager": manager, "parent": parent_before, "groups": groups,
            "limits": {"cpu_quota_us": cpu_quota_us, "cpu_period_us": 100000, "memory_bytes": memory_bytes, "swap_bytes": 0},
            "service_scope_observed": True, "installation_readiness_established": False}
