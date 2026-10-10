"""Read immutable observations bound by the initial installation event chain."""
import hashlib
import json

from native_inventory import private_bytes
from upgrade_journal import canonical, require, unique_object


def completed_observation(journal, stage):
    require(stage in journal.record["completed"])
    events = [event for event in journal.record["events"] if event["stage"] == stage and
              (event["kind"] == "succeeded" or event["kind"] == "reconciled" and event["evidence"]["applied"])]
    require(len(events) == 1)
    digest = events[0]["evidence"]["receipt_sha256"]
    path = journal.directory / ("enrollment-observation-" + digest + ".json")
    raw = private_bytes(path, 131_072)
    require(hashlib.sha256(raw).hexdigest() == digest)
    value = json.loads(raw, object_pairs_hook=unique_object)
    require(isinstance(value, dict) and set(value) == {"protocol", "purpose", "operation", "request_sha256", "stage", "result"})
    require(type(value["protocol"]) is int and value["protocol"] == 1 and value["purpose"] == "native_initial_stage_observation")
    require(value["operation"] == journal.operation and value["request_sha256"] == journal.request_sha256 and
            value["stage"] == stage and isinstance(value["result"], dict))
    require(private_bytes(path, 131_072) == raw)
    return value["result"]


def validate_baseline_observations(journal, activation, pointer_sha256):
    """Historical observation integrity only, never a fresh functional probe."""
    from enrollment_journal import STAGES
    observations = {stage: completed_observation(journal, stage) for stage in STAGES}
    owner = observations["bootstrap"]
    require(owner.get("outcome") in {"created", "recorded"} and owner.get("installation") == journal.intent["installation"])
    require(type(owner.get("user_id")) is int and owner["user_id"] > 0 and owner.get("role_at_creation") == "owner")
    require(observations["migrate"].get("schema") == activation["schema"] and
            observations["verify"].get("schema") == activation["schema"])
    for stage in ["activate", "enroll"]:
        observation = observations[stage]
        require(observation.get("pointer_sha256") == pointer_sha256 and observation.get("schema") == activation["schema"])
        probe = observation.get("public_access")
        require(isinstance(probe, dict) and probe.get("candidate") == activation["candidate"])
        require(all(probe.get(key) is True for key in ["initial_access_probe", "anonymous_private_api_denied",
                    "owner_login_verified", "current_owner_membership_verified", "authorized_repository_list_verified", "probe_session_revoked"]))
        require(isinstance(probe.get("receipt_sha256"), str))
        require(hashlib.sha256(canonical({key: value for key, value in probe.items() if key != "receipt_sha256"})).hexdigest() == probe["receipt_sha256"])
        if stage == "activate": require(probe["receipt_sha256"] == activation["public_probe_sha256"])
    return observations
