"""Fixed temporary loopback edge; already enrolled by the pinned runtime wrapper."""
import asyncio
import hashlib
import json
from pathlib import Path
import re
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from native_edge import routing_profile, supervise, verification_caddy_source
from native_inventory import directory_identity, executable_identity, private_bytes
from retirement_restore_plan import observe_target_group
from upgrade_journal import require, unique_object


def guardian(path, expected_sha256):
    require(sys.platform == "linux")
    require(isinstance(expected_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", expected_sha256))
    path = Path(path)
    directory_identity(path.parent, private=True)
    raw = private_bytes(path, 16_384)
    require(hashlib.sha256(raw).hexdigest() == expected_sha256)
    plan = json.loads(raw, object_pairs_hook=unique_object)
    require(isinstance(plan, dict) and set(plan) == {"protocol", "installation", "operation", "target_installation",
            "root", "group", "configuration_sha256", "caddy", "module_sha256", "edge_module_sha256", "caddyfile_sha256"})
    require(type(plan["protocol"]) is int and plan["protocol"] == 1)
    require(hashlib.sha256(private_bytes(Path(__file__).resolve())).hexdigest() == plan["module_sha256"])
    require(hashlib.sha256(private_bytes(Path(__file__).resolve().with_name("native_edge.py"))).hexdigest() == plan["edge_module_sha256"])
    root = Path(plan["root"]["path"])
    require(directory_identity(root, private=True) == plan["root"])
    configuration_raw = private_bytes(root / "configuration/installation.json")
    require(hashlib.sha256(configuration_raw).hexdigest() == plan["configuration_sha256"])
    configuration = json.loads(configuration_raw, object_pairs_hook=unique_object)
    require(configuration["installation"] == plan["target_installation"])
    require("GITGOOD_BARKPARK_ORIGIN" not in configuration["forge"])
    profile = routing_profile(configuration)
    require(profile["hostname"] == "127.0.0.1")
    require(executable_identity(plan["caddy"]["path"]) == plan["caddy"])
    source = private_bytes(path.parent / "Caddyfile")
    require(hashlib.sha256(source).hexdigest() == plan["caddyfile_sha256"])
    require(source.decode() == verification_caddy_source(root, configuration))
    group = observe_target_group(plan["installation"], plan["operation"], plan["target_installation"], "edge")
    require(group == plan["group"])
    require(Path("/proc/self/cgroup").read_text().splitlines() == ["0::" + group["kernel_path"]])
    # Mode and binding are fixed here; ordinary native activation remains separate.
    asyncio.run(supervise({"mode": "active", "profile": profile, "caddy": plan["caddy"]},
                          configuration, path.parent, loopback=True))


if __name__ == "__main__":
    try:
        require(len(sys.argv) == 3)
        guardian(sys.argv[1], sys.argv[2])
    except Exception:
        print("Retirement verification edge refused", file=sys.stderr)
        raise SystemExit(1)
