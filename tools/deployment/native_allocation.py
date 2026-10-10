"""Read-only admission of an already allocated empty native installation scope."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

from native_inventory import (capture_native_resources, cgroup_identity, database_environment,
                              directory_identity, private_bytes)
from native_actions import FORGE_KEYS, WEB_KEYS
from upgrade_journal import canonical, require, unique_object

EMPTY_SQL = """SELECT json_build_object(
 'relations', (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
               WHERE n.nspname <> 'information_schema' AND n.nspname !~ '^pg_'),
 'functions', (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
               WHERE n.nspname <> 'information_schema' AND n.nspname !~ '^pg_'),
 'types', (SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
               WHERE n.nspname <> 'information_schema' AND n.nspname !~ '^pg_'),
 'schemas', (SELECT count(*) FROM pg_namespace
               WHERE nspname <> 'information_schema' AND nspname <> 'public' AND nspname !~ '^pg_'),
 'extensions', (SELECT count(*) FROM pg_extension WHERE extname <> 'plpgsql'),
 'public_writable', (has_schema_privilege(current_user,'public','USAGE')
                     AND has_schema_privilege(current_user,'public','CREATE')))"""


def supported_platform():
    require(sys.platform == "linux" and platform.machine() == "x86_64")
    values = platform.freedesktop_os_release()
    require(values.get("ID") == "ubuntu" and values.get("VERSION_ID") == "24.04")
    return "ubuntu-24.04-linux-x86_64"


def observe_empty_database(psql, database_url):
    result = subprocess.run([psql, "--no-psqlrc", "--tuples-only", "--no-align",
                             "--set=ON_ERROR_STOP=1", "--command", EMPTY_SQL],
                            env=database_environment(database_url), stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)
    require(result.returncode == 0 and 0 < len(result.stdout) <= 8192)
    value = json.loads(result.stdout, object_pairs_hook=unique_object)
    require(isinstance(value, dict) and set(value) == {
        "relations", "functions", "types", "schemas", "extensions", "public_writable"})
    require(all(type(value[name]) is int and value[name] == 0
                for name in ["relations", "functions", "types", "schemas", "extensions"]))
    require(value["public_writable"] is True)
    return value


def scope_identity():
    return {"boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            "mount_namespace": os.readlink("/proc/self/ns/mnt"),
            "cgroup_namespace": os.readlink("/proc/self/ns/cgroup")}


def capture_initial_allocation(root, executables):
    profile = supported_platform()  # Refuse unsupported hosts before executable hashes or SQL.
    root = Path(root)
    root_identity = directory_identity(root, private=True)
    require({path.name for path in root.iterdir()} == {"configuration", "storage", "ssh-host", "history", "staging"})
    empty_directories = {}
    for name in ["storage", "history", "staging"]:
        empty_directories[name] = directory_identity(root / name, private=True)
        require(not list((root / name).iterdir()))
    observed = capture_native_resources(root, executables)
    configuration = json.loads(private_bytes(root / "configuration/installation.json"), object_pairs_hook=unique_object)
    require(set(configuration["forge"]) <= FORGE_KEYS and set(configuration["web"]) == WEB_KEYS)
    require(configuration["forge"].get("GITGOOD_INSTALLATION_ID") == observed["installation"])
    empty_database = observe_empty_database(observed["bindings"]["executables"]["psql"]["path"],
                                           configuration["forge"]["DATABASE_URL"])
    for name in ["native", "web", "edge", "maintenance"]:
        group = observed["bindings"]["cgroups"][name]
        require(cgroup_identity(observed["installation"], name) == group)
        require(dict(line.split() for line in (Path(group["path"]) / "cgroup.events").read_text().splitlines()).get("populated") == "0")
        require(not (Path(group["path"]) / "cgroup.procs").read_text().strip())
    require(directory_identity(root, private=True) == root_identity)
    for name, identity in empty_directories.items():
        require(directory_identity(root / name, private=True) == identity and not list((root / name).iterdir()))
    # Re-observe exact resources after the emptiness checks. This is admission,
    # not a reservation against subsequent writes by the same trusted actor.
    require(capture_native_resources(root, executables) == observed)
    allocation = {"protocol": 1, "purpose": "native_initial_allocation", "profile": profile,
                  "installation": observed["installation"], "bindings": observed["bindings"],
                  "bindings_sha256": observed["bindings_sha256"], "scope": scope_identity(),
                  "empty_directories": empty_directories, "empty_database": empty_database}
    return {"allocation": allocation, "allocation_sha256": hashlib.sha256(canonical(allocation)).hexdigest(),
            "limitations": ["Read-only admission of an already allocated host; no allocation, reservation or installation commands.",
                            "Kernel bindings apply to this boot and namespaces; reboot requires explicit scope re-enrollment.",
                            "No artifact readiness, owner creation, activation, managed Cloud or complete journey acceptance."]}
