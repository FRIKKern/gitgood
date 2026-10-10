"""Read-only admission of an actual native/maintenance owner and its helper."""
import os
from pathlib import Path
import subprocess

from native_service_scope import ServiceRefused, _observe_service, process_identity, read_bytes, require


def _ancestry(owner, scope, worker):
    """Bind every birth in the caller-to-owner chain; no command lines or signals."""
    relative = scope["groups"][worker]["path"].removeprefix("/sys/fs/cgroup")
    uid, gid = scope["uid"], scope["gid"]
    pid = os.getpid()
    seen = set()
    identities = []
    for _ in range(64):
        require(pid > 1 and pid not in seen)
        seen.add(pid)
        identity = process_identity(pid, uid, gid, relative)
        require(identity["mount_namespace"] == scope["manager"]["mount_namespace"])
        require(identity["cgroup_namespace"] == scope["manager"]["cgroup_namespace"])
        identities.append(identity)
        if pid == owner:
            break
        raw = read_bytes(Path("/proc") / str(pid) / "stat").decode("ascii")
        fields = raw[raw.rfind(")") + 2:].split()
        require(len(fields) >= 20 and fields[19] == identity["birth"])
        require(fields[1].isdecimal())
        pid = int(fields[1])
    else:
        raise ServiceRefused("Native worker ancestry unavailable or changed")
    # Reobserve both births and parent edges. A reparented helper cannot borrow
    # a live unrelated owner's identity at an unchanged group path.
    for index, identity in enumerate(identities):
        require(process_identity(identity["pid"], uid, gid, relative) == identity)
        if index + 1 < len(identities):
            raw = read_bytes(Path("/proc") / str(identity["pid"]) / "stat").decode("ascii")
            fields = raw[raw.rfind(")") + 2:].split()
            require(len(fields) >= 20 and fields[19] == identity["birth"])
            require(fields[1] == str(identities[index + 1]["pid"]))
    return identities


def observe_worker(installation, unit_sha256, *, worker, owner_pid, cpu_quota_us, memory_bytes, _root_files=None):
    """Observe fixed worker roles without allowing a worker to publish a generation.

    The independently sealed unit digest and limits remain required. The actual
    owner and caller must share the selected leaf and be an ancestor/descendant
    pair with ordinary credentials, empty capabilities and NoNewPrivileges.
    This observation establishes neither generation custody nor app readiness.
    """
    try:
        require(type(worker) is str and worker in {"native", "maintenance"})
        require(type(owner_pid) is int and 1 < owner_pid < 2147483648)
        options = {'caller_group':worker}
        if _root_files is not None: options['_root_files'] = _root_files
        scope = _observe_service(installation, unit_sha256, cpu_quota_us, memory_bytes, **options)
        require(owner_pid != scope["manager"]["pid"])
        chain = _ancestry(owner_pid, scope, worker)
        require(_observe_service(installation, unit_sha256, cpu_quota_us, memory_bytes, **options) == scope)
        require(_ancestry(owner_pid, scope, worker) == chain)
        return {"service_scope": scope, "worker": worker, "owner": chain[-1], "caller": chain[0],
                "generation_publication_established": False, "installation_readiness_established": False}
    except ServiceRefused:
        raise
    except (OSError, ValueError, UnicodeError, KeyError, TypeError, subprocess.SubprocessError):
        raise ServiceRefused("Native worker scope unavailable or changed") from None
