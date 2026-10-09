"""Observe the retained recovery point without releasing retirement custody."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
import uuid

from native_actions import verify_runtime_stage
from native_activation import NativeActivation
from native_inventory import directory_identity, executable_identity, private_bytes
from retirement_database import RetirementDatabase
from retirement_quiescence import RetirementQuiescence
from upgrade_journal import canonical, require, unique_object, validate_time

MAX_ARCHIVE = 16 * 1024**3 + 16 * 1024**2 + 64
CORE = {"candidate", "installation", "ciphertext_sha256", "recovery_point", "resource_fingerprints", "database_fingerprint"}


def retained_file_identity(path, maximum=MAX_ARCHIVE):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(descriptor, "rb") as source:
        before = os.fstat(source.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid() and before.st_nlink == 1)
        require(not before.st_mode & 0o077 and 0 < before.st_size <= maximum)
        digest = hashlib.file_digest(source, "sha256").hexdigest()
        after = os.fstat(source.fileno())
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns))
    named = path.lstat()
    require((named.st_dev, named.st_ino) == (before.st_dev, before.st_ino))
    return {"path": str(path), "device": before.st_dev, "inode": before.st_ino, "uid": before.st_uid,
            "mode": stat.S_IMODE(before.st_mode), "bytes": before.st_size, "sha256": digest}


def capture_retention_inputs(operation, installation, archive, key, pg_dump, pg_restore):
    """Read-only inputs; independently pin the canonical digest before admission."""
    archive_identity = retained_file_identity(archive)
    key_identity = retained_file_identity(key, 32)
    require(key_identity["bytes"] == 32)
    return {"protocol": 1, "operation": operation, "installation": installation,
            "archive": archive_identity, "key": key_identity,
            "scratch": directory_identity(Path(archive).parent, private=True),
            "tools": {"pg_dump": executable_identity(pg_dump), "pg_restore": executable_identity(pg_restore)}}


class RetirementSnapshot:
    def __init__(self, journal, resource_plan, retention, expected_checkpoint, configuration_bytes):
        self.journal = journal
        self.bindings = resource_plan["bindings"]
        self.quiescence = RetirementQuiescence(journal, resource_plan)
        self.database = RetirementDatabase(journal, resource_plan, configuration_bytes)
        require(isinstance(retention, dict) and set(retention) == {"protocol", "operation", "installation", "archive", "key", "scratch", "tools"})
        require(type(retention["protocol"]) is int and retention["protocol"] == 1)
        require(retention["operation"] == journal.operation and retention["installation"] == journal.plan["installation"])
        require(hashlib.sha256(canonical(retention)).hexdigest() == journal.plan["retention_sha256"])
        require(set(retention["tools"]) == {"pg_dump", "pg_restore"})
        self.retention = json.loads(canonical(retention))
        require(isinstance(expected_checkpoint, dict) and set(expected_checkpoint) == {"protocol", "purpose", "status", "checks", "limitations", *CORE})
        require(type(expected_checkpoint["protocol"]) is int and expected_checkpoint["protocol"] == 1)
        require(expected_checkpoint["purpose"] == "retirement_checkpoint" and expected_checkpoint["status"] == "complete")
        require(hashlib.sha256(canonical(expected_checkpoint)).hexdigest() == journal.plan["checkpoint_sha256"])
        require(expected_checkpoint["candidate"] == journal.plan["candidate"] and expected_checkpoint["installation"] == journal.plan["installation"])
        require(expected_checkpoint["ciphertext_sha256"] == journal.plan["archive_sha256"] == retention["archive"]["sha256"])
        require(isinstance(expected_checkpoint["resource_fingerprints"], dict) and set(expected_checkpoint["resource_fingerprints"]) == {"git", "ssh", "configuration"})
        for digest in [expected_checkpoint["database_fingerprint"], *expected_checkpoint["resource_fingerprints"].values()]:
            require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest))
        validate_time(expected_checkpoint["recovery_point"])
        require(isinstance(expected_checkpoint["checks"], list) and len(expected_checkpoint["checks"]) == 3)
        require(isinstance(expected_checkpoint["limitations"], list) and len(expected_checkpoint["limitations"]) == 3)
        self.expected = json.loads(canonical(expected_checkpoint))
        self.request = {"protocol": 1, "candidate": journal.plan["candidate"], "installation": journal.plan["installation"],
                        "ciphertext_sha256": journal.plan["archive_sha256"], "source": retention["archive"]["path"],
                        "key_path": retention["key"]["path"],
                        "roots": {"git": self.bindings["resources"]["storage"]["path"], "ssh": self.bindings["resources"]["ssh-host"]["path"],
                                  "configuration": self.bindings["resources"]["configuration"]["path"]}}
        for path in [retention["archive"]["path"], retention["key"]["path"], retention["scratch"]["path"]]:
            require(not any(Path(path).is_relative_to(Path(root)) for root in self.request["roots"].values()))
        require(retention["scratch"]["path"] == str(Path(retention["archive"]["path"]).parent))

    def _custody(self):
        self.journal._owned()
        require(self.journal.record["stage"] == "archive_verify" and self.journal.record["status"] == "running")
        self.quiescence.observe()
        raw = private_bytes(self.journal.directory / "current-release-v1.json", 16384)
        require(hashlib.sha256(raw).hexdigest() == self.journal.plan["current_sha256"])
        pointer = NativeActivation.validate(json.loads(raw, object_pairs_hook=unique_object))
        require(all(pointer[key] == self.journal.plan[key] for key in ["installation", "candidate", "artifact_sha256", "bindings_sha256"]))
        require(directory_identity(pointer["stage"]["path"], private=True) == pointer["stage"])
        return Path(pointer["stage"]["path"])

    def _retained(self):
        for name, maximum in [("archive", MAX_ARCHIVE), ("key", 32)]:
            require(retained_file_identity(self.retention[name]["path"], maximum) == self.retention[name])
        require(directory_identity(self.retention["scratch"]["path"], private=True) == self.retention["scratch"])
        for value in self.retention["tools"].values():
            require(executable_identity(value["path"]) == value)
        for name in ["node", "git"]:
            require(executable_identity(self.bindings["executables"][name]["path"]) == self.bindings["executables"][name])

    def _original_database(self):
        value = self.database.observe()
        require(value["original_present_verified"] and not value["desired_state_verified"] and value["connected_clients"] == 0)
        return value

    def _run_packaged(self, module, prefix, request_value, database_environment):
        """Fixed packaged reads/imports with retained custody and private results."""
        require((module, prefix) in {("retirement-snapshot.mjs", "snapshot"),
                                     ("retirement-restore-data.mjs", "restored-data")})
        stage = self._custody()
        self._retained()
        before = self._original_database()
        verified = verify_runtime_stage(stage, self.journal.plan["candidate"], self.journal.plan["artifact_sha256"])
        modules = list((verified["code"] / "forge/lib").glob("gitgood-*/priv/operations/" + module))
        require(len(modules) == 1)
        identifier = str(uuid.uuid4())
        request_path = self.journal.directory / (prefix + "-request-" + identifier + ".json")
        request = canonical(request_value) + b"\n"
        descriptor = self.journal._private_open(request_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        with os.fdopen(descriptor, "wb") as output:
            output.write(request)
            output.flush()
            os.fsync(output.fileno())
        environment = {**database_environment, "PATH": "/usr/bin:/bin", "HOME": "/nonexistent",
                       "GITGOOD_PSQL": self.database.psql["path"], "GITGOOD_GIT": self.bindings["executables"]["git"]["path"],
                       "GITGOOD_PG_DUMP": self.retention["tools"]["pg_dump"]["path"], "GITGOOD_PG_RESTORE": self.retention["tools"]["pg_restore"]["path"]}
        stdout = self.journal.directory / (prefix + "-result-" + identifier + ".json")
        stderr = self.journal.directory / (prefix + "-private-error-" + identifier + ".log")
        output = self.journal._private_open(stdout, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        try:
            errors = self.journal._private_open(stderr, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except BaseException:
            os.close(output)
            raise
        with os.fdopen(output, "wb") as sink, os.fdopen(errors, "wb") as diagnostic:
            child = subprocess.Popen([self.bindings["executables"]["node"]["path"], str(modules[0]), str(request_path), hashlib.sha256(request).hexdigest()],
                                     env=environment, stdin=subprocess.DEVNULL, stdout=sink, stderr=diagnostic, umask=0o077)
            try:
                deadline = time.monotonic() + 600
                while child.poll() is None:
                    require(time.monotonic() < deadline)
                    require(self._custody() == stage)
                    time.sleep(.05)
                require(child.returncode == 0)
                os.fsync(sink.fileno())
                os.fsync(diagnostic.fileno())
            finally:
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=5)
        observed = json.loads(private_bytes(stdout, 65536), object_pairs_hook=unique_object)
        require(self._custody() == stage)
        self._retained()
        after = self._original_database()
        require(after == before)
        require(verify_runtime_stage(stage, self.journal.plan["candidate"], self.journal.plan["artifact_sha256"]) == verified)
        return observed

    def observe(self):
        observed = self._run_packaged("retirement-snapshot.mjs", "snapshot", self.request, self.database.environment)
        require(isinstance(observed, dict) and set(observed) == {"protocol", "purpose", "status", "checks", "limitations", *CORE})
        require(type(observed["protocol"]) is int and observed["protocol"] == 1 and observed["purpose"] == "retirement_snapshot" and observed["status"] == "observed")
        require(isinstance(observed["checks"], list) and len(observed["checks"]) == 3 and isinstance(observed["limitations"], list) and len(observed["limitations"]) == 2)
        require(all(observed[key] == self.expected[key] for key in CORE))
        value = {"archive_identity_verified": True, "current_snapshot_verified": True, "writer_exclusion_verified": True,
                 "checkpoint_sha256": self.journal.plan["checkpoint_sha256"], "retention_sha256": self.journal.plan["retention_sha256"],
                 "resource_plan_sha256": self.journal.plan["resource_plan_sha256"], "archive_sha256": self.journal.plan["archive_sha256"],
                 "snapshot_sha256": hashlib.sha256(canonical(observed)).hexdigest()}
        # No restore_function_verified flag: a snapshot cannot authorize removal.
        return {**value, "receipt_sha256": hashlib.sha256(canonical(value)).hexdigest()}
