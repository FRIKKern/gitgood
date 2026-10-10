"""First-install ownership under the existing installation-wide lifecycle lock."""
import json
import hashlib
import os
import stat
import uuid

from enrollment_journal import EnrollmentJournal
from native_allocation import scope_identity
from retirement_snapshot import retained_file_identity
from stage_native_artifact import publish_directory, sync_directory
from upgrade_journal import canonical, fcntl, require, unique_object


class NativeEnrollmentCustody:
    def __init__(self, inputs):
        self.inputs = inputs
        self.directory = inputs.root / "history"
        self.journal = EnrollmentJournal(self.directory, inputs.request["operation"], inputs.intent, inputs.request_sha256)
        self.path = self.directory / "initial-lifecycle-anchor-v1.json"
        self.shared_path = self.directory / ".upgrade-history-lock-v1"
        self.shared = None
        self.shared_identity = None
        self.anchor_identity = None
        self.usable = True

    def _shared_identity(self):
        require(self.shared is not None)
        named = self.shared_path.lstat()
        opened = os.fstat(self.shared)
        require(stat.S_ISREG(named.st_mode) and named.st_uid == os.getuid() and
                named.st_nlink == 1 and not named.st_mode & 0o077)
        require((named.st_dev, named.st_ino, named.st_uid) == (opened.st_dev, opened.st_ino, opened.st_uid))
        return [named.st_dev, named.st_ino, named.st_uid]

    def _anchor(self):
        expected = {"protocol": 1, "purpose": "native_initial_lifecycle", "installation": self.inputs.intent["installation"],
                    "operation": self.inputs.request["operation"], "request_sha256": self.inputs.request_sha256,
                    "shared_lock_identity": self.shared_identity}
        if self.path.exists() or self.path.is_symlink():
            observed = json.loads(self._anchor_bytes(), object_pairs_hook=unique_object)
            require(isinstance(observed, dict) and set(observed) == set(expected))
            require(type(observed["protocol"]) is int and
                    isinstance(observed["shared_lock_identity"], list) and
                    all(type(part) is int for part in observed["shared_lock_identity"]))
            require(observed == expected)
        else:
            require(not self.journal.path.exists() and not self.journal.path.is_symlink())
            temporary = self.directory / (".initial-lifecycle-anchor-" + str(uuid.uuid4()) + ".partial")
            with os.fdopen(self.journal._open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL), "wb") as output:
                output.write(canonical(expected) + b"\n")
                output.flush()
                os.fsync(output.fileno())
            # Linux RENAME_NOREPLACE applies to this private regular file as well
            # as the staged directories owned by the same publication helper.
            publish_directory(temporary, self.path)
            sync_directory(self.directory)
        self.anchor_identity = retained_file_identity(self.path, 16_384)

    def _anchor_bytes(self):
        from native_inventory import private_bytes
        return private_bytes(self.path, 16_384)

    def __enter__(self):
        require(self.shared is None and self.usable)
        self.inputs.observe_inputs()
        require(scope_identity() == self.inputs.allocation["scope"])
        self.shared = self.journal._open(self.shared_path, os.O_RDWR | os.O_CREAT)
        try:
            try:
                fcntl.flock(self.shared, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                require(False)
            self.shared_identity = self._shared_identity()
            for name in ["upgrade-history-v1.json", "retirement-journal-v1.json"]:
                require(not (self.directory / name).exists() and not (self.directory / name).is_symlink())
            self._anchor()
            self.journal.__enter__()
            return self
        except BaseException:
            self.usable = False
            self.__exit__(None, None, None)
            raise

    def check(self, *, terminal=False):
        """Recheck held custody without granting a particular stage action."""
        require(type(terminal) is bool)
        require(self.usable and self.shared is not None)
        self.inputs.observe_inputs()
        require(self._shared_identity() == self.shared_identity)
        require(retained_file_identity(self.path, 16_384) == self.anchor_identity)
        require(scope_identity() == self.inputs.allocation["scope"])
        if terminal:
            require(self.journal.lock is not None and self.journal.usable)
            self.journal._validate()
            require(self.journal.record["status"] == "complete")
            require(hashlib.sha256(self.journal._read()).hexdigest() == self.journal.expected_digest)
        else:
            self.journal._owned()

    def owned(self, stages, *, observation=False):
        require(type(observation) is bool and isinstance(stages, (tuple, list, set)) and
                all(isinstance(stage, str) for stage in stages))
        self.check()
        require(self.journal.record["stage"] in stages)
        require(self.journal.record["status"] in ({"running", "uncertain", "failed"} if observation else {"running"}))

    def __exit__(self, kind, value, trace):
        self.journal.__exit__(kind, value, trace)
        if self.shared is not None:
            os.close(self.shared)
            self.shared = None
