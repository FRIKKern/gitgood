"""Produce restoration authority only from fixed actual runtime and retention checks."""
import hashlib

from retirement_probes import RetirementProbes
from retirement_runtime import RetirementRuntime
from retirement_snapshot import retained_file_identity
from native_inventory import directory_identity
from upgrade_journal import canonical, require, UpgradeRefused


class RetirementRestoration:
    def __init__(self, journal, resource_plan, retention, checkpoint, restoration, configuration_bytes):
        self.runtime = RetirementRuntime(journal, resource_plan, retention, checkpoint, restoration, configuration_bytes)
        require(self.runtime.full["protocol"] == 3)

    def restore_data(self):
        """Fixed first import into the independently allocated empty target."""
        self.runtime.empty()
        return self.runtime.data.verify("restore")

    def verify(self):
        runtime = self.runtime
        # A retry observes actual restored contents, never reimports populated data.
        runtime.data.verify("observe")
        runtime.empty()
        previous = runtime.root / "git/.gitgood-runtime-v1.json"
        prior_marker = retained_file_identity(previous, 4096) if previous.exists() or previous.is_symlink() else None
        before = runtime.materialization(marker=prior_marker)
        probes = RetirementProbes(runtime)
        try:
            runtime.start()
            observations = probes.functional()
            marker = runtime.runtime_marker()
        finally:
            # Identity-bound whole-group shutdown remains possible when the
            # database, archive or process diagnostics are unavailable.
            runtime.stop()
        after = runtime.materialization(marker=marker)
        for field in ["target_root", "target_database", "target_installation", "ports", "configuration_sha256", "target_resource_fingerprints"]:
            require(before[field] == after[field])
        runtime.data.verify("observe")
        current = runtime.snapshot.observe(restoration=runtime.full)
        require(current["current_snapshot_verified"] is True)
        runtime.empty()
        value = {"archive_identity_verified": True, "restore_function_verified": True,
                 "current_snapshot_verified": True, "writer_exclusion_verified": True,
                 "restore_sha256": runtime.journal.plan["restore_sha256"], "retention_sha256": runtime.journal.plan["retention_sha256"],
                 "resource_plan_sha256": runtime.journal.plan["resource_plan_sha256"], "archive_sha256": runtime.journal.plan["archive_sha256"],
                 "functional_probe_sha256": hashlib.sha256(canonical(observations)).hexdigest(),
                 "target_materialization_sha256": hashlib.sha256(canonical(after)).hexdigest(), "target_runtime_marker_sha256": marker["sha256"]}
        return {**value, "receipt_sha256": hashlib.sha256(canonical(value)).hexdigest()}

    def resume(self, *, allow_initial_import=False):
        """Reconcile source preservation, then permit fixed existing-target retry."""
        runtime = self.runtime
        require(type(allow_initial_import) is bool)
        require(runtime.journal.record["stage"] == "archive_verify" and runtime.journal.record["status"] in {"failed", "uncertain"})
        runtime.stop()
        evidence = runtime.snapshot.reconcile_unapplied(restoration=runtime.full)
        runtime.journal.reconcile(applied=False, evidence=evidence)
        runtime.journal.begin("archive_verify")
        if allow_initial_import:
            require(directory_identity(runtime.root, private=True) == runtime.target["target_root"])
            if not list(runtime.root.iterdir()):
                try:
                    runtime.data.verify("observe")
                except UpgradeRefused:
                    # The fixed helper independently refuses a populated, partial,
                    # replaced or wrong database before import. No cleanup/reset.
                    # Invalid retained inputs also refuse again before mutation.
                    self.restore_data()
        return self.verify()
