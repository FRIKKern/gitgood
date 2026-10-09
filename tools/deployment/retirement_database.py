"""Exact local database retirement; never force-disconnect clients or drop roles."""
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys

from native_inventory import cgroup_identity, database_environment, executable_identity
from upgrade_journal import canonical, require, unique_object


class RetirementDatabase:
    def __init__(self, journal, resource_plan, configuration_bytes):
        require(sys.platform == "linux")
        require(isinstance(resource_plan, dict) and set(resource_plan) == {"protocol", "operation", "installation", "bindings", "bindings_sha256", "entries"})
        require(type(resource_plan["protocol"]) is int and resource_plan["protocol"] == 1)
        require(hashlib.sha256(canonical(resource_plan)).hexdigest() == journal.plan["resource_plan_sha256"])
        self.journal = journal
        self.bindings = resource_plan["bindings"]
        require(resource_plan["operation"] == journal.operation and resource_plan["installation"] == journal.plan["installation"])
        require(hashlib.sha256(canonical(self.bindings)).hexdigest() == resource_plan["bindings_sha256"] == journal.plan["bindings_sha256"])
        require(self.bindings["installation"] == journal.plan["installation"] and self.bindings["uid"] == os.getuid() and self.bindings["host"] == socket.gethostname())
        require(isinstance(configuration_bytes, bytes) and 0 < len(configuration_bytes) <= 131_072)
        require(hashlib.sha256(configuration_bytes).hexdigest() == self.bindings["configuration_sha256"]["installation.json"])
        config = json.loads(configuration_bytes, object_pairs_hook=unique_object)
        require(config["installation"] == journal.plan["installation"])
        self.environment = database_environment(config["forge"]["DATABASE_URL"])
        self.expected = self.bindings["database"]
        self.name = self.environment["PGDATABASE"]
        require(self.name == self.expected["database"] and self.name not in {"postgres", "template0", "template1"})
        require(re.fullmatch(r"[a-z][a-z0-9_]{0,62}", self.name))
        self.psql = self.bindings["executables"]["psql"]
        self.master = {**self.environment, "PGDATABASE": "postgres", "PGAPPNAME": "gitgood native retirement"}

    def _custody(self, *, observing=False):
        self.journal._owned()
        require(self.journal.record["stage"] in ({"database_remove", "stores_remove", "retention_verify"} if observing else {"database_remove"}))
        require(self.journal.record["status"] in ({"running", "failed", "uncertain"} if observing else {"running"}))
        require(executable_identity(self.psql["path"]) == self.psql)
        for name in ["native", "web", "edge", "maintenance", "driver"]:
            group = self.bindings["cgroups"][name]
            require(cgroup_identity(self.bindings["installation"], name) == group)
            if name == "driver":
                require(Path("/proc/self/cgroup").read_text().splitlines() == ["0::" + group["kernel_path"]])
            else:
                require(dict(line.split() for line in (Path(group["path"]) / "cgroup.events").read_text().splitlines()).get("populated") == "0")
                require(not (Path(group["path"]) / "cgroup.procs").read_text().strip())

    def _command(self, sql, *, mutating=False):
        environment = dict(self.master)
        if mutating:
            environment["PGOPTIONS"] = "-c statement_timeout=10000 -c lock_timeout=5000 -c search_path=pg_catalog -c default_transaction_read_only=off"
        result = subprocess.run([self.psql["path"], "--no-psqlrc", "--tuples-only", "--no-align", "--set=ON_ERROR_STOP=1", "--command", sql],
                                env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=15)
        require(result.returncode == 0 and len(result.stdout) <= 8192)
        return result.stdout

    def _observe(self):
        # Read through the shared administrative database, so a lost drop
        # acknowledgement can be reconciled even when the target no longer exists.
        sql = """SELECT json_build_object(
 'cluster', (SELECT system_identifier::text FROM pg_control_system()),
 'database_oid', d.oid::bigint, 'owner_oid', d.datdba::bigint, 'role_oid', r.oid::bigint,
 'encoding', pg_encoding_to_char(d.encoding), 'version', current_setting('server_version'),
 'address', host(inet_server_addr()), 'port', inet_server_port(),
 'clients', (SELECT count(*) FROM pg_stat_activity WHERE datname='""" + self.name + """' AND backend_type='client backend'))
 FROM pg_roles r LEFT JOIN pg_database d ON d.datname='""" + self.name + "' WHERE r.rolname=current_user"
        value = json.loads(self._command(sql), object_pairs_hook=unique_object)
        require(set(value) == {"cluster", "database_oid", "owner_oid", "role_oid", "encoding", "version", "address", "port", "clients"})
        require(all(value[key] == self.expected[key] for key in ["cluster", "role_oid", "version", "address", "port"]))
        require(type(value["clients"]) is int and value["clients"] >= 0)
        absent = value["database_oid"] is None
        if absent:
            require(value["owner_oid"] is None and value["encoding"] is None and value["clients"] == 0)
        else:
            require(all(value[key] == self.expected[key] for key in ["database_oid", "owner_oid", "encoding"]))
        return {"resource_reobserved": True, "desired_state_verified": absent,
                "original_present_verified": not absent, "connected_clients": value["clients"],
                "bindings_sha256": self.journal.plan["bindings_sha256"],
                "resource_plan_sha256": self.journal.plan["resource_plan_sha256"],
                "database_identity_sha256": hashlib.sha256(canonical(value)).hexdigest()}

    def observe(self):
        self._custody(observing=True)
        value = self._observe()
        self._custody(observing=True)
        return {**value, "receipt_sha256": hashlib.sha256(canonical(value)).hexdigest()}

    def remove(self):
        self._custody()
        before = self._observe()
        require(before["connected_clients"] == 0)
        if not before["desired_state_verified"]:
            self._custody()
            # No FORCE, role deletion, client termination, or schema-level cleanup.
            # The supported owner profile serializes all managed lifecycle actors;
            # privileged external database administrators remain a trust boundary.
            self._command('DROP DATABASE "' + self.name + '"', mutating=True)
        value = self._observe()
        self._custody()
        require(value["desired_state_verified"])
        return {**value, "receipt_sha256": hashlib.sha256(canonical(value)).hexdigest()}
