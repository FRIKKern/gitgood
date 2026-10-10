"""Private sealed first-install inputs; no allocation, commands or journal claims."""
import hashlib
import json
from pathlib import Path
import re
import sys

from enrollment_journal import digest, identity, validate_intent
from native_allocation import supported_platform
from native_inventory import EXECUTABLES, directory_identity, private_bytes
from retirement_snapshot import retained_file_identity
from upgrade_journal import canonical, require, unique_object

FILES = {"request": ("request.json", 16_384), "allocation": ("allocation.json", 131_072),
         "inputs": ("inputs.json", 16_384)}


def bootstrap_digest(value):
    payload = ["gitgood-installation-owner-v1", *[value[key] for key in
               ["installation", "request", "username", "team", "password"]]]
    return hashlib.sha256(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


class NativeEnrollmentInputs:
    def __init__(self, directory, request_sha256):
        require(sys.platform == "linux")
        supported_platform()
        digest(request_sha256)
        self.directory = Path(directory)
        self.directory_identity = directory_identity(self.directory, private=True)
        self.bytes, self.file_identities = self._read()
        values = {key: json.loads(raw, object_pairs_hook=unique_object) for key, raw in self.bytes.items()}
        request = self.request = values["request"]
        require(isinstance(request, dict) and set(request) == {"protocol", "purpose", "operation", "intent"})
        require(type(request["protocol"]) is int and request["protocol"] == 1 and request["purpose"] == "native_initial_enrollment")
        require(hashlib.sha256(canonical(request)).hexdigest() == request_sha256)
        self.request_sha256 = request_sha256
        identity(request["operation"])
        self.intent = validate_intent(request["intent"])
        allocation = self.allocation = values["allocation"]
        require(isinstance(allocation, dict) and set(allocation) == {"protocol", "purpose", "profile", "installation",
                "bindings", "bindings_sha256", "scope", "empty_directories", "empty_database"})
        require(type(allocation["protocol"]) is int and allocation["protocol"] == 1 and allocation["purpose"] == "native_initial_allocation")
        require(allocation["profile"] == "ubuntu-24.04-linux-x86_64" and allocation["installation"] == self.intent["installation"])
        require(hashlib.sha256(canonical(allocation)).hexdigest() == self.intent["allocation_sha256"])
        bindings = allocation["bindings"]
        require(isinstance(bindings, dict) and set(bindings) == {"protocol", "installation", "host", "uid", "platform", "resources",
                "configuration_sha256", "ssh_host_key_sha256", "executables", "cgroups", "database"})
        require(type(bindings["protocol"]) is int and bindings["protocol"] == 1 and bindings["installation"] == self.intent["installation"])
        require(bindings["platform"] == "linux-x86_64" and hashlib.sha256(canonical(bindings)).hexdigest() == allocation["bindings_sha256"])
        require(isinstance(bindings["executables"], dict) and set(bindings["executables"]) == EXECUTABLES)
        for observed in bindings["executables"].values():
            require(isinstance(observed, dict) and set(observed) == {"path", "device", "inode", "uid", "bytes", "sha256"})
        require(isinstance(bindings["cgroups"], dict) and set(bindings["cgroups"]) == {"native", "web", "edge", "maintenance", "driver"})
        for observed in bindings["cgroups"].values():
            require(isinstance(observed, dict) and set(observed) == {"path", "kernel_path", "device", "inode", "delegated_uid"})
        database=bindings["database"]
        require(isinstance(database, dict) and set(database) == {"cluster", "database", "database_oid", "owner_oid", "role_oid", "encoding", "version", "address", "port"})
        require(database["version"] == "18.4" and database["encoding"] == "UTF8" and database["address"] == "127.0.0.1")
        scope = allocation["scope"]
        require(isinstance(scope, dict) and set(scope) == {"boot_id", "mount_namespace", "cgroup_namespace"})
        identity(scope["boot_id"])
        for name, prefix in [("mount_namespace", "mnt"), ("cgroup_namespace", "cgroup")]:
            require(isinstance(scope[name], str) and re.fullmatch(prefix + r":\[[0-9]+\]", scope[name]))
        resources = bindings["resources"]
        require(isinstance(resources, dict) and set(resources) == {"root", "configuration", "storage", "ssh-host"})
        self.root = Path(resources["root"]["path"])
        for name, recorded in resources.items():
            expected = self.root if name == "root" else self.root / name
            require(directory_identity(expected, private=True) == recorded)
        require(not self.directory.is_relative_to(self.root) and not self.root.is_relative_to(self.directory))
        empties = allocation["empty_directories"]
        require(isinstance(empties, dict) and set(empties) == {"storage", "history", "staging"})
        for name, recorded in empties.items():
            require(directory_identity(self.root / name, private=True) == recorded)
        require(empties["storage"] == resources["storage"])
        empty = allocation["empty_database"]
        require(isinstance(empty, dict) and set(empty) == {"relations", "functions", "types", "schemas", "extensions", "public_writable"})
        require(all(type(empty[name]) is int and empty[name] == 0 for name in ["relations", "functions", "types", "schemas", "extensions"]))
        require(empty["public_writable"] is True)
        inputs = self.inputs = values["inputs"]
        require(isinstance(inputs, dict) and set(inputs) == {"protocol", "bootstrap", "plan"})
        require(type(inputs["protocol"]) is int and inputs["protocol"] == 1 and hashlib.sha256(canonical(inputs)).hexdigest() == self.intent["inputs_sha256"])
        bootstrap = inputs["bootstrap"]
        require(isinstance(bootstrap, dict) and set(bootstrap) == {"installation", "request", "username", "team", "password"})
        require(bootstrap["installation"] == self.intent["installation"])
        identity(bootstrap["request"])
        require(all(isinstance(value, str) and "\0" not in value for value in bootstrap.values()))
        require(all(re.fullmatch(r"[a-z][a-z0-9-]{1,39}", bootstrap[name]) for name in ["username", "team"]))
        require(12 <= len(bootstrap["password"].encode("utf-8")) <= 256)
        plan = inputs["plan"]
        require(isinstance(plan, dict) and set(plan) == {"archive", "bootstrap_request_sha256"})
        require(bootstrap_digest(bootstrap) == plan["bootstrap_request_sha256"])
        archive = plan["archive"]
        require(isinstance(archive, dict) and set(archive) == {"path", "device", "inode", "uid", "mode", "bytes", "sha256"})
        require(isinstance(archive["path"], str) and not Path(archive["path"]).is_relative_to(self.root))
        require(retained_file_identity(archive["path"], 1_073_741_824) == archive and archive["sha256"] == self.intent["artifact_sha256"])
        self.archive = archive
        self.observe_inputs()

    def _read(self):
        require(directory_identity(self.directory, private=True) == self.directory_identity)
        raw, identities = {}, {}
        for key, (name, maximum) in FILES.items():
            path = self.directory / name
            raw[key] = private_bytes(path, maximum)
            identities[key] = retained_file_identity(path, maximum)
            require(hashlib.sha256(raw[key]).hexdigest() == identities[key]["sha256"])
        require(directory_identity(self.directory, private=True) == self.directory_identity)
        return raw, identities

    def observe_inputs(self):
        require(self._read() == (self.bytes, self.file_identities))
        for name, recorded in self.allocation["bindings"]["resources"].items():
            require(directory_identity(self.root if name == "root" else self.root / name, private=True) == recorded)
        for name, recorded in self.allocation["empty_directories"].items():
            require(directory_identity(self.root / name, private=True) == recorded)
        require(retained_file_identity(self.archive["path"], 1_073_741_824) == self.archive)
