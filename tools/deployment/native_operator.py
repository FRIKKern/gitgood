"""Read-only local operator entry point; recorded custody is not live readiness."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import uuid

from native_activation import NativeActivation
from native_inventory import directory_identity, private_bytes
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
    raw = private_bytes(index_path, MAX_HISTORY_BYTES)
    index = json.loads(raw, object_pairs_hook=unique_object)
    require(isinstance(index, dict) and index.get("installation") == installation)
    entries = index.get("operations")
    require(isinstance(entries, list) and 1 <= len(entries) <= MAX_OPERATIONS)
    for entry in entries:
        require(isinstance(entry, dict) and isinstance(entry.get("operation"), str))
        require(str(uuid.UUID(entry["operation"])) == entry["operation"])
    last = entries[-1]
    history = UpgradeHistory(directory, last["operation"], last["intent"])
    require(history._load() == index)
    paths = {index_path: MAX_HISTORY_BYTES, directory / "current-release-v1.json": 16384,
             directory / "retirement-journal-v1.json": 1048576}
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
        require(pointer["operation"] in {entry["operation"] for entry in entries})
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
            require(len(entries) > 1 and pointer["operation"] == entries[-2]["operation"])
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
    return {"protocol": 1, "purpose": "native_operator_status", "installation": installation, "observed_at": now(),
            "upgrades": upgrades["operations"], "activation_record": activation, "retirement": retirement,
            "limitations": ["Retained local records only; activation metadata is not live readiness or artifact verification.",
                            "Owner liveness observes the recorded process; this read neither claims custody nor establishes who holds the OS lock.",
                            "No database, store, archive usability or managed Cloud/provider inventory observation."]}


def main():
    parser = argparse.ArgumentParser(description="Inspect native custody or execute a fixed independently bound retirement.")
    commands = parser.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status", help="Read upgrade, activation and retirement records.")
    status.add_argument("--history-directory", required=True)
    status.add_argument("--installation", required=True)
    retirement = commands.add_parser("retire", help="Execute or reconcile fixed owned source retirement; retain recovery materials.")
    retirement.add_argument("--history-directory", required=True)
    retirement.add_argument("--plan-directory", required=True)
    retirement.add_argument("--plan-sha256", required=True)
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
                "native_operator_retirement_invalid" if arguments.command == "retire" else "native_operator_upgrade_invalid")
        print(json.dumps({"status": "refused", "code": code}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
