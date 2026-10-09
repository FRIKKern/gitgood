"""Durable current-release observation under the installation history lock."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import uuid

from native_actions import verify_runtime_stage
from native_inventory import directory_identity, private_bytes
from upgrade_journal import canonical, owner, require, unique_object


class NativeActivation:
    """A recorded pointer does not itself establish current live routing."""
    def __init__(self, history, journal):
        require(sys.platform == "linux")
        self.history = history
        self.journal = journal
        self.directory = history.directory
        directory_identity(self.directory, private=True)
        self.path = self.directory / "current-release-v1.json"
        self.usable = True

    @staticmethod
    def validate(value):
        require(isinstance(value, dict) and set(value) == {"protocol", "installation", "operation", "candidate", "artifact_sha256",
                "bindings_sha256", "stage", "stage_inventory_sha256", "schema", "public_probe_sha256"})
        require(type(value["protocol"]) is int and value["protocol"] == 1)
        for field in ["installation", "operation"]:
            require(isinstance(value[field], str) and str(uuid.UUID(value[field])) == value[field])
        require(isinstance(value["candidate"], str) and re.fullmatch(r"[0-9a-f]{40}", value["candidate"]))
        for field in ["artifact_sha256", "bindings_sha256", "stage_inventory_sha256", "public_probe_sha256"]:
            require(isinstance(value[field], str) and re.fullmatch(r"[0-9a-f]{64}", value[field]))
        stage = value["stage"]
        require(isinstance(stage, dict) and set(stage) == {"path", "device", "inode", "uid"})
        require(isinstance(stage["path"], str) and Path(stage["path"]).is_absolute())
        require(all(type(stage[field]) is int and stage[field] >= 0 for field in ["device", "inode", "uid"]))
        schema = value["schema"]
        require(isinstance(schema, list) and 1 <= len(schema) <= 256)
        require(all(isinstance(version, str) and re.fullmatch(r"[0-9]{14}", version) for version in schema))
        require(schema == sorted(set(schema)))
        return value

    def read(self):
        if not self.path.exists() and not self.path.is_symlink():
            return None
        raw = private_bytes(self.path, 16_384)
        value = self.validate(json.loads(raw, object_pairs_hook=unique_object))
        require(value["installation"] == self.history.intent["installation"] and value["bindings_sha256"] == self.history.intent["bindings_sha256"])
        return {"record": value, "sha256": hashlib.sha256(raw).hexdigest()}

    def activate(self, stage, schema, public_probe, *, expected_current_sha256):
        journal = self.journal
        require(self.usable and self.history.lock is not None and self.history.journal is journal)
        require(self.history.operation == journal.operation and self.history.intent == journal.intent)
        require(journal.directory == self.directory / "operations" / journal.operation)
        require(journal.lock is not None and journal.usable and journal.record["owner"] == owner())
        require(journal.record["status"] == "running" and journal.record["stage"] in {"public_verify", "recover"})
        recovering = journal.record["stage"] == "recover"
        prefix = "old" if recovering else "new"
        candidate, artifact = (journal.intent[prefix + "_candidate"], journal.intent[prefix + "_artifact_sha256"])
        verified = verify_runtime_stage(stage, candidate, artifact)
        require(schema == verified["migrations"])
        require(isinstance(public_probe, dict) and set(public_probe) == {"candidate", "public_functional_probe", "receipt_sha256"})
        require(public_probe["candidate"] == candidate and public_probe["public_functional_probe"] is True)
        require(isinstance(public_probe["receipt_sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", public_probe["receipt_sha256"]))
        stage_identity = directory_identity(stage, private=True)
        value = self.validate({"protocol": 1, "installation": journal.intent["installation"], "operation": journal.operation,
                "candidate": candidate, "artifact_sha256": artifact, "bindings_sha256": journal.intent["bindings_sha256"],
                "stage": stage_identity, "stage_inventory_sha256": verified["inventory_sha256"], "schema": schema,
                "public_probe_sha256": public_probe["receipt_sha256"]})
        current = self.read()
        if current is not None and current["record"] == value:
            # The exact write may have landed before its acknowledgement was lost.
            return current
        require((current["sha256"] if current else None) == expected_current_sha256)
        if current is not None:
            previous = current["record"]
            require(previous["installation"] == value["installation"] and previous["bindings_sha256"] == value["bindings_sha256"])
            allowed = {(journal.intent["old_candidate"], journal.intent["old_artifact_sha256"])}
            if recovering:
                allowed.add((journal.intent["new_candidate"], journal.intent["new_artifact_sha256"]))
            require((previous["candidate"], previous["artifact_sha256"]) in allowed)
        temporary = self.directory / (".current-release-" + str(uuid.uuid4()) + ".partial")
        try:
            descriptor = journal._private_open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            with os.fdopen(descriptor, "wb") as output:
                output.write(canonical(value) + b"\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
            descriptor = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except BaseException:
            # A replaced pointer with a failed acknowledgement is an observation,
            # never permission to proceed from a stale in-memory copy.
            self.usable = False
            raise
        return self.read()
