"""Fixed retained usability after the exact original database and stores are absent."""
import hashlib
import os
from pathlib import Path

from native_inventory import private_bytes
from retirement_database import RetirementDatabase
from retirement_probes import RetirementProbes
from retirement_quiescence import RetirementQuiescence
from retirement_runtime import RetirementRuntime
from retirement_snapshot import retained_file_identity
from upgrade_journal import canonical, require


CONFIGURATION_FILE = "retirement-configuration-v1.json"


def retain_configuration(journal, resource_plan, configuration_bytes):
    """Keep the independently hashed private database authority outside removable stores."""
    journal._owned()
    require(journal.record["stage"] in {"archive_verify", "database_remove"} and journal.record["status"] == "running")
    require(hashlib.sha256(canonical(resource_plan)).hexdigest() == journal.plan["resource_plan_sha256"])
    require(isinstance(configuration_bytes, bytes) and 0 < len(configuration_bytes) <= 131_072)
    require(hashlib.sha256(configuration_bytes).hexdigest() == resource_plan["bindings"]["configuration_sha256"]["installation.json"])
    exclusion = RetirementQuiescence(journal, resource_plan)
    exclusion.observe()
    database = RetirementDatabase(journal, resource_plan, configuration_bytes)
    observed = database.observe()
    require(observed["original_present_verified"] and not observed["desired_state_verified"] and observed["connected_clients"] == 0)
    source = Path(resource_plan["bindings"]["resources"]["configuration"]["path"]) / "installation.json"
    require(private_bytes(source) == configuration_bytes)
    path = journal.directory / CONFIGURATION_FILE
    for name in ["storage", "ssh-host", "configuration"]:
        original = resource_plan["bindings"]["resources"][name]["path"]
        require(not path.is_relative_to(Path(original)))
    if not path.exists() and not path.is_symlink():
        descriptor = journal._private_open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        with os.fdopen(descriptor, "wb") as output:
            output.write(configuration_bytes)
            output.flush()
            os.fsync(output.fileno())
    require(private_bytes(path) == configuration_bytes)
    descriptor = journal._private_open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    descriptor = os.open(journal.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    exclusion.observe()
    require(database.observe() == observed and private_bytes(source) == configuration_bytes)
    return {"configuration_sha256": hashlib.sha256(configuration_bytes).hexdigest()}


class RetirementRetention:
    def __init__(self, journal, resource_plan, retention, checkpoint, restoration):
        require(journal.record["stage"] == "retention_verify" and journal.record["status"] in {"running", "failed", "uncertain"})
        require(journal.record["completed"] == ["quiesce", "archive_verify", "database_remove", "stores_remove"])
        configuration = private_bytes(journal.directory / CONFIGURATION_FILE)
        self.runtime = RetirementRuntime(journal, resource_plan, retention, checkpoint, restoration, configuration,
                                         lifecycle_stage="retention_verify")
        require(self.runtime.full["protocol"] == 3)

    def verify(self):
        runtime = self.runtime
        require(runtime.journal.record["status"] == "running")
        runtime.empty()
        absence_before = runtime.snapshot._original_database()
        runtime.data.verify("observe")
        previous = retained_file_identity(runtime.root / "git/.gitgood-runtime-v1.json", 4096)
        before = runtime.materialization(marker=previous)
        try:
            runtime.start()
            observations = RetirementProbes(runtime).functional()
            marker = runtime.runtime_marker()
        finally:
            runtime.stop()
        after = runtime.materialization(marker=marker)
        for key in ["target_root", "target_database", "target_installation", "ports", "configuration_sha256", "target_resource_fingerprints"]:
            require(before[key] == after[key])
        restored = runtime.data.verify("observe")
        runtime.empty()
        absence_after = runtime.snapshot._original_database()
        require(absence_before == absence_after)
        value = {"retained_archive_usable": True, "owned_resources_absent": True, "writer_exclusion_verified": True,
                 "archive_sha256": runtime.journal.plan["archive_sha256"], "retention_sha256": runtime.journal.plan["retention_sha256"],
                 "restore_sha256": runtime.journal.plan["restore_sha256"], "resource_plan_sha256": runtime.journal.plan["resource_plan_sha256"],
                 "absence_sha256": hashlib.sha256(canonical(absence_after)).hexdigest(),
                 "functional_probe_sha256": hashlib.sha256(canonical(observations)).hexdigest(),
                 "target_materialization_sha256": hashlib.sha256(canonical(after)).hexdigest(),
                 "restored_data_sha256": restored["receipt_sha256"], "target_runtime_marker_sha256": marker["sha256"]}
        return {**value, "receipt_sha256": hashlib.sha256(canonical(value)).hexdigest()}

    def resume(self):
        """Source absence and retained inputs must be observed before the same fixed retry."""
        runtime = self.runtime
        require(runtime.journal.record["status"] in {"failed", "uncertain"})
        runtime.stop()
        runtime.snapshot._retained()
        absent = runtime.snapshot._original_database()
        value = {"unapplied_verified": True, "absence_sha256": hashlib.sha256(canonical(absent)).hexdigest(),
                 "archive_sha256": runtime.journal.plan["archive_sha256"]}
        runtime.journal.reconcile(applied=False, evidence={**value, "receipt_sha256": hashlib.sha256(canonical(value)).hexdigest()})
        runtime.journal.begin("retention_verify")
        return self.verify()
