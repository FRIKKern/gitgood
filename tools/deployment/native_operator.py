"""Read-only local operator entry point; recorded custody is not live readiness."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import os
import stat
import uuid

from enrollment_journal import EnrollmentJournal, digest as initial_digest

from native_activation import NativeActivation
from native_inventory import directory_identity, private_bytes
from native_initial_baseline import NAME as INITIAL_NAME, has_initial, read_initial_baseline
from retirement_journal import RetirementJournal
from upgrade_history import MAX_HISTORY_BYTES, MAX_OPERATIONS, UpgradeHistory
from upgrade_journal import require, unique_object, now


def _stamp(path, maximum):
    if not path.exists() and not path.is_symlink():
        return None
    raw = private_bytes(path, maximum)
    info = path.lstat()
    return {"device": info.st_dev, "inode": info.st_ino, "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest()}


def read_status(directory, installation):
    require(sys.platform == "linux")
    require(isinstance(installation, str) and str(uuid.UUID(installation)) == installation)
    directory = Path(directory)
    root_identity = directory_identity(directory, private=True)
    index_path = directory / "upgrade-history-v1.json"
    if not index_path.exists() and not index_path.is_symlink():
        return _initial_status(directory, installation, root_identity)
    raw = private_bytes(index_path, MAX_HISTORY_BYTES)
    index = json.loads(raw, object_pairs_hook=unique_object)
    require(isinstance(index, dict) and index.get("installation") == installation)
    entries = index.get("operations")
    require(isinstance(entries, list) and 1 <= len(entries) <= MAX_OPERATIONS)
    for entry in entries:
        require(isinstance(entry, dict) and isinstance(entry.get("operation"), str))
        require(str(uuid.UUID(entry["operation"])) == entry["operation"])
    last = entries[-1]
    initial = read_initial_baseline(directory) if has_initial(directory) else None
    history = UpgradeHistory(directory, last["operation"], last["intent"])
    require(history._load() == index)
    paths = {index_path: MAX_HISTORY_BYTES, directory / "current-release-v1.json": 16384,
             directory / "retirement-journal-v1.json": 1048576}
    if initial is not None:
        paths.update({directory / INITIAL_NAME:32768, directory / "initial-enrollment-v1.json":524288,
                      directory / "initial-lifecycle-anchor-v1.json":16384})
    for entry in entries:
        paths[directory / "operations" / entry["operation"] / "upgrade-journal-v1.json"] = 1048576
    before = {path: _stamp(path, maximum) for path, maximum in paths.items()}
    require(before[index_path]["sha256"] == hashlib.sha256(raw).hexdigest())
    upgrades = UpgradeHistory.read_history(directory, last["operation"], last["intent"])
    activation = None
    pointer_path = directory / "current-release-v1.json"
    if before[pointer_path] is not None:
        pointer = NativeActivation.validate(json.loads(private_bytes(pointer_path, 16384), object_pairs_hook=unique_object))
        require(pointer["installation"] == installation and pointer["bindings_sha256"] == index["bindings_sha256"])
        allowed = {entry["operation"] for entry in entries}
        if initial is not None: allowed.add(initial["operation"])
        require(pointer["operation"] in allowed)
        terminal = upgrades["operations"][-1]["status"]
        if terminal in {"complete", "recovered"}:
            prefix = "new" if terminal == "complete" else "old"
            require(pointer["operation"] == last["operation"])
            require(pointer["candidate"] == last["intent"][prefix + "_candidate"] and
                    pointer["artifact_sha256"] == last["intent"][prefix + "_artifact_sha256"])
        elif pointer["operation"] == last["operation"]:
            require(any(pointer["candidate"] == last["intent"][prefix + "_candidate"] and
                        pointer["artifact_sha256"] == last["intent"][prefix + "_artifact_sha256"] for prefix in ["old", "new"]))
        else:
            if len(entries) == 1:
                require(initial is not None and pointer == initial["activation"])
            else:
                require(pointer["operation"] == entries[-2]["operation"])
            require(pointer["candidate"] == last["intent"]["old_candidate"] and pointer["artifact_sha256"] == last["intent"]["old_artifact_sha256"])
        activation = {key: pointer[key] for key in ["installation", "operation", "candidate", "artifact_sha256", "bindings_sha256", "schema"]}
        activation["record_sha256"] = before[pointer_path]["sha256"]
    retirement = None
    retirement_path = directory / "retirement-journal-v1.json"
    if before[retirement_path] is not None:
        record = json.loads(private_bytes(retirement_path, 1048576), object_pairs_hook=unique_object)
        require(isinstance(record, dict) and isinstance(record.get("plan"), dict))
        plan = record["plan"]
        require(plan.get("installation") == installation and plan.get("bindings_sha256") == index["bindings_sha256"])
        require(activation is not None and plan.get("candidate") == activation["candidate"] and plan.get("artifact_sha256") == activation["artifact_sha256"])
        require(plan.get("current_sha256") == activation["record_sha256"])
        retirement = RetirementJournal.read_status(directory, plan, record["plan_sha256"])
        retirement["record_sha256"] = before[retirement_path]["sha256"]
    require(directory_identity(directory, private=True) == root_identity)
    require({path: _stamp(path, maximum) for path, maximum in paths.items()} == before)
    result = {"protocol": 1, "purpose": "native_operator_status", "installation": installation, "observed_at": now(),
            "upgrades": upgrades["operations"], "activation_record": activation, "retirement": retirement,
            "limitations": ["Retained local records only; activation metadata is not live readiness or artifact verification.",
                            "Owner liveness observes the recorded process; this read neither claims custody nor establishes who holds the OS lock.",
                            "No database, store, archive usability or managed Cloud/provider inventory observation."]}
    if initial is not None: result["initial_enrollment"] = _initial_metadata(initial)
    return result


def _initial_metadata(baseline):
    return {"operation":baseline["operation"], "candidate":baseline["activation"]["candidate"],
            "status":"complete", "baseline_sealed":True, "journal_sha256":baseline["journal_sha256"]}


def _initial_status(directory, installation, root_identity):
    paths = {directory / INITIAL_NAME:32768, directory / "initial-enrollment-v1.json":524288,
             directory / "initial-lifecycle-anchor-v1.json":16384,
             directory / "current-release-v1.json":16384, directory / "retirement-journal-v1.json":1048576,
             directory / "upgrade-history-v1.json":MAX_HISTORY_BYTES}
    before = {path:_stamp(path, maximum) for path,maximum in paths.items()}
    if before[directory / INITIAL_NAME] is None:
        return _initial_progress(directory,installation,root_identity,paths,before)
    baseline = read_initial_baseline(directory)
    require(baseline["installation"] == installation)
    pointer = baseline["activation"]
    require(before[directory / "current-release-v1.json"] is not None and
            before[directory / "current-release-v1.json"]["sha256"] == baseline["activation_sha256"])
    activation = {key:pointer[key] for key in ["installation", "operation", "candidate", "artifact_sha256", "bindings_sha256", "schema"]}
    activation["record_sha256"] = baseline["activation_sha256"]
    retirement = None
    path = directory / "retirement-journal-v1.json"
    if before[path] is not None:
        record = json.loads(private_bytes(path,1048576), object_pairs_hook=unique_object)
        require(isinstance(record,dict) and isinstance(record.get("plan"),dict))
        plan = record["plan"]
        require(all(plan.get(key) == activation[key] for key in ["installation", "candidate", "artifact_sha256", "bindings_sha256"]))
        require(plan.get("current_sha256") == activation["record_sha256"])
        retirement = RetirementJournal.read_status(directory,plan,record["plan_sha256"])
        retirement["record_sha256"] = before[path]["sha256"]
    require(directory_identity(directory,private=True) == root_identity)
    require({path:_stamp(path, maximum) for path,maximum in paths.items()} == before)
    return {"protocol":1, "purpose":"native_operator_status", "installation":installation, "observed_at":now(),
            "upgrades":[], "initial_enrollment":_initial_metadata(baseline), "activation_record":activation, "retirement":retirement,
            "limitations":["Retained local records only; activation metadata is not live readiness or artifact verification.",
                           "The complete initial journal is separate from upgrades; this read does not claim installation custody.",
                           "No database, store, archive usability or managed Cloud/provider inventory observation."]}


def _initial_progress(directory, installation, root_identity, paths, before):
    require(before[directory / "retirement-journal-v1.json"] is None)
    anchor = json.loads(private_bytes(directory / "initial-lifecycle-anchor-v1.json",16384),object_pairs_hook=unique_object)
    require(isinstance(anchor,dict) and set(anchor) == {"protocol","purpose","installation","operation","request_sha256","shared_lock_identity"})
    require(type(anchor["protocol"]) is int and anchor["protocol"] == 1 and anchor["purpose"] == "native_initial_lifecycle")
    require(anchor["installation"] == installation and isinstance(anchor["operation"],str) and str(uuid.UUID(anchor["operation"])) == anchor["operation"])
    initial_digest(anchor["request_sha256"])
    shared_path = directory / ".upgrade-history-lock-v1"; shared = shared_path.lstat()
    shared_identity = [shared.st_dev,shared.st_ino,shared.st_uid]
    require(stat.S_ISREG(shared.st_mode) and shared.st_uid == os.getuid() and shared.st_nlink == 1 and not shared.st_mode & 0o077)
    require(isinstance(anchor["shared_lock_identity"],list) and len(anchor["shared_lock_identity"]) == 3 and
            all(type(part) is int for part in anchor["shared_lock_identity"]) and anchor["shared_lock_identity"] == shared_identity)
    activation = None
    if before[directory / "initial-enrollment-v1.json"] is None:
        require(before[directory / "current-release-v1.json"] is None)
        initial = {"operation":anchor["operation"],"candidate":None,"status":"reserved","baseline_sealed":False}
    else:
        raw = private_bytes(directory / "initial-enrollment-v1.json",524288)
        record = json.loads(raw,object_pairs_hook=unique_object)
        require(isinstance(record,dict) and record.get("operation") == anchor["operation"] and record.get("request_sha256") == anchor["request_sha256"])
        status = EnrollmentJournal.read_status(directory,record["operation"],record["intent"],record["request_sha256"])
        require(status["installation"] == installation)
        initial = {key:status[key] for key in ["operation","candidate","stage","status","recorded_status","completed","epoch","events","owner_alive"]}
        initial["baseline_sealed"] = False
        if status["status"] == "complete": initial["status"] = "awaiting_handoff"
        if before[directory / "current-release-v1.json"] is not None:
            pointer = NativeActivation.validate(json.loads(private_bytes(directory / "current-release-v1.json",16384),object_pairs_hook=unique_object))
            require(pointer["operation"] == record["operation"] and all(pointer[key] == record["intent"][key] for key in ["installation","candidate","artifact_sha256"]))
            activation = {key:pointer[key] for key in ["installation","operation","candidate","artifact_sha256","bindings_sha256","schema"]}
            activation["record_sha256"] = before[directory / "current-release-v1.json"]["sha256"]
    require(directory_identity(directory,private=True) == root_identity)
    require({path:_stamp(path,maximum) for path,maximum in paths.items()} == before)
    shared = shared_path.lstat(); require([shared.st_dev,shared.st_ino,shared.st_uid] == shared_identity)
    return {"protocol":1,"purpose":"native_operator_status","installation":installation,"observed_at":now(),
            "upgrades":[],"initial_enrollment":initial,"activation_record":activation,"retirement":None,
            "limitations":["Retained initial responsibility only; an unsealed baseline is not an enrolled installation or live readiness.",
                           "Owner liveness does not establish who holds the OS lock; this read performs no claim or reconciliation.",
                           "No database, store, archive usability or managed Cloud/provider inventory observation."]}


def main():
    parser = argparse.ArgumentParser(description="Inspect native custody or execute fixed independently bound lifecycle stages.")
    commands = parser.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status", help="Read upgrade, activation and retirement records.")
    status.add_argument("--history-directory", required=True)
    status.add_argument("--installation", required=True)
    retirement = commands.add_parser("retire", help="Execute or reconcile fixed owned source retirement; retain recovery materials.")
    retirement.add_argument("--history-directory", required=True)
    retirement.add_argument("--plan-directory", required=True)
    retirement.add_argument("--plan-sha256", required=True)
    for name, help_text in [("enroll", "Install a fixed candidate on an admitted empty native host."),
                            ("enroll-resume", "Observe and resume the same retained initial installation intent.")]:
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--inputs-directory", required=True)
        command.add_argument("--request-sha256", required=True)
    for name, help_text in [("upgrade", "Execute a fixed enrolled-installation upgrade."),
                            ("upgrade-recover", "Recover exact compatible previous code for the same intent."),
                            ("upgrade-resume", "Repair forward under the same retained upgrade intent.")]:
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--history-directory", required=True)
        command.add_argument("--inputs-directory", required=True)
        command.add_argument("--request-sha256", required=True)
    arguments = parser.parse_args()
    try:
        if arguments.command == "status":
            result = read_status(arguments.history_directory, arguments.installation)
        elif arguments.command in {"enroll", "enroll-resume"}:
            from native_enrollment import NativeEnrollment
            engine = NativeEnrollment(arguments.inputs_directory, arguments.request_sha256)
            result = engine.run() if arguments.command == "enroll" else engine.resume()
        elif arguments.command == "retire":
            from native_retirement import NativeRetirement
            result = NativeRetirement(arguments.history_directory, arguments.plan_directory, arguments.plan_sha256).run()
        else:
            from native_upgrade_command import NativeUpgradeCommand
            result = NativeUpgradeCommand(arguments.history_directory, arguments.inputs_directory, arguments.request_sha256).run(arguments.command)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        # Never print private input, credentials, paths or exception details.
        code = ("native_operator_status_invalid" if arguments.command == "status" else
                "native_operator_retirement_invalid" if arguments.command == "retire" else
                "native_operator_enrollment_invalid" if arguments.command in {"enroll", "enroll-resume"} else "native_operator_upgrade_invalid")
        print(json.dumps({"status": "refused", "code": code}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
