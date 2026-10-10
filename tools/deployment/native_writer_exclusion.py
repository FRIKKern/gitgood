"""Fixed ordinary PostgreSQL writer exclusion for generation reconciliation.

This shares the existing application's advisory namespace/key. It creates no
marker or active generation and never grants authority from a lost session.
"""
import json
import os
import re
import selectors
import subprocess
import sys
import threading
import time
import uuid

from native_durable_database import SQL, DatabaseRefused, unique, validate_database
from native_inventory import database_environment
from upgrade_journal import UpgradeRefused

NAMESPACE = 1_197_034_575
KEY = 1
HELD = """EXISTS (SELECT 1 FROM pg_locks WHERE locktype='advisory'
 AND pid=pg_backend_pid() AND classid::bigint=1197034575 AND objid::bigint=1
 AND objsubid=2 AND mode='ExclusiveLock' AND granted)"""


class WriterExclusionRefused(Exception):
    pass


def require(value):
    if not value:
        raise WriterExclusionRefused("Native database writer exclusion unavailable or lost")


class NativeWriterExclusion:
    """One owned psql session; callers recheck before and after fixed effects.

    Expected database identity and psql trust are independent caller obligations.
    Exclusion is cooperative with the native application's existing lease;
    unexpected other client connections refuse. No generic SQL API is exposed.
    """
    def __init__(self, psql, database_url, expected_database):
        require(sys.platform == "linux" and os.getuid() == os.geteuid() and os.getuid() > 0)
        require(type(psql) is str and psql.startswith("/") and "\0" not in psql and len(psql) <= 4096)
        try:
            self.environment = database_environment(database_url)
            self.environment["PGPASSFILE"] = "/dev/null"
            self.environment["PGAPPNAME"] = "gitgood native writer exclusion v2"
            validate_database(expected_database, self.environment)
            self.expected = json.loads(json.dumps(expected_database, allow_nan=False))
        except (UpgradeRefused, DatabaseRefused, TypeError, ValueError):
            raise WriterExclusionRefused("Native database writer exclusion unavailable or lost") from None
        self.psql = psql
        self.owner = (os.getpid(), os.getuid(), threading.get_ident())
        self.child = None
        self.backend_pid = None
        self.backend_birth = None
        self.usable = True

    def _owner(self):
        require((os.getpid(), os.getuid(), threading.get_ident()) == self.owner and os.getuid() == os.geteuid())

    def _exchange(self, acquire):
        self._owner()
        require(self.usable and self.child is not None and self.child.poll() is None)
        nonce = str(uuid.uuid4())
        held = "pg_try_advisory_lock(1197034575::int,1::int)" if acquire else HELD
        command = ("SELECT json_build_object('request','" + nonce + "','identity',(" + SQL + "),"
                   "'held'," + held + ",'backend_pid',pg_backend_pid(),'backend_birth',"
                   "(SELECT floor(extract(epoch FROM backend_start)*1000000)::bigint::text "
                   "FROM pg_stat_activity WHERE pid=pg_backend_pid()),'clients',"
                   "(SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
                   "AND backend_type='client backend'));\n").encode()
        require(len(command) < 4096)
        require(self.child.stdin.write(command) == len(command))
        self.child.stdin.flush()
        output = bytearray()
        deadline = time.monotonic() + 10
        with selectors.DefaultSelector() as selector:
            selector.register(self.child.stdout, selectors.EVENT_READ)
            while b"\n" not in output:
                remaining = deadline - time.monotonic()
                require(remaining > 0 and selector.select(remaining))
                block = os.read(self.child.stdout.fileno(), min(4096, 16_385 - len(output)))
                require(block)
                output.extend(block)
                require(len(output) <= 16_384)
        require(output.endswith(b"\n") and output.count(b"\n") == 1)
        value = json.loads(output, object_pairs_hook=unique)
        require(type(value) is dict and set(value) == {"request", "identity", "held", "backend_pid", "backend_birth", "clients"})
        require(value["request"] == nonce and value["held"] is True)
        require(type(value["backend_pid"]) is int and 0 < value["backend_pid"] < 2**31)
        require(type(value["backend_birth"]) is str and re.fullmatch(r"[1-9][0-9]{0,19}", value["backend_birth"]))
        require(int(value["backend_birth"]) < 2**64)
        require(type(value["clients"]) is int and value["clients"] == 1)
        validate_database(value["identity"], self.environment)
        require(value["identity"] == self.expected)
        if acquire:
            require(self.backend_pid is None)
            self.backend_pid = value["backend_pid"]
            self.backend_birth = value["backend_birth"]
        else:
            require(value["backend_pid"] == self.backend_pid and value["backend_birth"] == self.backend_birth)
        require(self.child.poll() is None)
        return {"held": True, "backend_pid": self.backend_pid, "backend_birth": self.backend_birth, "database": self.expected.copy(),
                "generation_published": False}

    def __enter__(self):
        self._owner()
        require(self.usable and self.child is None)
        try:
            self.child = subprocess.Popen([self.psql, "--quiet", "--no-psqlrc", "--tuples-only",
                                           "--no-align", "--set=ON_ERROR_STOP=1"],
                                          env=self.environment, stdin=subprocess.PIPE,
                                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                          bufsize=0)
            self._exchange(True)
            return self
        except (OSError, ValueError, DatabaseRefused, WriterExclusionRefused, subprocess.SubprocessError):
            self.close()
            raise WriterExclusionRefused("Native database writer exclusion unavailable or lost") from None

    def check(self):
        self._owner()
        try:
            return self._exchange(False)
        except (OSError, ValueError, DatabaseRefused, WriterExclusionRefused, subprocess.SubprocessError):
            self.close()
            raise WriterExclusionRefused("Native database writer exclusion unavailable or lost") from None

    def close(self):
        self._owner()
        self.usable = False
        if self.child is not None:
            if self.child.poll() is None:
                self.child.terminate()
                try:
                    self.child.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.child.kill()
                    self.child.wait()
            for pipe in [self.child.stdin, self.child.stdout]:
                if pipe is not None:
                    pipe.close()
            self.child = None

    def __exit__(self, kind, value, trace):
        self.close()
