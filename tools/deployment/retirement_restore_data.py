"""Verify recovered database contents while retaining original writer custody."""
import hashlib
import json
import re

from retirement_snapshot import CORE, RetirementSnapshot
from upgrade_journal import canonical, require

TARGET_KEYS = {"address", "cluster", "database", "database_oid", "encoding", "owner_oid", "port", "role_oid", "version"}


class RetirementRestoreData:
    def __init__(self, journal, resource_plan, retention, expected_checkpoint, restoration, configuration_bytes):
        self.snapshot = RetirementSnapshot(journal, resource_plan, retention, expected_checkpoint, configuration_bytes)
        self.journal = journal
        require(isinstance(restoration, dict) and set(restoration) == {"protocol", "purpose", "operation", "installation", "target_database"})
        require(type(restoration["protocol"]) is int and restoration["protocol"] == 1)
        require(restoration["purpose"] == "retirement_restore_data_plan")
        require(restoration["operation"] == journal.operation and restoration["installation"] == journal.plan["installation"])
        require(hashlib.sha256(canonical(restoration)).hexdigest() == journal.plan["restore_sha256"])
        target = restoration["target_database"]
        require(isinstance(target, dict) and set(target) == TARGET_KEYS)
        require(target["database"] == "gitgood_retirement_restore_" + journal.operation.replace("-", ""))
        require(isinstance(target["cluster"], str) and re.fullmatch(r"[0-9]+", target["cluster"]))
        for name in ["database_oid", "owner_oid", "role_oid", "port"]:
            require(type(target[name]) is int and 0 < target[name] < 2**53)
        require(target["database_oid"] != self.snapshot.database.expected["database_oid"])
        require(target["database"] != self.snapshot.database.name)
        require(target["version"] == "18.4" and target["encoding"] == "UTF8" and target["address"] == "127.0.0.1")
        require(target["owner_oid"] == target["role_oid"])
        for name in TARGET_KEYS - {"database", "database_oid"}:
            require(target[name] == self.snapshot.database.expected[name])
        self.restoration = json.loads(canonical(restoration))
        self.target = self.restoration["target_database"]

    def verify(self, phase):
        require(isinstance(phase, str) and phase in {"restore", "observe"})
        request = {key: self.snapshot.request[key] for key in ["protocol", "installation", "candidate", "ciphertext_sha256", "source", "key_path"]}
        request.update(operation=self.journal.operation, phase=phase, target=self.target,
                       scratch_directory=self.snapshot.retention["scratch"]["path"])
        environment = {**self.snapshot.database.environment, "PGDATABASE": self.target["database"]}
        observed = self.snapshot._run_packaged("retirement-restore-data.mjs", "restored-data", request, environment)
        require(isinstance(observed, dict) and set(observed) == {"protocol", "purpose", "status", "operation", "target_database", "phase", "checks", "limitations", *CORE})
        require(type(observed["protocol"]) is int and observed["protocol"] == 1)
        require(observed["purpose"] == "retirement_restore_data" and observed["status"] == "verified")
        require(observed["operation"] == self.journal.operation and observed["phase"] == phase and observed["target_database"] == self.target)
        require(all(observed[key] == self.snapshot.expected[key] for key in CORE))
        require(isinstance(observed["checks"], list) and len(observed["checks"]) == 4)
        require(isinstance(observed["limitations"], list) and len(observed["limitations"]) == 3)
        value = {"archive_identity_verified": True, "restored_data_verified": True, "writer_exclusion_verified": True,
                 "restore_sha256": self.journal.plan["restore_sha256"], "retention_sha256": self.journal.plan["retention_sha256"],
                 "resource_plan_sha256": self.journal.plan["resource_plan_sha256"], "archive_sha256": self.journal.plan["archive_sha256"],
                 "target_database_sha256": hashlib.sha256(canonical(self.target)).hexdigest(),
                 "restored_data_sha256": hashlib.sha256(canonical(observed)).hexdigest()}
        # Actual application startup and authenticated functional probes remain
        # separate. This receipt cannot acknowledge the archive stage by itself.
        return {**value, "receipt_sha256": hashlib.sha256(canonical(value)).hexdigest()}
