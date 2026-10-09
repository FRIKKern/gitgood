"""Execute only the fixed owned retirement stages from independently bound inputs."""
import hashlib
import json
from pathlib import Path
import re
import sys

from native_actions import verify_runtime_stage
from native_activation import NativeActivation
from native_inventory import cgroup_identity, directory_identity, private_bytes
from retirement_database import RetirementDatabase
from retirement_fence import RetirementFence
from retirement_journal import RetirementJournal, STAGES
from retirement_quiescence import RetirementQuiescence
from retirement_restore_plan import validate_full_restore_plan
from retirement_restoration import RetirementRestoration
from retirement_retention import CONFIGURATION_FILE, RetirementRetention, retain_configuration
from retirement_snapshot import RetirementSnapshot, retained_file_identity
from retirement_stores import RetirementStores
from upgrade_journal import canonical, require, unique_object

INPUTS = {"plan": ("plan.json", 16_384), "resources": ("resources.json", 33_554_432),
          "retention": ("retention.json", 16_384), "checkpoint": ("checkpoint.json", 16_384),
          "restoration": ("full-restoration-plan.json", 65_536)}
ERRORS = {"quiesce": "quiescence_failed", "archive_verify": "archive_refused",
          "database_remove": "database_remove_failed", "stores_remove": "store_remove_failed",
          "retention_verify": "retention_failed"}


def evidence(value):
    value = {key: item for key, item in value.items() if key != "receipt_sha256"}
    return {**value, "receipt_sha256": hashlib.sha256(canonical(value)).hexdigest()}


class NativeRetirement:
    def __init__(self, history, plan_directory, plan_sha256):
        require(sys.platform == "linux")
        require(isinstance(plan_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", plan_sha256))
        self.directory = Path(plan_directory)
        self.identity = directory_identity(self.directory, private=True)
        self.input_bytes, self.input_identities = self._read()
        self.inputs = {name: json.loads(raw, object_pairs_hook=unique_object) for name, raw in self.input_bytes.items()}
        plan = self.inputs["plan"]
        self.journal = RetirementJournal(history, plan, plan_sha256)
        self.resources = self.inputs["resources"]
        RetirementStores(self.journal, self.resources)
        for name, field in [("resources", "resource_plan_sha256"), ("retention", "retention_sha256"),
                            ("checkpoint", "checkpoint_sha256"), ("restoration", "restore_sha256")]:
            require(hashlib.sha256(canonical(self.inputs[name])).hexdigest() == plan[field])
        self.full = validate_full_restore_plan(self.journal, self.inputs["restoration"])
        require(self.full["protocol"] == 3)
        target = Path(self.full["materialization"]["target_root"]["path"])
        for path in [self.journal.directory, *[self.directory / filename for filename, maximum in INPUTS.values()]]:
            require(not path.is_relative_to(target))
            for name in ["storage", "ssh-host", "configuration"]:
                original = Path(self.resources["bindings"]["resources"][name]["path"])
                require(not path.is_relative_to(original))

    def _read(self):
        require(directory_identity(self.directory, private=True) == self.identity)
        value, identities = {}, {}
        for name, (filename, maximum) in INPUTS.items():
            path = self.directory / filename
            value[name] = private_bytes(path, maximum)
            identities[name] = retained_file_identity(path, maximum)
            require(identities[name]["sha256"] == hashlib.sha256(value[name]).hexdigest())
        require(directory_identity(self.directory, private=True) == self.identity)
        return value, identities

    def _inputs_unchanged(self):
        require(self._read() == (self.input_bytes, self.input_identities))

    def _configuration(self):
        cached = self.journal.directory / CONFIGURATION_FILE
        source = Path(self.resources["bindings"]["resources"]["configuration"]["path"]) / "installation.json"
        raw = private_bytes(cached if cached.exists() or cached.is_symlink() else source)
        require(hashlib.sha256(raw).hexdigest() == self.resources["bindings"]["configuration_sha256"]["installation.json"])
        return raw

    def _snapshot(self, configuration):
        return RetirementSnapshot(self.journal, self.resources, self.inputs["retention"], self.inputs["checkpoint"], configuration)

    def _context(self):
        self._inputs_unchanged()
        journal = self.journal
        journal._owned()
        RetirementFence(journal, self.resources)._custody()
        raw = private_bytes(journal.directory / "current-release-v1.json", 16_384)
        require(hashlib.sha256(raw).hexdigest() == journal.plan["current_sha256"])
        pointer = NativeActivation.validate(json.loads(raw, object_pairs_hook=unique_object))
        require(all(pointer[key] == journal.plan[key] for key in ["installation", "candidate", "artifact_sha256", "bindings_sha256"]))
        require(directory_identity(pointer["stage"]["path"], private=True) == pointer["stage"])
        verify_runtime_stage(pointer["stage"]["path"], journal.plan["candidate"], journal.plan["artifact_sha256"])
        configuration = self._configuration()
        self._snapshot(configuration)._retained()
        return configuration

    def _restoration(self, configuration):
        return RetirementRestoration(self.journal, self.resources, self.inputs["retention"],
                                     self.inputs["checkpoint"], self.full, configuration)

    def _final(self):
        return RetirementRetention(self.journal, self.resources, self.inputs["retention"],
                                   self.inputs["checkpoint"], self.full)

    def _execute(self, stage):
        journal = self.journal
        journal.begin(stage)
        configuration = self._context()
        if stage == "quiesce":
            RetirementFence(journal, self.resources).install()
            return RetirementQuiescence(journal, self.resources).stop()
        RetirementQuiescence(journal, self.resources).observe()
        if stage == "archive_verify":
            action = self._restoration(configuration)
            action.restore_data()
            return action.verify()
        database = RetirementDatabase(journal, self.resources, configuration)
        if stage == "database_remove":
            retain_configuration(journal, self.resources, configuration)
            return database.remove()
        absent = database.observe()
        require(absent["desired_state_verified"] and absent["connected_clients"] == 0)
        if stage == "stores_remove":
            require(private_bytes(journal.directory / CONFIGURATION_FILE) == configuration)
            return RetirementStores(journal, self.resources).remove()
        require(stage == "retention_verify")
        return self._final().verify()

    def _resume(self):
        journal = self.journal
        require(journal.record["status"] in {"failed", "uncertain"})
        stage = journal.record["stage"]
        configuration = self._context()
        if stage == "quiesce":
            fence = RetirementFence(journal, self.resources)
            if fence.path.exists() or fence.path.is_symlink():
                fence.observe()
            # This proves same-resource replay safety, not absence of earlier stops.
            journal.reconcile(applied=False, evidence=evidence({"unapplied_verified": True,
                "resource_plan_sha256": journal.plan["resource_plan_sha256"], "quiescence_replay_safe": True}))
            return self._execute(stage)
        if stage == "archive_verify":
            return self._restoration(configuration).resume(allow_initial_import=True)
        if stage == "retention_verify":
            return self._final().resume()
        RetirementQuiescence(journal, self.resources).observe()
        database = RetirementDatabase(journal, self.resources, configuration)
        observed = database.observe()
        require(observed["connected_clients"] == 0)
        if stage == "stores_remove":
            require(observed["desired_state_verified"])
            require(private_bytes(journal.directory / CONFIGURATION_FILE) == configuration)
            observed = RetirementStores(journal, self.resources).observe()
        else:
            require(stage == "database_remove")
        if observed["desired_state_verified"]:
            journal.reconcile(applied=True, evidence=observed)
            return None
        journal.reconcile(applied=False, evidence=evidence({**observed, "unapplied_verified": True}))
        return self._execute(stage)

    def _result(self, outcome):
        record = self.journal.record
        return {"protocol": 1, "purpose": "native_retirement_execution", "operation": self.journal.operation,
                "installation": self.journal.plan["installation"], "outcome": outcome,
                "status": record["status"], "completed": list(record["completed"]),
                "limitations": ["Retained recovery materials, target, shared roles, history, code and kernel/provider resources remain owned and retained.",
                                "No cancellation, initial enrollment, target allocation, provider deallocation or managed Cloud acceptance."]}

    def run(self):
        self._inputs_unchanged()
        if self.journal.path.exists() or self.journal.path.is_symlink():
            observed = RetirementJournal.read_status(self.journal.directory, self.journal.plan, self.journal.plan_sha256)
            if observed["status"] == "complete":
                return {"protocol": 1, "purpose": "native_retirement_execution", "outcome": "recorded_complete",
                        **observed, "limitations": ["Previously recorded completion only; no new claim, mutation or fresh archive usability observation."]}
        # Refuse wrong driver membership before publishing new responsibility.
        group = self.resources["bindings"]["cgroups"]["driver"]
        require(cgroup_identity(self.journal.plan["installation"], "driver") == group)
        require(Path("/proc/self/cgroup").read_text().splitlines() == ["0::" + group["kernel_path"]])
        with self.journal as journal:
            while journal.record["status"] != "complete":
                stage = journal.record["stage"] if journal.record["status"] in {"failed", "uncertain"} else STAGES[len(journal.record["completed"])]
                try:
                    result = self._resume() if journal.record["status"] in {"failed", "uncertain"} else self._execute(stage)
                    self._inputs_unchanged()
                    if result is not None:
                        journal.succeed(result)
                except Exception:
                    if journal.usable and journal.record["status"] == "running":
                        journal.fail(ERRORS[stage])
                    raise
            return self._result("retired_owned_sources")
