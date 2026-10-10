"""Fixed first-install responsibility; no previous release or executable callbacks."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import uuid

from upgrade_journal import (canonical, fcntl, now, owner, owner_alive,
                             unique_object, validate_owner, validate_time)

STAGES = ("inspect", "stage", "migrate", "bootstrap", "verify", "activate", "enroll")
ERRORS = dict(zip(STAGES, ("artifact_refused", "staging_failed", "migration_failed", "bootstrap_failed",
                          "functional_probe_failed", "activation_failed", "handoff_failed")))
MAX_EVENTS = 256
MAX_BYTES = 524_288


class EnrollmentRefused(Exception):
    pass


def require(value):
    if not value:
        raise EnrollmentRefused("Native initial enrollment journal refused")


def identity(value):
    require(isinstance(value, str))
    try:
        parsed = str(uuid.UUID(value))
    except ValueError:
        raise EnrollmentRefused("Native initial enrollment identity refused") from None
    require(parsed == value)


def digest(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value))


def validate_intent(value):
    require(isinstance(value, dict) and set(value) == {
        "installation", "candidate", "artifact_sha256", "allocation_sha256", "inputs_sha256"})
    identity(value["installation"])
    require(isinstance(value["candidate"], str) and re.fullmatch(r"[0-9a-f]{40}", value["candidate"]))
    for name in ["artifact_sha256", "allocation_sha256", "inputs_sha256"]:
        digest(value[name])
    return copy.deepcopy(value)


def current_owner():
    return {**owner(), "mount_namespace": os.readlink("/proc/self/ns/mnt"),
            "cgroup_namespace": os.readlink("/proc/self/ns/cgroup")}


def validate_initial_owner(value):
    require(isinstance(value, dict) and set(value) == {
        "uid", "pid", "birth", "boot_id", "mount_namespace", "cgroup_namespace"})
    validate_owner({key: value[key] for key in ["uid", "pid", "birth", "boot_id"]})
    require(value["uid"] == os.getuid())
    for name, prefix in [("mount_namespace", "mnt"), ("cgroup_namespace", "cgroup")]:
        require(isinstance(value[name], str) and re.fullmatch(prefix + r":\[[0-9]+\]", value[name]))


def initial_owner_alive(value):
    if not owner_alive(value):
        return False
    try:
        return all(os.readlink(f"/proc/{value['pid']}/ns/{name}") == value[field]
                   for name, field in [("mnt", "mount_namespace"), ("cgroup", "cgroup_namespace")])
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return False


def validate_receipt(value, *, reconciled=False):
    require(isinstance(value, dict) and set(value) == ({"receipt_sha256", "applied"} if reconciled else {"receipt_sha256"}))
    digest(value["receipt_sha256"])
    if reconciled:
        require(type(value["applied"]) is bool)


class EnrollmentJournal:
    """One bound request, one OS lock, ordered stages and explicit uncertainty."""
    def __init__(self, directory, operation, intent, request_sha256):
        require(sys.platform == "linux" and fcntl is not None)
        self.directory = Path(directory)
        require(self.directory.is_absolute() and self.directory.resolve() == self.directory)
        self.directory_identity = self._directory_identity()
        identity(operation)
        self.operation = operation
        self.intent = validate_intent(intent)
        digest(request_sha256)
        request = {"protocol": 1, "purpose": "native_initial_enrollment", "operation": operation, "intent": self.intent}
        require(hashlib.sha256(canonical(request)).hexdigest() == request_sha256)
        self.request_sha256 = request_sha256
        self.path = self.directory / "initial-enrollment-v1.json"
        self.lock_path = self.directory / ".initial-enrollment-lock-v1"
        self.lock = None
        self.record = None
        self.usable = True
        self.expected_digest = None

    def _directory_identity(self):
        require(self.directory.resolve() == self.directory)
        value = self.directory.lstat()
        require(stat.S_ISDIR(value.st_mode) and value.st_uid == os.getuid() and not value.st_mode & 0o077)
        return value.st_dev, value.st_ino, value.st_uid

    def _open(self, path, flags):
        require(self._directory_identity() == self.directory_identity)
        fd = os.open(path, flags | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        value = os.fstat(fd)
        if not (stat.S_ISREG(value.st_mode) and value.st_uid == os.getuid() and
                value.st_nlink == 1 and not value.st_mode & 0o077):
            os.close(fd)
            raise EnrollmentRefused("Native enrollment record custody refused")
        return fd

    def _read(self):
        with os.fdopen(self._open(self.path, os.O_RDONLY), "rb") as source:
            require(0 < os.fstat(source.fileno()).st_size <= MAX_BYTES)
            raw = source.read(MAX_BYTES + 1)
        require(len(raw) <= MAX_BYTES)
        return raw

    def _lock_identity(self):
        named = self.lock_path.lstat()
        require(stat.S_ISREG(named.st_mode) and named.st_uid == os.getuid() and
                not named.st_mode & 0o077 and named.st_nlink == 1)
        if self.lock is not None:
            opened = os.fstat(self.lock)
            require((opened.st_dev, opened.st_ino, opened.st_uid) ==
                    (named.st_dev, named.st_ino, named.st_uid))
        return [named.st_dev, named.st_ino, named.st_uid]

    def __enter__(self):
        require(self.lock is None and self.usable)
        self.lock = self._open(self.lock_path, os.O_RDWR | os.O_CREAT)
        try:
            try:
                fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise EnrollmentRefused("Initial enrollment is already owned") from None
            if self.path.exists() or self.path.is_symlink():
                raw = self._read()
                self.record = json.loads(raw, object_pairs_hook=unique_object)
                self.expected_digest = hashlib.sha256(raw).hexdigest()
                self._validate()
                if self.record["status"] == "complete":
                    return self  # Exact terminal replay does not append another claim.
                if self.record["status"] == "running":
                    self.record["status"] = "uncertain"
                    self._event("interrupted", {})
            else:
                self.record = {"protocol": 1, "purpose": "native_initial_enrollment", "operation": self.operation,
                               "intent": self.intent, "request_sha256": self.request_sha256,
                               "lock_identity": self._lock_identity(),
                               "created_at": now(), "owner": current_owner(), "epoch": 0,
                               "stage": None, "status": "pending", "completed": [], "events": []}
            require(len(self.record["events"]) < MAX_EVENTS - 1)
            self.record["epoch"] += 1
            self.record["owner"] = current_owner()
            self._event("claimed", {})
            self._save()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, kind, value, trace):
        if self.lock is not None:
            os.close(self.lock)
            self.lock = None

    def _event(self, kind, evidence):
        require(len(self.record["events"]) < MAX_EVENTS)
        self.record["events"].append({"kind": kind, "at": now(), "stage": self.record["stage"],
                                      "owner": current_owner(), "epoch": self.record["epoch"], "evidence": evidence})

    def _validate(self):
        v = self.record
        require(isinstance(v, dict) and set(v) == {"protocol", "purpose", "operation", "intent", "request_sha256",
                "lock_identity", "created_at", "owner", "epoch", "stage", "status", "completed", "events"})
        require(type(v["protocol"]) is int and v["protocol"] == 1 and v["purpose"] == "native_initial_enrollment")
        require(v["operation"] == self.operation and validate_intent(v["intent"]) == self.intent and v["request_sha256"] == self.request_sha256)
        validate_time(v["created_at"])
        require(isinstance(v["lock_identity"], list) and len(v["lock_identity"]) == 3 and
                all(type(n) is int and n >= 0 for n in v["lock_identity"]) and
                v["lock_identity"] == self._lock_identity())
        validate_initial_owner(v["owner"])
        require(type(v["epoch"]) is int and 1 <= v["epoch"] <= MAX_EVENTS)
        require(isinstance(v["events"], list) and 1 <= len(v["events"]) <= MAX_EVENTS)
        stage, status, completed, epoch, claimed_owner = None, "pending", [], 0, None
        for e in v["events"]:
            require(isinstance(e, dict) and set(e) == {"kind", "at", "stage", "owner", "epoch", "evidence"})
            validate_time(e["at"])
            validate_initial_owner(e["owner"])
            require(type(e["epoch"]) is int)
            kind, evidence = e["kind"], e["evidence"]
            if kind == "claimed":
                require(status in {"pending", "failed", "uncertain"} and e["epoch"] == epoch + 1 and e["stage"] == stage and evidence == {})
                epoch, claimed_owner = e["epoch"], e["owner"]
            elif kind == "interrupted":
                require(status == "running" and e["epoch"] == epoch and e["stage"] == stage and evidence == {})
                status = "uncertain"
            else:
                require(e["epoch"] == epoch and e["owner"] == claimed_owner)
                if kind == "started":
                    require(status in {"pending", "failed"} and len(completed) < len(STAGES) and evidence == {})
                    stage = STAGES[len(completed)]
                    require(e["stage"] == stage)
                    status = "running"
                elif kind in {"succeeded", "reconciled"}:
                    require(len(completed) < len(STAGES) and e["stage"] == stage == STAGES[len(completed)])
                    require(status == ("running" if kind == "succeeded" else "uncertain"))
                    validate_receipt(evidence, reconciled=kind == "reconciled")
                    if kind == "succeeded" or evidence["applied"]:
                        completed.append(stage)
                        status = "complete" if len(completed) == len(STAGES) else "pending"
                    else:
                        status = "failed"
                elif kind == "failed":
                    require(status == "running" and e["stage"] == stage and isinstance(evidence, dict) and
                            set(evidence) == {"code"} and evidence["code"] == ERRORS[stage])
                    status = "failed"
                else:
                    raise EnrollmentRefused("Unknown initial enrollment event")
        require((v["stage"], v["status"], v["completed"], v["epoch"], v["owner"]) ==
                (stage, status, completed, epoch, claimed_owner))
        require(len(canonical(v)) <= MAX_BYTES)

    def _owned(self):
        require(self.lock is not None and self.usable and self.record["owner"] == current_owner())
        self._validate()
        require(len(self.record["events"]) < MAX_EVENTS and self._directory_identity() == self.directory_identity)
        require(hashlib.sha256(self._read()).hexdigest() == self.expected_digest)

    def _persist(self):
        raw = canonical(self.record) + b"\n"
        partial = self.directory / (".initial-enrollment-" + str(uuid.uuid4()) + ".partial")
        with os.fdopen(self._open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL), "wb") as target:
            target.write(raw)
            target.flush()
            os.fsync(target.fileno())
        os.replace(partial, self.path)
        fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        self.expected_digest = hashlib.sha256(raw).hexdigest()

    def _save(self):
        require(self.lock is not None and self.usable)
        self._validate()
        try:
            self._persist()
        except BaseException:
            self.usable = False
            raise

    def begin(self, stage):
        self._owned()
        require(self.record["status"] in {"pending", "failed"} and len(self.record["completed"]) < len(STAGES))
        require(stage == STAGES[len(self.record["completed"])])
        self.record.update(stage=stage, status="running")
        self._event("started", {})
        self._save()

    def succeed(self, stage, evidence):
        self._owned()
        validate_receipt(evidence)
        require(self.record["status"] == "running" and stage == self.record["stage"])
        self.record["completed"].append(stage)
        self.record["status"] = "complete" if stage == STAGES[-1] else "pending"
        self._event("succeeded", copy.deepcopy(evidence))
        self._save()

    def fail(self, code):
        self._owned()
        require(self.record["status"] == "running" and code == ERRORS[self.record["stage"]])
        self.record["status"] = "failed"
        self._event("failed", {"code": code})
        self._save()

    def reconcile(self, *, applied, evidence):
        self._owned()
        validate_receipt(evidence)
        require(type(applied) is bool and self.record["status"] == "uncertain")
        stage = self.record["stage"]
        if applied:
            self.record["completed"].append(stage)
            self.record["status"] = "complete" if stage == STAGES[-1] else "pending"
        else:
            self.record["status"] = "failed"
        self._event("reconciled", {**evidence, "applied": applied})
        self._save()

    def status(self):
        require(self.record is not None and self.usable)
        self._validate()
        alive = initial_owner_alive(self.record["owner"])
        return {"protocol": 1, "purpose": "native_initial_enrollment", "installation": self.intent["installation"],
                "operation": self.operation, "candidate": self.intent["candidate"], "stage": self.record["stage"],
                "status": "uncertain" if self.record["status"] == "running" and not alive else self.record["status"],
                "recorded_status": self.record["status"], "completed": list(self.record["completed"]),
                "epoch": self.record["epoch"], "events": len(self.record["events"]), "owner_alive": alive,
                "limitations": ["Responsibility metadata only; no fresh artifact, allocation, access or readiness proof.",
                                "Owner liveness does not establish who holds the exclusive OS lock."]}

    @classmethod
    def read_status(cls, directory, operation, intent, request_sha256):
        journal = cls(directory, operation, intent, request_sha256)
        journal.record = json.loads(journal._read(), object_pairs_hook=unique_object)
        return journal.status()
