"""Exclusive, recoverable resource-generation publication; no runtime activation."""
import hashlib
import itertools
import json
import os
from pathlib import Path
import uuid

from generation_custody import GenerationRecordCustody
from native_lifecycle_history import NativeLifecycleHistory
from native_durable_binding import observe_durable_binding, configuration
from native_service_scope import group_identity, read_bytes, process_identity
from native_writer_exclusion import NativeWriterExclusion
from resource_generations import canonical, identifier, digest, make_generation
from stage_native_artifact import publish_directory, sync_directory


class PublicationRefused(Exception):
    pass


def require(value):
    if not value:
        raise PublicationRefused("Native generation publication unavailable or uncertain")


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def stopped(scope):
    """Observe exact current groups, including descendants; never send signals."""
    require(scope["manager"]["pid"] == os.getpid())
    require(process_identity(os.getpid(), scope["uid"], scope["gid"],
                             scope["groups"]["driver"]["path"].removeprefix("/sys/fs/cgroup")) == scope["manager"])
    for name in ["native", "web", "edge", "maintenance"]:
        item = scope["groups"][name]
        require(group_identity(item["path"], scope["uid"]) == item)
        events = dict(line.split() for line in read_bytes(Path(item["path"]) / "cgroup.events", 1024).decode("ascii").splitlines())
        require(events.get("populated") == "0")


def old_gone(previous, current):
    """A new boot authorizes no signal; a same-boot restart needs exact absence."""
    if previous["boot_id"] != current["boot_id"]:
        return
    require(previous["parent"] != current["parent"])
    # The unit parent is beneath the root-controlled system.slice directory,
    # not renameable by this account. Replacement plus actual old-manager
    # absence is required; paths and PID reuse never authorize a signal.
    path = Path("/proc") / str(previous["manager"]["pid"])
    try:
        raw = read_bytes(path / "stat").decode("ascii")
    except FileNotFoundError:
        return
    fields = raw[raw.rfind(")") + 2:].split()
    require(len(fields) >= 20)
    require(fields[19] != previous["manager"]["birth"] or fields[0] in {"Z", "X"})


class GenerationPublication:
    """Publish only independently expected continuity under both exclusions.

    Allocation must independently seal the expected binding digest, history and
    existing lock identities, unit digest, limits and runtime paths. This class
    does not manufacture those authorities or convert protocol-1 responsibility.
    """
    def __init__(self, root, installation, expected_binding_sha256, history_identity,
                 lock_identity, unit_sha256, executables, *, cpu_quota_us, memory_bytes):
        identifier(installation)
        digest(expected_binding_sha256)
        digest(unit_sha256)
        require(type(root) is str and root == "/var/lib/gitgood/installations/" + installation)
        self.root = Path(root)
        self.installation = installation
        self.expected = expected_binding_sha256
        self.unit = unit_sha256
        require(type(executables) is dict and set(executables) == {"python", "node", "git", "psql", "caddy"})
        require(all(type(path) is str and 0 < len(path) <= 4096 and path.startswith("/") and "\0" not in path for path in executables.values()))
        self.executables = executables.copy()
        self.options = {"cpu_quota_us": cpu_quota_us, "memory_bytes": memory_bytes}
        self.custody = GenerationRecordCustody(self.root / "history", installation, history_identity, lock_identity)
        self.directory = self.root / "history"
        self.pointer = self.directory / "current-generation-v2.json"
        self.transitions = self.directory / "generation-transitions-v2"
        self.receipts = self.directory / "generation-receipts-v2"
        self.directory_identities = {}
        self.lifecycle_present = None

    def _check(self):
        self.custody.check()
        present = getattr(self, 'lifecycle_present', None)
        if present is not None:
            path = self.directory / 'lifecycle-responsibility-v2'
            require((path.exists() or path.is_symlink()) == present)
        for path, identity in self.directory_identities.items():
            require(self.custody._identity(path) == identity)

    def _lifecycle_view(self):
        self._check()
        path = self.directory / 'lifecycle-responsibility-v2'
        return NativeLifecycleHistory(self.custody) if path.exists() or path.is_symlink() else None

    def _lifecycle_state(self):
        view = self._lifecycle_view()
        try:
            return (view.references(), view.fingerprint()) if view else ([], None)
        finally:
            if view:view.close()

    def _observe(self):
        value = observe_durable_binding(str(self.root), self.installation, self.unit, self.executables, **self.options)
        require(value["binding_sha256"] == self.expected and sha(value["binding"]) == self.expected)
        stopped(value["scope"])
        self._check()
        return value

    def _read(self, path, maximum=65_536):
        self._check()
        descriptor = self.custody._open(path, os.O_RDONLY)
        with os.fdopen(descriptor, "rb") as source:
            before = os.fstat(source.fileno())
            require(0 < before.st_size <= maximum)
            raw = source.read(maximum + 1)
            after = os.fstat(source.fileno())
        require(len(raw) == before.st_size)
        require(all(getattr(before, field) == getattr(after, field) for field in
                    ["st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_mode", "st_nlink"]))
        named = path.lstat()
        require((named.st_dev, named.st_ino) == (before.st_dev, before.st_ino))
        def unique(pairs):
            value = {}
            for name, item in pairs:
                require(name not in value)
                value[name] = item
            return value
        value = json.loads(raw, object_pairs_hook=unique)
        require(raw == canonical(value))
        return value

    def _write(self, path, value, *, replace=False):
        self._check()
        raw = canonical(value)
        require(len(raw) <= 65_536)
        if not replace and (path.exists() or path.is_symlink()):
            require(self._read(path) == value)
            sync_directory(path.parent)
            return
        require(len(list(itertools.islice(path.parent.iterdir(), 1025))) < 1024)
        temporary = path.parent / (".partial-" + str(uuid.uuid4()))
        descriptor = self.custody._open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        with os.fdopen(descriptor, "wb") as target:
            target.write(raw)
            target.flush()
            os.fsync(target.fileno())
        self._check()
        if replace:
            os.replace(temporary, path)
        else:
            publish_directory(temporary, path)
        sync_directory(path.parent)
        require(self._read(path) == value)

    def _layout(self):
        # No implicit conversion or restart over legacy/unknown responsibility.
        allowed = {".upgrade-history-lock-v1", "generation-records-v2", "durable-binding-v2.json",
                   "current-generation-v2.json", "generation-transitions-v2", "generation-receipts-v2",
                   "lifecycle-responsibility-v2"}
        paths = list(itertools.islice(self.directory.iterdir(), 1031))
        require(len(paths) <= 1030)
        for path in paths:
            if path.name.startswith(".partial-"):
                identifier(path.name.removeprefix(".partial-"))
                descriptor = self.custody._open(path, os.O_RDONLY)
                try:
                    require(os.fstat(descriptor).st_size <= 65_536)
                finally:
                    os.close(descriptor)
            else:
                require(path.name in allowed)
        lifecycle = self.directory / 'lifecycle-responsibility-v2'
        self.lifecycle_present = lifecycle.exists() or lifecycle.is_symlink()
        if self.lifecycle_present:
            view = self._lifecycle_view()
            try:
                for role in ['lifecycle', 'records', 'heads']:
                    path = view.paths[role]
                    self.directory_identities[path] = self.custody._identity(path)
                view.check()
            finally:view.close()
        for path in [self.transitions, self.receipts]:
            if not path.exists() and not path.is_symlink():
                path.mkdir(mode=0o700)
                sync_directory(self.directory)
            self.directory_identities[path] = self.custody._identity(path)
            entries = list(itertools.islice(path.iterdir(), 1025))
            require(len(entries) <= 1024)
            for entry in entries:
                if entry.name.startswith(".partial-"):
                    identifier(entry.name.removeprefix(".partial-"))
                    descriptor = self.custody._open(entry, os.O_RDONLY)
                    try:
                        require(os.fstat(descriptor).st_size <= 65_536)
                    finally:
                        os.close(descriptor)
                else:
                    require(entry.name.endswith(".json"))
                    identifier(entry.name[:-5])
                    self._read(entry)

    def _validate_pointer(self, value, records, seen, lifecycle=None):
        require(type(value) is dict and set(value) == {"protocol", "installation", "operation", "generation_sha256", "transition_sha256"})
        require(type(value["protocol"]) is int and value["protocol"] == 2 and value["installation"] == self.installation)
        identifier(value["operation"])
        digest(value["generation_sha256"])
        digest(value["transition_sha256"])
        require(value["operation"] not in seen and len(seen) < 128)
        seen.add(value["operation"])
        transition = self._read(self.transitions / (value["operation"] + ".json"))
        require(type(transition) is dict and set(transition) == {"protocol", "kind", "installation", "operation", "durable_binding_sha256",
                "old_pointer", "old_pointer_sha256", "old_generation_sha256", "previous_publication_complete", "new_generation_sha256", "scope", "lifecycle_responsibilities", "created_at"})
        require(type(transition["protocol"]) is int and transition["protocol"] == 2 and transition["kind"] == "resource_generation_transition")
        require(transition["installation"] == self.installation)
        responsibilities = transition['lifecycle_responsibilities']
        require(type(responsibilities) is list)
        if responsibilities:
            require(lifecycle is not None)
            lifecycle._validate_references(responsibilities, value['generation_sha256'])
        require(sha(transition) == value["transition_sha256"] and transition["operation"] == value["operation"])
        require(transition["new_generation_sha256"] == value["generation_sha256"] and transition["durable_binding_sha256"] == self.expected)
        require(value["generation_sha256"] in records)
        record = records[value["generation_sha256"]]
        require(record["durable_binding_sha256"] == self.expected)
        require(record["scope"] == transition["scope"] and record["created_at"] == transition["created_at"])
        require(record["predecessor_sha256"] == transition["old_generation_sha256"])
        old = transition["old_pointer"]
        if old is None:
            require(transition["old_pointer_sha256"] is None and transition["previous_publication_complete"] is None)
        else:
            require(type(transition["previous_publication_complete"]) is bool)
            require(transition["old_pointer_sha256"] == sha(old))
            self._validate_pointer(old, records, seen, lifecycle)
            if transition["previous_publication_complete"]:
                require(self._complete(old))
            # A stopped publication may retain a successor before its pointer.
            # Recovery keeps that exact record as predecessor and references
            # the previously published pointer separately; never branch around it.
            ancestor = transition["old_generation_sha256"]
            visited = set()
            while ancestor != old["generation_sha256"]:
                require(ancestor in records and ancestor not in visited and len(visited) < 128)
                visited.add(ancestor)
                ancestor = records[ancestor]["predecessor_sha256"]

    def _current(self):
        if not self.pointer.exists() and not self.pointer.is_symlink():
            return None
        value = self._read(self.pointer, 16_384)
        lifecycle = self._lifecycle_view()
        try:
            self._validate_pointer(value, self.custody._records(), set(), lifecycle)
            if lifecycle:lifecycle.check()
        finally:
            if lifecycle:lifecycle.close()
        return value

    def _inventory(self, records):
        """Every retained operation remains closed responsibility, even off-tip."""
        lifecycle = self._lifecycle_view()
        try:
            self._publication_inventory(records, lifecycle)
            if lifecycle:lifecycle.check()
        finally:
            if lifecycle:lifecycle.close()

    def _publication_inventory(self, records, lifecycle):
        pointers = {}
        transition_paths = list(itertools.islice(self.transitions.iterdir(), 1025))
        receipt_paths = list(itertools.islice(self.receipts.iterdir(), 1025))
        require(len(transition_paths) <= 1024 and len(receipt_paths) <= 1024)
        for path in transition_paths:
            if path.name.startswith(".partial-"):
                continue
            transition = self._read(path)
            require(type(transition) is dict and "new_generation_sha256" in transition)
            pointer = {"protocol": 2, "installation": self.installation, "operation": path.name[:-5],
                       "generation_sha256": transition["new_generation_sha256"], "transition_sha256": sha(transition)}
            self._validate_pointer(pointer, records, set(), lifecycle)
            pointers[pointer["operation"]] = pointer
        for path in receipt_paths:
            if path.name.startswith(".partial-"):
                continue
            require(path.name[:-5] in pointers and self._complete(pointers[path.name[:-5]]))

    def _complete(self, pointer):
        path = self.receipts / (pointer["operation"] + ".json")
        if not path.exists() and not path.is_symlink():
            return False
        value = self._read(path, 16_384)
        require(value == {"protocol": 2, "installation": self.installation, "pointer_sha256": sha(pointer), "status": "complete"})
        return True

    def publish(self, *, operation, generation, created_at):
        identifier(operation)
        identifier(generation)
        require(operation != generation and operation != self.installation)
        with self.custody:
            self._layout()
            observed = self._observe()
            self._write(self.directory / "durable-binding-v2.json", observed["binding"])
            _, url = configuration(self.root, self.installation, observed["scope"]["uid"])
            with NativeWriterExclusion(observed["binding"]["executables"]["psql"]["path"], url,
                                       observed["binding"]["database"]) as lease:
                require(self._observe() == observed)
                lease.check()
                current = self._current()
                records = self.custody._records()
                self._inventory(records)
                lifecycle_state = self._lifecycle_state()
                previous = records[current["generation_sha256"]] if current else None
                if records and (not current or current["operation"] != operation):
                    used = {value["predecessor_sha256"] for value in records.values()}
                    tips = [(key, value) for key, value in records.items() if key not in used]
                    require(len(tips) == 1)
                    # A unique tip alone could conceal an earlier joined branch.
                    require(len([value["predecessor_sha256"] for value in records.values() if value["predecessor_sha256"] is not None]) == len(used - {None}))
                    matching = [value for value in records.values() if value["generation"] == generation]
                    if matching:
                        require(len(matching) == 1 and matching[0]["scope"] == observed["scope"] and matching[0]["created_at"] == created_at)
                        require(matching[0] == tips[0][1] and (current is None or sha(matching[0]) != current["generation_sha256"]))
                        predecessor = matching[0]["predecessor_sha256"]
                        previous = records[predecessor] if predecessor else None
                    else:
                        previous = tips[0][1]
                if current and current["operation"] == operation:
                    require(previous["generation"] == generation and previous["created_at"] == created_at)
                    require(previous["scope"] == observed["scope"])
                    if not self._complete(current):
                        transition = self._read(self.transitions / (operation + '.json'))
                        require(transition['lifecycle_responsibilities'] == lifecycle_state[0])
                    desired = current
                else:
                    if previous:
                        old_gone(previous["scope"], observed["scope"])
                    record = make_generation(observed["scope"], self.expected, generation=generation,
                                             created_at=created_at, previous=previous)
                    record_sha = sha(record)
                    transition = {"protocol": 2, "kind": "resource_generation_transition", "installation": self.installation,
                                  "operation": operation, "durable_binding_sha256": self.expected,
                                  "old_pointer": current,
                                  "old_pointer_sha256": sha(current) if current else None,
                                  "old_generation_sha256": sha(previous) if previous else None,
                                  "previous_publication_complete": self._complete(current) if current else None,
                                  "new_generation_sha256": record_sha, "scope": observed["scope"],
                                  "lifecycle_responsibilities": lifecycle_state[0], "created_at": created_at}
                    request_path = self.transitions / (operation + ".json")
                    if request_path.exists() or request_path.is_symlink():
                        require(self._read(request_path) == transition)
                    require(record_sha in records or len(records) < 128)
                    self.custody.retain(record)
                    lifecycle = self._lifecycle_view()
                    try:
                        if lifecycle:lifecycle.validate_references(lifecycle_state[0], record_sha)
                    finally:
                        if lifecycle:lifecycle.close()
                    require(self._lifecycle_state() == lifecycle_state)
                    self._write(request_path, transition)
                    desired = {"protocol": 2, "installation": self.installation, "operation": operation,
                               "generation_sha256": record_sha, "transition_sha256": sha(transition)}
                    require(self._current() == current)
                    require(self._observe() == observed)
                    lease.check()
                    require(self._lifecycle_state() == lifecycle_state)
                    self._write(self.pointer, desired, replace=True)
                # A pointer without this separately retained completion remains
                # stopped/uncertain. Resume reobserves both exclusions and facts.
                require(self._observe() == observed)
                lease.check()
                require(self._lifecycle_state() == lifecycle_state)
                self._write(self.receipts / (operation + ".json"),
                            {"protocol": 2, "installation": self.installation, "pointer_sha256": sha(desired), "status": "complete"})
                require(self._current() == desired and self._complete(desired))
                require(self._observe() == observed)
                lease.check()
                require(self._lifecycle_state() == lifecycle_state)
                return {"generation_publication_established": True, "installation_readiness_established": False,
                        "pointer": desired, "binding_sha256": self.expected, "scope": observed["scope"]}
