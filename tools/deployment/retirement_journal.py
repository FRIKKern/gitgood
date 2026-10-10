"""Fixed retirement responsibility; no resource deletion or arbitrary commands."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import uuid

from native_inventory import directory_identity, private_bytes
from native_activation import NativeActivation
from upgrade_history import UpgradeHistory
from upgrade_journal import (UpgradeRefused, canonical, fcntl, now, owner,
                             owner_alive, require, unique_object, validate_owner,
                             validate_time)

STAGES = ("quiesce", "archive_verify", "database_remove", "stores_remove", "retention_verify")
ERRORS = {"quiescence_failed", "archive_refused", "snapshot_changed",
          "database_remove_failed", "store_remove_failed", "retention_failed"}
DIGESTS = {"bindings_sha256", "artifact_sha256", "current_sha256", "checkpoint_sha256",
           "restore_sha256", "archive_sha256", "retention_sha256", "resource_plan_sha256"}


def validate_plan(plan):
    require(isinstance(plan, dict) and set(plan) == {"protocol", "operation", "installation", "candidate", *DIGESTS})
    require(type(plan["protocol"]) is int and plan["protocol"] == 1)
    for key in ["operation", "installation"]:
        require(isinstance(plan[key], str) and str(uuid.UUID(plan[key])) == plan[key])
    require(isinstance(plan["candidate"], str) and re.fullmatch(r"[0-9a-f]{40}", plan["candidate"]))
    for key in DIGESTS:
        require(isinstance(plan[key], str) and re.fullmatch(r"[0-9a-f]{64}", plan[key]))
    return json.loads(canonical(plan))


def validate_evidence(value):
    require(isinstance(value, dict) and 1 <= len(value) <= 16)
    require(isinstance(value.get("receipt_sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", value["receipt_sha256"]))
    for key, item in value.items():
        require(isinstance(key, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", key))
        require(type(item) is bool or type(item) is int and 0 <= item < 2**63 or
                isinstance(item, str) and re.fullmatch(r"[0-9a-f]{64}", item))


class RetirementJournal:
    """Use the same installation lock as upgrades and retain interrupted intent."""
    def __init__(self, directory, plan, plan_sha256):
        require(sys.platform == "linux" and fcntl is not None)
        self.directory = Path(directory)
        directory_identity(self.directory, private=True)
        self.plan = validate_plan(plan)
        self.plan_sha256 = hashlib.sha256(canonical(self.plan)).hexdigest()
        require(plan_sha256 == self.plan_sha256)
        self.operation = self.plan["operation"]
        self.path = self.directory / "retirement-journal-v1.json"
        self.lock = None
        self.record = None
        self.usable = True

    def _private_open(self, path, flags):
        descriptor = os.open(path, flags | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        value = os.fstat(descriptor)
        if not (stat.S_ISREG(value.st_mode) and value.st_uid == os.getuid() and value.st_nlink == 1 and not value.st_mode & 0o077):
            os.close(descriptor)
            raise UpgradeRefused("Native retirement custody refused")
        return descriptor

    def _prior_upgrade(self):
        from native_initial_baseline import has_initial, read_initial_baseline
        index_path = self.directory / "upgrade-history-v1.json"
        if not index_path.exists() and not index_path.is_symlink():
            require(has_initial(self.directory))
            baseline = read_initial_baseline(self.directory)
            pointer = baseline["activation"]
            current = private_bytes(self.directory / "current-release-v1.json", 16_384)
            require(hashlib.sha256(current).hexdigest() == baseline["activation_sha256"] == self.plan["current_sha256"])
            require(all(pointer[key] == self.plan[key] for key in ["installation", "candidate", "artifact_sha256", "bindings_sha256"]))
            return
        index = json.loads(private_bytes(self.directory / "upgrade-history-v1.json", 524_288), object_pairs_hook=unique_object)
        require(isinstance(index.get("operations"), list) and index["operations"])
        last = index["operations"][-1]
        history = UpgradeHistory.read_history(self.directory, last["operation"], last["intent"])
        require(history["operations"][-1]["status"] in {"complete", "recovered"})
        prefix = "new" if history["operations"][-1]["status"] == "complete" else "old"
        intent = last["intent"]
        require(intent["installation"] == self.plan["installation"] and intent["bindings_sha256"] == self.plan["bindings_sha256"])
        require(intent[prefix + "_candidate"] == self.plan["candidate"] and intent[prefix + "_artifact_sha256"] == self.plan["artifact_sha256"])
        current = private_bytes(self.directory / "current-release-v1.json", 16_384)
        require(hashlib.sha256(current).hexdigest() == self.plan["current_sha256"])
        pointer = NativeActivation.validate(json.loads(current, object_pairs_hook=unique_object))
        require(pointer["operation"] == last["operation"])
        require(all(pointer[key] == self.plan[key] for key in ["installation", "candidate", "artifact_sha256", "bindings_sha256"]))

    def __enter__(self):
        self.lock = self._private_open(self.directory / ".upgrade-history-lock-v1", os.O_RDWR | os.O_CREAT)
        try:
            try:
                fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise UpgradeRefused("Native installation lifecycle is already owned") from None
            if self.path.exists() or self.path.is_symlink():
                self.record = json.loads(private_bytes(self.path, 1_048_576), object_pairs_hook=unique_object)
                self._validate()
                require(self.record["plan"] == self.plan and self.record["plan_sha256"] == self.plan_sha256)
                if self.record["status"] == "running":
                    self._append("interrupted", {})
            else:
                self._prior_upgrade()
                self.record = {"protocol": 1, "plan": self.plan, "plan_sha256": self.plan_sha256,
                               "created_at": now(), "owner": owner(), "status": "pending", "stage": None,
                               "completed": [], "events": []}
            self.record["owner"] = owner()
            self._append("claimed", {})
            self._save()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, kind, value, trace):
        if self.lock is not None:
            os.close(self.lock)
            self.lock = None

    @staticmethod
    def _successful(stage, evidence):
        validate_evidence(evidence)
        if stage == "archive_verify":
            require(all(evidence.get(key) is True for key in ["archive_identity_verified", "restore_function_verified", "current_snapshot_verified", "writer_exclusion_verified"]))
        if stage in {"database_remove", "stores_remove"}:
            require(evidence.get("resource_reobserved") is True and evidence.get("desired_state_verified") is True)
        if stage == "retention_verify":
            require(evidence.get("retained_archive_usable") is True and evidence.get("owned_resources_absent") is True)

    def _validate(self):
        record = self.record
        require(isinstance(record, dict) and set(record) == {"protocol", "plan", "plan_sha256", "created_at", "owner", "status", "stage", "completed", "events"})
        require(type(record["protocol"]) is int and record["protocol"] == 1)
        require(validate_plan(record["plan"]) == self.plan and record["plan_sha256"] == self.plan_sha256)
        validate_owner(record["owner"])
        require(record["owner"]["uid"] == os.getuid())
        validate_time(record["created_at"])
        require(isinstance(record["events"], list) and 1 <= len(record["events"]) <= 1000)
        stage, status, completed = None, "pending", []
        for event in record["events"]:
            require(isinstance(event, dict) and set(event) == {"kind", "at", "stage", "owner", "evidence"})
            validate_owner(event["owner"])
            require(event["owner"]["uid"] == os.getuid())
            validate_time(event["at"])
            evidence = event["evidence"]
            if event["kind"] == "claimed":
                require(event["stage"] == stage and evidence == {})
            elif event["kind"] == "started":
                require(status == "pending" and len(completed) < len(STAGES))
                stage = STAGES[len(completed)]
                require(event["stage"] == stage and evidence == {})
                status = "running"
            elif event["kind"] == "interrupted":
                require(status == "running" and event["stage"] == stage and evidence == {})
                status = "uncertain"
            elif event["kind"] == "failed":
                require(status == "running" and event["stage"] == stage and isinstance(evidence, dict) and set(evidence) == {"code"} and evidence["code"] in ERRORS)
                status = "failed"
            elif event["kind"] in {"succeeded", "reconciled_applied"}:
                require(status in ({"running"} if event["kind"] == "succeeded" else {"failed", "uncertain"}) and event["stage"] == stage)
                self._successful(stage, evidence)
                completed.append(stage)
                status = "complete" if len(completed) == len(STAGES) else "pending"
            elif event["kind"] == "reconciled_unapplied":
                require(status in {"failed", "uncertain"} and event["stage"] == stage)
                validate_evidence(evidence)
                require(evidence.get("unapplied_verified") is True)
                status = "pending"
            else:
                require(False)
        require((record["stage"], record["status"], record["completed"]) == (stage, status, completed))
        require(completed == list(STAGES[:len(completed)]) and len(canonical(record)) <= 1_048_576)

    def _append(self, kind, evidence):
        require(self.lock is not None and self.usable and len(self.record["events"]) < 1000)
        self.record["events"].append({"kind": kind, "at": now(), "stage": self.record["stage"], "owner": owner(), "evidence": json.loads(canonical(evidence))})
        if kind == "interrupted":
            self.record["status"] = "uncertain"

    def _save(self):
        self._validate()
        temporary = self.directory / (".retirement-" + str(uuid.uuid4()) + ".partial")
        try:
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
        except BaseException:
            self.usable = False
            raise

    def _owned(self):
        require(self.lock is not None and self.usable and self.record["owner"] == owner())
        self._validate()
        require(len(self.record["events"]) < 1000)

    def begin(self, stage):
        self._owned()
        require(self.record["status"] == "pending" and len(self.record["completed"]) < len(STAGES))
        require(stage == STAGES[len(self.record["completed"])])
        self.record.update(stage=stage, status="running")
        self._append("started", {})
        self._save()

    def succeed(self, evidence):
        self._owned()
        require(self.record["status"] == "running")
        self._successful(self.record["stage"], evidence)
        self.record["completed"].append(self.record["stage"])
        self.record["status"] = "complete" if len(self.record["completed"]) == len(STAGES) else "pending"
        self._append("succeeded", evidence)
        self._save()

    def fail(self, code):
        self._owned()
        require(self.record["status"] == "running" and code in ERRORS)
        self.record["status"] = "failed"
        self._append("failed", {"code": code})
        self._save()

    def reconcile(self, *, applied, evidence):
        self._owned()
        require(type(applied) is bool and self.record["status"] in {"failed", "uncertain"})
        if applied:
            self._successful(self.record["stage"], evidence)
            self.record["completed"].append(self.record["stage"])
            self.record["status"] = "complete" if len(self.record["completed"]) == len(STAGES) else "pending"
        else:
            validate_evidence(evidence)
            require(evidence.get("unapplied_verified") is True)
            self.record["status"] = "pending"
        self._append("reconciled_applied" if applied else "reconciled_unapplied", evidence)
        self._save()

    @classmethod
    def read_status(cls, directory, plan, plan_sha256):
        journal = cls(directory, plan, plan_sha256)
        journal.record = json.loads(private_bytes(journal.path, 1_048_576), object_pairs_hook=unique_object)
        journal._validate()
        status = journal.record["status"]
        if status == "running" and not owner_alive(journal.record["owner"]):
            status = "uncertain"
        return {"operation": journal.operation, "status": status, "stage": journal.record["stage"],
                "completed": list(journal.record["completed"]), "events": len(journal.record["events"]),
                "owner_alive": owner_alive(journal.record["owner"])}
