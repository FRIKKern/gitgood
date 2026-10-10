"""Immutable generation-record custody under the existing installation OS lock.

Retaining a record does not publish a generation or establish database writer
exclusion. Actual continuity and lifecycle reconciliation remain caller duties.
"""
import hashlib
import itertools
import os
from pathlib import Path
import stat
import uuid

from resource_generations import (GenerationRefused, canonical, identifier,
                                  parse_generation, validate_generation,
                                  validate_successor)
from stage_native_artifact import publish_directory, sync_directory
from upgrade_journal import fcntl


class CustodyRefused(Exception):
    pass


def require(value):
    if not value:
        raise CustodyRefused("Native generation record custody refused")


class GenerationRecordCustody:
    """Retain closed records without replacing earlier responsibility.

    The caller independently supplies the previously observed history directory
    identity. This low-level store accepts a private directory; it grants no
    installation, process, database or active-generation authority.
    """
    def __init__(self, directory, installation, expected_identity, expected_lock_identity):
        try:
            identifier(installation)
        except GenerationRefused:
            raise CustodyRefused("Native generation record custody refused") from None
        require(type(expected_identity) is dict and set(expected_identity) == {"device", "inode", "uid"})
        require(all(type(value) is int and value > 0 for value in expected_identity.values()))
        require(type(expected_lock_identity) is dict and set(expected_lock_identity) == {"device", "inode", "uid"})
        require(all(type(value) is int and value > 0 for value in expected_lock_identity.values()))
        require(expected_lock_identity["uid"] == expected_identity["uid"])
        self.directory = Path(directory)
        require(self.directory.is_absolute() and self.directory.resolve(strict=True) == self.directory)
        require(os.getuid() == os.geteuid() == expected_identity["uid"])
        self.installation = installation
        self.identity = expected_identity.copy()
        self.expected_lock_identity = expected_lock_identity.copy()
        self.store = self.directory / "generation-records-v2"
        self.lock_path = self.directory / ".upgrade-history-lock-v1"
        self.lock = None
        self.lock_identity = None
        self.store_identity = None
        self.usable = True
        self._history()

    def _identity(self, path):
        require(path.resolve(strict=True) == path)
        value = path.lstat()
        require(stat.S_ISDIR(value.st_mode) and value.st_uid == os.getuid() and stat.S_IMODE(value.st_mode) == 0o700)
        return {"device": value.st_dev, "inode": value.st_ino, "uid": value.st_uid}

    def _history(self):
        require(self._identity(self.directory) == self.identity)

    def _open(self, path, flags):
        descriptor = os.open(path, flags | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, 0o600)
        try:
            opened, named = os.fstat(descriptor), path.lstat()
            require(stat.S_ISREG(opened.st_mode) and opened.st_uid == os.getuid() and opened.st_nlink == 1)
            require(stat.S_IMODE(opened.st_mode) == 0o600)
            require((opened.st_dev, opened.st_ino) == (named.st_dev, named.st_ino))
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    def __enter__(self):
        require(self.usable and self.lock is None and fcntl is not None)
        self._history()
        try:
            # Allocation/previous custody establishes the lock independently.
            # Creating a replacement here could bypass a retained old owner.
            self.lock = self._open(self.lock_path, os.O_RDWR)
            info = os.fstat(self.lock)
            require({"device": info.st_dev, "inode": info.st_ino, "uid": info.st_uid} == self.expected_lock_identity)
            try:
                fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise CustodyRefused("Native installation lifecycle is already owned") from None
            self.lock_identity = (info.st_dev, info.st_ino, info.st_uid)
            self._history()
            if not self.store.exists() and not self.store.is_symlink():
                self.store.mkdir(mode=0o700)
                sync_directory(self.directory)
            self.store_identity = self._identity(self.store)
            self.check()
            return self
        except BaseException:
            self.usable = False
            self.__exit__(None, None, None)
            raise

    def __exit__(self, kind, value, trace):
        if self.lock is not None:
            os.close(self.lock)
            self.lock = None
        self.usable = False

    def check(self):
        require(self.usable and self.lock is not None)
        self._history()
        require(self._identity(self.store) == self.store_identity)
        named, opened = self.lock_path.lstat(), os.fstat(self.lock)
        for info in [named, opened]:
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1)
            require(stat.S_IMODE(info.st_mode) == 0o600)
            require((info.st_dev, info.st_ino, info.st_uid) == self.lock_identity)

    def _read(self, path):
        descriptor = self._open(path, os.O_RDONLY)
        with os.fdopen(descriptor, "rb") as source:
            before = os.fstat(source.fileno())
            require(0 < before.st_size <= 16_384)
            raw = source.read(16_385)
            after = os.fstat(source.fileno())
        require(len(raw) == before.st_size)
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_mode", "st_nlink")
        require(all(getattr(before, field) == getattr(after, field) for field in fields))
        try:
            value = parse_generation(raw)
        except GenerationRefused:
            raise CustodyRefused("Native generation record custody refused") from None
        require(value["installation"] == self.installation and raw == canonical(value))
        return raw, value

    def _paths(self):
        paths = list(itertools.islice(self.store.iterdir(), 1025))
        require(len(paths) <= 1024)
        return paths

    def _records(self):
        self.check()
        paths = self._paths()
        records, generations = {}, set()
        for path in paths:
            name = path.name
            if name.startswith(".partial-"):
                try:
                    identifier(name[len(".partial-"):])
                except GenerationRefused:
                    raise CustodyRefused("Native generation record custody refused") from None
                # Interrupted files stay retained. Never infer completed custody
                # or publication from their names or contents.
                descriptor = self._open(path, os.O_RDONLY)
                try:
                    require(os.fstat(descriptor).st_size <= 16_384)
                finally:
                    os.close(descriptor)
                continue
            require(len(name) == 69 and name.endswith(".json") and all(c in "0123456789abcdef" for c in name[:-5]))
            raw, record = self._read(path)
            digest = hashlib.sha256(raw).hexdigest()
            require(name == digest + ".json" and record["generation"] not in generations)
            generations.add(record["generation"])
            records[digest] = record
        for record in records.values():
            previous = record["predecessor_sha256"]
            if previous is not None:
                require(previous in records)
                try:
                    validate_successor(records[previous], record)
                except GenerationRefused:
                    raise CustodyRefused("Native generation record custody refused") from None
        if records:
            require(sum(value["predecessor_sha256"] is None for value in records.values()) == 1)
            require(len({value["durable_binding_sha256"] for value in records.values()}) == 1)
        self.check()
        return records

    def retain(self, record):
        """Idempotent content-addressed retention, never an active pointer."""
        self.check()
        try:
            validate_generation(record)
            raw = canonical(record)
        except (GenerationRefused, ValueError, TypeError):
            raise CustodyRefused("Native generation record custody refused") from None
        require(record["installation"] == self.installation and len(raw) <= 16_384)
        digest = hashlib.sha256(raw).hexdigest()
        records = self._records()
        if digest in records:
            require(records[digest] == record)
            sync_directory(self.store)
            self.check()
            return {"sha256": digest, "replayed": True, "generation_published": False}
        require(record["generation"] not in {value["generation"] for value in records.values()})
        predecessor = record["predecessor_sha256"]
        if predecessor is None:
            require(not records)
        else:
            require(predecessor in records)
            try:
                validate_successor(records[predecessor], record)
            except GenerationRefused:
                raise CustodyRefused("Native generation record custody refused") from None
        require(len(self._paths()) < 1024)
        temporary = self.store / (".partial-" + str(uuid.uuid4()))
        descriptor = self._open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        with os.fdopen(descriptor, "wb") as target:
            target.write(raw)
            target.flush()
            os.fsync(target.fileno())
        self.check()
        # The existing Linux no-replace primitive preserves earlier records.
        publish_directory(temporary, self.store / (digest + ".json"))
        sync_directory(self.store)
        require(self._records()[digest] == record)
        return {"sha256": digest, "replayed": False, "generation_published": False}
