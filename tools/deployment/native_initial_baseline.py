"""Seal a real terminal first install without fabricating a prior upgrade."""
import hashlib
import json
import os
from pathlib import Path
import stat
import uuid

from enrollment_journal import EnrollmentJournal
from native_activation import NativeActivation
from native_actions import verify_runtime_stage
from native_inventory import directory_identity, private_bytes
from native_initial_observations import validate_baseline_observations
from stage_native_artifact import publish_directory, sync_directory
from upgrade_journal import canonical, require, unique_object

NAME = "initial-baseline-v1.json"


def has_initial(directory):
    return any((Path(directory) / name).exists() or (Path(directory) / name).is_symlink()
               for name in [NAME, "initial-enrollment-v1.json", "initial-lifecycle-anchor-v1.json"])


def read_initial_baseline(directory):
    """Read historical seals only; this never establishes current live readiness."""
    directory = Path(directory); identity = directory_identity(directory, private=True)
    require((directory / NAME).is_file() and not (directory / NAME).is_symlink())
    raw = private_bytes(directory / NAME, 32_768)
    value = json.loads(raw, object_pairs_hook=unique_object)
    require(isinstance(value, dict) and set(value) == {"protocol", "purpose", "installation", "operation", "intent",
            "request_sha256", "bindings_sha256", "journal_sha256", "anchor_sha256", "activation", "activation_sha256"})
    require(type(value["protocol"]) is int and value["protocol"] == 1 and value["purpose"] == "native_initial_baseline")
    journal = EnrollmentJournal(directory, value["operation"], value["intent"], value["request_sha256"])
    journal_raw = private_bytes(journal.path, 524_288)
    require(hashlib.sha256(journal_raw).hexdigest() == value["journal_sha256"])
    journal.record = json.loads(journal_raw, object_pairs_hook=unique_object); journal._validate()
    require(journal.record["status"] == "complete" and value["installation"] == journal.intent["installation"])
    anchor_raw = private_bytes(directory / "initial-lifecycle-anchor-v1.json", 16_384)
    require(hashlib.sha256(anchor_raw).hexdigest() == value["anchor_sha256"])
    anchor = json.loads(anchor_raw, object_pairs_hook=unique_object)
    require(isinstance(anchor, dict) and set(anchor) == {"protocol", "purpose", "installation", "operation", "request_sha256", "shared_lock_identity"})
    require(type(anchor["protocol"]) is int and anchor["protocol"] == 1 and anchor["purpose"] == "native_initial_lifecycle")
    require(all(anchor[key] == value[key] for key in ["installation", "operation", "request_sha256"]))
    lock = (directory / ".upgrade-history-lock-v1").lstat()
    require(stat.S_ISREG(lock.st_mode) and lock.st_uid == os.getuid() and lock.st_nlink == 1 and not lock.st_mode & 0o077)
    require(isinstance(anchor["shared_lock_identity"], list) and len(anchor["shared_lock_identity"]) == 3 and
            all(type(part) is int for part in anchor["shared_lock_identity"]) and
            anchor["shared_lock_identity"] == [lock.st_dev, lock.st_ino, lock.st_uid])
    activation = NativeActivation.validate(value["activation"])
    require(all(activation[key] == value[key] for key in ["installation", "operation", "bindings_sha256"]))
    require(all(activation[key] == journal.intent[key] for key in ["candidate", "artifact_sha256"]))
    require(hashlib.sha256(canonical(activation) + b"\n").hexdigest() == value["activation_sha256"])
    validate_baseline_observations(journal, activation, value["activation_sha256"])
    require(directory_identity(directory, private=True) == identity)
    require(private_bytes(directory / NAME, 32_768) == raw and
            private_bytes(journal.path, 524_288) == journal_raw and
            private_bytes(directory / "initial-lifecycle-anchor-v1.json", 16_384) == anchor_raw)
    return value


def require_initial_upgrade(baseline, intent):
    initial = baseline["activation"]
    require(intent["installation"] == initial["installation"] and intent["bindings_sha256"] == initial["bindings_sha256"])
    require(intent["old_candidate"] == initial["candidate"] and intent["old_artifact_sha256"] == initial["artifact_sha256"])


def seal_initial_baseline(custody):
    """Publish after terminal acknowledgement; exact terminal reopen can finish metadata handoff."""
    custody.check(terminal=True)
    journal = custody.journal; directory = custody.directory
    pointer_raw = private_bytes(directory / "current-release-v1.json", 16_384)
    activation = NativeActivation.validate(json.loads(pointer_raw, object_pairs_hook=unique_object))
    require(all(activation[key] == journal.intent[key] for key in ["installation", "candidate", "artifact_sha256"]))
    require(activation["operation"] == journal.operation and activation["bindings_sha256"] == custody.inputs.allocation["bindings_sha256"])
    stage = custody.inputs.root / "staging" / ("native-" + journal.operation)
    require(activation["stage"] == directory_identity(stage, private=True))
    verified = verify_runtime_stage(stage, journal.intent["candidate"], journal.intent["artifact_sha256"])
    require(activation["stage_inventory_sha256"] == verified["inventory_sha256"] and activation["schema"] == verified["migrations"])
    require(pointer_raw == canonical(activation) + b"\n")
    validate_baseline_observations(journal, activation, hashlib.sha256(pointer_raw).hexdigest())
    value = {"protocol":1, "purpose":"native_initial_baseline", "installation":journal.intent["installation"],
             "operation":journal.operation, "intent":journal.intent, "request_sha256":journal.request_sha256,
             "bindings_sha256":custody.inputs.allocation["bindings_sha256"], "activation":activation,
             "activation_sha256":hashlib.sha256(pointer_raw).hexdigest(),
             "journal_sha256":hashlib.sha256(journal._read()).hexdigest(),
             "anchor_sha256":hashlib.sha256(custody._anchor_bytes()).hexdigest()}
    path = directory / NAME
    if path.exists() or path.is_symlink():
        require(read_initial_baseline(directory) == value)
        return value
    temporary = directory / (".initial-baseline-" + str(uuid.uuid4()) + ".partial")
    try:
        with os.fdopen(journal._open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL), "wb") as target:
            target.write(canonical(value) + b"\n"); target.flush(); os.fsync(target.fileno())
        custody.check(terminal=True)
        require(private_bytes(directory / "current-release-v1.json", 16_384) == pointer_raw)
        publish_directory(temporary, path); sync_directory(directory)
    except BaseException:
        custody.usable = False
        raise
    require(read_initial_baseline(directory) == value)
    return value
