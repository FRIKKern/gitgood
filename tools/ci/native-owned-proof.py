#!/usr/bin/env python3
"""Bounded, disposable GitHub Ubuntu 24.04 ownership component proof.

Run as root only on a fresh GitHub-hosted runner after building the clean release
and pinned runtimes. Never enrolls/activates a product, repairs prior ownership,
starts a VM, or removes a retained marker. See native-hosted-ownership.md.
"""
import argparse
from contextlib import ExitStack
from functools import cached_property
import ast
import base64
import copy
import ctypes
import cProfile
import hashlib
import hmac
from http.cookies import SimpleCookie
import itertools
import json
import os
from pathlib import Path
import platform
import pstats
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import time
import uuid
import urllib.error
import urllib.request
import socket
import ssl
import root_runtime_probe
import native_read_probe
import native_path_probe

sys.dont_write_bytecode = True
LIMITS = {"cpu_quota_us": 200000, "memory_bytes": 536870912}
COPY_LIMIT = 2 * 1024**3
FILE_LIMIT = 64 * 1024**2  # OTP 29's first dual-mapped JIT memfd is 64 MiB.
MODULES = Path("/opt/gitgood/native/v2")
CASES = ("helper-loss", "marker-permission-loss", "original-backend-loss")
BASE_ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
STARTUP_CALLS = {"profile", "monitor", "admission", "inputs", "artifact", "configuration",
                 "lease", "fence", "claim", "attachment"}
STARTUP_MARKS = {"bootstrap", "build-valid", "dependencies", "application-start", "application-started",
                 "witness-started", "witness-current", "witness-samples", "descendant-started", "attached"}


def require(value, phase="fixture invariant"):
    if not value:
        raise ValueError(phase)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def read_json(path, maximum=65536):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= maximum)
    return json.loads(path.read_bytes())


def write_new(path, value, mode=0o644, uid=0, gid=0):
    raw = value if isinstance(value, bytes) else canonical(value)
    require(len(raw) <= 131072)
    partial = path.parent / ('.fixture-' + str(uuid.uuid4()) + '.partial')
    descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as target:
        target.write(raw)
        target.flush()
        os.fchown(target.fileno(), uid, gid)
        os.fchmod(target.fileno(), mode)
        os.fsync(target.fileno())
    if sys.platform == 'linux':
        rename = ctypes.CDLL(None, use_errno=True).renameat2
        rename.argtypes = [ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
        rename.restype = ctypes.c_int
        if rename(-100,os.fsencode(partial),-100,os.fsencode(path),1) != 0:
            raise OSError(ctypes.get_errno(),'Fixture publication refused')
        directory = os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(directory)
        finally:os.close(directory)
    elif os.name == 'nt':
        # Windows rename refuses an existing destination. This path permits
        # small local fixture tests, never a hosted ownership proof.
        os.rename(partial,path)
    else:
        raise ValueError('Unsupported fixture publication platform')


def command(arguments, *, environment=None, input_bytes=None, timeout=20):
    # Child output stays private. Failed commands reveal only the current phase.
    result = subprocess.run(arguments, env=environment or BASE_ENV, input=input_bytes,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    require(result.returncode == 0, "bounded fixture command failed")
    require(len(result.stdout) <= 131072 and len(result.stderr) <= 131072, "command output limit")
    return result.stdout


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def identity(path):
    value = path.lstat()
    return {"device": value.st_dev, "inode": value.st_ino, "uid": value.st_uid}


def file_record(path, uid):
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_uid == uid)
    require(stat.S_IMODE(before.st_mode) == 0o600 and 0 < before.st_size <= 131072)
    return {"path": str(path), **identity(path), "bytes": before.st_size, "sha256": digest(path)}


def fingerprint(path):
    value = path.lstat()
    require(stat.S_ISREG(value.st_mode) and value.st_nlink == 1 and value.st_size <= 65536)
    return {"device": value.st_dev, "inode": value.st_ino, "uid": value.st_uid,
            "mode": stat.S_IMODE(value.st_mode), "bytes": value.st_size, "sha256": digest(path)}


def root_directory(path):
    """Create only missing ancestors; refuse symlink/writable existing custody."""
    path = Path(path)
    for entry in reversed([path, *path.parents]):
        if not entry.exists():
            entry.mkdir(mode=0o755)
        value = entry.lstat()
        require(stat.S_ISDIR(value.st_mode) and value.st_uid == 0 and not value.st_mode & 0o022)
        require(entry.resolve() == entry)


def harden_hosted_opt():
    """Secure only the disposable runner's /opt directory, never its children."""
    require(sys.platform == "linux" and os.geteuid() == 0)
    require(os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted")
    path = Path("/opt")
    require(path.resolve(strict=True) == path)
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(descriptor)
        require(stat.S_ISDIR(before.st_mode) and before.st_uid == 0)
        original = (before.st_dev, before.st_ino, before.st_uid, before.st_gid)
        named_before = path.lstat()
        require(tuple(getattr(named_before, key) for key in ["st_dev", "st_ino", "st_uid", "st_gid"]) == original)
        # GitHub's image setup makes /opt writable. Production ancestors must
        # be root-controlled; secure the actual parent instead of exempting it.
        os.fchmod(descriptor, 0o755)
        after = os.fstat(descriptor)
        require(tuple(getattr(after, key) for key in ["st_dev", "st_ino", "st_uid", "st_gid"]) == original)
        require(stat.S_ISDIR(after.st_mode) and stat.S_IMODE(after.st_mode) == 0o755)
        named = path.lstat()
        require(tuple(getattr(named, key) for key in ["st_dev", "st_ino", "st_uid", "st_gid", "st_mode"]) ==
                tuple(getattr(after, key) for key in ["st_dev", "st_ino", "st_uid", "st_gid", "st_mode"]))
        return {"path": "/opt", "device": after.st_dev, "inode": after.st_ino, "uid": after.st_uid,
                "before_mode": stat.S_IMODE(before.st_mode), "after_mode": stat.S_IMODE(after.st_mode),
                "recursive_changes": False, "production_guards_modified": False}
    finally:
        os.close(descriptor)


def copy_inventory(source):
    source = source.resolve(strict=True)
    paths = sorted(source.rglob("*")) if source.is_dir() else [source]
    require(len(paths) <= 30000, "runtime file count limit")
    total = 0
    for path in paths:
        resolved = path.resolve(strict=True)
        require(resolved.is_relative_to(source if source.is_dir() else source.parent))
        value = resolved.stat()
        require(stat.S_ISREG(value.st_mode) or (stat.S_ISDIR(value.st_mode) and not path.is_symlink()))
        if stat.S_ISREG(value.st_mode):
            total += value.st_size
            require(value.st_size <= 268435456 and total <= COPY_LIMIT, "runtime byte limit")
    return paths, total


def copy_runtime(source, destination):
    source = source.resolve(strict=True)
    paths, total = copy_inventory(source)
    require(not destination.exists() and not destination.is_symlink())
    if source.is_dir():
        destination.mkdir(mode=0o755)
    for path in paths:
        target = destination / path.relative_to(source) if source.is_dir() else destination
        if path.is_dir():
            target.mkdir(mode=0o755)
        else:
            shutil.copyfile(path, target, follow_symlinks=True)
            os.chmod(target, 0o755 if path.stat().st_mode & 0o111 else 0o644)
            require(target.stat().st_nlink == 1 and digest(target) == digest(path))
    return total


def module_closure(directory):
    """Only production Python dependencies of the actual protected entries."""
    tree = ast.parse((directory / "native_generation_admission_entry.py").read_text())
    assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == "REQUIRED_MODULES" for target in node.targets))
    pending = list(ast.literal_eval(assignment.value.args[0]))
    found = set()
    while pending:
        name = pending.pop()
        if name in found:
            continue
        require(re.fullmatch(r"[a-z][a-z0-9_]*\.py", name) and not name.startswith("test_"))
        path = directory / name
        require(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= 1024**2)
        found.add(name)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                imports = [node.module.split(".")[0]]
            elif isinstance(node, ast.Import):
                imports = [alias.name.split(".")[0] for alias in node.names]
            else:
                continue
            pending.extend(module + ".py" for module in imports if (directory / (module + ".py")).is_file())
        require(len(found) <= 128)
    return sorted(found)


def relocate_postgresql_client(runtime):
    """Relocate this fixture copy only; no environment-based library override."""
    psql = runtime / "postgres/bin/psql"
    library = runtime / "postgres/lib/libpq.so.5"
    original = digest(psql)
    command(["/usr/bin/patchelf", "--set-rpath", str(runtime / "postgres/lib"), str(psql)])
    require(command(["/usr/bin/patchelf", "--print-rpath", str(psql)]).decode().strip() == str(runtime / "postgres/lib"))
    require(psql.stat().st_uid == 0 and psql.stat().st_nlink == 1 and not psql.stat().st_mode & 0o022)
    require(library.is_file() and not library.is_symlink() and library.stat().st_uid == 0)
    return {"fixture_copy_only": True, "source_psql_sha256": original,
            "relocated_psql_sha256": digest(psql), "copied_libpq_sha256": digest(library)}


def ordinary_client_provenance(runtime, account):
    """Prove the new UID can load the copied library under the scrubbed env."""
    psql = runtime / "postgres/bin/psql"
    loader = str(Path("/lib64/ld-linux-x86-64.so.2").resolve(strict=True))
    runuser = ["/usr/sbin/runuser", "--user", account, "--"]
    raw = command([*runuser, loader, "--list", str(psql)]).decode()
    found = []
    for line in raw.splitlines():
        if "=>" not in line:
            continue
        name, target = line.strip().split("=>", 1)
        path = Path(target.strip().split()[0])
        require(path.is_absolute() and path.exists(), "unresolved client library")
        resolved = path.resolve(strict=True)
        for entry in [resolved, *resolved.parents]:
            value = entry.lstat()
            require(value.st_uid == 0 and not value.st_mode & 0o022, "client library custody")
        if name.strip() == "libpq.so.5":
            require(path == runtime / "postgres/lib/libpq.so.5", "unsealed PostgreSQL client library")
            found.append(path)
    require(len(found) == 1)
    require(command([*runuser, str(psql), "--version"]).strip() == b"psql (PostgreSQL) 18.4")


def process(pid):
    require(type(pid) is int and 1 < pid < 2**31)
    raw = Path(f"/proc/{pid}/stat").read_text()
    fields = raw[raw.rfind(")") + 2:].split()
    status = dict(line.split(":", 1) for line in Path(f"/proc/{pid}/status").read_text().splitlines())
    require(len(set(status["Uid"].split())) == 1)
    return {"pid": pid, "birth": fields[19], "state": fields[0], "parent": int(fields[1]),
            "session": int(fields[3]), "uid": int(status["Uid"].split()[0]),
            "cgroup": Path(f"/proc/{pid}/cgroup").read_text().strip()}


def absent(original):
    try:
        # Zombies do not count as absent: retain the exact original birth fence.
        return process(original["pid"])["birth"] != original["birth"]
    except FileNotFoundError:
        return True


def descendant_of(pid, owner):
    for _ in range(16):
        if pid == owner:
            return True
        if pid <= 1:
            return False
        pid = process(pid)["parent"]
    return False


def wait_for(path, run, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if (run / "manager-failed.json").exists():
            failed = read_json(run / "manager-failed.json")
            # Only fixed phase/error type, never arbitrary subprocess messages.
            raise RuntimeError("manager:" + failed["phase"] + ":" + failed["error_type"])
        if path.exists():
            return read_json(path)
        if path.name == "attached.json" and (run / "owner-exited.json").exists():
            raise RuntimeError("original owner exited before attachment")
        time.sleep(.1)
    raise TimeoutError("fixture receipt deadline")


def failure_check_site(error):
    """Only a fixed fixture source location; no messages, values or source text."""
    result = {'status': 'unavailable'}
    cursor = error.__traceback__
    for _ in range(128):
        if cursor is None:
            return result
        code = cursor.tb_frame.f_code
        if (code.co_filename == __file__ and code.co_name != 'require' and
                re.fullmatch(r'[a-zA-Z_][a-zA-Z_0-9]{0,63}', code.co_name) and
                type(cursor.tb_lineno) is int and 0 < cursor.tb_lineno < 10000):
            result = {'file': 'native-owned-proof.py', 'function': code.co_name, 'line': cursor.tb_lineno}
        cursor = cursor.tb_next
    return {'status': 'unavailable'}


def manager_failure(detail):
    """Closed metadata only, including an optional fixed manager source site."""
    if type(detail) is not dict or set(detail) not in ({'phase','error_type'},
            {'phase','error_type','check_site'},{'phase','error_type','check_site','artifact_failure'}):return None
    if not all(type(detail[name]) is str and re.fullmatch(r'[a-zA-Z-]{1,64}',detail[name]) for name in ('phase','error_type')):return None
    result = {name:detail[name] for name in ('phase','error_type')}
    if 'check_site' in detail:
        site = detail['check_site']
        if site == {'status':'unavailable'}:result['check_site'] = site
        elif (type(site) is dict and set(site) == {'file','function','line'}
                and type(site['file']) is str and site['file'] in {'native-owned-manager.py','native-successor-manager.py'}
                and type(site['function']) is str and re.fullmatch(r'[a-zA-Z_][a-zA-Z_0-9]{0,63}',site['function'])
                and type(site['line']) is int and 0 < site['line'] < 10000):result['check_site'] = dict(site)
        else:return None
    if 'artifact_failure' in detail:
        observed = artifact_failure(detail['artifact_failure'])
        if observed is None or detail['phase'] != 'actual-controller-root-artifact-stage':return None
        result['artifact_failure'] = observed
    return result


def artifact_failure(detail):
    """Validate bounded fixed source metadata, never a free-form traceback."""
    files = {'native_artifact_controller.py','native_root_artifact_dispatch.py',
        'native_root_artifact_policy.py','native_protected_artifact.py',
        'native_root_controller_request.py','native_root_database_exclusion.py',
        'native_root_live_binding.py','native_root_lifecycle.py',
        'native_root_controller.py','native_ownership_database.py','native_root_database_reader.py'}
    functions = {'__init__','check','stage','begin_stage','allocate',
        '_preflight_archive','_check_archive_input','_inspect','_base','_current','_observe','_query',
        '_query_database','_lease','_socket','_client','_lock','_validate_stage',
        '_staged_output','serve_artifact_stage','_exchange','identity','exclusion',
        '_socket_for_process','_tcp_socket_inode','_tcp_socket_reply'}
    types = {'RootArtifactDispatchRefused','ArtifactControllerRefused',
        'RootArtifactPolicyRefused','ProtectedArtifactRefused','RootControllerRequestRefused',
        'RootDatabaseExclusionRefused','RootLiveBindingRefused','RootLifecycleRefused',
        'RootControllerRefused','OwnershipDatabaseRefused','RootDatabaseReaderRefused','TimeoutError',
        'BrokenPipeError','ConnectionResetError','OSError','ValueError','AssertionError','other'}
    if (type(detail) is not dict or set(detail) != {'chain','elapsed_ms'}
            or type(detail['elapsed_ms']) is not int or not 0 <= detail['elapsed_ms'] <= 1200000
            or type(detail['chain']) is not list or not 1 <= len(detail['chain']) <= 16):return None
    for item in detail['chain']:
        if (type(item) is not dict or set(item) != {'error_type','check_site'}
                or type(item['error_type']) is not str or item['error_type'] not in types):return None
        site = item['check_site']
        if site == {'status':'unavailable'}:continue
        if (type(site) is not dict or set(site) != {'file','function','line'}
                or type(site['file']) is not str or site['file'] not in files
                or type(site['function']) is not str or site['function'] not in functions
                or type(site['line']) is not int or not 0 < site['line'] < 10000):return None
    return json.loads(canonical(detail))


def root_stage_refusal(result, elapsed_ms):
    """Local Root metadata only; ordinary refusal frames contain no diagnosis."""
    if (type(result) is not dict or set(result) != {'protocol','kind','status','root_refusal'}
            or type(result['protocol']) is not int or result['protocol'] != 2
            or result['kind'] != 'native_root_artifact_result' or result['status'] != 'refused'):return None
    return artifact_failure({'chain':result['root_refusal'],'elapsed_ms':elapsed_ms})


def bounded_diagnostic_read(path, maximum=4096):
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= maximum)
    fields = ["st_dev", "st_ino", "st_uid", "st_gid", "st_mode", "st_nlink", "st_size", "st_mtime_ns"]
    # Linux execution checks change time too. Windows' stat/fstat disagree on
    # ctime (creation versus change time); local parser tests use stable fields.
    if sys.platform == "linux":
        fields.append("st_ctime_ns")
    def metadata(value):
        return tuple(getattr(value, key) for key in fields)
    original = metadata(before)
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0) |
                         getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        require(metadata(os.fstat(descriptor)) == original)
        raw = os.read(descriptor, maximum + 1)
        require(len(raw) == before.st_size and len(raw) <= maximum)
        require(metadata(os.fstat(descriptor)) == original)
        require(metadata(path.lstat()) == original)
        return raw
    finally:
        os.close(descriptor)


def startup_diagnostics(run):
    """Only a closed event vocabulary crosses the private/public boundary."""
    result = {"status": "unavailable"}
    try:
        path = run / "startup-events.txt"
        if path.exists():
            events = bounded_diagnostic_read(path).decode("ascii").splitlines()
            allowed = {name + ":" + outcome for name in STARTUP_CALLS
                       for outcome in ["entered", "accepted", "refused", "exception"]}
            allowed |= {name + ":observed" for name in STARTUP_MARKS}
            require(1 <= len(events) <= 64 and all(event in allowed for event in events))
            result = {"status": "observed", "events": events}
        exited = run / "owner-exited.json"
        if exited.exists():
            detail = json.loads(bounded_diagnostic_read(exited, 1024))
            require(set(detail) == {"exit_code", "fixture_signalled_beam"})
            require(type(detail["exit_code"]) is int and -127 <= detail["exit_code"] <= 255)
            require(detail["fixture_signalled_beam"] is False)
            result["original_exit_code"] = detail["exit_code"]
    except Exception:
        # Malformed diagnostics are never copied through, even on fixture failure.
        return {"status": "invalid"}
    return result


def case_startup_diagnostics(seed):
    # Owners write in fixed stage directories. An arbitrary phase never selects
    # another pathname and the existing closed event vocabulary still applies.
    label = seed.get('proof_phase', '').partition(':')[0]
    run = Path(seed['run'])
    if label in {'migration-owner', 'bootstrap-owner', 'runtime-owner'}:
        run = run / label
    return startup_diagnostics(run)


class Database:
    def __init__(self, psql):
        self.psql = str(psql)
        require(os.environ.get("PGHOST") == "127.0.0.1")
        require(re.fullmatch(r"[1-9][0-9]{3,4}", os.environ.get("PGPORT", "")) is not None)
        require(1024 <= int(os.environ["PGPORT"]) <= 65535)
        require(re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", os.environ.get("PGUSER", "")) is not None)
        require(0 < len(os.environ.get("PGPASSWORD", "")) <= 256)
        self.environment = {**BASE_ENV, **{name: os.environ[name] for name in ["PGHOST", "PGPORT", "PGUSER", "PGPASSWORD"]},
                            "PGDATABASE": "postgres", "PGPASSFILE": "/dev/null", "PGCONNECT_TIMEOUT": "3",
                            "PGOPTIONS": "-c statement_timeout=5000"}

    def query(self, sql, *, database="postgres", role=None, password=None, timeout=12):
        require(type(timeout) in {int, float} and 0 < timeout <= 12)
        environment = {**self.environment, "PGDATABASE": database}
        if role:
            environment.update(PGUSER=role, PGPASSWORD=password)
        return command([self.psql, "-X", "-A", "-t", "-q", "-v", "ON_ERROR_STOP=1", "--file=-"],
                       environment=environment, input_bytes=sql.encode(), timeout=timeout).decode().strip()

    def predicate(self, session):
        require(type(session["backend_pid"]) is int and 1 < session["backend_pid"] < 2**31)
        require(re.fullmatch(r"[1-9][0-9]{0,19}", session["backend_birth"]) is not None)
        return (f"pid={session['backend_pid']} AND "
                f"floor(extract(epoch FROM backend_start)*1000000)::bigint={session['backend_birth']}")

    def backend_absent(self, session):
        return self.query("SELECT count(*) FROM pg_stat_activity WHERE " + self.predicate(session)) == "0"


def capture_application_backends(database, seed, server_scope):
    dbname = 'gg_proof_' + seed['installation'].replace('-', '')
    predicate = "datname='" + dbname + "' AND usename='" + seed['account'] + "'"
    sql = "SELECT pid::text||':'||floor(extract(epoch FROM backend_start)*1000000)::bigint::text FROM pg_stat_activity WHERE " + predicate + ' ORDER BY pid'
    deadline = time.monotonic() + 5
    previous = None

    def query():
        remaining = deadline - time.monotonic()
        require(remaining > 0, 'application backend discovery did not stabilize')
        return database.query(sql, timeout=remaining)

    while True:
        require(time.monotonic() < deadline, 'application backend discovery did not stabilize')
        rows = query()
        if rows != previous or len(rows.splitlines()) < 2:
            previous = rows
            time.sleep(.05)
            continue
        captured = []
        for row in rows.splitlines():
            pid, birth = row.split(':')
            session = {'backend_pid': int(pid), 'backend_birth': birth}
            kernel = process(int(pid))
            require(kernel['uid'] == server_scope['postgres_uid'])
            # Only commit this discovery after two equal SQL observations,
            # kernel checks and a final unchanged SQL list. No effects or
            # original-identity replacement are allowed by a pending discovery.
            captured.append({'session': session,
                'kernel': {name: kernel[name] for name in ('pid', 'birth', 'uid', 'cgroup')}})
        current = query()
        if current == rows:
            require(time.monotonic() < deadline, 'application backend discovery did not stabilize')
            return captured
        previous = current
        time.sleep(.05)


def listeners_absent(config):
    for port in (int(config['forge']['PORT']), int(config['forge']['GITGOOD_SSH_PORT'])):
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=.3):
                return False
        except ConnectionRefusedError:
            pass
    return True


def require_tls_refusal(context, hostname, *, server_name=False):
    """A wrong SNI can be refused by Caddy before any certificate is delivered.

    Keep client CA/hostname validation enabled. Accept only certificate refusal
    or a closed server-name handshake-alert vocabulary after positive TLS proof;
    network errors, unrelated TLS errors and a successful handshake still fail.
    The untrusted-issuer test must always fail client certificate verification.
    """
    require(context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname is True)
    with socket.create_connection(('127.0.0.1', 4443), timeout=3) as connection:
        try:
            context.wrap_socket(connection, server_hostname=hostname)
        except ssl.SSLCertVerificationError:
            return 'certificate-verification'
        except ssl.SSLError as error:
            require(server_name and error.reason in {'TLSV1_ALERT_UNRECOGNIZED_NAME',
                'TLSV1_ALERT_INTERNAL_ERROR', 'SSLV3_ALERT_HANDSHAKE_FAILURE'}, 'unexpected TLS refusal')
            return 'server-name-handshake-alert'
        else:
            raise ValueError('Wrong TLS hostname or untrusted issuer accepted')


def probe_native_runtime(seed, config, stage, *, public=False):
    """Actual API/Git, with a separately requested real CA/hostname-verified edge."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    certificate = Path(seed['root']) / 'configuration/tls-certificate.pem'
    context = ssl.create_default_context(cafile=str(certificate)) if public else None
    handlers = [urllib.request.ProxyHandler({}), NoRedirect()]
    if public:handlers.append(urllib.request.HTTPSHandler(context=context))
    opener = urllib.request.build_opener(*handlers)
    base = config['forge']['GITGOOD_PUBLIC_URL'] if public else 'http://127.0.0.1:' + config['forge']['PORT']

    def request(method, path, expected, body=None, token=None, extra=None):
        headers = {'Accept': 'application/json', **(extra or {})}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        if body is not None:
            headers['Content-Type'] = 'application/json'
        item = urllib.request.Request(base + path, data=None if body is None else canonical(body), headers=headers, method=method)
        try:
            response = opener.open(item, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            require(response.status == expected, 'native API refused expected outcome')
            raw = response.read(262145)
            require(len(raw) <= 262144)
            return json.loads(raw), response.headers

    if public:
        seed['proof_phase'] = 'public-runtime:verified-tls-readiness'
        deadline = time.monotonic() + 30
        while True:
            try:
                with opener.open(base + '/health/ready', timeout=3) as response:
                    if response.status == 200:break
            except (urllib.error.URLError, OSError):pass
            require(time.monotonic() < deadline, 'public TLS readiness deadline');time.sleep(.1)
        seed['proof_phase'] = 'public-runtime:frontend-html-and-packaged-assets'
        with opener.open(base + '/', timeout=5) as response:
            html = response.read(262145)
            require(response.status == 200 and len(html) <= 262144 and b'gitgood' in html.lower())
        assets = re.findall(rb'(?:src|href)="(/assets/[^"<>]+\.js)"', html)
        require(assets, 'production frontend script not rendered')
        for asset in assets[:4]:
            with opener.open(base + asset.decode('ascii'), timeout=5) as response:
                payload = response.read(8388609)
                require(response.status == 200 and len(payload) <= 8388608)
                client = (Path(seed['web']) / 'dist/client').resolve(strict=True)
                asset_path = (client / asset.decode('ascii').lstrip('/')).resolve(strict=True)
                require(asset_path.is_relative_to(client) and asset_path.stat().st_size <= 8388608)
                expected = asset_path.read_bytes()
                require(hashlib.sha256(payload).digest() == hashlib.sha256(expected).digest(), 'served frontend differs from sealed artifact')
        seed['proof_phase'] = 'public-runtime:internal-route-denial'
        try:
            opener.open(base + '/internal/readiness', timeout=5)
        except urllib.error.HTTPError as error:
            require(error.code == 404)
        else:raise ValueError('Internal route exposed at public edge')
        seed['proof_phase'] = 'public-runtime:wrong-hostname-refusal'
        wrong_hostname_refusal = require_tls_refusal(context, 'localhost', server_name=True)
        seed['proof_phase'] = 'public-runtime:untrusted-issuer-refusal'
        require(require_tls_refusal(ssl.create_default_context(), '127.0.0.1') == 'certificate-verification')
        seed['proof_phase'] = 'public-runtime:owner-login-and-private-api'
    ready, _ = request('GET', '/health/ready', 200)
    require(ready['candidate'] == seed['candidate'] and ready['dirty'] is False and ready['status'] == 'ready')
    require(ready['operational_mode'] == 'active')
    if public:
        live, _ = request('GET', '/health/live', 200)
        require(live['service'] == 'gitgood-web' and live['candidate'] == seed['candidate'] and live['dirty'] is False)
        require(ready['forge_candidate'] == seed['candidate'])
    else:require(all(ready['checks'].values()))
    request('GET', '/api/repos', 401)
    stamp = str(int(time.time()))
    frame = '\n'.join(('gitgood-login-origin-v1', '127.0.0.1', stamp, 'POST', '/api/session'))
    signature = hmac.new(base64.b64decode(config['forge']['GITGOOD_PROXY_KEY']), frame.encode(), hashlib.sha256).hexdigest()
    login_headers = {
            'Origin': config['forge']['GITGOOD_WEB_ORIGIN'], 'x-gitgood-client-address': '127.0.0.1',
            'x-gitgood-client-time': stamp, 'x-gitgood-client-signature': signature}
    if public:
        login_headers.update({'x-gitgood-client-address': '203.0.113.10', 'x-gitgood-client-signature': '0' * 64,
                              'x-gitgood-edge-key': 'forged', 'x-gitgood-edge-client': '203.0.113.10'})
    login, headers = request('POST', '/api/session', 200,
        {'username': 'owner', 'password': 'synthetic-secret-éé'}, extra=login_headers)
    require(login['user']['username'] == 'owner' and any(item['team'] == 'pilot' and item['role'] == 'owner' for item in login['teams']))
    cookies = SimpleCookie();cookies.load(headers['Set-Cookie'])
    session = cookies['gitgood_session'].value
    require(cookies['gitgood_session']['secure'] and cookies['gitgood_session']['httponly'])
    if public:
        current, _ = request('GET', '/api/session', 200, extra={'Cookie': 'gitgood_session=' + session})
        require(current['user']['username'] == 'owner')
    request('POST', '/api/repos', 201, {'team': 'pilot', 'name': 'native-runtime'}, token=session,
        extra={'idempotency-key': str(uuid.uuid4())})
    credential, _ = request('POST', '/api/repos/pilot/native-runtime/credentials', 200, {}, token=session)
    probe = stage / 'root-runtime-probe';probe.mkdir(mode=0o700)
    git = seed['executables']['git']
    environment = {**BASE_ENV, 'HOME': str(probe), 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
        'GIT_TERMINAL_PROMPT': '0', 'GIT_CONFIG_COUNT': '2', 'GIT_CONFIG_KEY_0': 'http.extraHeader',
        'GIT_CONFIG_VALUE_0': 'Authorization: Basic ' + base64.b64encode(('owner:' + credential['token']).encode()).decode(),
        'GIT_CONFIG_KEY_1': 'credential.helper', 'GIT_CONFIG_VALUE_1': ''}
    if public:environment.update({'GIT_SSL_CAINFO': str(certificate), 'GIT_SSL_NO_VERIFY': 'false'})
    if public:seed['proof_phase'] = 'public-runtime:https-git-push-and-readback'
    checkout = probe / 'http-client'
    command([git, 'clone', base + '/git/pilot/native-runtime.git', str(checkout)], environment=environment, timeout=30)
    command([git, '-C', str(checkout), 'symbolic-ref', 'HEAD', 'refs/heads/main'], environment=environment)
    (checkout / 'README.md').write_text('Native owned runtime fixture\n')
    command([git, '-C', str(checkout), 'config', 'user.name', 'Fixture'], environment=environment)
    command([git, '-C', str(checkout), 'config', 'user.email', 'fixture@example.invalid'], environment=environment)
    command([git, '-C', str(checkout), 'add', 'README.md'], environment=environment)
    command([git, '-C', str(checkout), 'commit', '-m', 'Native runtime fixture'], environment=environment)
    revision = command([git, '-C', str(checkout), 'rev-parse', 'HEAD'], environment=environment).strip()
    command([git, '-C', str(checkout), 'push', 'origin', 'main'], environment=environment, timeout=30)
    cloned = probe / 'http-readback'
    command([git, 'clone', base + '/git/pilot/native-runtime.git', str(cloned)], environment=environment, timeout=30)
    require(command([git, '-C', str(cloned), 'rev-parse', 'HEAD'], environment=environment).strip() == revision)
    key = probe / 'ssh-key'
    if public:seed['proof_phase'] = 'public-runtime:ssh-readback-and-session-revocation'
    command(['/usr/bin/ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)])
    request('POST', '/api/ssh-keys', 201, {'label': 'native-runtime-fixture', 'public_key': key.with_suffix('.pub').read_text()},
        token=session, extra={'idempotency-key': str(uuid.uuid4())})
    known = probe / 'known_hosts'
    host_key = (Path(seed['root']) / 'ssh-host/ssh_host_ed25519_key.pub').read_text().split()
    known.write_text('[127.0.0.1]:' + config['forge']['GITGOOD_SSH_PORT'] + ' ' + ' '.join(host_key[:2]) + '\n')
    ssh = probe / 'ssh-client'
    write_new(ssh, b'#!/usr/bin/python3.12\nimport os,sys\nos.execv("/usr/bin/ssh",["ssh","-F","/dev/null","-o","BatchMode=yes","-o","IdentitiesOnly=yes","-o","StrictHostKeyChecking=yes","-o","UserKnownHostsFile="+os.environ["GITGOOD_PROOF_KNOWN_HOSTS"],"-i",os.environ["GITGOOD_PROOF_SSH_KEY"],*sys.argv[1:]])\n', 0o700)
    ssh_env = {**environment, 'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'credential.helper', 'GIT_CONFIG_VALUE_0': '',
        'GIT_SSH': str(ssh), 'GIT_SSH_VARIANT': 'ssh', 'GITGOOD_PROOF_KNOWN_HOSTS': str(known), 'GITGOOD_PROOF_SSH_KEY': str(key)}
    ssh_checkout = probe / 'ssh-readback'
    command([git, 'clone', 'ssh://owner@127.0.0.1:' + config['forge']['GITGOOD_SSH_PORT'] + '/pilot/native-runtime.git',
        str(ssh_checkout)], environment=ssh_env, timeout=30)
    require(command([git, '-C', str(ssh_checkout), 'rev-parse', 'HEAD'], environment=ssh_env).strip() == revision)
    request('GET', '/api/repos', 401)
    request('DELETE', '/api/session', 200, token=session)
    request('GET', '/api/repos', 401, token=session)
    return {'internal_readiness_and_signed_owner_login_verified': not public, 'anonymous_private_api_denied': True,
        'internal_http_git_push_and_readback_verified': not public, 'ssh_git_readback_verified': True,
        'session_revocation_verified': True, 'public_tls_and_frontend_verified': public,
        'public_https_git_push_and_readback_verified': public, 'public_cookie_and_owner_login_verified': public,
        'wrong_hostname_and_untrusted_issuer_refused': public, 'complete_browser_journey_verified': False,
        'wrong_hostname_refusal': wrong_hostname_refusal if public else None}


def unit_text(seed, manager):
    return f"""[Unit]
Description=Gitgood disposable native ownership component proof
StartLimitIntervalSec=60
StartLimitBurst=1
[Service]
Type=exec
User={seed['account']}
Group={seed['account']}
ExecStart=/usr/bin/python3.12 -I -S {manager} {seed['seal_directory']}/fixture-seed.json
WorkingDirectory={seed['run']}
Delegate=cpu memory
DelegateSubgroup=driver
CPUQuota=200%
CPUQuotaPeriodSec=100ms
MemoryMax={LIMITS['memory_bytes']}
MemorySwapMax=0
LimitFSIZE={FILE_LIMIT}
LimitCORE=0
KillMode=control-group
Restart=on-failure
RestartSec=60
NoNewPrivileges=yes
CapabilityBoundingSet=
AmbientCapabilities=
UMask=0077
TimeoutStopSec=15
StandardOutput=null
StandardError=null
""".encode()


def allocate_case(label, runtime, database, candidate, *, controller=False, lifecycle=False, business_inputs=False, business_effects=False, schema_refusal=False, inventory_refusal=False, runtime_effects=False, runtime_schema_refusal=False, public_runtime=False, default_release=False, artifact_stage=False):
    installation = str(uuid.uuid4())
    account = "gg_" + base64.b32encode(uuid.UUID(installation).bytes).decode().lower().rstrip("=")
    command(["/usr/sbin/useradd", "--system", "--user-group", "--no-create-home", "--home-dir", "/nonexistent",
             "--shell", "/usr/sbin/nologin", account])
    import pwd
    user = pwd.getpwnam(account)
    ordinary_client_provenance(runtime, account)
    root = Path("/var/lib/gitgood/installations") / installation
    run = Path("/run/gitgood-owned-proof") / installation
    seal = Path("/etc/gitgood/installations") / installation
    for parent in [root.parent, run.parent, seal.parent]:
        root_directory(parent)
    seal.mkdir(mode=0o755)
    for directory in [root, run, *[root / name for name in ["configuration", "storage", "ssh-host", "history", "staging"]]]:
        directory.mkdir(mode=0o700)
        os.chown(directory, user.pw_uid, user.pw_gid)
    write_new(root / "history/.upgrade-history-lock-v1", b"", 0o600, user.pw_uid, user.pw_gid)
    password = secrets.token_hex(32)
    dbname = "gg_proof_" + installation.replace("-", "")
    database.query(f"CREATE ROLE {account} LOGIN PASSWORD '{password}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;")
    database.query(f"CREATE DATABASE {dbname} OWNER {account} TEMPLATE template0 ENCODING 'UTF8' LOCALE_PROVIDER libc LC_COLLATE 'C.UTF-8' LC_CTYPE 'C.UTF-8';")
    database.query("REVOKE EXECUTE ON FUNCTION pg_catalog.pg_control_system() FROM PUBLIC;\n"
                   f"GRANT EXECUTE ON FUNCTION pg_catalog.pg_control_system() TO {account};", database=dbname)
    proxy = base64.b64encode(secrets.token_bytes(32)).decode()
    forge = {
        "DATABASE_URL": f"postgresql://{account}:{password}@127.0.0.1:{database.environment['PGPORT']}/{dbname}",
        "SECRET_KEY_BASE": secrets.token_hex(64), "PHX_HOST": "127.0.0.1",
        "GITGOOD_PUBLIC_URL": "https://127.0.0.1:4443", "GITGOOD_WEB_ORIGIN": "https://127.0.0.1:4443",
        "GITGOOD_PROXY_KEY": proxy, "GITGOOD_STORAGE": str(root / "storage"), "PORT": "4400",
        "GITGOOD_SSH_PORT": "4422", "GITGOOD_SSH_HOST_KEY_DIRECTORY": str(root / "ssh-host"),
        "GITGOOD_SSH_PUBLIC_HOST": "127.0.0.1", "GITGOOD_SSH_PUBLIC_PORT": "4422", "GITGOOD_INSTALLATION_ID": installation}
    config = {"protocol": 1, "installation": installation, "forge": forge,
              "web": {"PORT": "4500", "GITGOOD_API_URL": "http://127.0.0.1:4400", "GITGOOD_PROXY_KEY": proxy, "NODE_ENV": "production"},
              "edge": {"tls_certificate": "tls-certificate.pem", "tls_key": "tls-key.pem"}}
    write_new(root / "configuration/installation.json", config, 0o600, user.pw_uid, user.pw_gid)
    command(["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(root / "ssh-host/ssh_host_ed25519_key")])
    command(["/usr/bin/openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=127.0.0.1",
             "-addext", "subjectAltName=IP:127.0.0.1",
             "-keyout", str(root / "configuration/tls-key.pem"), "-out", str(root / "configuration/tls-certificate.pem")])
    for path in [*list((root / "ssh-host").iterdir()), *list((root / "configuration").iterdir())]:
        os.chmod(path, 0o600)
        os.chown(path, user.pw_uid, user.pw_gid)
    seed = {"installation": installation, "case": label, "account": account, "uid": user.pw_uid, "gid": user.pw_gid,
            "root": str(root), "run": str(run), "seal_directory": str(seal), "unit": f"gitgood-installation-{installation}.service",
            "executables": {"python": "/usr/bin/python3.12", "git": str(runtime / "git"), "node": str(runtime / "node"),
                            "psql": str(runtime / "postgres/bin/psql"), "caddy": str(runtime / "caddy")},
            "release": str(runtime / "release"), "worker": str(runtime / "native-owned-worker.exs"), "limits": LIMITS,
            "candidate": candidate, "generation_operation": str(uuid.uuid4()), "generation": str(uuid.uuid4()),
            "ownership_operation": str(uuid.uuid4())}
    if lifecycle:
        require(controller)
        seed['lifecycle_fixture'] = True
    if business_inputs:
        require(lifecycle)
        seed['business_inputs_fixture'] = True
    if business_effects:
        require(business_inputs)
        seed['business_effects_fixture'] = True
    if schema_refusal:
        require(business_effects)
        seed['schema_refusal_fixture'] = True
    if inventory_refusal:
        require(business_effects and not schema_refusal)
        seed['inventory_refusal_fixture'] = True
    if runtime_effects:
        require(business_effects and not schema_refusal and not inventory_refusal)
        seed['runtime_effects_fixture'] = True
    if runtime_schema_refusal:
        require(runtime_effects)
        seed['runtime_schema_refusal_fixture'] = True
    if public_runtime:
        require(runtime_effects and not runtime_schema_refusal)
        seed['public_runtime_fixture'] = True
        seed['web'] = str(runtime / 'web')
        seed['edge_template'] = str(runtime / 'Caddyfile.example')
    if default_release:
        require(public_runtime)
        seed['default_release_fixture'] = True
    if artifact_stage:
        require(default_release)
        seed['artifact_stage_fixture'] = True
    if controller:
        directory = Path('/run/gitgood/installations') / installation
        root_directory(directory.parent)
        directory.mkdir(mode=0o700)
        os.chown(directory, user.pw_uid, user.pw_gid)
        seed['controller_directory'] = str(directory)
    unit = unit_text(seed, runtime / ("native-successor-manager.py" if controller else "native-owned-manager.py"))
    seed["unit_sha256"] = hashlib.sha256(unit).hexdigest()
    write_new(Path("/etc/systemd/system") / seed["unit"], unit)
    if controller:
        write_new(seal / 'controller-endpoint-v2.json', {
            'protocol': 2, 'kind': 'native_controller_endpoint_seal', 'installation': installation,
            'uid': user.pw_uid, 'gid': user.pw_gid, 'unit_sha256': seed['unit_sha256'],
            'directory_identity': identity(directory), 'limits': LIMITS})
    write_new(seal / "fixture-seed.json", seed)
    return seed, config, password


def seal_observation(seed, config, password, observed, database, server_scope):
    """Check the ordinary observation against independently allocated facts."""
    from native_durable_binding import executable
    from native_durable_database import SQL, validate_database
    from native_service_scope import root_file
    from resource_generations import validate_scope
    root = Path(seed["root"])
    binding = observed["binding"]
    validate_scope(observed["scope"])
    require(observed["scope"]["installation"] == seed["installation"])
    require(observed["scope"]["uid"] == seed["uid"] and observed["scope"]["gid"] == seed["gid"])
    require(observed["scope"]["unit_definition"]["sha256"] == seed["unit_sha256"])
    require(binding["installation"] == seed["installation"])
    require(binding["host"] == {"machine_id": Path("/etc/machine-id").read_text().strip(),
                                "profile": "ubuntu-24.04-linux-x86_64",
                                "os_release": root_file(Path("/etc/os-release").resolve(strict=True), 4096)[0]})
    require(binding["account"] == {"name": seed["account"], "uid": seed["uid"], "gid": seed["gid"]})
    for name in ["root", "configuration", "storage", "ssh-host", "history", "staging"]:
        path = root if name == "root" else root / name
        require(binding["resources"][name] == {"path": str(path), **identity(path)})
    require(binding["configuration"] == {name: file_record(root / "configuration" / name, seed["uid"])
                                        for name in ["installation.json", "tls-certificate.pem", "tls-key.pem"]})
    require(binding["ssh_host_keys"] == {name: file_record(root / "ssh-host" / name, seed["uid"])
                                        for name in ["ssh_host_ed25519_key", "ssh_host_ed25519_key.pub"]})
    require(binding["executables"] == {name: executable(path) for name, path in seed["executables"].items()})
    dbname = "gg_proof_" + seed["installation"].replace("-", "")
    observed_db = json.loads(database.query(SQL, database=dbname, role=seed["account"], password=password))
    validate_database(observed_db, {"PGDATABASE": dbname, "PGUSER": seed["account"], "PGPORT": database.environment["PGPORT"]})
    require(binding["database"] == observed_db)
    require(read_json(root / "configuration/installation.json") == config)
    sha = hashlib.sha256(canonical(binding)).hexdigest()
    require(sha == observed["binding_sha256"])
    seal = Path(seed["seal_directory"])
    require(not (seal / "lifecycle-worker-admission-v2.json").exists())
    require(not (root / "history/lifecycle-responsibility-v2").exists())
    write_new(seal / "ownership-admission-v3.json", {
        "protocol": 3, "kind": "native_application_ownership_seal", "installation": seed["installation"],
        "operation": seed["ownership_operation"], "candidate": seed["candidate"], "binding_sha256": sha})
    write_new(seal / ("backend-kernel-" + server_scope["boot_id"] + ".json"), {
        "protocol": 2, "kind": "native_backend_kernel_scope_seal", "installation": seed["installation"], "server_scope": server_scope})
    write_new(seal / "generation-admission-v2.json", {
        "protocol": 2, "kind": "native_generation_admission_seal", "installation": seed["installation"], "binding_sha256": sha,
        "history_identity": identity(root / "history"), "lock_identity": identity(root / "history/.upgrade-history-lock-v1"),
        "unit_sha256": seed["unit_sha256"], "executables": seed["executables"], "limits": LIMITS, "database": observed_db})


def capture_attachment(seed, attached, database, *, mode='runtime', protocol=3):
    from native_ownership_records import validate_record
    record = attached["record"]
    validate_record(record)
    require(record["installation"] == seed["installation"] and record["operation"] == seed["ownership_operation"])
    require(record["candidate"] == seed["candidate"] and record["mode"] == mode and record['protocol'] == protocol)
    require(attached["distinct_attached_heartbeat_samples"] >= 5)
    require(attached["beam_pid"] == record["owner"]["pid"])
    owner = process(attached["beam_pid"])
    helper = process(attached["helper_pid"])
    descendant = process(attached["descendant_pid"])
    group = "0::/system.slice/" + seed["unit"] + ("/native" if mode == 'runtime' else '/maintenance')
    for item in [owner, helper, descendant]:
        require(item["uid"] == seed["uid"] and item["state"] not in ["Z", "X"] and item["cgroup"] == group)
    require(owner["birth"] == record["owner"]["birth"])
    require(descendant_of(helper["pid"], owner["pid"]) and descendant_of(descendant["pid"], owner["pid"]))
    require(descendant["session"] == descendant["pid"])
    backend = process(record["database_session"]["backend_pid"])
    require(backend["birth"] == record["backend_kernel"]["kernel_birth"])
    require(backend["uid"] == record["backend_kernel"]["server_scope"]["postgres_uid"])
    predicate = database.predicate(record["database_session"])
    require(database.query("SELECT count(*) FROM pg_stat_activity WHERE " + predicate +
                           " AND application_name='gitgood native installation lease v2'") == "1")
    require(database.query("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND granted "
                           f"AND pid={backend['pid']} AND classid::bigint=1197034575 AND objid::bigint=1 AND objsubid=2 AND mode='ExclusiveLock'") == "1")
    storage = Path(seed["root"]) / "storage"
    retained = storage / ".gitgood-ownership-v2" / ((record['claim'] if protocol == 4 else seed["ownership_operation"]) + ".json")
    marker = storage / (".gitgood-runtime-v2.json" if mode == 'runtime' else '.gitgood-maintenance-v2.json')
    require(read_json(retained) == record)
    require(read_json(marker)["record_sha256"] == hashlib.sha256(canonical(record)).hexdigest())
    return {"owner": owner, "helper": helper, "descendant": descendant, "backend": backend,
            "retained": retained, "marker": marker, "record_file": fingerprint(retained), "marker_file": fingerprint(marker)}


def observe_default_lease(seed, record, database, server_scope):
    """Root's independent read-only fixture observation; never bypass ordinary admission."""
    owner, session = record['owner'], record['database_session']
    actual = process(owner['pid'])
    require(actual['birth'] == owner['birth'] and actual['uid'] == owner['uid'] == seed['uid'] and actual['state'] not in {'Z','X'})
    backend = process(session['backend_pid'])
    require(backend['birth'] == record['backend_kernel']['kernel_birth'] and backend['uid'] == server_scope['postgres_uid'])
    dbname = 'gg_proof_' + seed['installation'].replace('-', '')
    require(re.fullmatch(r'[a-z0-9_]+', dbname) and re.fullmatch(r'[a-z0-9_]+', seed['account']))
    predicate = database.predicate(session) + " AND datname='" + dbname + "' AND usename='" + seed['account'] + "'"
    rows = database.query("SELECT host(client_addr)||':'||client_port::text FROM pg_stat_activity WHERE " + predicate +
        " AND backend_type='client backend' AND application_name='gitgood native installation lease v2'").splitlines()
    require(len(rows) == 1 and re.fullmatch(r'127\.0\.0\.1:[1-9][0-9]{0,4}', rows[0]))
    port = int(rows[0].split(':')[1]);require(port <= 65535)
    require(database.query("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND granted "
        f"AND pid={session['backend_pid']} AND classid::bigint=1197034575 AND objid::bigint=1 AND objsubid=2 AND mode='ExclusiveLock'") == '1')
    server_port = int(database.environment['PGPORT'])
    require(server_port == session['database']['port'])
    process_path = Path('/proc') / str(owner['pid'])
    require(os.readlink(process_path / 'ns/net') == os.readlink('/proc/self/ns/net'))
    with (process_path / 'net/tcp').open('rb') as source:raw = source.read(1048577)
    require(len(raw) <= 1048576)
    lines = raw.decode('ascii').splitlines();require(len(lines) <= 8193)
    sockets = []
    for line in lines[1:]:
        fields = line.split();require(len(fields) >= 10)
        if fields[1] == '0100007F:' + format(port, '04X') and fields[2] == '0100007F:' + format(server_port, '04X') and fields[3] == '01':
            require(fields[7] == str(seed['uid']) and re.fullmatch(r'[1-9][0-9]{0,19}', fields[9]))
            sockets.append(fields[9])
    require(len(sockets) == 1)
    descriptors = []
    with os.scandir(process_path / 'fd') as entries:
        for index, entry in enumerate(entries):
            require(index < 4096)
            try:target = os.readlink(entry.path)
            except FileNotFoundError:continue
            if target == 'socket:[' + sockets[0] + ']':descriptors.append(entry.name)
    require(len(descriptors) == 1)
    require(os.readlink(process_path / 'fd' / descriptors[0]) == 'socket:[' + sockets[0] + ']')
    require(process(owner['pid'])['birth'] == owner['birth'] and process(session['backend_pid'])['birth'] == backend['birth'])
    return {'client_port': port, 'socket_inode': sockets[0], 'descriptor': descriptors[0]}


def discover_default_helper(seed):
    """Bounded discovery tolerates only disappearance of an unselected member."""
    from native_service_scope import members
    native = Path('/sys/fs/cgroup/system.slice') / seed['unit'] / 'native'
    helper_pids = []
    for pid in members(native):
        text = str(pid)
        try:
            with (Path('/proc') / text / 'cmdline').open('rb') as source:command_line = source.read(4097)
        except (FileNotFoundError, ProcessLookupError):continue
        require(len(command_line) <= 4096)
        arguments = command_line.split(b'\0')
        if b'/opt/gitgood/native/v2/native_generation_monitor_entry.py' in arguments:
            require(arguments[0] == seed['executables']['python'].encode())
            helper_pids.append(pid)
    require(len(helper_pids) == 1, 'normal release original monitor not unique')
    return helper_pids[0]


def capture_default_attachment(seed, launched, config, database, server_scope):
    """Root's actual normal-release observations; no fixture witness or fake samples."""
    from native_ownership_records import validate_record
    record = launched['record'];validate_record(record)
    require(launched['release_command'] == 'start' and launched['fixture_runtime_application_substitution'] is False)
    require(record['protocol'] == 4 and record['mode'] == 'runtime')
    require(all(record[name] == seed[{'installation':'installation','operation':'ownership_operation','candidate':'candidate'}[name]]
                for name in ('installation', 'operation', 'candidate')))
    owner = process(record['owner']['pid']);helper = process(discover_default_helper(seed))
    require(owner['birth'] == record['owner']['birth'] and descendant_of(helper['pid'], owner['pid']))
    require(all(item['uid'] == seed['uid'] and item['cgroup'] == '0::/system.slice/' + seed['unit'] + '/native'
                for item in (owner, helper)))
    backend = process(record['database_session']['backend_pid'])
    require(backend['birth'] == record['backend_kernel']['kernel_birth'] and backend['uid'] == server_scope['postgres_uid'])
    samples = 0
    deadline = time.monotonic() + 30
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    ready_url = 'http://127.0.0.1:' + config['forge']['PORT'] + '/health/ready'
    original_connection = None
    while samples < 5:
        require(time.monotonic() < deadline)
        for original in (owner, helper):
            actual = process(original['pid'])
            require(actual['state'] not in {'Z','X'} and all(actual[name] == original[name]
                for name in ('pid','birth','uid','parent','cgroup','session')))
        current = observe_default_lease(seed, record, database, server_scope)
        if original_connection is None:original_connection = current
        else:require(current == original_connection)
        try:
            with opener.open(ready_url, timeout=3) as response:
                require(response.geturl() == ready_url)
                raw = response.read(65537);require(len(raw) <= 65536)
                ready = json.loads(raw)
                require(response.status == 200 and ready['candidate'] == seed['candidate'] and ready['dirty'] is False)
                require(ready['status'] == 'ready' and all(ready['checks'].values()))
        except urllib.error.URLError:
            time.sleep(.1);continue
        samples += 1;time.sleep(.2)
    retained = Path(seed['root']) / 'storage/.gitgood-ownership-v2' / (record['claim'] + '.json')
    marker = Path(seed['root']) / 'storage/.gitgood-runtime-v2.json'
    require(read_json(retained) == record and read_json(marker)['record_sha256'] == hashlib.sha256(canonical(record)).hexdigest())
    return {'owner': owner, 'helper': helper, 'backend': backend, 'retained': retained, 'marker': marker,
        'record_file': fingerprint(retained), 'marker_file': fingerprint(marker), 'independent_current_samples': samples}


def inject_loss(label, captured, session, database):
    if label == "helper-loss":
        helper = captured["helper"]
        descriptor = root_runtime_probe.pidfd_open(helper["pid"])
        try:
            current = process(helper["pid"])
            require(all(current[name] == helper[name] for name in ["pid", "birth", "uid", "parent", "cgroup"]))
            require(current["state"] not in ["Z", "X"])
            root_runtime_probe.pidfd_sigkill(descriptor)
        finally:
            os.close(descriptor)
    elif label == "marker-permission-loss":
        require(fingerprint(captured["marker"]) == captured["marker_file"])
        os.chmod(captured["marker"], 0o640, follow_symlinks=False)
    elif label == "original-backend-loss":
        require(process(captured["backend"]["pid"])["birth"] == captured["backend"]["birth"])
        require(database.query("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE " + database.predicate(session)) == "t")
    else:
        raise ValueError("unknown fault")


def inject_default_release_loss(seed, stage, captured, session, database):
    """The fixture must enter and acknowledge its observation window before loss."""
    seal, run = Path(seed['seal_directory']), Path(seed['run'])
    write_new(seal / 'fixture-observe-native-abort-first.json', {'observe_original_permanent_release_abort': True})
    ready = wait_for(stage / 'native-abort-observation-ready.json', run, 15)
    require(ready == {'original_release_running': True, 'public_stop_deferred_until_native_exit': True})
    inject_loss('helper-loss', captured, session, database)


def run_case(seed, config, password, database, server_scope):
    run = Path(seed["run"])
    seal = Path(seed["seal_directory"])
    seed["proof_phase"] = "start-service"
    command(["/usr/bin/systemctl", "daemon-reload"])
    command(["/usr/bin/systemctl", "start", seed["unit"]])
    seed["proof_phase"] = "independent-binding-seal"
    observed = wait_for(run / "observed.json", run, 40)
    seal_observation(seed, config, password, observed, database, server_scope)
    seed["proof_phase"] = "real-generation-publication"
    published = wait_for(run / "published.json", run, 50)
    require(published["generation_publication_established"] is True and published["installation_readiness_established"] is False)
    write_new(seal / "fixture-start.json", {"start": True})
    seed["proof_phase"] = "actual-startup-claim-attached-heartbeats"
    attached = wait_for(run / "attached.json", run, 100)
    seed["proof_phase"] = "independent-live-owner-backend-observation"
    captured = capture_attachment(seed, attached, database)
    launched = wait_for(run / "launched.json", run, 5)
    sentinel = process(launched["sentinel_pid"])
    require(sentinel["cgroup"] == "0::/system.slice/" + seed["unit"] + "/web" and sentinel["uid"] == seed["uid"])
    start = time.monotonic()
    session = attached["record"]["database_session"]
    seed["proof_phase"] = "inject-original-loss"
    inject_loss(seed["case"], captured, session, database)
    seed["proof_phase"] = "original-beam-backend-disappearance"
    exited = wait_for(run / "owner-exited.json", run, 15)
    require(exited["fixture_signalled_beam"] is False and exited["exit_code"] != 0)
    deadline = time.monotonic() + 10
    while not (absent(captured["owner"]) and absent(captured["backend"]) and database.backend_absent(session)):
        require(time.monotonic() < deadline, "original owner/backend not absent")
        time.sleep(.1)
    loss_seconds = round(time.monotonic() - start, 3)
    require(not absent(sentinel), "sibling died before cleanup")
    # It must really survive the BEAM, otherwise this case proves no descendant fence.
    require(not absent(captured["descendant"]), "detached descendant did not survive BEAM")
    require(fingerprint(captured["retained"]) == captured["record_file"])
    expected_marker = {**captured["marker_file"], "mode": 0o640} if seed["case"] == "marker-permission-loss" else captured["marker_file"]
    require(fingerprint(captured["marker"]) == expected_marker)
    seed["proof_phase"] = "fixture-descendant-quiescence"
    write_new(seal / "fixture-cleanup.json", {"original_owner_and_backend_absent": True})
    quiescent = wait_for(run / "quiescent.json", run, 12)
    require(quiescent == {"native_empty": True, "sibling_preserved": True,
                          "cleanup_actor": "fixture-manager", "product_controller_verified": False})
    deadline = time.monotonic() + 5
    while not (absent(captured["descendant"]) and absent(captured["helper"])):
        require(time.monotonic() < deadline, "original fixture descendants remain")
        time.sleep(.1)
    native = Path("/sys/fs/cgroup/system.slice") / seed["unit"] / "native"
    require("populated 0" in (native / "cgroup.events").read_text() and not absent(sentinel))
    require(fingerprint(captured["retained"]) == captured["record_file"])
    require(fingerprint(captured["marker"]) == expected_marker)
    require(not (seal / "lifecycle-worker-admission-v2.json").exists())
    require(not (Path(seed["root"]) / "history/lifecycle-responsibility-v2").exists())
    seed["proof_phase"] = "complete"
    return {"case": seed["case"], "status": "passed", "installation": seed["installation"],
            "record_sha256": captured["record_file"]["sha256"], "distinct_attached_heartbeat_samples": attached["distinct_attached_heartbeat_samples"],
            "original_owner_and_sql_and_kernel_backend_absent": True, "loss_observation_seconds": loss_seconds,
            "detached_descendant_survived_beam": True, "native_descendants_quiesced_by_fixture_manager": True,
            "original_helper_and_descendant_kernel_identities_absent": True,
            "sibling_preserved_until_unit_shutdown": True, "ownership_record_and_marker_retained": True,
            "lifecycle_policy_absent": True, "native_application_acceptance": False, "product_controller_verified": False}


def provision_stage_archive(seed):
    """Only the fresh hosted fixture: original complete production payload."""
    from native_protected_artifact import MAX_ARCHIVE,MAX_CONTENT,MAX_MEMBERS,RESERVE
    from inspect_native_artifact import inspect_native_artifact
    source = Path('/var/lib/gitgood/artifact-inputs')/seed['installation']/seed['ownership_operation']
    policy = Path(seed['seal_directory'])/'artifacts'
    destination = Path('/opt/gitgood/artifacts')/seed['installation']
    for directory in (source,policy,destination):
        require(not directory.exists());root_directory(directory)
    write_new(policy/'allocation-lock-v1',b'',0o600)
    payloads = [];total = 0
    for name,path in (('forge',Path(seed['release'])),('web',Path(seed['web']))):
        paths,amount = copy_inventory(path);total += amount
        payloads.append((path,name))
        payloads.extend((entry,name+'/'+str(entry.relative_to(path))) for entry in paths)
    require(len(payloads) <= MAX_MEMBERS and total <= MAX_CONTENT)
    estimate = total+len(payloads)*8192+1048576
    for directory in (Path('/'),source):
        capacity = os.statvfs(directory);require(capacity.f_bavail*capacity.f_frsize >= RESERVE+estimate)
    archive = source/'archive.tar.gz'
    originals = {path:tuple(getattr(path.lstat(),field) for field in
        ('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')) for path,_ in payloads}
    metrics = {'members':0,'declared_bytes':0,'max_member_bytes':0,'max_name_length':0}
    with archive.open('xb') as output:
        with tarfile.open(fileobj=output,mode='w:gz',format=tarfile.PAX_FORMAT) as target:
            for path,name in payloads:
                info = target.gettarinfo(str(path),name);info.uid=info.gid=0;info.uname=info.gname=''
                metrics['members'] += 1;metrics['declared_bytes'] += info.size
                metrics['max_member_bytes'] = max(metrics['max_member_bytes'],info.size)
                metrics['max_name_length'] = max(metrics['max_name_length'],len(info.name))
                if info.isfile():
                    with path.open('rb') as content:target.addfile(info,content)
                else:require(info.isdir());target.addfile(info)
        output.flush();os.fchmod(output.fileno(),0o444);os.fsync(output.fileno())
    require(0 < archive.stat().st_size <= MAX_ARCHIVE)
    for path,original in originals.items():
        require(tuple(getattr(path.lstat(),field) for field in
            ('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')) == original)
    sha = digest(archive);inspected = inspect_native_artifact(archive,sha,seed['candidate'])
    require(inspected['members'] == len(payloads))
    require(metrics['members'] == inspected['members'] and metrics['declared_bytes'] == inspected['declared_bytes'])
    seed['archive_member_metrics'] = metrics
    return {'protocol':2,'kind':'native_artifact_declaration','installation':seed['installation'],
        'operation':seed['ownership_operation'],'candidate':seed['candidate'],'sha256':sha,'bytes':archive.stat().st_size}


def seal_public_runtime(seed,binding_sha256):
    from native_public_runtime import web_inventory
    from native_service_scope import root_file
    web,_ = web_inventory(seed['web'],seed['candidate'])
    edge_template,_ = root_file(Path(seed['edge_template']),16384)
    write_new(Path(seed['seal_directory'])/'public-runtime-v2.json',{'protocol':2,'kind':'native_public_runtime_seal',
        'installation':seed['installation'],'operation':seed['ownership_operation'],
        'candidate':seed['candidate'],'binding_sha256':binding_sha256,'web':web,'edge_template':edge_template})


def seal_lifecycle_fixture(seed, binding_sha256):
    """Real Root/input custody, with explicitly synthetic stage observations."""
    from native_operation_inputs import file_identity, file_record
    directory = Path('/var/lib/gitgood/operation-inputs') / seed['installation'] / seed['ownership_operation']
    root_directory(directory.parent.parent)
    root_directory(directory.parent)
    directory.mkdir(mode=0o700)
    os.chown(directory, seed['uid'], seed['gid'])
    artifact = provision_stage_archive(seed) if seed.get('artifact_stage_fixture') else None
    for name in ('allocation.json', 'inputs.json'):
        payload = {'protocol': 2, 'fixture_only': True, 'business_stage_effects_verified': False}
        if name == 'inputs.json' and seed.get('business_inputs_fixture'):
            target_versions = [1, 2]
            if seed.get('business_effects_fixture'):
                builds = list((Path(seed['release']) / 'lib').glob('gitgood-*/priv/build-identity.json'))
                require(len(builds) == 1)
                build = read_json(builds[0])
                require(build['candidate'] == seed['candidate'] and build['dirty'] is False)
                target_versions = [int(value) for value in build['migrations']]
                require(target_versions and target_versions == sorted(set(target_versions)))
            payload['business'] = {'kind': 'native_initial_business_inputs',
                'installation': seed['installation'], 'operation': seed['ownership_operation'], 'candidate': seed['candidate'],
                'migrations': {'before_versions': [], 'target_versions': target_versions},
                'bootstrap': {'installation': seed['installation'], 'request': seed['ownership_operation'],
                    'username': 'owner', 'team': 'pilot', 'password': 'synthetic-secret-éé'}}
        if name == 'inputs.json' and artifact is not None:payload['artifact'] = artifact
        write_new(directory / name, payload, 0o600, seed['uid'], seed['gid'])
    declared = {name: {'bytes': (directory / name).stat().st_size,
                      'sha256': hashlib.sha256((directory / name).read_bytes()).hexdigest()}
                for name in ('allocation.json', 'inputs.json')}
    request = {'protocol': 2, 'kind': 'native_lifecycle_request', 'installation': seed['installation'],
        'operation': seed['ownership_operation'], 'purpose': 'native_initial_enrollment',
        'durable_binding_sha256': binding_sha256, 'files': declared}
    write_new(directory / 'request.json', request, 0o600, seed['uid'], seed['gid'])
    files = {name: file_record(file_identity((directory / name).stat(), seed['uid'], seed['gid'], 16384),
                              (directory / name).read_bytes())
             for name in ('request.json', 'allocation.json', 'inputs.json')}
    operation = {'protocol': 2, 'kind': 'native_operation_inputs_seal',
        **{name: request[name] for name in ('installation', 'operation', 'purpose', 'durable_binding_sha256')},
        'uid': seed['uid'], 'gid': seed['gid'], 'directory_identity': identity(directory), 'files': files}
    seal = Path(seed['seal_directory'])
    (seal / 'operations').mkdir(mode=0o755)
    write_new(seal / 'operations' / (seed['ownership_operation'] + '.json'), operation)
    policy = {'protocol': 2,
        'kind': 'native_lifecycle_worker_seal',
        **{name: request[name] for name in ('installation', 'operation', 'purpose', 'durable_binding_sha256')},
        'candidate': seed['candidate'], 'request_sha256': hashlib.sha256(canonical(request)).hexdigest(),
        'inputs_seal_sha256': hashlib.sha256(canonical(operation)).hexdigest(), 'uid': seed['uid'], 'gid': seed['gid']}
    write_new(seal / 'lifecycle-worker-admission-v2.json', policy)
    if seed.get('public_runtime_fixture') and artifact is None:seal_public_runtime(seed,binding_sha256)
    paths = [seal / 'lifecycle-worker-admission-v2.json',
             seal / 'operations' / (seed['ownership_operation'] + '.json'),
             *(directory / name for name in ('request.json', 'allocation.json', 'inputs.json'))]
    return {'files': {path: fingerprint(path) for path in paths},
            'input_directory': directory, 'input_identity': identity(directory),
            'request': request, 'sealed_files': files, 'inputs_seal_sha256': policy['inputs_seal_sha256'],
            'target_versions': target_versions if seed.get('business_inputs_fixture') else None}


def observe_fixture_lifecycle_history(seed, pointer, preserved):
    """Root independently checks retained fixture history; no business acceptance."""
    from native_lifecycle_responsibility import replay, sha, validate_inventory
    from native_operation_inputs import file_identity, file_record as input_file_record
    def check_inputs():
        directory = preserved['input_directory']
        require(identity(directory) == preserved['input_identity'])
        for path, original in preserved['files'].items():
            require(fingerprint(path) == original)
        for name, original in preserved['sealed_files'].items():
            path = directory / name
            require(input_file_record(file_identity(path.stat(), seed['uid'], seed['gid'], 16384),
                                      path.read_bytes()) == original)
    check_inputs()
    history = Path(seed['root']) / 'history'
    lifecycle = history / 'lifecycle-responsibility-v2'
    require({path.name for path in itertools.islice(lifecycle.iterdir(), 3)} == {'records', 'heads'})
    operation = seed['ownership_operation']
    require({path.name for path in itertools.islice((lifecycle / 'heads').iterdir(), 2)} == {operation + '.json'})
    head_path = lifecycle / 'heads' / (operation + '.json')
    file_record(head_path, seed['uid'])
    head = read_json(head_path)
    require(set(head) == {'protocol', 'kind', 'installation', 'operation', 'snapshot_sha256'})
    require(head['protocol'] == 2 and head['kind'] == 'native_lifecycle_head')
    require((head['installation'], head['operation']) == (seed['installation'], operation))
    generation = pointer['generation_sha256']
    generations = {generation: read_json(history / 'generation-records-v2' / (generation + '.json'))}
    require(sha(generations[generation]) == generation)
    paths = list(itertools.islice((lifecycle / 'records').iterdir(), 12))
    require(len(paths) == 11)
    rows, records = {}, {}
    for path in paths:
        file_record(path, seed['uid'])
        value = read_json(path)
        key = sha(value)
        require(path.name == key + '.json')
        replay(value, generations)
        require(value['origin']['request'] == preserved['request'])
        require(value['origin']['inputs_seal_sha256'] == preserved['inputs_seal_sha256'])
        records[key] = value
        rows[key] = {'operation': operation, 'origin': sha(value['origin']),
            'previous': value['predecessor_sha256'], 'events': len(value['events']),
            'events_sha256': sha(value['events']), 'prefix_sha256': sha(value['events'][:-1])}
    validate_inventory(rows, {operation: head})
    tip = records[head['snapshot_sha256']]
    stages = ('inspect', 'stage', 'migrate', 'bootstrap', 'verify')
    require((tip['status'], tip['stage'], tip['completed'], tip['epoch']) == ('pending', 'verify', list(stages), 1))
    require(tip['generation_sha256'] == generation)
    receipts = {stage: sha({'fixture_only': True, 'business_stage_effects_verified': False,
        **({'ownership_boundary_observed': label} if label else {})})
        for stage, label in zip(stages, (None, None, 'migration-owner', 'bootstrap-owner', 'runtime-owner'))}
    if seed.get('artifact_stage_fixture'):
        actual = read_json(Path(seed['run'])/'artifact-stage-complete.json')
        receipts.update(inspect=actual['inspection_receipt_sha256'],stage=actual['stage_receipt_sha256'])
    require([(event['stage'], event['evidence']['receipt_sha256']) for event in tip['events']
             if event['kind'] == 'succeeded'] == [(stage, receipts[stage]) for stage in stages])
    check_inputs()
    return {'sealed_lifecycle_inputs_retained': True, 'fixture_lifecycle_history_verified': True,
            'remaining_lifecycle_stages': ['activate', 'enroll']}


def run_successor_case(seed, config, password, database, server_scope):
    with ExitStack() as root_views:
        return _run_successor_case(seed,config,password,database,server_scope,root_views)


def root_reader_loss_checks(seed, database, server_scope):
    """Disposable fixture faults target only its newly owned Root SQL readers."""
    from native_root_live_binding import NativeRootLiveBindingObservation, RootLiveBindingRefused
    name = 'gg_proof_'+seed['installation'].replace('-','')
    def writer():
        rows = database.query("SELECT a.pid::text||':'||floor(extract(epoch FROM a.backend_start)*1000000)::bigint::text "
            "FROM pg_stat_activity a JOIN pg_locks l ON l.pid=a.pid WHERE a.datname='"+name+
            "' AND a.usename='"+seed['account']+"' AND l.locktype='advisory' AND l.granted "
            "AND l.classid::bigint=1197034575 AND l.objid::bigint=1 AND l.objsubid=2 "
            "AND l.mode='ExclusiveLock'").splitlines()
        require(len(rows) == 1 and re.fullmatch(r'[1-9][0-9]{0,9}:[1-9][0-9]{0,19}',rows[0]))
        pid = int(rows[0].split(':')[0]);require(pid < 2**31)
        actual = process(pid);require(actual['uid'] == server_scope['postgres_uid'] and actual['state'] not in {'Z','X'})
        return rows[0],{name:actual[name] for name in ('pid','birth','uid','cgroup')}
    original_writer = writer();results = {}
    for fault in ('owned-client-loss','owned-backend-loss'):
        view = NativeRootLiveBindingObservation(seed['installation'],seed['ownership_operation'])
        try:
            require(view.check() == view.check())
            reader = view.database_reader;require(reader is not None)
            client = process(reader.child.pid);backend = process(reader.reader['backend_pid'])
            require(client['uid'] == 0 and client['birth'] == reader.client['birth'] and client['state'] not in {'Z','X'})
            require(backend['uid'] == server_scope['postgres_uid'] and backend['birth'] == reader.kernel
                and backend['state'] not in {'Z','X'})
            require(reader.reader['read_only'] == 'on' and reader.reader['isolation'] == 'read committed'
                and reader.reader['held'] is False and writer() == original_writer)
            pid = reader.reader['backend_pid'];birth = reader.reader['backend_birth']
            require(type(pid) is int and 0 < pid < 2**31 and re.fullmatch(r'[1-9][0-9]{0,19}',birth))
            predicate = (f"pid={pid} AND floor(extract(epoch FROM backend_start)*1000000)::bigint={birth} "
                "AND datname='"+name+"' AND usename='"+seed['account']+
                "' AND application_name='gitgood native root read-only observer v2'")
            require(database.query('SELECT count(*) FROM pg_stat_activity WHERE '+predicate) == '1')
            if fault == 'owned-client-loss':
                reader.child.kill();reader.child.wait(timeout=5)
            else:
                require(database.query('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE '+predicate) == 't')
            try:view.check()
            except RootLiveBindingRefused:require(not view.usable and not reader.usable)
            else:require(False)
            try:view.check()
            except RootLiveBindingRefused:require(not view.usable and not reader.usable)
            else:require(False)
            require(writer() == original_writer and not absent(original_writer[1]))
            results[fault] = True
        finally:view.close()
    require(set(results) == {'owned-client-loss','owned-backend-loss'} and all(results.values()))
    return {'owned_root_client_loss_refused':True,'owned_root_backend_loss_refused':True,
        'original_ordinary_writer_retained':True,'reconnection_or_replacement':False,
        'complete_journey_acceptance':False}


def root_guard_self_costs(stats):
    """Disjoint self-time totals only; unknown names remain unnamed."""
    totals = {name:[0,0.0] for name in ('installed_python','pathlib_python','copy_python',
        'json_python','regex_python','uuid_python','builtin','other_python')}
    path_files = {method.__code__.co_filename for method in
        (Path.__init__,Path.__str__,Path.__truediv__,Path.resolve,Path.stat,Path.lstat)}
    path_packages = {Path(name).parent for name in path_files if Path(name).parent.name == 'pathlib'}
    for (filename,line,_function),(_primitive,calls,total,_cumulative,_callers) in stats.items():
        require(type(filename) is str and type(line) is int)
        require(type(calls) is int and 0 <= calls <= 10000000)
        require(type(total) in {int,float} and 0 <= total <= 1200)
        path = Path(filename)
        if filename == '~' and line == 0:category = 'builtin'
        elif path.parent == MODULES and path.suffix == '.py':category = 'installed_python'
        elif filename in path_files or any(path.is_relative_to(parent) for parent in path_packages):category = 'pathlib_python'
        elif path == Path(copy.__file__):category = 'copy_python'
        elif path.parent == Path(json.__file__).parent:category = 'json_python'
        elif path.parent == Path(re.__file__).parent:category = 'regex_python'
        elif path == Path(uuid.__file__):category = 'uuid_python'
        else:category = 'other_python'
        totals[category][0] += calls;totals[category][1] += total
    require(all(calls <= 10000000 and total <= 1200 for calls,total in totals.values()))
    return [{'file':'guard-self-costs.py','function':category,'line':0,'calls':calls,
        'self_ms':int(total*1000),'cumulative_ms':int(total*1000),
        'self_us':int(total*1000000),'cumulative_us':int(total*1000000)}
        for category,(calls,total) in sorted(totals.items())]


def root_guard_builtin_self_codes():
    """Closed CPython builtin keys; no names taken from measured values."""
    functions = ('all','any','getattr','hasattr','hash','isinstance','issubclass','iter','len','next','setattr','sorted','sum','min','max')
    methods = (
        ('dict','get','dict_get'),('dict','items','dict_items'),('dict','values','dict_values'),
        ('dict','keys','dict_keys'),('dict','copy','dict_copy'),('dict','update','dict_update'),
        ('dict','setdefault','dict_setdefault'),('dict','pop','dict_pop'),
        ('list','append','list_append'),('list','extend','list_extend'),('list','pop','list_pop'),
        ('set','add','set_add'),('set','update','set_update'),
        ('str','join','str_join'),('str','split','str_split'),('str','splitlines','str_splitlines'),
        ('str','startswith','str_startswith'),('str','endswith','str_endswith'),('str','partition','str_partition'),
        ('str','encode','str_encode'),('str','strip','str_strip'),('str','rfind','str_rfind'),('str','replace','str_replace'),
        ('bytes','decode','bytes_decode'),('bytes','split','bytes_split'),('bytes','splitlines','bytes_splitlines'),
        ('bytes','startswith','bytes_startswith'),('bytes','partition','bytes_partition'),('bytes','strip','bytes_strip'),
        ('bytearray','extend','bytearray_extend'),
        ('_io.BufferedReader','read','buffered_read'),('_io.BufferedRandom','read','buffered_random_read'),
        ('_io.FileIO','read','file_read'),('_io.FileIO','readall','file_readall'),
        ('_io.TextIOWrapper','read','text_read'),('_io._IOBase','__exit__','io_exit'),
        ('_io.BufferedWriter','write','buffered_write'),('_io.BufferedWriter','flush','buffered_flush'),
        ('_io.FileIO','write','file_write'),('_io._IOBase','flush','io_flush'),
        ('_thread.lock','acquire','lock_acquire'),('select.epoll','poll','epoll_poll'))
    others = (('_io.open','io_open'),('posix.getuid','getuid'),('posix.geteuid','geteuid'),
        ('posix.getgid','getgid'),('posix.getegid','getegid'),('posix.getpid','getpid'),
        ('posix.getxattr','getxattr'),('posix.dup','dup'),('_thread.get_ident','thread_ident'),
        ('time.monotonic','monotonic'),('time.perf_counter','perf_counter'),('pwd.getpwnam','account_lookup'),
        ('_ctypes.byref','ctypes_byref'),('_ctypes.sizeof','ctypes_sizeof'))
    codes = {('~',0,'<built-in method builtins.'+name+'>'):name for name in functions}
    codes.update({('~',0,"<method '"+method+"' of '"+owner+"' objects>"):tag for owner,method,tag in methods})
    codes.update({('~',0,'<built-in method '+name+'>'):tag for name,tag in others})
    return codes


def root_guard_path_helper_codes(excluded):
    """Only fixed attributes' exact loaded pathlib code objects."""
    names = ('__new__','__init__','__fspath__','__hash__','__eq__','__lt__','__le__','__gt__','__ge__',
        '__getitem__','__len__','_load_parts','_parse_path','_parse_parts','_parse_args',
        '_from_parts','_from_parsed_parts','_from_parsed_string','_format_parsed_parts',
        '_make_child','_make_child_relpath','_str','_str_normcase','_parts_normcase','_tail',
        'with_segments','drive','root','anchor','name','parts','parents','parent','is_absolute',
        'as_posix','joinpath','relative_to','is_relative_to')
    files = {method.__code__.co_filename for method in
        (Path.__init__,Path.__str__,Path.__truediv__,Path.resolve,Path.stat,Path.lstat)}
    packages = {Path(name).parent for name in files if Path(name).parent.name == 'pathlib'}
    codes = {}
    for owner in (*Path.__mro__,type(Path('/').parents)):
        for name in names:
            value = vars(owner).get(name)
            if isinstance(value,property):value = value.fget
            elif isinstance(value,(staticmethod,classmethod)):value = value.__func__
            elif isinstance(value,cached_property):value = value.func
            for _ in range(4):
                wrapped = getattr(value,'__wrapped__',None)
                if wrapped is None:break
                value = wrapped
            code = getattr(value,'__code__',None)
            if code is None or code.co_name not in names:continue
            key = (code.co_filename,code.co_firstlineno,code.co_name)
            if key not in excluded and (code.co_filename in files or
                    any(Path(code.co_filename).is_relative_to(parent) for parent in packages)):
                codes[key] = code.co_name
    return codes


def root_guard_hot_self(stats,excluded_path_codes):
    """Bounded self-cost rows from public modules and closed runtime keys."""
    modules = {
        'enrollment_journal.py','generation_custody.py','generation_publication.py','inspect_native_artifact.py',
        'native_actions.py','native_artifact_controller.py','native_backend_observation.py','native_backend_observation_entry.py',
        'native_backend_scope.py','native_command_endpoint.py','native_command_wire.py','native_controller_scope.py',
        'native_durable_binding.py','native_durable_database.py','native_generation_admission.py','native_generation_admission_entry.py',
        'native_generation_lease_guard.py','native_generation_monitor.py','native_generation_monitor_entry.py','native_generation_reader.py',
        'native_inventory.py','native_kernel_backend.py','native_lifecycle_business_inputs.py','native_lifecycle_generation_reader.py',
        'native_lifecycle_history.py','native_lifecycle_responsibility.py','native_lifecycle_worker_inputs.py',
        'native_monitor_business_inputs.py','native_monitor_ownership_attachment.py','native_operation_inputs.py',
        'native_ownership_controller.py','native_ownership_database.py','native_ownership_handoff.py','native_ownership_handoff_entry.py',
        'native_ownership_marker_guard.py','native_ownership_markers.py','native_ownership_observation.py',
        'native_ownership_publication.py','native_ownership_publication_entry.py','native_ownership_records.py',
        'native_ownership_transition.py','native_prior_backend.py','native_protected_artifact.py','native_public_runtime.py',
        'native_root_artifact_dispatch.py','native_root_artifact_policy.py','native_root_controller.py','native_root_controller_request.py',
        'native_root_database_exclusion.py','native_root_database_reader.py','native_root_lifecycle.py','native_root_live_binding.py',
        'native_service_scope.py','native_systemd_properties.py','native_worker_scope.py','native_writer_exclusion.py',
        'resource_generations.py','stage_native_artifact.py','upgrade_journal.py'}
    builtin_codes = root_guard_builtin_self_codes();path_codes = root_guard_path_helper_codes(excluded_path_codes)
    module_totals = {};builtin_totals = {};path_totals = {}
    def add(totals,key,calls,total):
        count,elapsed = totals.get(key,(0,0.0));count += calls;elapsed += total
        require(count <= 10000000 and elapsed <= 1200);totals[key] = count,elapsed
    for (filename,line,function),(_primitive,calls,total,_cumulative,_callers) in stats.items():
        require(type(filename) is str and type(line) is int and type(function) is str)
        require(type(calls) is int and 0 <= calls <= 10000000)
        require(type(total) in {int,float} and 0 <= total <= 1200)
        path = Path(filename);key = filename,line,function
        if path.parent == MODULES and path.name in modules:add(module_totals,(path.name,'module_self',0),calls,total)
        if key in builtin_codes:add(builtin_totals,('builtin-self.py',builtin_codes[key],0),calls,total)
        if key in path_codes and 0 < line < 10000:add(path_totals,('pathlib-self.py',path_codes[key],line),calls,total)
    def selected(totals,maximum):
        rows = [{'file':file,'function':function,'line':line,'calls':calls,
            'self_ms':int(total*1000),'cumulative_ms':int(total*1000),
            'self_us':int(total*1000000),'cumulative_us':int(total*1000000)}
            for (file,function,line),(calls,total) in totals.items()]
        return sorted(rows,key=lambda row:(-row['self_us'],-row['calls'],row['file'],row['function'],row['line']))[:maximum]
    return selected(module_totals,8)+selected(builtin_totals,8)+selected(path_totals,9)


def root_guard_path_callers(stats, allowed, path_codes):
    """Direct public source-to-pathlib edge totals from the existing sample."""
    totals = {}
    for key, values in stats.items():
        if key not in path_codes:continue
        callers = values[4];require(type(callers) is dict)
        for caller, costs in callers.items():
            if type(caller) is not tuple or len(caller) != 3:continue
            filename,line,function = caller
            if type(filename) is not str or type(function) is not str:continue
            path = Path(filename)
            if (path.parent != MODULES or not path.name.startswith('native_') or
                    path.name not in allowed or function not in allowed[path.name]):continue
            require(type(line) is int and 0 < line < 10000)
            require(type(costs) is tuple and len(costs) == 4)
            primitive,calls,total,cumulative = costs
            require(all(type(value) is int and 0 <= value <= 10000000 for value in (primitive,calls)))
            require(all(type(value) in {int,float} and 0 <= value <= 1200 for value in (total,cumulative)))
            label = (path.name[:-3]+'.'+function,line)
            count,elapsed = totals.get(label,(0,0.0));count += calls;elapsed += cumulative
            require(count <= 10000000 and elapsed <= 1200);totals[label] = count,elapsed
    rows = [{'file':'path-callers.py','function':function,'line':line,'calls':calls,
        'self_ms':0,'self_us':0,'cumulative_ms':int(elapsed*1000),'cumulative_us':int(elapsed*1000000)}
        for (function,line),(calls,elapsed) in totals.items()]
    return sorted(rows,key=lambda row:(-row['cumulative_us'],-row['calls'],row['function'],row['line']))[:8]


ROOT_GUARD_SELF_FUNCTIONS = {
    'native_service_scope.py': {
        '__init__','_fingerprint','_observe_allocated_service','_observe_root_controller','_observe_service',
        '_process_security_fields','_process_status_fields','_root_file_parent_plan','_root_file_parents',
        '_root_file_path','bounded_command','close','field','freeze','group_identity','installed_version',
        'members','observe_service','parse_properties','process_identity','process_security','read',
        'read_bytes','require','root_file','systemd_properties',},
    'native_systemd_properties.py': {
        '__init__','_get','_get_all','_get_many','_get_many_serial','_read_property','_read_selected',
        '_read_value','_string','close','completed','manager_version','require','unit_properties',},
    'native_kernel_backend.py': {
        '_capture_process','_check_scope','_kernel_absence','_positive','_read','_stat','_status',
        '_validate_record','_validate_scope','capture_backend_kernel_identity',
        'observe_held_backend_kernel_identity','observe_prior_backend_identity_absence','require',},
    'native_durable_binding.py': {
        '__init__','_canonical_private_path','_fingerprint','_persistent_identity',
        '_root_persistent_identity','close','configuration','directory','executable','freeze',
        'observe_durable_binding','persistent_identity','private_file','read','require','unique',},
    'native_root_database_reader.py': {
        '__init__','_base','_binary','_client','_configuration','_exchange','_file','_reader',
        '_stage_observation','_statement','close','exclusion','identity','require',},
    'native_root_lifecycle.py': {
        '__enter__','__exit__','__init__','_current','_directory','_directory_metadata','_file','_identity',
        '_layout','_lifecycle_view','_names','_open','_pin_snapshot','_root','_snapshot','_write','admit',
        'borrow_custody','check','close','parse_generation_seal','publish','require','retain','root_owner',},
    'resource_generations.py': {
        'canonical','closed','digest','directory','generation_sha256','identifier','integer',
        'make_generation','parse_generation','require','unique','validate_generation','validate_scope',
        'validate_successor',},
}


def root_guard_installed_self(stats):
    """Eight public function self costs from the same existing guard profile.

    This closed source inventory names functions in measured hot modules. Only
    their public source label/line and bounded numeric costs leave the profile.
    No source, caller mapping, argument, local or observation is read here.
    """
    rows = []
    for (filename,line,function),(_primitive,calls,total,_cumulative,_callers) in stats.items():
        if type(filename) is not str or type(function) is not str:continue
        path = Path(filename)
        if (path.parent != MODULES or path.name not in ROOT_GUARD_SELF_FUNCTIONS or
                function not in ROOT_GUARD_SELF_FUNCTIONS[path.name]):continue
        require(type(line) is int and 0 < line < 10000)
        require(type(calls) is int and 0 <= calls <= 10000000)
        require(type(total) in {int,float} and 0 <= total <= 1200)
        rows.append({'file':'installed-self.py','function':path.stem+'.'+function,'line':line,'calls':calls,
            'self_ms':int(total*1000),'cumulative_ms':int(total*1000),
            'self_us':int(total*1000000),'cumulative_us':int(total*1000000)})
    return sorted(rows,key=lambda row:(-row['self_us'],-row['calls'],row['function'],row['line']))[:8]


def root_stage_profile(profile):
    """Closed public code counters only; no stacks, argument values or paths."""
    allowed = {
        'native_protected_artifact.py':{'stage','check','_preflight_archive','_check_archive_input','_check_output','directory','_artifact_path'},
        'native_root_artifact_dispatch.py':{'stage','check','serve_artifact_stage'},
        'native_root_artifact_policy.py':{'allocate','check','_inspect','_directory','_root_directory_metadata'},
        'native_root_database_exclusion.py':{'check','_base','_query','_socket','_client'},
        'native_root_database_reader.py':{'_base','_exchange','_client','_configuration'},
        'native_root_live_binding.py':{'check','_observe','_current'},
        'native_root_lifecycle.py':{'check','_snapshot','_current','_identity','_names','_file'},
        'native_root_controller.py':{'check','_service','observed'},
        'native_service_scope.py':{'_observe_allocated_service','read_bytes','root_file',
            'read','_fingerprint','_root_file_path','process_identity','process_security',
            '_process_status_fields','_process_security_fields','group_identity','members',
            '_root_file_parents','_root_file_parent_plan'},
        'native_systemd_properties.py':{'unit_properties','_get_many'},
        'native_lifecycle_history.py':{'__init__','check','_check_files','_read'},
        'native_ownership_database.py':{'_socket_for_process'},
        'native_kernel_backend.py':{'_check_scope','_capture_process','_stat','_read'},
        'native_durable_binding.py':{'configuration','_persistent_identity','read','private_file','directory','_canonical_private_path'},
        'native_backend_scope.py':{'check'},
        'native_generation_lease_guard.py':{'persistent_fingerprint','_fingerprint_path','read'},
        'native_controller_scope.py':{'private_directory'},
        'resource_generations.py':{'canonical'},
        'copy.py':{'deepcopy','_deepcopy_dict','_deepcopy_list','_deepcopy_tuple'},
        'pathlib.py':{'__init__','__str__','__truediv__','resolve','stat','lstat'},
        'posix.py':{'stat','lstat','fstat','open','read','readlink','scandir','listdir','close'},
        'socket.py':{'sendto','recvmsg','send','recv'},
        'guard-self-costs.py':{'installed_python','pathlib_python','copy_python','json_python',
            'regex_python','uuid_python','builtin','other_python'},
    }
    # Match only these six loaded code objects, including their original line.
    # This also handles stdlib layouts split across implementation modules.
    path_codes = {(method.__code__.co_filename,method.__code__.co_firstlineno,method.__code__.co_name)
        for method in (Path.__init__,Path.__str__,Path.__truediv__,Path.resolve,Path.stat,Path.lstat)}
    # CPython C entries have a closed profiler name and no source line. Match
    # the complete key; never infer a primitive from a filename or substring.
    builtin_codes = {('~',0,'<built-in method posix.'+name+'>'):('posix.py',name)
        for name in allowed['posix.py']}
    builtin_codes.update({('~',0,"<method '"+name+"' of '_socket.socket' objects>"):('socket.py',name)
        for name in allowed['socket.py']})
    reserved = {('native_root_artifact_policy.py','_directory'),
        ('native_root_artifact_policy.py','_root_directory_metadata'),
        ('native_protected_artifact.py','directory'),('native_protected_artifact.py','_artifact_path'),
        ('copy.py','deepcopy'),('resource_generations.py','canonical'),('native_root_controller.py','observed'),
        ('native_service_scope.py','_process_status_fields'),('native_service_scope.py','_process_security_fields'),
        ('native_service_scope.py','_root_file_parents'),('native_generation_lease_guard.py','read'),
        ('native_root_artifact_dispatch.py','check')}
    reserved.update((label,name) for label in ('pathlib.py','posix.py','socket.py','guard-self-costs.py') for name in allowed[label])
    rows = []
    stats = pstats.Stats(profile).stats
    for (filename,line,function),(primitive,calls,total,cumulative,_callers) in stats.items():
        path = Path(filename)
        builtin = (filename,line,function) in builtin_codes
        if builtin:label,function = builtin_codes[(filename,line,function)]
        elif path.parent == MODULES and path.name not in {'copy.py','pathlib.py','posix.py','socket.py','guard-self-costs.py','builtin-self.py','pathlib-self.py'}:label = path.name
        elif path == Path(copy.__file__):label = 'copy.py'
        elif (filename,line,function) in path_codes:label = 'pathlib.py'
        else:continue
        if function == 'module_self' or label not in allowed or function not in allowed[label]:continue
        if (type(line) is not int or not (line == 0 if builtin else 0 < line < 10000) or type(calls) is not int
                or not 0 <= calls <= 10000000):continue
        values = [total,cumulative]
        if not all(type(value) in {int,float} and 0 <= value <= 1200 for value in values):continue
        rows.append({'file':label,'function':function,'line':line,'calls':calls,
            'self_ms':int(total*1000),'cumulative_ms':int(cumulative*1000),
            'self_us':int(total*1000000),'cumulative_us':int(cumulative*1000000)})
    # Category totals apply only to the installed staging guard sample. They
    # are postprocessing of that same profile, not another measured invocation.
    if any(filename == str(MODULES/'native_root_artifact_dispatch.py') and
            type(line) is int and 0 < line < 10000 and function == 'check'
            for filename,line,function in stats):
        rows.extend(root_guard_self_costs(stats))
        hot = root_guard_hot_self(stats,path_codes)
        detail = root_guard_installed_self(stats)
        # Refine the eight coarse installed-module slots. Their category
        # aggregate remains above; keep the original primitive/path quotas and
        # direct caller attribution within the same total64-row bound.
        if detail:hot = [row for row in hot if row['function'] != 'module_self'] + detail
        rows.extend(hot)
        callers = root_guard_path_callers(stats,allowed,path_codes | set(root_guard_path_helper_codes(path_codes)))
        rows.extend(callers)
        reserved.update((row['file'],row['function']) for row in callers)
    # Reserve the fixed diagnostic questions before filling remaining slots by
    # cost. Low-cost required helpers must not disappear at the 64-row cap.
    rows = sorted(rows,key=lambda value:(0 if (value['file'],value['function']) in reserved else
        1 if value['file'] in {'builtin-self.py','pathlib-self.py','installed-self.py'} or value['function']=='module_self' else 2,
        -value['cumulative_us'],-value['self_us'],
        value['file'],value['function'],value['line']))[:64]
    return sorted(rows,key=lambda value:(value['file'],value['function'],value['line']))


class RootGuardSample:
    """Profile only fixed read-only guard ten; never a whole stage or effect."""
    def __init__(self):
        self.calls = 0;self.profile = None;self.completed = False

    def wrap(self, original):
        def checked(*arguments, **keywords):
            self.calls += 1
            if self.calls != 10 or sys.implementation.name != 'cpython':
                return original(*arguments, **keywords)
            monitoring = getattr(sys,'monitoring',None)
            if (sys.getprofile() is not None or (monitoring is not None
                    and monitoring.get_tool(monitoring.PROFILER_ID) is not None)):
                return original(*arguments, **keywords)
            self.profile = cProfile.Profile()
            try:return self.profile.runcall(original,*arguments,**keywords)
            finally:self.completed = True
        return checked

    def values(self):
        if not self.completed:return None
        return {'diagnostic_only':True,'guard_number':10,'profiled_checks':1,
            'rows':root_stage_profile(self.profile)}


STAGE_MEASUREMENT_TARGETS = (
    ('native_root_artifact_dispatch','_ObservedArtifactStage','check'),
    ('native_protected_artifact','NativeProtectedArtifactStage','_preflight_archive'),
    ('native_protected_artifact','NativeProtectedArtifactStage','_check_archive_input'),
    ('native_protected_artifact','NativeProtectedArtifactStage','_check_output'),
    ('native_protected_artifact','NativeProtectedArtifactStage','_code_parent'),
    ('native_protected_artifact','NativeProtectedArtifactStage','_code_directory'),
    ('native_root_artifact_policy','NativeRootArtifactPolicyAllocation','check'),
    ('native_root_database_exclusion','NativeRootDatabaseExclusionObservation','check'),
    ('native_root_database_reader','NativeRootDatabaseReader','_base'),
    ('native_root_database_reader','NativeRootDatabaseReader','_exchange'),
    ('native_root_controller','NativeRootControllerObservation','_service'),
    ('native_systemd_properties','ReadOnlySystemdProperties','_get_many'),
    ('native_systemd_properties','ReadOnlySystemdProperties','_get_all'),
    ('native_service_scope','_CapturedRootFiles','read'),
    ('native_durable_binding','_CapturedExecutableDigests','read'),
    ('native_root_lifecycle','NativeRootLifecycleObservation','_current'),
    ('native_root_live_binding','NativeRootLiveBindingObservation','_observe'),
)


def _timed_stage_method(original, counter):
    """Forward the exact call/result/error; retain only count and elapsed time."""
    def timed(*arguments, **keywords):
        started = time.monotonic_ns()
        try:return original(*arguments, **keywords)
        finally:
            counter['calls'] += 1
            counter['elapsed_ns'] += max(0,time.monotonic_ns()-started)
    return timed


def stage_measurement_values(counters):
    names = {'.'.join(target) for target in STAGE_MEASUREMENT_TARGETS}
    require(type(counters) is dict and set(counters) == names)
    rows = []
    for name in sorted(names):
        value = counters[name]
        require(type(value) is dict and set(value) == {'calls','elapsed_ns'})
        require(type(value['calls']) is int and 0 <= value['calls'] <= 10000000)
        require(type(value['elapsed_ns']) is int and 0 <= value['elapsed_ns'] <= 1200000000000)
        rows.append({'method':name,'calls':value['calls'],'cumulative_ms':value['elapsed_ns']//1000000})
    return {'diagnostic_only':True,'overlapping_cumulative_times':True,'methods':rows}


class RootGuardCPU:
    """CPU clocks around existing guards only; exclude child/server CPU."""
    def __init__(self):
        self.calls = 0;self.wall_ns = 0;self.process_ns = 0;self.thread_ns = 0

    def wrap(self, original):
        def checked(*arguments, **keywords):
            wall = time.monotonic_ns();process = time.process_time_ns();thread = time.thread_time_ns()
            try:return original(*arguments, **keywords)
            finally:
                self.calls += 1
                self.thread_ns += max(0,time.thread_time_ns()-thread)
                self.process_ns += max(0,time.process_time_ns()-process)
                self.wall_ns += max(0,time.monotonic_ns()-wall)
        return checked

    def values(self):
        require(type(self.calls) is int and 0 <= self.calls <= 10000000)
        require(all(type(value) is int and 0 <= value <= 1200000000000
            for value in (self.wall_ns,self.process_ns,self.thread_ns)))
        return {'diagnostic_only':True,'existing_guards_only':True,'calls':self.calls,
            'wall_ms':self.wall_ns//1000000,'process_cpu_ms':self.process_ns//1000000,
            'calling_thread_cpu_ms':self.thread_ns//1000000,'child_cpu_included':False}


class RootStageMeasurements:
    """Fixture-only fixed method timers, restored even on interrupted staging.

    Aggregate timers never inspect arguments or retain results. One fixed
    read-only guard is sampled separately; no profile spans a stage effect.
    An uninstrumented full production run is required for deadline acceptance.
    """
    def __init__(self):
        self.originals = []
        self.sample = RootGuardSample()
        self.cpu = RootGuardCPU()
        self.counters = {'.'.join(target):{'calls':0,'elapsed_ns':0}
            for target in STAGE_MEASUREMENT_TARGETS}

    def __enter__(self):
        try:
            for module_name,class_name,method_name in STAGE_MEASUREMENT_TARGETS:
                module = sys.modules[module_name]
                require(Path(module.__file__).parent == MODULES)
                owner = getattr(module,class_name)
                original = owner.__dict__[method_name]
                require(callable(original))
                self.originals.append((owner,method_name,original))
                wrapped = _timed_stage_method(original,self.counters['.'.join((module_name,class_name,method_name))])
                if (module_name,class_name,method_name) == STAGE_MEASUREMENT_TARGETS[0]:
                    wrapped = self.cpu.wrap(self.sample.wrap(wrapped))
                setattr(owner,method_name,wrapped)
            return self
        except BaseException:
            self.__exit__(None,None,None);raise

    def __exit__(self, *_):
        for owner,name,original in reversed(self.originals):setattr(owner,name,original)
        self.originals.clear()

    def values(self):
        return stage_measurement_values(self.counters)


def _run_successor_case(seed, config, password, database, server_scope, root_views):
    """Independent witness of actual protected same-controller handoffs."""
    run, seal = Path(seed['run']), Path(seed['seal_directory'])
    storage = Path(seed['root']) / 'storage'
    transition = storage / '.gitgood-successors-v4'
    command(['/usr/bin/systemctl', 'daemon-reload'])
    command(['/usr/bin/systemctl', 'start', seed['unit']])
    seed['proof_phase'] = 'successor-independent-binding-seal'
    observed = wait_for(run / 'observed.json', run, 40)
    seal_observation(seed, config, password, observed, database, server_scope)
    published = wait_for(run / 'published.json', run, 50)
    require(published['generation_publication_established'] is True)
    require(published['installation_readiness_established'] is False)
    preserved_lifecycle = None
    if seed.get('lifecycle_fixture'):
        preserved_lifecycle = seal_lifecycle_fixture(seed, observed['binding_sha256'])
    business_database = 'gg_proof_' + seed['installation'].replace('-', '')
    if seed.get('business_effects_fixture'):
        database.query('CREATE SCHEMA fixture_shadow AUTHORIZATION ' + seed['account'], database=business_database)
        database.query('ALTER ROLE ' + seed['account'] + ' IN DATABASE ' + business_database + ' SET search_path TO fixture_shadow, public')
    if seed.get('schema_refusal_fixture'):
        database.query('CREATE TABLE public.fixture_unexpected_relation (id integer)',
            database=business_database, role=seed['account'], password=password)
    staged_artifact_observation = None
    if seed.get('artifact_stage_fixture'):
        from native_root_artifact_dispatch import serve_artifact_stage
        root_directory(Path('/run/gitgood/root-artifacts'))
        listener = root_views.enter_context(socket.socket(socket.AF_UNIX,socket.SOCK_STREAM))
        path = Path('/run/gitgood/root-artifacts')/(seed['installation']+'.sock')
        require(not path.exists());listener.bind(str(path));os.chown(path,0,seed['gid']);os.chmod(path,0o620)
        listener.listen(1);listener.settimeout(30)
    write_new(seal / 'fixture-start.json', {'start': True})
    if seed.get('artifact_stage_fixture'):
        seed['proof_phase'] = 'actual-ordinary-inspection-and-serialized-root-stage'
        connection,_ = listener.accept()
        seed['artifact_stage_started'] = time.monotonic()
        seed['proof_phase'] = 'original-root-read-only-observer-loss-checks'
        seed['root_reader_refusal_observation'] = root_reader_loss_checks(seed,database,server_scope)
        seed['proof_phase'] = 'actual-ordinary-inspection-and-serialized-root-stage'
        # Compare the four-role pure lexical candidate on the original guard,
        # then restore SDK descriptors, clear plans and revalidate custody before
        # original measurements/effects. Full staging and deadlines are unchanged.
        measurements = RootStageMeasurements()
        from native_root_artifact_dispatch import _ObservedArtifactStage
        metadata = native_path_probe.Loaded(Path(seed['release']).parent/'native-metadata-probe')
        diagnostic = native_path_probe.AtFirstGuard(metadata,_ObservedArtifactStage,measurements,
            comparison=native_path_probe.compare_descriptor_guard)
        try:
            with diagnostic:
                served = serve_artifact_stage(seed['installation'],seed['ownership_operation'],connection)
        finally:
            if diagnostic.result is not None:seed['native_descriptor_comparison'] = diagnostic.result
            seed['root_stage_measurements'] = measurements.values()
            seed['root_guard_cpu'] = measurements.cpu.values()
            sample = measurements.sample.values()
            if sample is not None:seed['root_guard_sample'] = sample
        if served['status'] == 'refused':
            elapsed = min(1200000,max(0,int((time.monotonic()-seed['artifact_stage_started'])*1000)))
            seed['root_stage_refusal'] = root_stage_refusal(served,elapsed)
            require(seed['root_stage_refusal'] is not None)
        require(served['status'] == 'staged')
        staged_artifact_observation = wait_for(run/'artifact-stage-complete.json',run,20)
        require(staged_artifact_observation['actual_ordinary_controller_inspection'] is True
            and staged_artifact_observation['actual_root_stage_output_independently_checked'] is True
            and staged_artifact_observation['complete_journey_acceptance'] is False
            and staged_artifact_observation['stage_receipt_sha256'] == served['receipt_sha256'])
        code = Path('/opt/gitgood/artifacts')/seed['installation']/('native-'+seed['ownership_operation'])/'code'
        seed['release'] = str(code/'forge');seed['web'] = str(code/'web')
        seal_public_runtime(seed,observed['binding_sha256'])
    opened = wait_for(run / 'controller-open.json', run, 15)
    manager = process(opened['actual_main_pid'])
    require(opened['controller_identity'] == observed['scope']['manager'])
    require(manager['pid'] == opened['controller_identity']['pid'] and manager['birth'] == opened['controller_identity']['birth'])
    require(manager['uid'] == seed['uid'] and manager['cgroup'] == '0::/system.slice/' + seed['unit'] + '/driver')
    require(command(['/usr/bin/systemctl', 'show', seed['unit'], '--property=MainPID', '--value']).strip() == str(manager['pid']).encode())
    # Root's production observer independently reuses the allocated unit policy;
    # it cannot impersonate an ordinary worker or receive fixture authority maps.
    from native_root_controller import NativeRootControllerObservation
    root_view = NativeRootControllerObservation(seed['installation'])
    try:
        require(root_view.check() == observed['scope'])
        require(root_view.check() == observed['scope'])
    finally:
        root_view.close()
    stages = []
    captured_records = []
    pointer = None
    previous_sha = None
    maintenance_refusal = bool(seed.get('schema_refusal_fixture') or seed.get('inventory_refusal_fixture'))
    runtime_observation = {}
    root_lifecycle_observation = None
    root_live_binding_observation = None
    root_controller_request_observation = None
    root_controller_request_refusals = False
    root_database_exclusion_observation = None
    root_database_exclusion_loss_refused = False
    root_database_view = None
    for label, mode, fault in [('migration-owner', 'migrate', 'helper-loss'),
                              ('bootstrap-owner', 'migrate', 'original-backend-loss'),
                              ('runtime-owner', 'runtime', 'helper-loss')]:
        seed['proof_phase'] = label + ':held-writer-exclusion'
        stage = run / label
        pending = wait_for(stage / 'reserved.json', run, 20)
        if seed.get('lifecycle_fixture') and label == 'migration-owner':
            # Observe the actual current controller, fixed Root policies,
            # ordinary-owned inputs and complete recorded histories while the
            # manager retains its original reservation. No effect grant follows.
            from native_root_lifecycle import NativeRootLifecycleObservation
            lifecycle_view = NativeRootLifecycleObservation(seed['installation'],seed['ownership_operation'])
            try:
                root_lifecycle_observation = lifecycle_view.check()
                require(lifecycle_view.check() == root_lifecycle_observation)
                require(all(root_lifecycle_observation[name] == expected for name,expected in (
                    ('installation',seed['installation']),('operation',seed['ownership_operation']),
                    ('candidate',seed['candidate']),('stage','migrate'),('recorded_status','running'),
                    ('original_controller_and_complete_history_observed',True),
                    ('live_durable_resource_identity_verified',False),('lifecycle_exclusion_established',False),
                    ('stage_effect_authorized',False),('complete_journey_acceptance',False))))
            finally:lifecycle_view.close()
            from native_root_live_binding import NativeRootLiveBindingObservation
            binding_view = NativeRootLiveBindingObservation(seed['installation'],seed['ownership_operation'])
            try:
                root_live_binding_observation = binding_view.check()
                require(binding_view.check() == root_live_binding_observation)
                require(all(root_live_binding_observation[name] == expected for name,expected in (
                    ('installation',seed['installation']),('operation',seed['ownership_operation']),
                    ('candidate',seed['candidate']),('stage','migrate'),('recorded_status','running'),
                    ('original_live_files_and_database_observed',True),('live_durable_resource_identity_verified',True),
                    ('lifecycle_exclusion_established',False),('stage_effect_authorized',False),('complete_journey_acceptance',False))))
            finally:binding_view.close()
            from native_root_controller_request import NativeRootControllerRequest, RootControllerRequestRefused
            from native_command_wire import _peer
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as listener:
                listener.bind(str(stage/'root-request.sock'))
                os.chown(stage/'root-request.sock',seed['uid'],seed['gid']);os.chmod(stage/'root-request.sock',0o600)
                listener.listen(1);listener.settimeout(10)
                # The same ordinary account in a different process must not
                # impersonate the original MainPID, even with well-formed data.
                client_code = ('import json,socket,sys; s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); '
                    's.settimeout(2); s.connect(sys.argv[1]); '
                    's.sendall(sys.argv[2].encode()); s.shutdown(socket.SHUT_WR); s.close()')
                foreign_frame = canonical({'protocol':2,'kind':'native_root_controller_request',
                    'installation':seed['installation'],'operation':seed['ownership_operation'],'history_lock_fd':8})+b'\n'
                with subprocess.Popen([seed['executables']['python'],'-c',client_code,str(stage/'root-request.sock'),
                        foreign_frame.decode('ascii')],user=seed['uid'],group=seed['gid'],extra_groups=[],
                        env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL) as foreign:
                    connection,_ = listener.accept()
                    foreign_peer = _peer(connection,seed['uid'])
                    require(foreign_peer['pid'] != manager['pid'] and foreign_peer['gid'] == seed['gid'])
                    try:NativeRootControllerRequest(seed['installation'],seed['ownership_operation'],connection)
                    except RootControllerRequestRefused:require(connection.fileno() == -1)
                    else:require(False)
                    require(foreign.wait(timeout=5) == 0)
                write_new(seal/'fixture-root-request-start.json',{'start':True})
                connection,_ = listener.accept()
                require(_peer(connection,seed['uid']) == {'pid':manager['pid'],'uid':seed['uid'],'gid':seed['gid']})
                try:NativeRootControllerRequest(seed['installation'],seed['ownership_operation'],connection)
                except RootControllerRequestRefused:require(connection.fileno() == -1)
                else:require(False)
                write_new(seal/'fixture-root-request-refused.json',{'wrong_operation_refused':True})
                connection,_ = listener.accept()
                request_view = NativeRootControllerRequest(seed['installation'],seed['ownership_operation'],connection)
                root_views.callback(request_view.close)
                root_controller_request_observation = request_view.check()
                require(request_view.check() == root_controller_request_observation)
                require(all(root_controller_request_observation[name] is expected for name,expected in (
                    ('original_controller_peer_authenticated',True),('original_controller_history_lock_observed',True),
                    ('database_writer_exclusion_verified',False),('lifecycle_exclusion_established',False),
                    ('stage_effect_authorized',False),('complete_journey_acceptance',False))))
                from native_root_database_exclusion import NativeRootDatabaseExclusionObservation, RootDatabaseExclusionRefused
                root_database_view = NativeRootDatabaseExclusionObservation(request_view)
                root_views.callback(root_database_view.close)
                root_database_exclusion_observation = root_database_view.check()
                require(root_database_view.check() == root_database_exclusion_observation)
                require(all(root_database_exclusion_observation[name] is expected for name,expected in (
                    ('original_database_writer_lease_observed',True),('original_database_client_socket_observed',True),
                    ('original_database_backend_kernel_observed',True),('database_writer_exclusion_verified',True),
                    ('lease_acquired',False),('lifecycle_exclusion_established',False),
                    ('stage_effect_authorized',False),('complete_journey_acceptance',False))))
                root_controller_request_refusals = True
                write_new(seal/'fixture-root-request-accepted.json',{'original_peer_and_history_lock_observed':True})
        runtime_refusal = bool(seed.get('runtime_schema_refusal_fixture') and label == 'runtime-owner')
        stage_refusal = maintenance_refusal or runtime_refusal
        if runtime_refusal:
            database.query('DELETE FROM public.schema_migrations WHERE version=' + str(preserved_lifecycle['target_versions'][-1]), database=business_database)
        if stage_refusal:
            lifecycle_head = Path(seed['root']) / 'history/lifecycle-responsibility-v2/heads' / (seed['ownership_operation'] + '.json')
            original_head = fingerprint(lifecycle_head)
            lifecycle_snapshot = Path(seed['root']) / 'history/lifecycle-responsibility-v2/records' / (read_json(lifecycle_head)['snapshot_sha256'] + '.json')
            original_snapshot = fingerprint(lifecycle_snapshot)
            require(read_json(lifecycle_snapshot)['status'] == 'running' and read_json(lifecycle_snapshot)['stage'] == ('verify' if runtime_refusal else 'migrate'))
        reservation = read_json(transition / (pending['claim'] + '.reservation.json'))
        require(pending['reservation_sha256'] == hashlib.sha256(canonical(reservation)).hexdigest())
        require(reservation['mode'] == mode and reservation['predecessor_sha256'] == previous_sha)
        require(set(reservation['absence']) == {entry['sha'] for entry in captured_records})
        exclusion = reservation['exclusion_kernel']
        session = exclusion['database_session']
        excluded = process(session['backend_pid'])
        require(excluded['birth'] == exclusion['kernel_birth'] and excluded['uid'] == server_scope['postgres_uid'])
        require(database.query('SELECT count(*) FROM pg_stat_activity WHERE ' + database.predicate(session)) == '1')
        require(database.query("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND granted "
            f"AND pid={excluded['pid']} AND classid::bigint=1197034575 AND objid::bigint=1 AND objsubid=2 AND mode='ExclusiveLock'") == '1')
        write_new(seal / ('fixture-launch-' + label + '.json'), {'exclusion_observed': True})
        seed['proof_phase'] = label + ':protected-handoff-and-heartbeats'
        if seed.get('lifecycle_fixture') and label == 'migration-owner':
            refused_startup = wait_for(stage / 'wrong-action-refused.json', run, 45)
            require(refused_startup == {'requested_action': 'bootstrap', 'recorded_stage': 'migrate',
                'before_handoff_and_lease': True, 'fixture_probe_started': False})
            require(not (transition / (pending['claim'] + '.assignment.json')).exists())
            require(not list((storage / '.gitgood-ownership-v2').glob('*.json')))
            require(not absent(excluded) and database.query('SELECT count(*) FROM pg_stat_activity WHERE ' + database.predicate(session)) == '1')
            require(database.query("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND granted "
                f"AND pid={excluded['pid']} AND classid::bigint=1197034575 AND objid::bigint=1 AND objsubid=2 AND mode='ExclusiveLock'") == '1')
            write_new(seal / 'fixture-correct-action.json', {'original_reservation_retained': True})
        default_stage = bool(seed.get('default_release_fixture') and label == 'runtime-owner')
        if default_stage:
            attached = wait_for(stage / 'default-owner.json', run, 100)
            seed['proof_phase'] = 'default-release:independent-original-socket-lease-and-readiness'
            captured = capture_default_attachment(seed, attached, config, database, server_scope)
        else:
            attached = wait_for(stage / 'attached.json', run, 100)
            captured = capture_attachment(seed, attached, database, mode=mode, protocol=4)
        if root_database_view is not None and label == 'migration-owner':
            # The real handoff reaped the original controller psql child and
            # server backend. Prove this retained Root view cannot adopt the
            # new BEAM's lease, while original peer/history/resources still match.
            require(root_database_view.request.check() == root_database_view.observed)
            require(absent(root_database_view.client) and absent(excluded))
            try:root_database_view.check()
            except RootDatabaseExclusionRefused:require(root_database_view.usable is False)
            else:require(False)
            try:root_database_view.check()
            except RootDatabaseExclusionRefused:require(root_database_view.usable is False)
            else:require(False)
            root_database_exclusion_loss_refused = True
        if seed.get('business_inputs_fixture') and not seed.get('business_effects_fixture') and label != 'runtime-owner':
            private = wait_for(stage / 'private-inputs-observed.json', run, 5)
            require(private == {'action': 'migrate' if label == 'migration-owner' else 'bootstrap',
                'original_guard_and_ownership_bound': True, 'credential_status_redacted': True,
                'bootstrap_digest_validated': label == 'bootstrap-owner', 'business_effects_executed': False})
        else:
            require(not (stage / 'private-inputs-observed.json').exists())
        record = attached['record']
        require(record['claim'] == pending['claim'] and record['reservation_sha256'] == pending['reservation_sha256'])
        require(record['predecessor_sha256'] == previous_sha)
        if pointer is None:
            pointer = record['pointer']
        require(record['pointer'] == pointer and record['scope'] == observed['scope'])
        if not default_stage:
            require(attached['repeated_admission_refused'] is True)
            refused = wait_for(stage / 'repeat-admission-refused.json', run, 5)
            require(refused == {'actual_endpoint_refused': True, 'controller_state': 'complete',
                               'assignment_preserved': True, 'claim': record['claim']})
        assignment = read_json(transition / (record['claim'] + '.assignment.json'))
        require(assignment['owner'] == record['owner'] and assignment['claim'] == record['claim'])
        require(assignment['peer']['uid'] == seed['uid'] and assignment['peer']['pid'] != manager['pid'])
        require(absent(excluded) and database.backend_absent(session))
        for prior in captured_records:
            require(fingerprint(prior['captured']['retained']) == prior['captured']['record_file'])
        if captured_records:
            archive = transition / (record['claim'] + '.old-marker.json')
            require(fingerprint(archive) == captured_records[-1]['captured']['marker_file'])
        public_stage = seed.get('public_runtime_fixture') and label == 'runtime-owner'
        if not public_stage:
            write_new(seal / ('fixture-sentinel-' + label + '.json'), {'publication_observed': True})
            sibling = wait_for(stage / 'sentinel.json', run, 5)
            sentinel = process(sibling['sentinel_pid'])
            require(sentinel['uid'] == seed['uid'] and sentinel['cgroup'] == '0::/system.slice/' + seed['unit'] + '/web')
        application_backends = []
        if seed.get('business_effects_fixture') and label != 'runtime-owner':
            application_backends = capture_application_backends(database, seed, server_scope)
            write_new(stage / 'maintenance-execute.json', {'original_backends_captured': True}, 0o600, seed['uid'], seed['gid'])
            seed['proof_phase'] = label + ':actual-maintenance-effects'
            if not maintenance_refusal:
                outcome = wait_for(stage / 'maintenance-effects-observed.json', run, 65)
                require(outcome == {'action': 'migrate' if label == 'migration-owner' else 'bootstrap',
                    'fixed_native_entrypoint_used': True, 'schema_versions_observed': True,
                    'bootstrap_owner_observed': label == 'bootstrap-owner', 'business_effects_observed': True,
                    'credential_status_redacted': True})
                target = preserved_lifecycle['target_versions']
                actual_versions = database.query('SELECT coalesce(string_agg(version::text,\',\' ORDER BY version),\'\') FROM public.schema_migrations', database=business_database)
                require(actual_versions == ','.join(map(str, target)))
                require(database.query("SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='fixture_shadow'", database=business_database) == '0')
                if label == 'bootstrap-owner':
                    require(database.query("SELECT count(*) FROM public.installation_owner_bootstraps WHERE installation='" + seed['installation'] + "'::uuid AND request='" + seed['ownership_operation'] + "'::uuid AND username='owner' AND team='pilot'", database=business_database) == '1')
                    require(database.query("SELECT count(*) FROM public.users u JOIN public.memberships m ON m.user_id=u.id WHERE u.username='owner' AND m.team='pilot' AND m.role='owner'", database=business_database) == '1')
                else:
                    require(database.query('SELECT count(*) FROM public.users', database=business_database) == '0')
                after_backends = capture_application_backends(database, seed, server_scope)
                require(all(item in after_backends for item in application_backends))
                application_backends = after_backends
            require(not (stage / 'private-inputs-observed.json').exists())
        if seed.get('runtime_effects_fixture') and label == 'runtime-owner':
            if not default_stage:
                require(listeners_absent(config), 'product listeners started before runtime prerequisites')
            application_backends = capture_application_backends(database, seed, server_scope)
            if not default_stage:
                write_new(stage / 'runtime-activate.json', {'original_backends_captured': True}, 0o600, seed['uid'], seed['gid'])
            seed['proof_phase'] = label + ':actual-product-runtime-activation'
            if not runtime_refusal:
                if not default_stage:
                    active = wait_for(stage / 'runtime-workers-observed.json', run, 65)
                    require(active == {'fixed_native_runtime_entrypoint_used': True, 'schema_before_workers_verified': True,
                        'actual_product_workers_started': True, 'internal_readiness_observed': True, 'public_activation_verified': False})
                if public_stage:
                    write_new(seal / 'fixture-start-public-runtime.json', {'original_runtime_prerequisites_observed': True})
                    public_services = wait_for(stage / 'public-services.json', run, 40)
                    require(public_services['fixed_production_launcher_used'] is True and public_services['public_activation_verified'] is False)
                    public_births = {}
                    for name in ('web', 'edge'):
                        value = public_services[name];actual = process(value['pid'])
                        require(actual['birth'] == value['birth'] and actual['uid'] == seed['uid'])
                        require(actual['cgroup'] == '0::/system.slice/' + seed['unit'] + '/' + name)
                        public_births[name] = actual
                runtime_observation = probe_native_runtime(seed, config, stage, public=bool(public_stage))
                if default_stage:
                    runtime_observation.update(default_packaged_release_start_verified=True,
                        fixture_runtime_application_substitution=False,
                        independent_original_owner_kernel_sql_readiness_samples=captured['independent_current_samples'])
                require(database.query("SELECT count(*) FROM public.repositories WHERE team='pilot' AND name='native-runtime' AND status='ready'", database=business_database) == '1')
                require(database.query("SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='fixture_shadow'", database=business_database) == '0')
                after_backends = capture_application_backends(database, seed, server_scope)
                require(all(item in after_backends for item in application_backends))
                application_backends = after_backends
        if not stage_refusal:
            seed['proof_phase'] = label + ':inject-original-helper-or-backend-loss'
            if default_stage:
                inject_default_release_loss(seed, stage, captured, record['database_session'], database)
            else:
                inject_loss(fault, captured, record['database_session'], database)
        seed['proof_phase'] = label + ':owner-exit-acknowledgement'
        exited = wait_for(stage / 'owner-exited.json', run, 15)
        require(exited['fixture_signalled_beam'] is False and exited['exit_code'] != 0)
        if default_stage:
            require(exited['public_stop_deferred_until_native_release_exit'] is True)
            runtime_observation['original_permanent_default_release_abort_verified'] = True
        seed['proof_phase'] = label + ':original-owner-sql-kernel-absence'
        until = time.monotonic() + 10
        while not (absent(captured['owner']) and absent(captured['backend']) and database.backend_absent(record['database_session']) and
                   all(absent(item['kernel']) and database.backend_absent(item['session']) for item in application_backends)):
            require(time.monotonic() < until, 'original successor owner/backend not absent')
            time.sleep(.1)
        if seed.get('runtime_effects_fixture') and label == 'runtime-owner':
            require(listeners_absent(config), 'original product listener survived owner failure')
        seed['proof_phase'] = label + ':surviving-descendant-and-sibling'
        if public_stage:
            public_cleanup = wait_for(stage / 'public-quiescent.json', run, 12)
            require(public_cleanup == {'original_native_web_edge_leaves_empty': True,
                'cleanup_actor': 'native-public-runtime', 'retained_responsibility_untouched': True})
            require(all(absent(value) for value in public_births.values()))
            if not default_stage:require(absent(captured['descendant']))
            for name in ('native', 'web', 'edge'):
                group = Path('/sys/fs/cgroup/system.slice') / seed['unit'] / name
                require('populated 0' in (group / 'cgroup.events').read_text())
            with socket.socket() as probe:
                require(probe.connect_ex(('127.0.0.1', 4443)) != 0)
            runtime_observation['fixed_public_runtime_cleanup_verified'] = True
            runtime_observation['captured_web_edge_births_absent'] = True
        else:
            require(not absent(captured['descendant']) and not absent(sentinel))
        seed['proof_phase'] = label + ':retained-record-and-marker-before-quiescence'
        require(fingerprint(captured['retained']) == captured['record_file'])
        require(fingerprint(captured['marker']) == captured['marker_file'])
        write_new(seal / ('fixture-cleanup-' + label + '.json'), {'original_owner_and_backend_absent': True})
        seed['proof_phase'] = label + ':selected-leaf-quiescence'
        quiescent = wait_for(stage / 'quiescent.json', run, 12)
        if public_stage:
            require(quiescent == {'selected_leaf_empty': True, 'cleanup_actor': 'native-public-runtime',
                'fixed_public_runtime_cleanup_verified': True})
        else:
            require(quiescent == {'selected_leaf_empty': True, 'sibling_preserved': True,
                'cleanup_actor': 'fixture-manager', 'product_controller_cleanup_verified': False})
        leaf = Path('/sys/fs/cgroup/system.slice') / seed['unit'] / ('native' if mode == 'runtime' else 'maintenance')
        require('populated 0' in (leaf / 'cgroup.events').read_text())
        if not public_stage:require(not absent(sentinel))
        seed['proof_phase'] = label + ':original-helper-and-descendant-absence'
        until = time.monotonic() + 5
        while not (absent(captured['helper']) and (default_stage or absent(captured['descendant']))):
            require(time.monotonic() < until, 'original successor descendants remain')
            time.sleep(.1)
        write_new(seal / ('fixture-reap-sentinel-' + label + '.json'), {'sibling_preservation_observed': True})
        seed['proof_phase'] = label + ':sibling-reap-acknowledgement'
        wait_for(stage / 'sibling-reaped.json', run, 5)
        if not public_stage:require(absent(sentinel))
        seed['proof_phase'] = label + ':retained-record-and-marker-after-quiescence'
        require(fingerprint(captured['retained']) == captured['record_file'])
        require(fingerprint(captured['marker']) == captured['marker_file'])
        digest = hashlib.sha256(canonical(record)).hexdigest()
        captured_records.append({'sha': digest, 'record': record, 'captured': captured})
        previous_sha = digest
        stages.append({'stage': label, 'mode': mode, 'claim': record['claim'], 'record_sha256': digest,
            'distinct_attached_heartbeat_samples': None if default_stage else attached['distinct_attached_heartbeat_samples'],
            'independent_original_owner_kernel_sql_readiness_samples': captured['independent_current_samples'] if default_stage else None,
            'held_exclusion_observed_before_owner_launch': True, 'original_exclusion_sql_and_kernel_backend_absent': True,
            'actual_protected_handoff_completed': True, 'repeated_assignment_refused_by_actual_endpoint': not default_stage,
            'original_owner_sql_and_kernel_backend_absent': True, 'record_and_marker_retained': True,
            'captured_application_sql_and_kernel_backends_absent': bool(application_backends),
            'actual_product_runtime_workers_executed': bool(seed.get('runtime_effects_fixture') and label == 'runtime-owner' and not runtime_refusal),
            'selected_descendants_quiesced_by_fixture_manager': not public_stage,
            'sibling_preserved_then_exactly_reaped': not public_stage,
            'fixed_public_runtime_cleanup_verified': bool(public_stage)})
        write_new(seal / ('fixture-next-' + label + '.json'), {'old_owner_backend_and_leaves_absent': True})
        if stage_refusal:
            expected_claims = 3 if runtime_refusal else 1
            require(label == ('runtime-owner' if runtime_refusal else 'migration-owner') and len(stages) == expected_claims)
            require(not (stage / 'maintenance-effects-observed.json').exists())
            require(not (stage / 'runtime-workers-observed.json').exists())
            if runtime_refusal:
                require(database.query('SELECT count(*) FROM public.repositories', database=business_database) == '0')
                actual_versions = database.query('SELECT coalesce(string_agg(version::text,\',\' ORDER BY version),\'\') FROM public.schema_migrations', database=business_database)
                require(actual_versions == ','.join(map(str, preserved_lifecycle['target_versions'][:-1])))
            else:
                require(database.query("SELECT to_regclass('public.schema_migrations') IS NULL AND to_regclass('public.users') IS NULL AND to_regclass('public.installation_owner_bootstraps') IS NULL", database=business_database) == 't')
            if seed.get('schema_refusal_fixture'):
                require(database.query('SELECT count(*) FROM public.fixture_unexpected_relation', database=business_database) == '0')
            elif not runtime_refusal:
                require(database.query("SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('public','fixture_shadow')", database=business_database) == '0')
            require(fingerprint(lifecycle_head) == original_head and fingerprint(lifecycle_snapshot) == original_snapshot)
            complete = wait_for(run / 'controller-maintenance-refusal-complete.json', run, 10)
            require(complete == {'claims': expected_claims, 'fixture_did_not_advance_lifecycle': True})
            require(process(manager['pid'])['birth'] == manager['birth'])
            require({path.name for path in (storage / '.gitgood-ownership-v2').iterdir()} == {item['record']['claim'] + '.json' for item in captured_records})
            for index, prior in enumerate(captured_records):
                require(fingerprint(prior['captured']['retained']) == prior['captured']['record_file'])
                retained_marker = prior['captured']['marker'] if index == len(captured_records)-1 else transition / (captured_records[index+1]['record']['claim'] + '.old-marker.json')
                require(fingerprint(retained_marker) == prior['captured']['marker_file'])
            return {'case': seed['case'], 'status': 'passed', 'stages': stages,
                'root_original_controller_scope_observed': True,
                'root_original_lifecycle_history_observed': root_lifecycle_observation is not None,
                'root_original_live_binding_observed': root_live_binding_observation is not None,
                'root_original_controller_request_and_history_lock_observed': root_controller_request_observation is not None,
                'root_foreign_peer_and_wrong_operation_refused': root_controller_request_refusals,
                'root_original_controller_database_exclusion_observed': root_database_exclusion_observation is not None,
                'root_original_database_client_loss_refused': root_database_exclusion_loss_refused,
                'actual_nonempty_schema_refused_without_migrations': bool(seed.get('schema_refusal_fixture')),
                'actual_nested_migration_entry_refused_without_effects': bool(seed.get('inventory_refusal_fixture')),
                'actual_runtime_schema_refused_before_product_workers': runtime_refusal,
                'permanent_maintenance_failure_terminated_original_beam': maintenance_refusal,
                'permanent_runtime_failure_terminated_original_beam': runtime_refusal,
                'running_lifecycle_snapshot_and_head_retained': True,
                'all_original_records_and_marker_inodes_retained': True,
                'business_lifecycle_stages_executed': runtime_refusal, 'native_application_acceptance': False,
                'complete_journey_acceptance': False, 'product_controller_cleanup_verified': False}
    seed['proof_phase'] = 'controller-chain-completion'
    complete = wait_for(run / 'controller-chain-complete.json', run, 10)
    require(complete == {'actual_controller_handoff_completed': True, 'claims': 3, 'same_controller': True,
        'same_boot_and_generation': True, 'business_lifecycle_stages_executed': False})
    require(process(manager['pid'])['birth'] == manager['birth'])
    require(len({item['record']['claim'] for item in captured_records}) == 3)
    require(len({(item['record']['owner']['pid'], item['record']['owner']['birth']) for item in captured_records}) == 3)
    require(len({(item['record']['database_session']['backend_pid'], item['record']['database_session']['backend_birth']) for item in captured_records}) == 3)
    require({path.name for path in (storage / '.gitgood-ownership-v2').iterdir()} == {item['record']['claim'] + '.json' for item in captured_records})
    seed['proof_phase'] = 'complete-chain-retained-records-and-markers'
    for index, item in enumerate(captured_records):
        require(fingerprint(item['captured']['retained']) == item['captured']['record_file'])
        marker = item['captured']['marker'] if index == 2 else transition / (captured_records[index + 1]['record']['claim'] + '.old-marker.json')
        require(fingerprint(marker) == item['captured']['marker_file'])
    seed['proof_phase'] = 'complete-chain-lifecycle-history'
    lifecycle_observation = {}
    if preserved_lifecycle is not None:
        lifecycle_observation = observe_fixture_lifecycle_history(seed, pointer, preserved_lifecycle)
    else:
        require(not (seal / 'lifecycle-worker-admission-v2.json').exists())
        require(not (Path(seed['root']) / 'history/lifecycle-responsibility-v2').exists())
    return {'case': seed['case'],
        'status': 'passed', 'stages': stages,
        'actual_same_boot_same_generation_controller_handoff_verified': True,
        'migration_bootstrap_runtime_modes_observed': True, 'business_lifecycle_stages_executed': bool(seed.get('business_effects_fixture')),
        'complete_business_lifecycle_verified': False,
        'all_original_records_and_marker_inodes_retained': True, 'native_application_acceptance': False,
        'complete_journey_acceptance': False, 'product_controller_cleanup_verified': False,
        'actual_lifecycle_startup_boundary_verified': bool(seed.get('lifecycle_fixture')),
        'root_original_controller_scope_observed': True,
        'root_original_lifecycle_history_observed': root_lifecycle_observation is not None,
        'root_original_live_binding_observed': root_live_binding_observation is not None,
        'root_original_controller_request_and_history_lock_observed': root_controller_request_observation is not None,
        'root_foreign_peer_and_wrong_operation_refused': root_controller_request_refusals,
        'root_original_controller_database_exclusion_observed': root_database_exclusion_observation is not None,
        'root_original_database_client_loss_refused': root_database_exclusion_loss_refused,
        'lifecycle_stage_effect_receipts_are_fixture_metadata': bool(seed.get('lifecycle_fixture')),
        'inspection_and_stage_receipts_are_fixture_metadata': bool(seed.get('lifecycle_fixture') and not seed.get('artifact_stage_fixture')),
        'actual_ordinary_inspection_and_serialized_root_stage_verified': staged_artifact_observation is not None,
        'actual_runtime_from_staged_output_verified': staged_artifact_observation is not None and bool(seed.get('default_release_fixture')),
        **({'artifact_stage_observation':staged_artifact_observation,
            'root_reader_refusal_observation':seed['root_reader_refusal_observation']} if staged_artifact_observation is not None else {}),
        **({'root_stage_profile':seed['root_stage_profile']} if seed.get('root_stage_profile') is not None else {}),
        **({'root_stage_measurements':seed['root_stage_measurements']} if seed.get('root_stage_measurements') is not None else {}),
        **({'root_guard_cpu':seed['root_guard_cpu']} if seed.get('root_guard_cpu') is not None else {}),
        **({'root_guard_sample':seed['root_guard_sample']} if seed.get('root_guard_sample') is not None else {}),
        **({'native_descriptor_comparison':seed['native_descriptor_comparison']} if seed.get('native_descriptor_comparison') is not None else {}),
        'actual_private_input_stream_verified': bool(seed.get('business_inputs_fixture')),
        'actual_migration_and_bootstrap_effects_observed': bool(seed.get('business_effects_fixture')),
        'actual_shadow_namespace_excluded': bool(seed.get('business_effects_fixture')),
        'actual_product_runtime_workers_executed': bool(seed.get('runtime_effects_fixture')),
        **runtime_observation,
        **lifecycle_observation}


def preflight(args):
    require(sys.platform == "linux" and platform.machine() == "x86_64" and os.geteuid() == 0)
    require(sys.implementation.name in {'cpython','pypy'})
    require(os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted")
    require(Path("/proc/1/comm").read_text() == "systemd\n")
    release = Path("/etc/os-release").read_text()
    require('ID=ubuntu\n' in release and 'VERSION_ID="24.04"\n' in release)
    require(command(["/usr/bin/systemctl", "--version"]).startswith(b"systemd 255"))
    require(Path("/sys/fs/cgroup/cgroup.controllers").is_file())
    require(not MODULES.exists() and not MODULES.is_symlink(), "existing native installation is never overwritten")
    require(re.fullmatch(r"[0-9a-f]{40}", args.candidate) is not None)
    for path in [args.workspace, args.release, args.postgres, args.node, args.caddy]:
        require(path.is_absolute() and path == path.resolve(strict=True), "noncanonical runtime input")
    require(args.output.is_absolute() and args.output.parent == args.output.parent.resolve(strict=True))
    workspace = args.workspace.resolve(strict=True)
    git_environment = {**BASE_ENV, "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "safe.directory", "GIT_CONFIG_VALUE_0": str(workspace)}
    require(command(["/usr/bin/git", "-C", str(workspace), "rev-parse", "HEAD"],
                    environment=git_environment).decode().strip() == args.candidate)
    require(command(["/usr/bin/git", "-C", str(workspace), "status", "--porcelain", "--untracked-files=no"],
                    environment=git_environment) == b"", "tracked source must match clean candidate")
    require(args.release.resolve(strict=True) == workspace / "apps/forge/_build/prod/rel/gitgood")
    for source in [args.release, args.postgres, args.caddy]:
        require(source.resolve(strict=True).is_relative_to(workspace))
    require(args.output.resolve().is_relative_to(workspace) and not args.output.exists() and not args.output.is_symlink())
    require(command([str(args.node.resolve(strict=True)), "--version"]).strip() == b"v22.23.3")
    require(command([str((args.postgres / "bin/psql").resolve(strict=True)), "--version"]).strip() == b"psql (PostgreSQL) 18.4")
    require(command([str(args.caddy.resolve(strict=True)), "version"]).startswith(b"v2.11.7"))
    require(Path("/usr/bin/patchelf").is_file())
    extra = [workspace / 'tools/ci' / name for name in ('native-owned-manager.py', 'native-owned-worker.exs', 'native-successor-manager.py')]
    extra += [workspace / 'tools/deployment' / name for name in module_closure(workspace / 'tools/deployment')]
    extra += [workspace / '.gitgood/native-web-product', workspace / 'docs/deployment/Caddyfile.example']
    extra += [workspace/'tools/ci'/name for name in native_path_probe.HELPERS]
    extra += [workspace/'.gitgood/native-metadata-probe'/name for name in ('manifest.json',native_read_probe.metadata.extension_name())]
    total = sum(copy_inventory(path)[1] for path in [args.release, args.postgres, args.node, args.caddy, Path("/usr/bin/git"), *extra])
    require(total <= COPY_LIMIT, "bounded copy preflight")
    # Include the private runtime copy and complete archive/output staging;
    # both the system and each output volume retain the required reserve.
    estimate = total * 4 + 1024**3
    for path in (Path('/'),Path('/opt'),args.output.parent):
        require(shutil.disk_usage(path).free-estimate >= 20*1024**3, "bounded disk preflight")
    return workspace, total


def finalize(receipt, units, output, phase):
    """Cleanup failure is a failed process as well as a failed receipt."""
    stop_errors = []
    for unit in units:
        try:
            command(["/usr/bin/systemctl", "stop", unit], timeout=25)
        except Exception:
            stop_errors.append(unit)
    if stop_errors:
        receipt["status"] = "failed"
        receipt["cleanup_errors"] = stop_errors
    receipt["last_phase"] = phase
    if output is not None:
        write_new(output / "receipt.json", receipt)
    print(json.dumps({"scope": receipt["scope"], "status": receipt["status"], "last_phase": phase,
                      "passed_cases": len(receipt["cases"]), "native_application_acceptance": False}))
    return 0 if receipt["status"] == "passed" else 1


def main(args):
    receipt = {"protocol": 1, "scope": "ownership-maintenance-and-native-runtime-component", "status": "failed", "candidate": args.candidate,
               "native_application_acceptance": False, "complete_journey_acceptance": False,
               "reboot_verified": False, "successor_reconciliation_verified": False,
               "production_deadlines_modified": False, "limits": LIMITS, "cases": []}
    receipt["fixture_file_size_limit_bytes"] = FILE_LIMIT
    phase = "preflight"
    output = None
    units = []
    seed = None
    try:
        workspace, total = preflight(args)
        args.output.mkdir(mode=0o755)
        os.chmod(args.output, 0o755)
        output = args.output
        if sys.implementation.name == 'pypy':
            phase = 'verify-diagnostic-root-runtime'
            receipt['root_runtime_probe'] = root_runtime_probe.observe()
        phase = "secure-disposable-host-opt"
        receipt["hosted_opt_custody"] = harden_hosted_opt()
        phase = "create-protected-runtime-prefix"
        runtime = Path("/opt/gitgood-owned-proof") / str(uuid.uuid4())
        root_directory(runtime.parent)
        runtime.mkdir(mode=0o755)
        for source, name in [(args.release, "release"), (args.postgres, "postgres"), (args.node, "node"), (args.caddy, "caddy"),
                             (Path("/usr/bin/git"), "git"), (workspace / '.gitgood/native-web-product', 'web'),
                             (workspace / 'docs/deployment/Caddyfile.example', 'Caddyfile.example')]:
            phase = "copy-private-" + name
            copy_runtime(source, runtime / name)
        for name in ["native-owned-manager.py", "native-owned-worker.exs", "native-successor-manager.py"]:
            phase = "copy-fixture-" + name.removeprefix("native-owned-").split(".")[0]
            copy_runtime(workspace / "tools/ci" / name, runtime / name)
        phase = 'copy-fresh-native-metadata-diagnostic'
        metadata_directory = runtime/'native-metadata-probe';metadata_directory.mkdir(mode=0o755)
        for name in native_path_probe.HELPERS:
            copy_runtime(workspace/'tools/ci'/name,metadata_directory/name)
        for name in ('manifest.json',native_read_probe.metadata.extension_name()):
            copy_runtime(workspace/'.gitgood/native-metadata-probe'/name,metadata_directory/name)
        phase = "relocate-private-postgresql-client"
        receipt["postgresql_client_relocation"] = relocate_postgresql_client(runtime)
        modules = module_closure(workspace / "tools/deployment")
        root_directory(MODULES.parent)
        MODULES.mkdir(mode=0o755)
        for name in modules:
            copy_runtime(workspace / "tools/deployment" / name, MODULES / name)
        receipt["installed_production_modules"] = {name: digest(MODULES / name) for name in modules}
        receipt["copied_runtime_bytes"] = total
        sys.path.insert(0, str(MODULES))
        from native_generation_admission_entry import trusted_modules
        trusted_modules(MODULES)
        phase = "capture-real-postgresql-host-scope"
        database = Database(runtime / "postgres/bin/psql")
        require(database.query("SHOW server_version") == "18.4")
        require(database.query("SELECT rolsuper FROM pg_roles WHERE rolname=current_user") == "t")
        data = Path(database.query("SHOW data_directory")).resolve(strict=True)
        postmaster = process(int((data / "postmaster.pid").read_text().splitlines()[0]))
        require(postmaster["uid"] > 0 and postmaster["state"] not in ["Z", "X"])
        server_scope = {"boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                        "postgres_uid": postmaster["uid"],
                        "pid_namespace": os.readlink(f"/proc/{postmaster['pid']}/ns/pid"),
                        "time_namespace": os.readlink(f"/proc/{postmaster['pid']}/ns/time")}
        require(server_scope["pid_namespace"] == os.readlink("/proc/1/ns/pid") == os.readlink("/proc/self/ns/pid"))
        require(server_scope["time_namespace"] == os.readlink("/proc/self/ns/time"))
        require([line.split() for line in Path("/proc/self/timens_offsets").read_text().splitlines()] == [["monotonic", "0", "0"], ["boottime", "0", "0"]])
        for label in CASES:
            phase = label + ":allocate"
            seed, config, password = allocate_case(label, runtime, database, args.candidate)
            units.append(seed["unit"])
            phase = label + ":claim-and-loss"
            result = run_case(seed, config, password, database, server_scope)
            phase = label + ":stop-owned-unit"
            command(["/usr/bin/systemctl", "stop", seed["unit"]], timeout=25)
            group = Path("/sys/fs/cgroup/system.slice") / seed["unit"]
            require(not group.exists() or "populated 0" in (group / "cgroup.events").read_text())
            result["owned_unit_stopped"] = True
            receipt["cases"].append(result)
        phase = 'same-controller-successor:allocate'
        seed, config, password = allocate_case('same-controller-successor', runtime, database, args.candidate, controller=True)
        units.append(seed['unit'])
        phase = 'same-controller-successor:protected-handoffs'
        result = run_successor_case(seed, config, password, database, server_scope)
        command(['/usr/bin/systemctl', 'stop', seed['unit']], timeout=25)
        group = Path('/sys/fs/cgroup/system.slice') / seed['unit']
        require(not group.exists() or 'populated 0' in (group / 'cgroup.events').read_text())
        result['owned_unit_stopped'] = True
        receipt['cases'].append(result)
        receipt['same_boot_same_generation_successor_handoff_verified'] = True
        phase = 'lifecycle-startup-boundary:allocate'
        seed, config, password = allocate_case('lifecycle-startup-boundary', runtime, database,
            args.candidate, controller=True, lifecycle=True)
        units.append(seed['unit'])
        phase = 'lifecycle-startup-boundary:protected-handoffs'
        result = run_successor_case(seed, config, password, database, server_scope)
        command(['/usr/bin/systemctl', 'stop', seed['unit']], timeout=25)
        group = Path('/sys/fs/cgroup/system.slice') / seed['unit']
        require(not group.exists(), 'owned lifecycle fixture unit remained after stop')
        receipt['cases'].append({**result, 'owned_unit_stopped': True})
        receipt['lifecycle_startup_boundary_verified'] = True
        phase = 'private-business-inputs-boundary:allocate'
        seed, config, password = allocate_case('private-business-inputs-boundary', runtime, database,
            args.candidate, controller=True, lifecycle=True, business_inputs=True)
        units.append(seed['unit'])
        phase = 'private-business-inputs-boundary:attached-inputs-and-loss'
        result = run_successor_case(seed, config, password, database, server_scope)
        command(['/usr/bin/systemctl', 'stop', seed['unit']], timeout=25)
        require(not (Path('/sys/fs/cgroup/system.slice') / seed['unit']).exists())
        receipt['cases'].append({**result, 'owned_unit_stopped': True})
        receipt['private_business_input_stream_verified'] = True
        phase = 'maintenance-effects-boundary:allocate'
        seed, config, password = allocate_case('maintenance-effects-boundary', runtime, database,
            args.candidate, controller=True, lifecycle=True, business_inputs=True, business_effects=True)
        units.append(seed['unit'])
        phase = 'maintenance-effects-boundary:fixed-effects-and-loss'
        result = run_successor_case(seed, config, password, database, server_scope)
        command(['/usr/bin/systemctl', 'stop', seed['unit']], timeout=25)
        require(not (Path('/sys/fs/cgroup/system.slice') / seed['unit']).exists())
        receipt['cases'].append({**result, 'owned_unit_stopped': True})
        receipt['fixed_migration_and_bootstrap_effects_observed'] = True
        phase = 'native-runtime-effects:allocate'
        seed, config, password = allocate_case('native-runtime-effects', runtime, database,
            args.candidate, controller=True, lifecycle=True, business_inputs=True, business_effects=True, runtime_effects=True)
        units.append(seed['unit'])
        phase = 'native-runtime-effects:product-workers-internal-api-git-and-loss'
        result = run_successor_case(seed, config, password, database, server_scope)
        command(['/usr/bin/systemctl', 'stop', seed['unit']], timeout=25)
        require(not (Path('/sys/fs/cgroup/system.slice') / seed['unit']).exists())
        receipt['cases'].append({**result, 'owned_unit_stopped': True})
        receipt['fixed_native_product_runtime_verified'] = True
        phase = 'native-public-runtime:allocate'
        seed, config, password = allocate_case('native-public-runtime', runtime, database,
            args.candidate, controller=True, lifecycle=True, business_inputs=True, business_effects=True,
            runtime_effects=True, public_runtime=True)
        units.append(seed['unit'])
        phase = 'native-public-runtime:tls-frontend-git-and-controller-loss-cleanup'
        result = run_successor_case(seed, config, password, database, server_scope)
        command(['/usr/bin/systemctl', 'stop', seed['unit']], timeout=25)
        require(not (Path('/sys/fs/cgroup/system.slice') / seed['unit']).exists())
        receipt['cases'].append({**result, 'owned_unit_stopped': True})
        receipt['fixed_public_runtime_tls_frontend_and_loss_verified'] = True
        phase = 'native-default-release:allocate'
        seed, config, password = allocate_case('native-default-release', runtime, database,
            args.candidate, controller=True, lifecycle=True, business_inputs=True, business_effects=True,
            runtime_effects=True, public_runtime=True, default_release=True, artifact_stage=True)
        units.append(seed['unit'])
        phase = 'native-default-release:ordinary-boot-public-function-and-original-loss'
        result = run_successor_case(seed, config, password, database, server_scope)
        command(['/usr/bin/systemctl', 'stop', seed['unit']], timeout=25)
        require(not (Path('/sys/fs/cgroup/system.slice') / seed['unit']).exists())
        receipt['cases'].append({**result, 'owned_unit_stopped': True})
        receipt['actual_default_packaged_release_start_verified'] = True
        phase = 'native-runtime-schema-refusal:allocate'
        seed, config, password = allocate_case('native-runtime-schema-refusal', runtime, database,
            args.candidate, controller=True, lifecycle=True, business_inputs=True, business_effects=True, runtime_effects=True, runtime_schema_refusal=True)
        units.append(seed['unit'])
        phase = 'native-runtime-schema-refusal:before-product-workers'
        result = run_successor_case(seed, config, password, database, server_scope)
        command(['/usr/bin/systemctl', 'stop', seed['unit']], timeout=25)
        require(not (Path('/sys/fs/cgroup/system.slice') / seed['unit']).exists())
        receipt['cases'].append({**result, 'owned_unit_stopped': True})
        receipt['actual_runtime_schema_refusal_verified'] = True
        phase = 'maintenance-schema-refusal:allocate'
        seed, config, password = allocate_case('maintenance-schema-refusal', runtime, database,
            args.candidate, controller=True, lifecycle=True, business_inputs=True, business_effects=True, schema_refusal=True)
        units.append(seed['unit'])
        phase = 'maintenance-schema-refusal:fixed-refusal-and-original-absence'
        result = run_successor_case(seed, config, password, database, server_scope)
        command(['/usr/bin/systemctl', 'stop', seed['unit']], timeout=25)
        require(not (Path('/sys/fs/cgroup/system.slice') / seed['unit']).exists())
        receipt['cases'].append({**result, 'owned_unit_stopped': True})
        receipt['actual_nonempty_schema_refusal_verified'] = True
        phase = 'maintenance-inventory-refusal:inject-owned-nested-fixture-file'
        migration_directories = list((runtime / 'release/lib').glob('gitgood-*/priv/repo/migrations'))
        require(len(migration_directories) == 1)
        nested = migration_directories[0] / 'fixture-nested'
        nested.mkdir(mode=0o755)
        write_new(nested / '99999999999999_fixture_nested_effect.exs',
            b'defmodule Gitgood.Repo.Migrations.FixtureNestedEffect do\n  use Ecto.Migration\n  def change, do: create(table(:fixture_nested_effect))\nend\n')
        phase = 'maintenance-inventory-refusal:allocate'
        seed, config, password = allocate_case('maintenance-inventory-refusal', runtime, database,
            args.candidate, controller=True, lifecycle=True, business_inputs=True, business_effects=True, inventory_refusal=True)
        units.append(seed['unit'])
        phase = 'maintenance-inventory-refusal:fixed-refusal-and-original-absence'
        result = run_successor_case(seed, config, password, database, server_scope)
        command(['/usr/bin/systemctl', 'stop', seed['unit']], timeout=25)
        require(not (Path('/sys/fs/cgroup/system.slice') / seed['unit']).exists())
        receipt['cases'].append({**result, 'owned_unit_stopped': True})
        receipt['actual_nested_migration_entry_refusal_verified'] = True
        require(all(case['root_original_controller_scope_observed'] is True for case in receipt['cases'][3:]))
        receipt['root_original_controller_scope_observation_verified'] = True
        require(all(case['root_original_lifecycle_history_observed'] is True for case in receipt['cases'][4:]))
        require(receipt['cases'][3]['root_original_lifecycle_history_observed'] is False)
        receipt['root_original_lifecycle_history_observation_verified'] = True
        require(all(case['root_original_live_binding_observed'] is True for case in receipt['cases'][4:]))
        require(receipt['cases'][3]['root_original_live_binding_observed'] is False)
        receipt['root_original_live_binding_observation_verified'] = True
        require(all(case['root_original_controller_request_and_history_lock_observed'] is True for case in receipt['cases'][4:]))
        require(receipt['cases'][3]['root_original_controller_request_and_history_lock_observed'] is False)
        receipt['root_original_controller_request_and_history_lock_verified'] = True
        require(all(case['root_foreign_peer_and_wrong_operation_refused'] is True for case in receipt['cases'][4:]))
        require(receipt['cases'][3]['root_foreign_peer_and_wrong_operation_refused'] is False)
        receipt['root_foreign_peer_and_wrong_operation_refusal_verified'] = True
        require(all(case['root_original_controller_database_exclusion_observed'] is True for case in receipt['cases'][4:]))
        require(all(case['root_original_database_client_loss_refused'] is True for case in receipt['cases'][4:]))
        require(receipt['cases'][3]['root_original_controller_database_exclusion_observed'] is False)
        require(receipt['cases'][3]['root_original_database_client_loss_refused'] is False)
        receipt['root_original_controller_database_exclusion_and_loss_verified'] = True
        receipt["status"] = "passed"
        phase = "complete"
    except Exception as error:
        receipt["failure"] = {"phase": phase, "error_type": type(error).__name__,
                              "check_site": failure_check_site(error)}
        if seed is not None:
            receipt["failure"]["component_phase"] = seed.get("proof_phase", "allocation")
            receipt["failure"]["startup"] = case_startup_diagnostics(seed)
            if seed.get('artifact_stage_started') is not None:
                from native_root_artifact_dispatch import failure_observation
                detail = {'chain':failure_observation(error),
                    'elapsed_ms':min(1200000,max(0,int((time.monotonic()-seed['artifact_stage_started'])*1000)))}
                observed = artifact_failure(detail)
                if observed is not None:receipt['failure']['artifact_failure'] = observed
            if seed.get('root_reader_refusal_observation') is not None:
                receipt['failure']['root_reader_refusal_observation'] = seed['root_reader_refusal_observation']
            if seed.get('root_stage_profile') is not None:
                receipt['failure']['root_stage_profile'] = seed['root_stage_profile']
            if seed.get('root_stage_measurements') is not None:
                receipt['failure']['root_stage_measurements'] = seed['root_stage_measurements']
            if seed.get('root_guard_cpu') is not None:
                receipt['failure']['root_guard_cpu'] = seed['root_guard_cpu']
            if seed.get('root_guard_sample') is not None:
                receipt['failure']['root_guard_sample'] = seed['root_guard_sample']
            if seed.get('native_descriptor_comparison') is not None:
                receipt['failure']['native_descriptor_comparison'] = seed['native_descriptor_comparison']
            if seed.get('root_stage_refusal') is not None:
                receipt['failure']['root_stage_refusal'] = seed['root_stage_refusal']
            if seed.get('archive_member_metrics') is not None:
                receipt['failure']['archive_member_metrics'] = seed['archive_member_metrics']
            failed = Path(seed["run"]) / "manager-failed.json"
            if failed.exists():
                detail = read_json(failed, 8192)
                observed_manager = manager_failure(detail)
                if observed_manager is not None:receipt["failure"]["manager"] = observed_manager
        # No exception string, stack, configuration, private logs, SQL or secret
        # environment is written into the publishable receipt.
    finally:
        result = finalize(receipt, units, output, phase)
    return result


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["workspace", "release", "postgres", "node", "caddy", "output"]:
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--candidate", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main(arguments()))
