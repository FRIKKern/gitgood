"""Closed resource-generation records; validation does not authorize publication.

Persistent continuity, writer exclusion and atomic publication are separate
requirements. These helpers perform no filesystem, process or database action.
"""
import datetime
import hashlib
import json
import re
import uuid


class GenerationRefused(Exception):
    pass


def require(value):
    if not value:
        raise GenerationRefused("Native generation record refused")


def closed(value, keys):
    require(type(value) is dict and set(value) == set(keys))


def integer(value, minimum=1, maximum=2**64 - 1):
    require(type(value) is int and minimum <= value <= maximum)


def identifier(value):
    require(isinstance(value, str) and len(value) == 36)
    try:
        require(str(uuid.UUID(value)) == value)
    except ValueError:
        raise GenerationRefused("Native generation record refused") from None


def digest(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def directory(value, path, uid):
    closed(value, ("path", "device", "inode", "uid"))
    require(value["path"] == path and value["uid"] == uid)
    integer(value["uid"], maximum=2**32 - 1)
    integer(value["device"])
    integer(value["inode"])


def validate_scope(scope):
    closed(scope, ("protocol", "profile", "installation", "boot_id", "uid", "gid", "unit", "unit_definition",
                   "manager", "parent", "groups", "limits", "service_scope_observed", "installation_readiness_established"))
    require(type(scope["protocol"]) is int and scope["protocol"] == 2 and scope["profile"] == "systemd")
    identifier(scope["installation"])
    identifier(scope["boot_id"])
    integer(scope["uid"], maximum=2**32 - 1)
    integer(scope["gid"], maximum=2**32 - 1)
    unit = "gitgood-installation-" + scope["installation"] + ".service"
    require(scope["unit"] == unit and scope["service_scope_observed"] is True and scope["installation_readiness_established"] is False)
    definition = scope["unit_definition"]
    closed(definition, ("path", "device", "inode", "bytes", "sha256"))
    require(definition["path"] == "/etc/systemd/system/" + unit)
    integer(definition["device"])
    integer(definition["inode"])
    integer(definition["bytes"], maximum=16384)
    digest(definition["sha256"])
    manager = scope["manager"]
    closed(manager, ("pid", "birth", "uid", "security", "mount_namespace", "cgroup_namespace"))
    integer(manager["pid"], maximum=2**31 - 1)
    integer(manager["uid"], maximum=2**32 - 1)
    require(manager["uid"] == scope["uid"])
    require(isinstance(manager["birth"], str) and re.fullmatch(r"[1-9][0-9]{0,19}", manager["birth"]))
    integer(int(manager["birth"]))
    for field, prefix in [("mount_namespace", "mnt"), ("cgroup_namespace", "cgroup")]:
        require(isinstance(manager[field], str) and re.fullmatch(prefix + r":\[[1-9][0-9]{0,19}\]", manager[field]))
    security = manager["security"]
    closed(security, ("gid", "supplementary_groups", "capabilities", "no_new_privileges"))
    integer(security["gid"], maximum=2**32 - 1)
    require(security["gid"] == scope["gid"] and security["no_new_privileges"] is True)
    require(type(security["supplementary_groups"]) is list and security["supplementary_groups"] in [[], [scope["gid"]]])
    require(all(type(group) is int for group in security["supplementary_groups"]))
    capabilities = security["capabilities"]
    closed(capabilities, ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"))
    require(all(type(value) is int and value == 0 for value in capabilities.values()))
    path = "/sys/fs/cgroup/system.slice/" + unit
    directory(scope["parent"], path, scope["uid"])
    closed(scope["groups"], ("driver", "native", "web", "edge", "maintenance"))
    identities = {(scope["parent"]["device"], scope["parent"]["inode"])}
    for name, value in scope["groups"].items():
        directory(value, path + "/" + name, scope["uid"])
        require(value["device"] == scope["parent"]["device"])
        identities.add((value["device"], value["inode"]))
    require(len(identities) == 6)
    limits = scope["limits"]
    closed(limits, ("cpu_quota_us", "cpu_period_us", "memory_bytes", "swap_bytes"))
    integer(limits["cpu_quota_us"], 1000, 6400000)
    integer(limits["cpu_period_us"], 100000, 100000)
    integer(limits["memory_bytes"], 134217728, 68719476736)
    integer(limits["swap_bytes"], 0, 0)


def validate_generation(record):
    closed(record, ("protocol", "kind", "generation", "installation", "durable_binding_sha256",
                    "predecessor_sha256", "scope", "created_at"))
    require(type(record["protocol"]) is int and record["protocol"] == 2 and record["kind"] == "resource_generation")
    identifier(record["generation"])
    identifier(record["installation"])
    require(record["generation"] != record["installation"])
    digest(record["durable_binding_sha256"])
    if record["predecessor_sha256"] is not None:
        digest(record["predecessor_sha256"])
    validate_scope(record["scope"])
    require(record["installation"] == record["scope"]["installation"])
    value = record["created_at"]
    require(isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z", value))
    try:
        datetime.datetime.fromisoformat(value)
    except ValueError:
        raise GenerationRefused("Native generation record refused") from None
    require(len(canonical(record)) <= 16384)


def generation_sha256(record):
    validate_generation(record)
    return hashlib.sha256(canonical(record)).hexdigest()


def validate_successor(previous, current):
    validate_generation(previous)
    validate_generation(current)
    require(current["predecessor_sha256"] == generation_sha256(previous))
    require(current["generation"] != previous["generation"] and current["installation"] == previous["installation"])
    require(current["durable_binding_sha256"] == previous["durable_binding_sha256"] and current["scope"] != previous["scope"])


def make_generation(scope, durable_binding_sha256, *, generation, created_at, previous=None):
    # Deep-copy input data; later caller edits cannot mutate the constructed record.
    validate_scope(scope)
    digest(durable_binding_sha256)
    identifier(generation)
    copied = json.loads(canonical(scope))
    record = {"protocol": 2, "kind": "resource_generation", "generation": generation,
              "installation": copied.get("installation"), "durable_binding_sha256": durable_binding_sha256,
              "predecessor_sha256": generation_sha256(previous) if previous is not None else None,
              "scope": copied, "created_at": created_at}
    validate_generation(record)
    if previous is not None:
        validate_successor(previous, record)
    return record


def parse_generation(raw):
    require(type(raw) is bytes and 0 < len(raw) <= 16384)
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value)
            value[key] = item
        return value
    try:
        record = json.loads(raw, object_pairs_hook=unique)
    except (ValueError, UnicodeError, RecursionError):
        raise GenerationRefused("Native generation record refused") from None
    validate_generation(record)
    return record
