"""Fixed operator choices over an already enrolled native upgrade engine."""
import hashlib
import json
from pathlib import Path
import re
import sys

from native_inventory import cgroup_identity, directory_identity, private_bytes
from native_upgrade import NativeUpgrade
from retirement_snapshot import retained_file_identity
from upgrade_history import UpgradeHistory
from upgrade_journal import canonical, require, unique_object

FILES = {"request": ("request.json", 16_384), "intent": ("intent.json", 16_384),
         "inventory": ("inventory.json", 131_072)}
ACTIONS = {"upgrade": "run", "upgrade-recover": "recover_previous", "upgrade-resume": "resume_forward"}


class NativeUpgradeCommand:
    def __init__(self, history, inputs_directory, request_sha256):
        require(sys.platform == "linux")
        require(isinstance(request_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", request_sha256))
        self.directory = Path(inputs_directory)
        self.directory_identity = directory_identity(self.directory, private=True)
        self.bytes, self.identities = self._read()
        values = {name: json.loads(raw, object_pairs_hook=unique_object) for name, raw in self.bytes.items()}
        request = self.request = values["request"]
        require(isinstance(request, dict) and set(request) == {"protocol", "purpose", "operation", "installation",
                "root", "history", "inventory_sha256", "intent_sha256", "plan_sha256"})
        require(type(request["protocol"]) is int and request["protocol"] == 1 and request["purpose"] == "native_upgrade_execution")
        require(hashlib.sha256(canonical(request)).hexdigest() == request_sha256)
        require(isinstance(request["root"], dict) and isinstance(request["history"], dict))
        require(directory_identity(history, private=True) == request["history"])
        require(directory_identity(request["root"]["path"], private=True) == request["root"])
        for name in ["inventory", "intent"]:
            require(hashlib.sha256(canonical(values[name])).hexdigest() == request[name + "_sha256"])
        inventory, intent = values["inventory"], values["intent"]
        require(isinstance(inventory, dict) and set(inventory) == {"protocol", "installation", "bindings",
                "bindings_sha256", "observed_runtime_candidate", "limitations"})
        require(type(inventory["protocol"]) is int and inventory["protocol"] == 1)
        require(isinstance(inventory["bindings"], dict) and set(inventory["bindings"]) == {"protocol", "installation",
                "host", "uid", "platform", "resources", "configuration_sha256", "ssh_host_key_sha256", "executables", "cgroups", "database"})
        require(request["installation"] == inventory["installation"] == intent["installation"])
        require(inventory["bindings"]["resources"]["root"] == request["root"])
        self.engine = NativeUpgrade(request["root"]["path"], inventory, history, request["operation"], intent, request["plan_sha256"])
        self.plan_identity = retained_file_identity(self.engine.plan_path, 16_384)
        self.plan_directory_identity = directory_identity(self.engine.plan_path.parent, private=True)
        for path in [Path(history), *[self.directory / name for name, maximum in FILES.values()]]:
            for role in ["storage", "ssh-host", "configuration"]:
                require(not path.is_relative_to(Path(inventory["bindings"]["resources"][role]["path"])))

    def _read(self):
        require(directory_identity(self.directory, private=True) == self.directory_identity)
        raw, identities = {}, {}
        for name, (filename, maximum) in FILES.items():
            path = self.directory / filename
            raw[name] = private_bytes(path, maximum)
            identities[name] = retained_file_identity(path, maximum)
            require(identities[name]["sha256"] == hashlib.sha256(raw[name]).hexdigest())
        require(directory_identity(self.directory, private=True) == self.directory_identity)
        return raw, identities

    def observe_inputs(self):
        require(self._read() == (self.bytes, self.identities))
        require(directory_identity(self.request["history"]["path"], private=True) == self.request["history"])
        require(directory_identity(self.request["root"]["path"], private=True) == self.request["root"])
        require(directory_identity(self.engine.plan_path.parent, private=True) == self.plan_directory_identity)
        require(retained_file_identity(self.engine.plan_path, 16_384) == self.plan_identity)
        require(self.engine._plan() == self.engine.plan)

    def run(self, action):
        require(action in ACTIONS)
        self.observe_inputs()
        history = self.engine.history
        if history.path.exists() or history.path.is_symlink():
            index = history._load()
            if index["operations"][-1]["operation"] == self.engine.operation:
                observed = UpgradeHistory.read_history(history.directory, self.engine.operation, self.engine.intent)["operations"][-1]
                if observed["status"] in {"complete", "recovered"}:
                    self.observe_inputs()
                    return {"protocol": 1, "purpose": "native_upgrade_execution", "outcome": "recorded_" + observed["status"],
                            "installation": self.request["installation"], "operation": self.engine.operation,
                            "status": observed["status"], "completed": observed["completed"],
                            "limitations": ["Previously recorded responsibility only; no new claim, mutation or fresh readiness observation."]}
        group = self.engine.inventory["bindings"]["cgroups"]["driver"]
        require(cgroup_identity(self.request["installation"], "driver") == group)
        require(Path("/proc/self/cgroup").read_text().splitlines() == ["0::" + group["kernel_path"]])
        if action == "upgrade":
            result = self.engine.run()
        elif action == "upgrade-recover":
            result = self.engine.recover_previous()
        else:
            result = self.engine.resume_forward()
        self.observe_inputs()
        status = result["status"]
        return {"protocol": 1, "purpose": "native_upgrade_execution", "outcome": result["outcome"],
                "installation": self.request["installation"], "operation": self.engine.operation,
                "status": status["status"], "completed": status["completed"],
                "verification": self.verification(result),
                "limitations": ["Enrolled native installation only; no initial enrollment, allocation, cancellation or managed Cloud acceptance."]}

    def verification(self, result):
        """Publish only closed probe metadata, never remote bodies or credentials."""
        expected = self.engine.intent["old_candidate" if result["outcome"] == "recovered_previous" else "new_candidate"]
        value = result["observations"]
        report = {"candidate": expected, "pointer_sha256": value["pointer_sha256"]}
        require(isinstance(report["pointer_sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", report["pointer_sha256"]))
        for name in ["before", "after"]:
            schema = value.get(name, value.get("schema"))
            require(isinstance(schema, list) and 1 <= len(schema) <= 512)
            require(all(isinstance(item, str) and re.fullmatch(r"[0-9]{1,20}", item) for item in schema))
            report[name + "_schema"] = list(schema)
        for name in ["internal", "public"]:
            probe = value[name]["observations"]
            require(probe["candidate"] == expected and probe["anonymous_refused"] is True)
            require(isinstance(probe["commit"], str) and re.fullmatch(r"[0-9a-f]{40}", probe["commit"]))
            view = {"candidate": expected, "commit": probe["commit"], "anonymous_refused": True}
            for field in ["https_ref_sha256", *(["ssh_ref_sha256"] if name == "public" else [])]:
                require(isinstance(probe[field], str) and re.fullmatch(r"[0-9a-f]{64}", probe[field]))
                view[field] = probe[field]
            ready = probe["ready"]
            require(isinstance(ready, list) and len(ready) == (1 if name == "public" else 2))
            require(all(item["candidate"] == expected and item["service"] in {"gitgood", "gitgood-web"} and item["ready"] is True for item in ready))
            view["ready"] = [{"candidate": expected, "service": item["service"], "ready": True} for item in ready]
            report[name] = view
        return report
