#!/usr/bin/env python3
"""Bounded, disposable GitHub Ubuntu 24.04 ownership component proof.

Run as root only on a fresh GitHub-hosted runner after building the clean release
and pinned runtimes. Never enrolls/activates a product, repairs prior ownership,
starts a VM, or removes a retained marker. See native-hosted-ownership.md.
"""
import argparse
import ast
import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import time
import uuid

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
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(descriptor, "wb") as target:
        target.write(raw)
        target.flush()
        os.fsync(target.fileno())
        os.fchmod(target.fileno(), mode)
        os.fchown(target.fileno(), uid, gid)


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

    def query(self, sql, *, database="postgres", role=None, password=None):
        environment = {**self.environment, "PGDATABASE": database}
        if role:
            environment.update(PGUSER=role, PGPASSWORD=password)
        return command([self.psql, "-X", "-A", "-t", "-q", "-v", "ON_ERROR_STOP=1", "--file=-"],
                       environment=environment, input_bytes=sql.encode(), timeout=12).decode().strip()

    def predicate(self, session):
        require(type(session["backend_pid"]) is int and 1 < session["backend_pid"] < 2**31)
        require(re.fullmatch(r"[1-9][0-9]{0,19}", session["backend_birth"]) is not None)
        return (f"pid={session['backend_pid']} AND "
                f"floor(extract(epoch FROM backend_start)*1000000)::bigint={session['backend_birth']}")

    def backend_absent(self, session):
        return self.query("SELECT count(*) FROM pg_stat_activity WHERE " + self.predicate(session)) == "0"


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


def allocate_case(label, runtime, database, candidate):
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
    unit = unit_text(seed, runtime / "native-owned-manager.py")
    seed["unit_sha256"] = hashlib.sha256(unit).hexdigest()
    write_new(Path("/etc/systemd/system") / seed["unit"], unit)
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


def capture_attachment(seed, attached, database):
    from native_ownership_records import validate_record
    record = attached["record"]
    validate_record(record)
    require(record["installation"] == seed["installation"] and record["operation"] == seed["ownership_operation"])
    require(record["candidate"] == seed["candidate"] and record["mode"] == "runtime")
    require(attached["distinct_attached_heartbeat_samples"] >= 5)
    require(attached["beam_pid"] == record["owner"]["pid"])
    owner = process(attached["beam_pid"])
    helper = process(attached["helper_pid"])
    descendant = process(attached["descendant_pid"])
    group = "0::/system.slice/" + seed["unit"] + "/native"
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
    retained = storage / ".gitgood-ownership-v2" / (seed["ownership_operation"] + ".json")
    marker = storage / ".gitgood-runtime-v2.json"
    require(read_json(retained) == record)
    require(read_json(marker)["record_sha256"] == hashlib.sha256(canonical(record)).hexdigest())
    return {"owner": owner, "helper": helper, "descendant": descendant, "backend": backend,
            "retained": retained, "marker": marker, "record_file": fingerprint(retained), "marker_file": fingerprint(marker)}


def inject_loss(label, captured, session, database):
    if label == "helper-loss":
        helper = captured["helper"]
        descriptor = os.pidfd_open(helper["pid"], 0)
        try:
            current = process(helper["pid"])
            require(all(current[name] == helper[name] for name in ["pid", "birth", "uid", "parent", "cgroup"]))
            require(current["state"] not in ["Z", "X"])
            signal.pidfd_send_signal(descriptor, signal.SIGKILL)
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


def preflight(args):
    require(sys.platform == "linux" and platform.machine() == "x86_64" and os.geteuid() == 0)
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
    total = sum(copy_inventory(path)[1] for path in [args.release, args.postgres, args.node, args.caddy, Path("/usr/bin/git")])
    require(total <= COPY_LIMIT and shutil.disk_usage("/opt").free >= total + 1024**3, "bounded disk preflight")
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
    receipt = {"protocol": 1, "scope": "publication-only-component", "status": "failed", "candidate": args.candidate,
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
        phase = "secure-disposable-host-opt"
        receipt["hosted_opt_custody"] = harden_hosted_opt()
        phase = "create-protected-runtime-prefix"
        runtime = Path("/opt/gitgood-owned-proof") / str(uuid.uuid4())
        root_directory(runtime.parent)
        runtime.mkdir(mode=0o755)
        for source, name in [(args.release, "release"), (args.postgres, "postgres"), (args.node, "node"), (args.caddy, "caddy"),
                             (Path("/usr/bin/git"), "git")]:
            phase = "copy-private-" + name
            copy_runtime(source, runtime / name)
        for name in ["native-owned-manager.py", "native-owned-worker.exs"]:
            phase = "copy-fixture-" + name.removeprefix("native-owned-").split(".")[0]
            copy_runtime(workspace / "tools/ci" / name, runtime / name)
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
        receipt["status"] = "passed"
        phase = "complete"
    except Exception as error:
        receipt["failure"] = {"phase": phase, "error_type": type(error).__name__}
        if seed is not None:
            receipt["failure"]["component_phase"] = seed.get("proof_phase", "allocation")
            receipt["failure"]["startup"] = startup_diagnostics(Path(seed["run"]))
            failed = Path(seed["run"]) / "manager-failed.json"
            if failed.exists():
                detail = read_json(failed, 1024)
                if (set(detail) == {"phase", "error_type"} and
                        all(isinstance(value, str) and re.fullmatch(r"[a-zA-Z-]{1,64}", value) for value in detail.values())):
                    receipt["failure"]["manager"] = detail
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
