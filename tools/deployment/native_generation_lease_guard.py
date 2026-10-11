"""Poisoning read-only guard; database exclusion stays on the held app session."""
from pathlib import Path
import stat
import subprocess

from generation_publication import require, sha, PublicationRefused
from native_durable_binding import persistent_identity, BindingRefused, _CapturedExecutableDigests
from native_durable_database import DatabaseRefused
from native_generation_reader import GenerationAdmissionRefused, _ReadOnlyCustody
from native_service_scope import ServiceRefused, _observe_service, _CapturedRootFiles
from native_worker_scope import observe_worker, _ancestry
from generation_custody import CustodyRefused
from resource_generations import GenerationRefused


class GenerationLeaseGuardRefused(Exception):
    pass


def persistent_fingerprint(binding):
    """Metadata of previously content-validated files; never observes a database."""
    uid = binding['account']['uid']
    resources = binding['resources']
    require(set(resources) == {'root', 'configuration', 'storage', 'ssh-host', 'history', 'staging'})
    root = Path(resources['root']['path'])
    require({p.name for p in root.iterdir()} == set(resources) - {'root'})
    require({p.name for p in (root/'configuration').iterdir()} == set(binding['configuration']))
    require({p.name for p in (root/'ssh-host').iterdir()} == set(binding['ssh_host_keys']))
    result = {}
    for item in resources.values():
        path = Path(item['path']); info = path.lstat()
        require(path.resolve(strict=True) == path and stat.S_ISDIR(info.st_mode))
        require(info.st_uid == uid and stat.S_IMODE(info.st_mode) == 0o700)
        require((info.st_dev, info.st_ino, info.st_uid) == (item['device'], item['inode'], item['uid']))
        result[str(path)] = (info.st_dev, info.st_ino, info.st_uid, info.st_mode)
    files = [(item, uid, False) for name in ['configuration', 'ssh_host_keys'] for item in binding[name].values()]
    files += [(item, 0, True) for item in binding['executables'].values()]
    files.append((binding['host']['os_release'], 0, False))
    # machine-id's content was checked in the full persistent observation.
    machine = Path('/etc/machine-id'); info = machine.lstat()
    require(machine.resolve(strict=True) == machine and stat.S_ISREG(info.st_mode))
    require(info.st_uid == 0 and info.st_nlink == 1 and not info.st_mode & 0o022)
    result[str(machine)] = tuple(getattr(info, field) for field in
                               ['st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_uid','st_mode','st_nlink'])
    parents = set()
    for item, owner, executable in files:
        path = Path(item['path']); info = path.lstat()
        require(path.resolve(strict=True) == path and stat.S_ISREG(info.st_mode))
        require(info.st_uid == owner and info.st_nlink == 1 and info.st_size == item['bytes'])
        require((info.st_dev, info.st_ino) == (item['device'], item['inode']))
        require(not info.st_mode & 0o022 if owner == 0 else stat.S_IMODE(info.st_mode) == 0o600)
        require(not executable or info.st_mode & 0o111)
        result[str(path)] = tuple(getattr(info, field) for field in
                                 ['st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_uid','st_mode','st_nlink'])
        parents.update(path.parents)
    for parent in parents:
        if parent in [root, *root.parents] or parent not in [root/'configuration', root/'ssh-host']:
            value = parent.lstat()
            # Every ancestor is inspected with lstat; file canonicalization and
            # both full fingerprints also bracket these directory identities.
            require(stat.S_ISDIR(value.st_mode))
            if parent == root:
                require(value.st_uid == uid and stat.S_IMODE(value.st_mode) == 0o700)
            else:
                require(value.st_uid == 0 and not value.st_mode & 0o022)
            result[str(parent)] = (value.st_dev, value.st_ino, value.st_uid, value.st_mode)
    return result


class NativeGenerationLeaseGuard:
    """A single capture followed by checks; any refusal prevents future reuse."""
    def __init__(self, reader, *, worker, owner_pid):
        require(type(worker) is str and worker in {'native','maintenance'})
        require(type(owner_pid) is int and 1 < owner_pid < 2**31)
        require(getattr(reader, 'worker', worker) == worker)
        self.reader = reader
        self.worker, self.owner_pid = worker, owner_pid
        self.started = self.usable = False
        self.root_files = _CapturedRootFiles()
        self.executable_files = _CapturedExecutableDigests(reader.executables)

    def close(self):
        self.usable = False
        self.root_files.close()
        self.executable_files.close()
        self.reader.custody.__exit__(None, None, None)
        self.reader.close()

    def _current_worker(self):
        # The two observations in check bracket file custody and ancestry.
        # Calling observe_worker twice would perform four service observations.
        scope = _observe_service(self.reader.installation, self.reader.unit,
                                 **self.reader.options, caller_group=self.worker, _root_files=self.root_files)
        require(self.owner_pid != scope['manager']['pid'])
        chain = _ancestry(self.owner_pid, scope, self.worker)
        return {'scope':scope, 'owner':chain[-1], 'worker':self.worker}, chain

    def capture(self):
        try:
            require(not self.started)
            self.started = True
            owner = observe_worker(self.reader.installation, self.reader.unit,
                                   worker=self.worker, owner_pid=self.owner_pid, **self.reader.options,
                                   _root_files=self.root_files)
            observed = {'scope':owner['service_scope'], 'owner':owner['owner'], 'worker':owner['worker']}
            original = self.reader.custody
            self.reader.custody = _ReadOnlyCustody(self.reader.directory, self.reader.installation,
                                                  original.identity, original.expected_lock_identity)
            # Retain only a read-only descriptor; taking the controller's lock
            # would deadlock startup and is expressly prohibited.
            self.reader.custody.__enter__()
            snapshot = self.reader._snapshot(observed['scope'])
            before = persistent_fingerprint(snapshot['binding'])
            binding = persistent_identity(self.reader.root, observed['scope'], self.reader.executables,
                                          _executable_files=self.executable_files)
            require(binding == snapshot['binding'] and sha(binding) == self.reader.expected)
            require(persistent_identity(self.reader.root, observed['scope'], self.reader.executables,
                                        _executable_files=self.executable_files) == binding)
            require(persistent_fingerprint(snapshot['binding']) == before)
            require(observe_worker(self.reader.installation, self.reader.unit,
                                   worker=self.worker, owner_pid=self.owner_pid, **self.reader.options,
                                   _root_files=self.root_files) == owner)
            require(self.reader._snapshot(observed['scope']) == snapshot)
            self.reader._check()
            self.root_files.freeze()
            self.executable_files.freeze()
            admitted = {'published_generation_admitted':True, 'writer_exclusion_established':False,
                        'installation_readiness_established':False, 'lifecycle_responsibility_admitted':False,
                        'pointer':snapshot['pointer'], 'binding_sha256':self.reader.expected,
                        'worker_observation':owner}
            self.observed, self.snapshot, self.files = observed, snapshot, before
            self.usable = True
            return {'admission':admitted, 'scope_sha256':sha(observed),
                    'history_sha256':sha(snapshot), 'persistent_files_sha256':sha(before)}
        except (PublicationRefused, GenerationAdmissionRefused, BindingRefused, DatabaseRefused,
                ServiceRefused, CustodyRefused, GenerationRefused, OSError, ValueError,
                TypeError, KeyError, UnicodeError, RecursionError, subprocess.SubprocessError):
            self.close()
            raise GenerationLeaseGuardRefused('Native generation lease guard unavailable') from None

    def check(self):
        try:
            require(self.usable)
            observed, chain = self._current_worker()
            require(observed == self.observed)
            # Private content and the database were observed twice during capture;
            # Root binary hashes remain bound to unchanged metadata. Complete names,
            # inode, size, mode, link count and nanosecond ctime/mtime now bind it.
            # Ordinary callers cannot restore ctime after an in-place edit.
            require(self.reader._fingerprint() == self.snapshot['files'])
            require(persistent_fingerprint(self.snapshot['binding']) == self.files)
            current, current_chain = self._current_worker()
            require(current == observed and current_chain == chain)
            require(self.reader._fingerprint() == self.snapshot['files'])
            require(persistent_fingerprint(self.snapshot['binding']) == self.files)
            return {'current':True, 'scope_sha256':sha(self.observed),
                    'history_sha256':sha(self.snapshot), 'persistent_files_sha256':sha(self.files)}
        except (PublicationRefused, GenerationAdmissionRefused, BindingRefused, DatabaseRefused, ServiceRefused,
                CustodyRefused, GenerationRefused, OSError, ValueError, TypeError,
                KeyError, UnicodeError, RecursionError, subprocess.SubprocessError):
            self.close()
            raise GenerationLeaseGuardRefused('Native generation lease guard lost') from None
