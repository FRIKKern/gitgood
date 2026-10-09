"""Private, single-host responsibility journal for fixed native upgrade stages."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import uuid

if sys.platform == "linux":
    import fcntl
else:
    fcntl = None


class UpgradeRefused(Exception):
    pass


def require(value):
    if not value:
        raise UpgradeRefused("Native upgrade journal refused")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def owner():
    value = Path("/proc/self/stat").read_text()
    birth = value[value.rfind(")") + 2:].split()[19]
    require(birth.isdecimal())
    return {"uid": os.getuid(), "pid": os.getpid(), "birth": birth}


STAGES = ("inspect", "stage", "maintenance", "migrate", "verify", "activate", "public_verify")
ERRORS = {"artifact_refused", "staging_failed", "stop_failed", "migration_failed",
          "readiness_failed", "functional_probe_failed", "activation_failed",
          "public_probe_failed", "recovery_failed"}


def validate_owner(value):
    require(isinstance(value, dict) and set(value) == {"uid", "pid", "birth"})
    require(type(value["uid"]) is int and 0 <= value["uid"] < 2**32)
    require(type(value["pid"]) is int and 0 < value["pid"] < 2**32)
    require(isinstance(value["birth"], str) and re.fullmatch(r"[0-9]{1,20}", value["birth"]))


def validate_time(value):
    require(isinstance(value, str) and len(value) <= 40)
    parsed = datetime.datetime.fromisoformat(value)
    require(parsed.utcoffset() == datetime.timedelta(0))


def validate_evidence(evidence):
    require(isinstance(evidence, dict) and len(canonical(evidence)) <= 8192)
    for key, value in evidence.items():
        require(isinstance(key, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", key))
        require(type(value) is bool or (type(value) is int and 0 <= value < 2**63) or
                (isinstance(value, str) and (re.fullmatch(r"[0-9a-f]{64}", value) or
                 value in (*STAGES, "recover", *ERRORS))))


def require_receipt(evidence):
    require(isinstance(evidence.get("receipt_sha256"), str) and
            re.fullmatch(r"[0-9a-f]{64}", evidence["receipt_sha256"]))


def validate_intent(intent):
    require(isinstance(intent, dict) and set(intent) == {
        "installation", "old_candidate", "new_candidate", "old_artifact_sha256",
        "new_artifact_sha256", "bindings_sha256", "rollback_policy"})
    require(isinstance(intent["installation"], str))
    require(str(uuid.UUID(intent["installation"])) == intent["installation"])
    for name in ("old_candidate", "new_candidate"):
        require(isinstance(intent[name], str) and re.fullmatch(r"[0-9a-f]{40}", intent[name]))
    for name in ("old_artifact_sha256", "new_artifact_sha256", "bindings_sha256"):
        require(isinstance(intent[name], str) and re.fullmatch(r"[0-9a-f]{64}", intent[name]))
    require(intent["rollback_policy"] in {"same_schema_only", "forward_only"})
    return json.loads(canonical(intent))


class UpgradeJournal:
    """Hold an OS lock; never turn an interrupted action into a successful one."""
    def __init__(self, directory, operation, intent):
        require(fcntl is not None)
        self.directory = Path(directory)
        require(self.directory.is_absolute() and self.directory.resolve() == self.directory)
        info = self.directory.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o077)
        require(isinstance(operation, str) and str(uuid.UUID(operation)) == operation)
        self.operation = operation
        self.intent = validate_intent(intent)
        self.path = self.directory / "upgrade-journal-v1.json"
        self.lock = None
        self.record = None
        self.usable = True

    def _private_open(self, path, flags, mode=0o600):
        descriptor = os.open(path, flags | os.O_NOFOLLOW | os.O_CLOEXEC, mode)
        info = os.fstat(descriptor)
        if not (stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and
                info.st_nlink == 1 and not info.st_mode & 0o077):
            os.close(descriptor)
            raise UpgradeRefused("Native upgrade journal custody refused")
        return descriptor

    def __enter__(self):
        self.lock = self._private_open(self.directory / ".upgrade-lock-v1", os.O_RDWR | os.O_CREAT)
        try:
            try:
                fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise UpgradeRefused("Native upgrade is already owned") from None
            if self.path.exists() or self.path.is_symlink():
                descriptor = self._private_open(self.path, os.O_RDONLY)
                with os.fdopen(descriptor, "rb") as source:
                    require(os.fstat(source.fileno()).st_size <= 1_048_576)
                    self.record = json.loads(source.read(), object_pairs_hook=unique_object)
                self._validate_record()
                require(self.record["operation"] == self.operation and self.record["intent"] == self.intent)
                if self.record["status"] == "running":
                    self.record["status"] = "uncertain"
                    self._event("interrupted", {"stage": self.record["stage"]})
            else:
                self.record = {"protocol": 1, "operation": self.operation, "intent": self.intent,
                               "intent_sha256": hashlib.sha256(canonical(self.intent)).hexdigest(),
                               "stage": None, "status": "pending", "completed": [],
                               "events": [], "created_at": now(), "owner": owner()}
            self.record["owner"] = owner()
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

    def _validate_record(self):
        value = self.record
        require(isinstance(value, dict) and set(value) == {
            "protocol", "operation", "intent", "intent_sha256", "stage", "status",
            "completed", "events", "created_at", "owner"})
        require(type(value["protocol"]) is int and value["protocol"] == 1)
        require(isinstance(value["operation"], str) and str(uuid.UUID(value["operation"])) == value["operation"])
        validate_owner(value["owner"])
        require(value["owner"]["uid"] == os.getuid())
        validate_time(value["created_at"])
        require(validate_intent(value["intent"]) == value["intent"])
        require(value["intent_sha256"] == hashlib.sha256(canonical(value["intent"])).hexdigest())
        require(value["status"] in {"pending", "running", "uncertain", "failed", "complete", "recovered"})
        require(value["stage"] is None or value["stage"] in (*STAGES, "recover"))
        completed = value["completed"]
        require(isinstance(completed, list) and completed == list(STAGES[:len(completed)]))
        require(isinstance(value["events"], list) and len(value["events"]) <= 1000)
        # Replay the fixed protocol: a plausible status string cannot erase an interrupted action.
        stage, status, completed = None, "pending", []
        for event in value["events"]:
            require(isinstance(event, dict) and set(event) == {"kind", "at", "stage", "owner", "evidence"})
            validate_owner(event["owner"])
            require(event["owner"]["uid"] == os.getuid())
            validate_time(event["at"])
            evidence = event["evidence"]
            validate_evidence(evidence)
            kind = event["kind"]
            if kind == "claimed":
                require(event["stage"] == stage and evidence == {})
            elif kind == "started":
                require(status in {"pending", "failed"} and len(completed) < len(STAGES))
                stage = STAGES[len(completed)]
                require(event["stage"] == stage and evidence == {})
                status = "running"
            elif kind == "interrupted":
                require(status == "running" and event["stage"] == stage and evidence == {"stage": stage})
                status = "uncertain"
            elif kind in {"succeeded", "reconciled"}:
                require(len(completed) < len(STAGES) and stage in STAGES and event["stage"] == stage and stage == STAGES[len(completed)])
                require_receipt(evidence)
                require(status == ("running" if kind == "succeeded" else "uncertain"))
                applied = True if kind == "succeeded" else evidence.get("applied")
                require(type(applied) is bool)
                if applied:
                    completed.append(stage)
                    status = "complete" if stage == STAGES[-1] else "pending"
                else:
                    status = "failed"
            elif kind == "failed":
                require(status == "running" and event["stage"] == stage and set(evidence) == {"code"})
                require(evidence["code"] in ERRORS)
                status = "failed"
            elif kind == "recovery_started":
                require(status in {"failed", "uncertain"} and event["stage"] == "recover" and evidence == {})
                stage, status = "recover", "running"
            elif kind == "recovered":
                require(stage == event["stage"] == "recover" and status == "running")
                require_receipt(evidence)
                require(evidence.get("previous_identity_verified") is True and evidence.get("public_functional_probe") is True)
                status = "recovered"
            else:
                raise UpgradeRefused("Unknown native upgrade event")
        require(value["stage"] == stage and value["status"] == status and value["completed"] == completed)
        require(len(canonical(value)) <= 1_048_576)

    def _validate_evidence(self, evidence):
        require(self.lock is not None and self.usable)
        require(len(self.record["events"]) < 1000)
        validate_evidence(evidence)

    def _event(self, kind, evidence):
        # Only digest/count/boolean observations belong in the journal, never payloads or environment.
        self._validate_evidence(evidence)
        self.record["events"].append({"kind": kind, "at": now(), "stage": self.record["stage"],
                                      "owner": owner(), "evidence": evidence})

    def _save(self):
        require(self.lock is not None and self.usable)
        self._validate_record()
        try:
            self._persist()
        except BaseException:
            # Replace/fsync may have succeeded before an error. Reopen and reconcile;
            # continuing from the in-memory copy would hide that uncertainty.
            self.usable = False
            raise

    def _persist(self):
        temporary = self.directory / (".upgrade-journal-" + str(uuid.uuid4()) + ".partial")
        descriptor = self._private_open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        with os.fdopen(descriptor, "wb") as target:
            target.write(canonical(self.record) + b"\n")
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, self.path)
        descriptor = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def begin(self, stage):
        self._validate_evidence({})
        require(self.lock is not None and stage in STAGES)
        require(self.record["status"] in {"pending", "failed"})
        require(len(self.record["completed"]) < len(STAGES))
        require(stage == STAGES[len(self.record["completed"])])
        require(self.record["stage"] in (None, stage, self.record["completed"][-1] if self.record["completed"] else None))
        self.record.update(stage=stage, status="running")
        self._event("started", {})
        self._save()

    def succeed(self, stage, evidence):
        self._validate_evidence(evidence)
        require_receipt(evidence)
        require(self.record["status"] == "running" and self.record["stage"] == stage and stage in STAGES)
        require(stage == STAGES[len(self.record["completed"])])
        self.record["completed"].append(stage)
        self.record["status"] = "complete" if stage == STAGES[-1] else "pending"
        self._event("succeeded", evidence)
        self._save()

    def fail(self, code):
        self._validate_evidence({"code": code})
        require(self.record["status"] == "running" and code in ERRORS)
        self.record["status"] = "failed"
        self._event("failed", {"code": code})
        self._save()

    def reconcile(self, *, applied, evidence):
        self._validate_evidence(evidence)
        require_receipt(evidence)
        require(type(applied) is bool and self.record["status"] == "uncertain")
        stage = self.record["stage"]
        require(stage in STAGES)
        self._event("reconciled", {**evidence, "applied": applied})
        if applied:
            self.record["completed"].append(stage)
            self.record["status"] = "complete" if stage == STAGES[-1] else "pending"
        else:
            self.record["status"] = "failed"
        self._save()

    def begin_recovery(self):
        self._validate_evidence({})
        require(self.record["status"] in {"failed", "uncertain"})
        self.record.update(stage="recover", status="running")
        self._event("recovery_started", {})
        self._save()

    def recovered(self, evidence):
        self._validate_evidence(evidence)
        require_receipt(evidence)
        require(self.record["stage"] == "recover" and self.record["status"] == "running")
        require(evidence.get("previous_identity_verified") is True and evidence.get("public_functional_probe") is True)
        self.record["status"] = "recovered"
        self._event("recovered", evidence)
        self._save()

    def status(self):
        require(self.lock is not None and self.usable)
        return self._status()

    @classmethod
    def read_status(cls, directory, operation, intent):
        """Read one atomic snapshot without claiming, changing ownership or appending events."""
        journal = cls(directory, operation, intent)
        descriptor = journal._private_open(journal.path, os.O_RDONLY)
        with os.fdopen(descriptor, "rb") as source:
            require(os.fstat(source.fileno()).st_size <= 1_048_576)
            journal.record = json.loads(source.read(), object_pairs_hook=unique_object)
        journal._validate_record()
        require(journal.record["operation"] == operation and journal.record["intent"] == journal.intent)
        return journal._status()

    def _status(self):
        failures = [event for event in self.record["events"] if event["kind"] == "failed"]
        return {"protocol": 1, "operation": self.operation, "stage": self.record["stage"],
                "status": self.record["status"], "completed": list(self.record["completed"]),
                "intent_sha256": self.record["intent_sha256"], "events": len(self.record["events"]),
                "last_failure": {"stage": failures[-1]["stage"], "code": failures[-1]["evidence"]["code"]} if failures else None}
