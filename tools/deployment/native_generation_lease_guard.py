"""Poisoning read-only guard; database exclusion stays on the held app session."""
from pathlib import Path
import copy
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
from native_lifecycle_business_inputs import _project, LifecycleBusinessInputsRefused


class GenerationLeaseGuardRefused(Exception):
    pass


def _fingerprint_path(raw):
    path = Path(raw)
    require(path.is_absolute() and path.anchor == '/' and '..' not in path.parts and '\0' not in str(path))
    return path


def persistent_fingerprint(binding):
    """Metadata of previously content-validated files; never observes a database."""
    return _PersistentFingerprintPlan(binding).read()


class _PersistentFingerprintPlan:
    """Fixed path structure only; every read observes all filesystem metadata anew.

    A retaining caller must separately check its original sealed binding before
    reading. No filesystem observation, file content or returned result is held.
    """
    def __init__(self, binding):
        self.uid = binding['account']['uid']
        resources = binding['resources']
        require(set(resources) == {'root', 'configuration', 'storage', 'ssh-host', 'history', 'staging'})
        root = _fingerprint_path(resources['root']['path'])
        self.entries = ((root, frozenset(resources) - {'root'}),
            (root/'configuration', frozenset(binding['configuration'])),
            (root/'ssh-host', frozenset(binding['ssh_host_keys'])))
        parents = set(root.parents);recorded_parents = set();directories = []
        for item in resources.values():
            path = _fingerprint_path(item['path'])
            directories.append((path, str(path), item['device'], item['inode'], item['uid']))
            parents.update(path.parents)
        self.directories = tuple(directories)
        files = [(item, self.uid, False) for name in ['configuration', 'ssh_host_keys'] for item in binding[name].values()]
        files += [(item, 0, True) for item in binding['executables'].values()]
        files.append((binding['host']['os_release'], 0, False))
        self.machine = _fingerprint_path('/etc/machine-id');parents.update(self.machine.parents)
        file_paths = []
        for item, owner, executable in files:
            path = _fingerprint_path(item['path'])
            file_paths.append((path, str(path), owner, executable, item['bytes'], item['device'], item['inode']))
            parents.update(path.parents);recorded_parents.update(path.parents)
        self.files = tuple(file_paths)
        root_ancestors = {root, *root.parents};private = {root/'configuration', root/'ssh-host'}
        self.parents = tuple((parent, str(parent), parent in recorded_parents and
            (parent in root_ancestors or parent not in private), parent == root) for parent in parents)

    def read(self):
        uid = self.uid;result = {}
        for path, names in self.entries:
            require({p.name for p in path.iterdir()} == names)
        for path, key, device, inode, owner in self.directories:
            info = path.lstat()
            require(stat.S_ISDIR(info.st_mode))
            require(info.st_uid == uid and stat.S_IMODE(info.st_mode) == 0o700)
            require((info.st_dev, info.st_ino, info.st_uid) == (device, inode, owner))
            result[key] = (info.st_dev, info.st_ino, info.st_uid, info.st_mode)
        # machine-id's content was checked in the full persistent observation.
        info = self.machine.lstat()
        require(stat.S_ISREG(info.st_mode))
        require(info.st_uid == 0 and info.st_nlink == 1 and not info.st_mode & 0o022)
        result[str(self.machine)] = tuple(getattr(info, field) for field in
            ['st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_uid','st_mode','st_nlink'])
        for path, key, owner, executable, size, device, inode in self.files:
            info = path.lstat()
            require(stat.S_ISREG(info.st_mode))
            require(info.st_uid == owner and info.st_nlink == 1 and info.st_size == size)
            require((info.st_dev, info.st_ino) == (device, inode))
            require(not info.st_mode & 0o022 if owner == 0 else stat.S_IMODE(info.st_mode) == 0o600)
            require(not executable or info.st_mode & 0o111)
            result[key] = tuple(getattr(info, field) for field in
                ['st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_uid','st_mode','st_nlink'])
        for parent, key, recorded, is_root in self.parents:
            value = parent.lstat();require(stat.S_ISDIR(value.st_mode))
            if recorded:
                if is_root:
                    require(value.st_uid == uid and stat.S_IMODE(value.st_mode) == 0o700)
                else:
                    require(value.st_uid == 0 and not value.st_mode & 0o022)
                result[key] = (value.st_dev, value.st_ino, value.st_uid, value.st_mode)
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

    def private_business_inputs(self, action):
        """Private fixed-action data, bracketed by the original poisoned guard."""
        try:
            require(type(action) is str and action in {'migrate', 'bootstrap'})
            before = self.check()
            require(self.worker == 'maintenance' and 'lifecycle' in self.snapshot)
            require(self.snapshot['lifecycle']['stage'] == action and
                    self.snapshot['lifecycle']['recorded_status'] == 'running')
            inputs = self.reader.inputs
            metadata = inputs.check()
            observed = self.snapshot['lifecycle']
            require(metadata['request_sha256'] == observed['request_sha256'] and
                    metadata['candidate'] == observed['candidate'] and
                    metadata['request']['operation'] == observed['operation'])
            result = _project(inputs._private_payloads(), observed, action, self.reader.installation)
            require(self.check() == before)
            return result
        except Exception:
            self.close()
            raise LifecycleBusinessInputsRefused('Native lifecycle business inputs unavailable') from None

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
            if 'lifecycle' in snapshot:
                admitted['lifecycle_observation'] = copy.deepcopy(snapshot['lifecycle'])
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
