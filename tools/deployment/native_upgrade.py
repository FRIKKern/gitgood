"""Fixed native upgrade execution; plans contain identities and paths, never commands."""
import hashlib
import json
from pathlib import Path
import re
import sys

from inspect_native_artifact import inspect_native_artifact
from native_actions import NativeActions, verify_runtime_stage
from native_activation import NativeActivation
from native_edge import start_edge
from native_inventory import directory_identity, private_bytes
from native_probes import NativeProbes
from stage_native_artifact import stage_native_artifact
from upgrade_history import UpgradeHistory
from upgrade_journal import canonical, require, unique_object


def receipt(value):
    return {"receipt_sha256": hashlib.sha256(canonical(value)).hexdigest()}


class NativeUpgrade:
    """An enrolled working release is required before a new operation can start."""
    def __init__(self, root, inventory, history, operation, intent, plan_sha256):
        require(sys.platform == "linux")
        self.root = Path(root)
        self.inventory = inventory
        self.history = UpgradeHistory(history, operation, intent)
        self.intent = self.history.intent
        self.operation = self.history.operation
        require(isinstance(inventory, dict) and isinstance(inventory.get("bindings"), dict))
        require(inventory.get("bindings_sha256") == self.intent["bindings_sha256"])
        require(hashlib.sha256(canonical(inventory["bindings"])).hexdigest() == self.intent["bindings_sha256"])
        require(inventory["bindings"].get("installation") == self.intent["installation"])
        require(directory_identity(self.root, private=True) == inventory["bindings"].get("resources", {}).get("root"))
        require(isinstance(plan_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", plan_sha256))
        self.plan_sha256 = plan_sha256
        self.plan_path = self.history.directory / "plans" / (self.operation + ".json")
        self.plan = self._plan()
        self.stage = Path(self.plan["stages"]) / ("native-" + self.operation)

    def _plan(self):
        directory_identity(self.history.directory, private=True)
        directory_identity(self.plan_path.parent, private=True)
        raw = private_bytes(self.plan_path, 16_384)
        require(hashlib.sha256(raw).hexdigest() == self.plan_sha256)
        value = json.loads(raw, object_pairs_hook=unique_object)
        require(isinstance(value, dict) and set(value) == {"protocol", "operation", "intent_sha256", "old_stage", "new_archive",
                "stages", "credentials", "credentials_sha256", "expected_current_sha256"})
        require(type(value["protocol"]) is int and value["protocol"] == 1 and value["operation"] == self.operation)
        require(value["intent_sha256"] == hashlib.sha256(canonical(self.intent)).hexdigest())
        for name in ["old_stage", "new_archive", "stages", "credentials"]:
            require(isinstance(value[name], str) and 0 < len(value[name]) <= 4096)
            path = Path(value[name])
            require(path.is_absolute() and path.resolve() == path)
            if name != "new_archive":
                directory_identity(path, private=True)
        for name in ["credentials_sha256", "expected_current_sha256"]:
            require(isinstance(value[name], str) and re.fullmatch(r"[0-9a-f]{64}", value[name]))
        return value

    def _context(self, journal):
        require(self._plan() == self.plan)
        actions = NativeActions(self.root, self.inventory, journal)
        probes = NativeProbes(actions, self.plan["credentials"], self.plan["credentials_sha256"])
        activation = NativeActivation(self.history, journal)
        old = verify_runtime_stage(self.plan["old_stage"], self.intent["old_candidate"], self.intent["old_artifact_sha256"])
        return actions, probes, activation, old

    def _closed_previous(self, journal):
        """Recovery never treats a successful spawn as a working previous release."""
        journal.begin_recovery()
        # Group stops stay possible even when PostgreSQL is unavailable. Do them
        # before database-dependent re-observation or any attempt to restart code.
        actions = NativeActions.__new__(NativeActions)
        actions.bindings = self.inventory["bindings"]
        actions.journal = journal
        stopped = {name: actions.stop_group(name) for name in ["edge", "native", "web", "maintenance"]}
        actions, probes, activation, old = self._context(journal)
        start_edge(actions, "maintenance")
        maintenance = probes.maintenance()
        schema = probes.schema()
        require(schema == old["migrations"])
        current = activation.read()
        require(current is not None)
        require((current["record"]["candidate"], current["record"]["artifact_sha256"]) in {
            (self.intent["old_candidate"], self.intent["old_artifact_sha256"]),
            (self.intent["new_candidate"], self.intent["new_artifact_sha256"])})
        actions.start_native(self.plan["old_stage"], previous=True)
        actions.start_web(self.plan["old_stage"], previous=True)
        internal = probes.functional(self.plan["old_stage"], previous=True)
        require(probes.maintenance() == maintenance)
        actions.stop_group("edge")
        start_edge(actions, "active")
        public = probes.functional(self.plan["old_stage"], previous=True, public=True)
        pointer = activation.activate(self.plan["old_stage"], schema, public["receipt"], expected_current_sha256=current["sha256"])
        observations = {"stopped": stopped, "schema": schema, "maintenance": maintenance,
                        "internal": internal, "public": public, "pointer_sha256": pointer["sha256"]}
        journal.recovered({**receipt(observations), "previous_identity_verified": True, "public_functional_probe": True})
        return {"outcome": "recovered_previous", "operation": self.operation, "status": journal.status(), "observations": observations}

    def recover_previous(self):
        with self.history as journal:
            require(journal.record["status"] in {"failed", "uncertain"})
            try:
                return self._closed_previous(journal)
            except Exception:
                if journal.usable and journal.record["status"] == "running":
                    journal.fail("recovery_failed")
                # An incompatible or unavailable schema leaves routes closed or
                # in maintenance. No down migration or unproven code rollback.
                raise

    def run(self):
        with self.history as journal:
            # This first executing profile does not infer applied stages on retry.
            # Same-intent failed/uncertain operations require explicit recovery.
            require(journal.record["status"] == "pending" and not journal.record["completed"])
            code = "artifact_refused"
            try:
                journal.begin("inspect")
                actions, probes, activation, old = self._context(journal)
                current = activation.read()
                require(current is not None and current["sha256"] == self.plan["expected_current_sha256"])
                require(current["record"]["stage"] == directory_identity(self.plan["old_stage"], private=True))
                require(current["record"]["candidate"] == self.intent["old_candidate"] and current["record"]["artifact_sha256"] == self.intent["old_artifact_sha256"])
                schema = probes.schema()
                require(schema == old["migrations"] == current["record"]["schema"])
                baseline = probes.functional(self.plan["old_stage"], previous=True, public=True)
                inspected = inspect_native_artifact(self.plan["new_archive"], self.intent["new_artifact_sha256"], self.intent["new_candidate"])
                require(inspected["migrations"][:len(schema)] == schema)
                require(self.intent["rollback_policy"] == ("same_schema_only" if inspected["migrations"] == schema else "forward_only"))
                journal.succeed("inspect", receipt({"baseline": baseline, "schema": schema, "candidate": inspected}))

                code = "staging_failed"
                journal.begin("stage")
                staged = stage_native_artifact(self.plan["new_archive"], self.intent["new_artifact_sha256"], self.intent["new_candidate"], self.plan["stages"], self.operation)
                verified = verify_runtime_stage(self.stage, self.intent["new_candidate"], self.intent["new_artifact_sha256"])
                journal.succeed("stage", receipt(staged))

                code = "stop_failed"
                journal.begin("maintenance")
                actions.stop_group("edge")
                start_edge(actions, "maintenance")
                maintenance = probes.maintenance()
                stopped = {name: actions.stop_group(name) for name in ["native", "web", "maintenance"]}
                before = probes.schema()
                require(before == schema)
                journal.succeed("maintenance", receipt({"maintenance": maintenance, "stopped": stopped, "schema": before}))

                code = "migration_failed"
                journal.begin("migrate")
                migrated = actions.migrate(self.stage)
                after = probes.schema()
                require(after == verified["migrations"])
                journal.succeed("migrate", receipt({"command": migrated, "before": before, "after": after}))

                code = "readiness_failed"
                journal.begin("verify")
                actions.start_native(self.stage)
                actions.start_web(self.stage)
                probes.readiness(self.intent["new_candidate"])
                code = "functional_probe_failed"
                internal = probes.functional(self.stage)
                require(probes.maintenance() == maintenance)
                journal.succeed("verify", receipt(internal))

                code = "activation_failed"
                journal.begin("activate")
                actions.stop_group("edge")
                start_edge(actions, "active")
                ready = probes.readiness(self.intent["new_candidate"], public=True)
                journal.succeed("activate", receipt(ready))

                code = "public_probe_failed"
                journal.begin("public_verify")
                public = probes.functional(self.stage, public=True)
                require(probes.schema() == after)
                pointer = activation.activate(self.stage, after, public["receipt"], expected_current_sha256=self.plan["expected_current_sha256"])
                observations = {"before": before, "after": after, "internal": internal, "public": public, "pointer_sha256": pointer["sha256"]}
                journal.succeed("public_verify", receipt(observations))
                return {"outcome": "activated", "operation": self.operation, "status": journal.status(), "observations": observations}
            except Exception:
                if journal.usable and journal.record["status"] == "running":
                    journal.fail(code)
                    if journal.record["stage"] not in {"inspect", "stage"}:
                        try:
                            return self._closed_previous(journal)
                        except Exception:
                            if journal.usable and journal.record["status"] == "running":
                                journal.fail("recovery_failed")
                raise
