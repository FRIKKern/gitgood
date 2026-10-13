"""Fixed, bounded request entry for independently sealed generation admission."""
import json
from pathlib import Path
import sys

from native_durable_database import unique, validate_database
from native_lifecycle_generation_reader import open_reader
from native_service_scope import root_file
from resource_generations import canonical, identifier


class AdmissionRequestRefused(Exception):
    pass


def require(value):
    if not value:
        raise AdmissionRequestRefused("Native generation admission request refused")


def admit_request(raw):
    """Read one closed request; all authority comes from its fixed Root seal."""
    require(type(raw) is bytes and 0 < len(raw) <= 4096 and b"\0" not in raw)
    request = json.loads(raw, object_pairs_hook=unique)
    require(type(request) is dict and set(request) == {"protocol", "installation", "worker", "owner_pid"})
    require(type(request["protocol"]) is int and request["protocol"] == 2)
    identifier(request["installation"])
    require(type(request["worker"]) is str and request["worker"] in {"native", "maintenance"})
    require(type(request["owner_pid"]) is int and 1 < request["owner_pid"] < 2**31)
    installation = request["installation"]
    path = Path("/etc/gitgood/installations") / installation / "generation-admission-v2.json"
    seal_file, sealed = root_file(path, 16_384)
    seal = json.loads(sealed, object_pairs_hook=unique)
    require(sealed == canonical(seal))
    require(type(seal) is dict and set(seal) == {"protocol", "kind", "installation", "binding_sha256",
            "history_identity", "lock_identity", "unit_sha256", "executables", "limits", "database"})
    require(type(seal["protocol"]) is int and seal["protocol"] == 2)
    require(seal["kind"] == "native_generation_admission_seal" and seal["installation"] == installation)
    require(type(seal["limits"]) is dict and set(seal["limits"]) == {"cpu_quota_us", "memory_bytes"})
    database = seal["database"]
    require(type(database) is dict)
    validate_database(database, {"PGDATABASE": database.get("database"), "PGUSER": database.get("role"),
                                 "PGPORT": str(database.get("port"))})
    reader = open_reader("/var/lib/gitgood/installations/" + installation, installation,
                                    seal["binding_sha256"], seal["history_identity"], seal["lock_identity"],
                                    seal["unit_sha256"], seal["executables"], worker=request['worker'], **seal["limits"])
    try:result = reader.admit(worker=request["worker"], owner_pid=request["owner_pid"])
    finally:reader.close()
    require(result["published_generation_admitted"] and not result["writer_exclusion_established"])
    require(result["binding_sha256"] == seal["binding_sha256"])
    require(not result["installation_readiness_established"] and not result["lifecycle_responsibility_admitted"])
    require(root_file(path, 16_384) == (seal_file, sealed))
    value = {"protocol": 2, "installation": installation, "worker": request["worker"],
            "pointer": result["pointer"], "binding_sha256": result["binding_sha256"],
            "worker_observation": result["worker_observation"], "database": database,
            "seal_file": seal_file, "published_generation_admitted": True,
            "writer_exclusion_established": False, "installation_readiness_established": False,
            "lifecycle_responsibility_admitted": False}
    if 'lifecycle_observation' in result:
        value['lifecycle_observation'] = result['lifecycle_observation']
    return value


def main():
    try:
        require(len(sys.argv) == 1)
        raw = sys.stdin.buffer.readline(4097)
        require(raw.endswith(b"\n") and len(raw) <= 4096)
        value = canonical(admit_request(raw))
        require(len(value) <= 16_384)
        sys.stdout.buffer.write(value + b"\n")
        sys.stdout.buffer.flush()
        return 0
    except Exception:
        # No credential, request, traceback or configuration is written on refusal.
        sys.stdout.buffer.write(b'{"protocol":2,"status":"refused"}\n')
        sys.stdout.buffer.flush()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
