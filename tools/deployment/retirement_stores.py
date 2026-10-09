"""Remove exactly planned native stores through pinned directory descriptors."""
import hashlib
import os
from pathlib import Path
import socket
import stat
import sys

from native_inventory import cgroup_identity, directory_identity
from upgrade_journal import canonical, require

STORES = ("configuration", "ssh-host", "storage")
MAX_ENTRIES = 100_000
MAX_BYTES = 16 * 1024**3
FIELDS = {"path", "type", "device", "inode", "uid", "mode", "bytes", "sha256"}
DIRECTORY = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
FILE = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)


def _identity(value):
    return {"device": value.st_dev, "inode": value.st_ino, "uid": value.st_uid}


def _metadata(path, value, digest=None):
    require(value.st_uid == os.getuid() and not value.st_mode & 0o022)
    require(stat.S_ISDIR(value.st_mode) or stat.S_ISREG(value.st_mode))
    if stat.S_ISREG(value.st_mode):
        require(value.st_nlink == 1 and 0 <= value.st_size <= MAX_BYTES)
    return {"path": path, "type": "directory" if stat.S_ISDIR(value.st_mode) else "file",
            **_identity(value), "mode": stat.S_IMODE(value.st_mode),
            "bytes": value.st_size if stat.S_ISREG(value.st_mode) else 0, "sha256": digest}


def _inventory(root_descriptor):
    entries = []
    total = 0
    def walk(parent, name, relative, depth):
        nonlocal total
        require(len(entries) < MAX_ENTRIES and depth <= 64 and len(relative.encode()) <= 4096)
        value = os.stat(name, dir_fd=parent, follow_symlinks=False)
        metadata = _metadata(relative, value)
        descriptor = os.open(name, DIRECTORY if metadata["type"] == "directory" else FILE, dir_fd=parent)
        try:
            require(_metadata(relative, os.fstat(descriptor)) == metadata)
            if metadata["type"] == "directory":
                entries.append(metadata)
                for child in sorted(os.listdir(descriptor)):
                    require(child not in {"", ".", ".."} and "/" not in child and "\0" not in child)
                    walk(descriptor, child, relative + "/" + child, depth + 1)
            else:
                with os.fdopen(os.dup(descriptor), "rb") as source:
                    metadata["sha256"] = hashlib.file_digest(source, "sha256").hexdigest()
                after = os.fstat(descriptor)
                require(_metadata(relative, after) == {**metadata, "sha256": None})
                require((after.st_mtime_ns, after.st_ctime_ns) == (value.st_mtime_ns, value.st_ctime_ns))
                total += metadata["bytes"]
                require(total <= MAX_BYTES)
                entries.append(metadata)
            require(_identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) == _identity(value))
        finally:
            os.close(descriptor)
    for name in STORES:
        try:
            os.stat(name, dir_fd=root_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            continue
        walk(root_descriptor, name, name, 0)
    return sorted(entries, key=lambda value: value["path"])


def capture_store_plan(root, inventory, operation):
    """Read-only inventory; independently pin its digest before retirement."""
    require(sys.platform == "linux")
    bindings = inventory["bindings"]
    require(hashlib.sha256(canonical(bindings)).hexdigest() == inventory["bindings_sha256"])
    root = Path(root)
    require(directory_identity(root, private=True) == bindings["resources"]["root"])
    for name in STORES:
        require(directory_identity(root / name, private=name == "configuration") == bindings["resources"][name])
    descriptor = os.open(root, DIRECTORY)
    try:
        require(_identity(os.fstat(descriptor)) == {key: bindings["resources"]["root"][key] for key in ["device", "inode", "uid"]})
        entries = _inventory(descriptor)
    finally:
        os.close(descriptor)
    require(set(STORES) <= {entry["path"] for entry in entries})
    return {"protocol": 1, "operation": operation, "installation": bindings["installation"],
            "bindings": bindings, "bindings_sha256": inventory["bindings_sha256"], "entries": entries}


class RetirementStores:
    """This action is admitted only by the continuously owned retirement stage."""
    def __init__(self, journal, resource_plan):
        require(sys.platform == "linux")
        require(isinstance(resource_plan, dict) and set(resource_plan) == {"protocol", "operation", "installation", "bindings", "bindings_sha256", "entries"})
        require(type(resource_plan["protocol"]) is int and resource_plan["protocol"] == 1)
        require(hashlib.sha256(canonical(resource_plan)).hexdigest() == journal.plan["resource_plan_sha256"])
        require(resource_plan["operation"] == journal.operation and resource_plan["installation"] == journal.plan["installation"])
        self.journal = journal
        self.bindings = resource_plan["bindings"]
        require(hashlib.sha256(canonical(self.bindings)).hexdigest() == resource_plan["bindings_sha256"] == journal.plan["bindings_sha256"])
        require(self.bindings["installation"] == journal.plan["installation"] and self.bindings["uid"] == os.getuid() and self.bindings["host"] == socket.gethostname())
        resources = self.bindings["resources"]
        require(set(resources) == {"root", *STORES})
        self.root = Path(resources["root"]["path"])
        require(self.root.is_absolute() and self.root.resolve() == self.root)
        for name in STORES:
            require(resources[name]["path"] == str(self.root / name))
        entries = resource_plan["entries"]
        require(isinstance(entries, list) and 3 <= len(entries) <= MAX_ENTRIES)
        self.entries = {}
        for entry in entries:
            require(isinstance(entry, dict) and set(entry) == FIELDS)
            path = entry["path"]
            require(isinstance(path, str) and len(path.encode()) <= 4096 and "\0" not in path and path.split("/")[0] in STORES)
            require(all(part not in {"", ".", ".."} for part in path.split("/")) and path not in self.entries)
            require(entry["type"] in {"directory", "file"})
            require(all(type(entry[key]) is int and entry[key] >= 0 for key in ["device", "inode", "uid", "mode", "bytes"]))
            require(entry["uid"] == os.getuid() and entry["mode"] <= 0o777 and not entry["mode"] & 0o022)
            require(entry["bytes"] <= MAX_BYTES)
            require(entry["type"] != "directory" or entry["bytes"] == 0 and entry["sha256"] is None)
            require(entry["type"] != "file" or isinstance(entry["sha256"], str) and len(entry["sha256"]) == 64 and all(char in "0123456789abcdef" for char in entry["sha256"]))
            if "/" in path:
                require(self.entries.get(path.rsplit("/", 1)[0], {}).get("type") == "directory")
            self.entries[path] = entry
        require(list(self.entries) == sorted(self.entries) and set(STORES) <= set(self.entries))
        require(sum(entry["bytes"] for entry in entries) <= MAX_BYTES)
        for name in STORES:
            require(self.entries[name]["type"] == "directory")
            require({key: self.entries[name][key] for key in ["device", "inode", "uid"]} == {key: resources[name][key] for key in ["device", "inode", "uid"]})

    def _custody(self, *, observing=False):
        self.journal._owned()
        require(self.journal.record["stage"] in ({"stores_remove", "retention_verify"} if observing else {"stores_remove"}))
        require(self.journal.record["status"] in ({"running", "failed", "uncertain"} if observing else {"running"}))
        require(directory_identity(self.root, private=True) == self.bindings["resources"]["root"])
        for name in ["native", "web", "edge", "maintenance", "driver"]:
            group = self.bindings["cgroups"][name]
            require(cgroup_identity(self.bindings["installation"], name) == group)
            if name == "driver":
                require(Path("/proc/self/cgroup").read_text().splitlines() == ["0::" + group["kernel_path"]])
            else:
                require(dict(line.split() for line in (Path(group["path"]) / "cgroup.events").read_text().splitlines()).get("populated") == "0")
                require(not (Path(group["path"]) / "cgroup.procs").read_text().strip())

    def _open_root(self):
        descriptor = os.open(self.root, DIRECTORY)
        try:
            require(_identity(os.fstat(descriptor)) == {key: self.bindings["resources"]["root"][key] for key in ["device", "inode", "uid"]})
        except BaseException:
            os.close(descriptor)
            raise
        return descriptor

    def _observe(self, root):
        observed = _inventory(root)
        require(all(self.entries.get(entry["path"]) == entry for entry in observed))
        return {"remaining": len(observed), "removed": len(self.entries) - len(observed),
                "desired_state_verified": not observed, "resource_reobserved": True,
                "resource_plan_sha256": self.journal.plan["resource_plan_sha256"],
                "bindings_sha256": self.journal.plan["bindings_sha256"],
                "remaining_sha256": hashlib.sha256(canonical(observed)).hexdigest()}

    def observe(self):
        self._custody(observing=True)
        root = self._open_root()
        try:
            value = self._observe(root)
            self._custody(observing=True)
            return {**value, "receipt_sha256": hashlib.sha256(canonical(value)).hexdigest()}
        finally:
            os.close(root)

    def _remove_entry(self, root, entry):
        parents = [root]
        chain = []
        parts = entry["path"].split("/")
        try:
            for number, part in enumerate(parts[:-1]):
                parent = parents[-1]
                child = os.open(part, DIRECTORY, dir_fd=parent)
                parents.append(child)
                expected = self.entries["/".join(parts[:number + 1])]
                require(_metadata(expected["path"], os.fstat(child)) == expected)
                chain.append((parent, part, child))
            parent, name = parents[-1], parts[-1]
            try:
                value = os.stat(name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                return
            require(_metadata(entry["path"], value) == {**entry, "sha256": None})
            if entry["type"] == "file":
                descriptor = os.open(name, FILE, dir_fd=parent)
                with os.fdopen(descriptor, "rb") as source:
                    require(_metadata(entry["path"], os.fstat(source.fileno())) == {**entry, "sha256": None})
                    require(hashlib.file_digest(source, "sha256").hexdigest() == entry["sha256"])
                    after = os.fstat(source.fileno())
                    require((after.st_mtime_ns, after.st_ctime_ns) == (value.st_mtime_ns, value.st_ctime_ns))
            self._custody()
            for ancestor, part, child in chain:
                require(_identity(os.stat(part, dir_fd=ancestor, follow_symlinks=False)) == _identity(os.fstat(child)))
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
            require(_metadata(entry["path"], current) == {**entry, "sha256": None})
            if entry["type"] == "file":
                require((current.st_mtime_ns, current.st_ctime_ns) == (value.st_mtime_ns, value.st_ctime_ns))
            if entry["type"] == "directory":
                os.rmdir(name, dir_fd=parent)
            else:
                os.unlink(name, dir_fd=parent)
            os.fsync(parent)
        except FileNotFoundError:
            # An already removed ancestor means the planned descendant is absent.
            require(not any(value["path"].startswith(entry["path"] + "/") for value in _inventory(root)))
        finally:
            for descriptor in reversed(parents[1:]):
                os.close(descriptor)

    def remove(self):
        self._custody()
        root = self._open_root()
        try:
            self._observe(root)  # Refuse unexpected/replacement entries before the first deletion.
            for entry in sorted(self.entries.values(), key=lambda value: (-value["path"].count("/"), value["path"]), reverse=False):
                self._remove_entry(root, entry)
            value = self._observe(root)
            self._custody()
            require(value["desired_state_verified"])
            return {**value, "receipt_sha256": hashlib.sha256(canonical(value)).hexdigest()}
        finally:
            os.close(root)
