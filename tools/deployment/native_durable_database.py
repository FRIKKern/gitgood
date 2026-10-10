"""Bounded read-only PostgreSQL identity for protocol-2 durable bindings.

This observation neither excludes writers nor publishes an installation binding.
The caller supplies an independently pinned psql path and private database URL.
"""
import json
import os
import re
import selectors
import subprocess
import time

from native_inventory import database_environment
from upgrade_journal import UpgradeRefused


class DatabaseRefused(Exception):
    pass


def require(value):
    if not value:
        raise DatabaseRefused("Native durable database identity unavailable or changed")


SQL = """SELECT json_build_object(
 'cluster', (SELECT system_identifier::text FROM pg_control_system()),
 'database', d.datname, 'database_oid', d.oid::bigint, 'owner_oid', d.datdba::bigint,
 'role', r.rolname, 'session_role', session_user, 'role_oid', r.oid::bigint,
 'encoding', pg_encoding_to_char(d.encoding), 'version', current_setting('server_version'),
 'address', host(inet_server_addr()), 'port', inet_server_port(),
 'can_login', r.rolcanlogin, 'superuser', r.rolsuper, 'create_database', r.rolcreatedb,
 'create_role', r.rolcreaterole, 'replication', r.rolreplication, 'bypass_rls', r.rolbypassrls,
 'memberships', (SELECT count(*) FROM pg_auth_members WHERE member=r.oid))
 FROM pg_database d JOIN pg_roles r ON r.rolname=current_user
 WHERE d.datname=current_database() AND d.datdba=r.oid"""
FIELDS = {"cluster", "database", "database_oid", "owner_oid", "role", "session_role", "role_oid",
          "encoding", "version", "address", "port", "can_login", "superuser", "create_database",
          "create_role", "replication", "bypass_rls", "memberships"}


def unique(pairs):
    result = {}
    for name, value in pairs:
        require(name not in result)
        result[name] = value
    return result


def validate_database(value, environment):
    require(type(value) is dict and set(value) == FIELDS)
    require(type(value["cluster"]) is str and re.fullmatch(r"[1-9][0-9]{0,19}", value["cluster"]))
    require(int(value["cluster"]) < 2**64)
    for name in ("database_oid", "owner_oid", "role_oid"):
        require(type(value[name]) is int and 0 < value[name] < 2**32)
    require(value["owner_oid"] == value["role_oid"])
    require(value["database"] == environment["PGDATABASE"])
    require(value["role"] == value["session_role"] == environment["PGUSER"])
    require(value["version"] == "18.4" and value["encoding"] == "UTF8")
    require(value["address"] == "127.0.0.1" and type(value["port"]) is int and value["port"] == int(environment["PGPORT"]))
    require(value["can_login"] is True)
    require(all(value[name] is False for name in ("superuser", "create_database", "create_role", "replication", "bypass_rls")))
    require(type(value["memberships"]) is int and value["memberships"] == 0)
    return value


def query_identity(psql, environment, *, timeout=10, maximum=16384):
    # Keep credentials solely in this child's explicit environment, never argv.
    arguments = [psql, "--no-psqlrc", "--tuples-only", "--no-align", "--set=ON_ERROR_STOP=1", "--command", SQL]
    with subprocess.Popen(arguments, env=environment, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as child:
        output = bytearray()
        try:
            deadline = time.monotonic() + timeout
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    require(remaining > 0 and selector.select(remaining))
                    block = os.read(child.stdout.fileno(), min(4096, maximum + 1 - len(output)))
                    if not block:
                        break
                    output.extend(block)
                    require(len(output) <= maximum)
            require(child.wait(timeout=max(.01, deadline - time.monotonic())) == 0)
            require(0 < len(output) <= maximum)
            return bytes(output)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()


def observe_durable_database(psql, database_url):
    """Observe exact ordinary owner identity through a fixed read-only query.

    Executable trust and expected installation/database binding are separate
    caller obligations. No session is retained as a writer-exclusion lease.
    """
    try:
        require(type(psql) is str and psql.startswith("/") and "\0" not in psql and len(psql) <= 4096)
        environment = database_environment(database_url)
        # Empty explicit passwords must not discover an unsealed ~/.pgpass.
        environment["PGPASSFILE"] = "/dev/null"
        raw = query_identity(psql, environment)
        return validate_database(json.loads(raw, object_pairs_hook=unique), environment)
    except DatabaseRefused:
        raise
    except (UpgradeRefused, OSError, ValueError, UnicodeError, RecursionError, subprocess.SubprocessError):
        raise DatabaseRefused("Native durable database identity unavailable or changed") from None
