"""Serialize successive native upgrades while retaining sealed terminal journals."""
import hashlib
import json
import os
from pathlib import Path
import stat
import uuid

from upgrade_journal import (UpgradeJournal, UpgradeRefused, canonical, fcntl,
                             require, unique_object, validate_intent)

MAX_OPERATIONS = 128
MAX_HISTORY_BYTES = 524_288


class UpgradeHistory:
    """A dedicated private history directory; the lock spans the whole operation."""
    def __init__(self, directory, operation, intent):
        self.guard = UpgradeJournal(directory, operation, intent)
        self.directory = self.guard.directory
        self.operation = operation
        self.intent = self.guard.intent
        self.path = self.directory / "upgrade-history-v1.json"
        self.operations = self.directory / "operations"
        self.lock = None
        self.journal = None

    def _read(self, path, maximum):
        descriptor = self.guard._private_open(path, os.O_RDONLY)
        with os.fdopen(descriptor, "rb") as source:
            require(os.fstat(source.fileno()).st_size <= maximum)
            data = source.read(maximum + 1)
        require(len(data) <= maximum)
        return data

    def _load(self):
        value = json.loads(self._read(self.path, MAX_HISTORY_BYTES), object_pairs_hook=unique_object)
        require(isinstance(value, dict) and set(value) == {"protocol", "installation", "bindings_sha256", "operations"})
        require(type(value["protocol"]) is int and value["protocol"] == 1)
        entries = value["operations"]
        require(isinstance(entries, list) and 1 <= len(entries) <= MAX_OPERATIONS)
        seen = set()
        previous = None
        for number, entry in enumerate(entries):
            require(isinstance(entry, dict) and set(entry) == {"operation", "intent", "journal_sha256"})
            operation = entry["operation"]
            require(isinstance(operation, str) and str(uuid.UUID(operation)) == operation and operation not in seen)
            seen.add(operation)
            intent = validate_intent(entry["intent"])
            require(intent["installation"] == value["installation"] and intent["bindings_sha256"] == value["bindings_sha256"])
            if previous:
                require(intent["old_candidate"] == previous["candidate"] and intent["old_artifact_sha256"] == previous["artifact"])
            directory = self.operations / operation
            terminal = number < len(entries) - 1
            if terminal:
                self._private_directory(directory)
                data = self._read(directory / "upgrade-journal-v1.json", 1_048_576)
                require(entry["journal_sha256"] == hashlib.sha256(data).hexdigest())
                status = UpgradeJournal.read_status(directory, operation, intent)
                require(status["status"] in {"complete", "recovered"})
                prefix = "new" if status["status"] == "complete" else "old"
                previous = {"candidate": intent[prefix + "_candidate"], "artifact": intent[prefix + "_artifact_sha256"]}
            else:
                require(entry["journal_sha256"] is None)
        require({p.name for p in self.operations.iterdir()} <= seen)
        return value

    def _save(self, value):
        data = canonical(value) + b"\n"
        require(len(data) <= MAX_HISTORY_BYTES)
        temporary = self.directory / (".upgrade-history-" + str(uuid.uuid4()) + ".partial")
        descriptor = self.guard._private_open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        with os.fdopen(descriptor, "wb") as target:
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, self.path)
        self._sync(self.directory)

    @staticmethod
    def _sync(directory):
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _private_directory(self, directory):
        require(directory.resolve() == directory)
        value = directory.lstat()
        require(stat.S_ISDIR(value.st_mode) and value.st_uid == os.getuid() and not value.st_mode & 0o077)

    def __enter__(self):
        self.lock = self.guard._private_open(self.directory / ".upgrade-history-lock-v1", os.O_RDWR | os.O_CREAT)
        try:
            try:
                fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise UpgradeRefused("Native installation upgrade is already owned") from None
            if not self.operations.exists() and not self.operations.is_symlink():
                self.operations.mkdir(mode=0o700)
                self._sync(self.directory)
            self._private_directory(self.operations)
            if self.path.exists() or self.path.is_symlink():
                value = self._load()
                require(value["installation"] == self.intent["installation"] and value["bindings_sha256"] == self.intent["bindings_sha256"])
                entries = value["operations"]
                last = entries[-1]
                if last["operation"] == self.operation:
                    require(last["intent"] == self.intent)
                else:
                    require(self.operation not in {e["operation"] for e in entries} and len(entries) < MAX_OPERATIONS)
                    previous_directory = self.operations / last["operation"]
                    require(previous_directory.is_dir() and not previous_directory.is_symlink())
                    require((previous_directory / "upgrade-journal-v1.json").is_file())
                    previous = UpgradeJournal(previous_directory, last["operation"], last["intent"])
                    # Keep the previous journal's lock until its exact terminal bytes are sealed.
                    descriptor = previous._private_open(previous_directory / ".upgrade-lock-v1", os.O_RDWR | os.O_CREAT)
                    try:
                        try:
                            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        except BlockingIOError:
                            raise UpgradeRefused("Previous native upgrade is still owned") from None
                        status = UpgradeJournal.read_status(previous_directory, last["operation"], last["intent"])
                        require(status["status"] in {"complete", "recovered"})
                        prefix = "new" if status["status"] == "complete" else "old"
                        require(self.intent["old_candidate"] == last["intent"][prefix + "_candidate"])
                        require(self.intent["old_artifact_sha256"] == last["intent"][prefix + "_artifact_sha256"])
                        data = self._read(previous.path, 1_048_576)
                        last["journal_sha256"] = hashlib.sha256(data).hexdigest()
                        entries.append({"operation": self.operation, "intent": self.intent, "journal_sha256": None})
                        self._save(value)
                    finally:
                        os.close(descriptor)
            else:
                require(not list(self.operations.iterdir()))
                value = {"protocol": 1, "installation": self.intent["installation"], "bindings_sha256": self.intent["bindings_sha256"],
                         "operations": [{"operation": self.operation, "intent": self.intent, "journal_sha256": None}]}
                self._save(value)
            # Durable reservation precedes creation/claim. A lost acknowledgement never starts an action.
            directory = self.operations / self.operation
            if not directory.exists() and not directory.is_symlink():
                directory.mkdir(mode=0o700)
                self._sync(self.operations)
            self._private_directory(directory)
            self.journal = UpgradeJournal(directory, self.operation, self.intent)
            return self.journal.__enter__()
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, kind, value, trace):
        if self.journal is not None:
            self.journal.__exit__(kind, value, trace)
            self.journal = None
        if self.lock is not None:
            os.close(self.lock)
            self.lock = None

    @classmethod
    def read_history(cls, directory, operation, intent):
        """Read without claiming an operation or changing its retained journal."""
        history = cls(directory, operation, intent)
        history._private_directory(history.operations)
        value = history._load()
        require(value["installation"] == history.intent["installation"] and value["bindings_sha256"] == history.intent["bindings_sha256"])
        require(value["operations"][-1]["operation"] == operation and value["operations"][-1]["intent"] == history.intent)
        result = []
        for entry in value["operations"]:
            path = history.operations / entry["operation"]
            require(not path.is_symlink())
            if path.exists():
                history._private_directory(path)
            if entry is value["operations"][-1] and (not path.exists() or not (path / "upgrade-journal-v1.json").exists()):
                require(not (path / "upgrade-journal-v1.json").is_symlink())
                status = {"stage": None, "status": "reserved", "events": 0}
            else:
                status = UpgradeJournal.read_status(path, entry["operation"], entry["intent"])
            result.append({"operation": entry["operation"], "old_candidate": entry["intent"]["old_candidate"],
                           "new_candidate": entry["intent"]["new_candidate"], "journal_sha256": entry["journal_sha256"], **status})
        return {"protocol": 1, "installation": value["installation"], "operations": result,
                "limitations": ["History coordinates responsibility; it does not execute or verify installed activation."]}
