"""Read-only worker admission against a completed, unchanged generation.

This does not acquire a writer lease or authorize lifecycle effects. Read before
starting the application lease; database identity queries retain no session.
"""
import itertools
import os
from pathlib import Path

from generation_custody import GenerationRecordCustody, CustodyRefused
from generation_publication import GenerationPublication, PublicationRefused, require, sha
from native_durable_binding import persistent_identity, BindingRefused
from native_durable_database import DatabaseRefused
from native_service_scope import ServiceRefused
from native_worker_scope import observe_worker
from resource_generations import GenerationRefused


class GenerationAdmissionRefused(Exception):
    pass


class _ReadOnlyCustody(GenerationRecordCustody):
    """Observe the existing lock identity without taking it or creating a store.

    The controller may retain its lifecycle lock while starting a worker. Taking
    that lock here would deadlock admission. Live worker scope, complete current
    publication and repeated snapshots are required separately.
    """
    def __enter__(self):
        require(self.usable and self.lock is None)
        self._history()
        try:
            self.lock = self._open(self.lock_path, os.O_RDONLY)
            info = os.fstat(self.lock)
            require({"device": info.st_dev, "inode": info.st_ino, "uid": info.st_uid} == self.expected_lock_identity)
            self.lock_identity = (info.st_dev, info.st_ino, info.st_uid)
            self.store_identity = self._identity(self.store)
            self.check()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def retain(self, record):
        raise GenerationAdmissionRefused("Read-only generation admission cannot retain records")


class NativeGenerationReader(GenerationPublication):
    """Reuse the publication validator with strictly read-only file custody.

    Allocation independently supplies the expected durable digest, history/lock,
    unit, runtime paths and limits. A stored digest never supplies that authority.
    Only the current publication-only profile is admitted; partial files and any
    lifecycle responsibility require explicit reconciliation before admission.
    """
    def __init__(self, *args, **options):
        super().__init__(*args, **options)
        original = self.custody
        self.custody = _ReadOnlyCustody(self.directory, self.installation,
                                       original.identity, original.expected_lock_identity)

    def publish(self, **options):
        raise GenerationAdmissionRefused("Read-only generation admission cannot publish")

    def _write(self, *args, **options):
        raise GenerationAdmissionRefused("Read-only generation admission cannot write")

    def close(self):
        self.custody.__exit__(None, None, None)

    def _layout(self):
        policy = Path('/etc/gitgood/installations')/self.installation/'lifecycle-worker-admission-v2.json'
        require(not policy.exists() and not policy.is_symlink())
        expected = {".upgrade-history-lock-v1", "generation-records-v2", "durable-binding-v2.json",
                    "current-generation-v2.json", "generation-transitions-v2", "generation-receipts-v2"}
        paths = list(itertools.islice(self.directory.iterdir(), 7))
        require(len(paths) == 6 and {path.name for path in paths} == expected)
        for path in [self.custody.store, self.transitions, self.receipts]:
            identity = self.custody._identity(path)
            if path in self.directory_identities:
                require(self.directory_identities[path] == identity)
            else:
                self.directory_identities[path] = identity
            self._entries(path)
        self._check()

    def _entries(self, directory):
        entries = list(itertools.islice(directory.iterdir(), 1025))
        require(len(entries) <= 1024 and all(not entry.name.startswith(".partial-") for entry in entries))
        return entries

    def _fingerprint(self):
        """Bind individual file identities and complete bounded directory names."""
        self._layout()
        paths = [self.custody.lock_path, self.directory / "durable-binding-v2.json", self.pointer]
        for directory in [self.custody.store, self.transitions, self.receipts]:
            paths.extend(self._entries(directory))
        result = {}
        for path in paths:
            info = path.lstat()
            result[str(path.relative_to(self.directory))] = tuple(getattr(info, field) for field in
                ["st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_uid", "st_mode", "st_nlink"])
        self._check()
        return result

    def _snapshot(self, scope):
        before = self._fingerprint()
        binding = self._read(self.directory / "durable-binding-v2.json")
        require(sha(binding) == self.expected)
        records = self.custody._records()
        require(0 < len(records) <= 128 and all(record["durable_binding_sha256"] == self.expected for record in records.values()))
        self._inventory(records)
        current = self._current()
        require(current is not None and self._complete(current))
        used = {record["predecessor_sha256"] for record in records.values()}
        tips = [key for key in records if key not in used]
        require(tips == [current["generation_sha256"]])
        require(sum(record["predecessor_sha256"] is not None for record in records.values()) == len(used - {None}))
        record = records[current["generation_sha256"]]
        require(record["scope"] == scope)
        transitions = {path.name: self._read(path) for path in self._entries(self.transitions)}
        receipts = {path.name: self._read(path) for path in self._entries(self.receipts)}
        require(self._fingerprint() == before)
        return {"binding": binding, "pointer": current, "record": record,
                "records": records, "transitions": transitions, "receipts": receipts, "files": before}

    def admit(self, *, worker, owner_pid):
        """Admit an actual worker to a completed generation before lease startup."""
        try:
            observed = observe_worker(self.installation, self.unit, worker=worker, owner_pid=owner_pid, **self.options)
            scope = observed["service_scope"]
            with self.custody:
                first = self._snapshot(scope)
                binding = persistent_identity(self.root, scope, self.executables)
                require(binding == first["binding"] and sha(binding) == self.expected)
                require(persistent_identity(self.root, scope, self.executables) == binding)
                require(observe_worker(self.installation, self.unit, worker=worker, owner_pid=owner_pid, **self.options) == observed)
                require(self._snapshot(scope) == first)
                self._check()
                return {"published_generation_admitted": True, "writer_exclusion_established": False,
                        "installation_readiness_established": False, "lifecycle_responsibility_admitted": False,
                        "pointer": first["pointer"], "binding_sha256": self.expected,
                        "worker_observation": observed}
        except GenerationAdmissionRefused:
            raise
        except (PublicationRefused, CustodyRefused, BindingRefused, DatabaseRefused,
                ServiceRefused, GenerationRefused, OSError, ValueError, TypeError,
                KeyError, UnicodeError, RecursionError):
            raise GenerationAdmissionRefused("Published native generation unavailable, incomplete or changed") from None
