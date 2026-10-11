"""Protected original protocol-2 inputs; no lifecycle lock, generation or effects."""
import hashlib
import json
import os
from pathlib import Path
import stat

from native_command_wire import decode_command
from native_controller_scope import NativeControllerScope, private_directory
from native_service_scope import _CapturedRootFiles, root_file
from resource_generations import canonical


class OperationInputsRefused(Exception):
    pass


def require(value):
    if not value:
        raise OperationInputsRefused('Native operation inputs unavailable or changed')


# These are distinct fresh protocol-2 input formats. They do not adopt the
# existing protocol-1 enrollment/upgrade journals or confer stage admission.
POLICIES = {
    'native_initial_enrollment': {
        'actions': frozenset({'enroll', 'enroll-resume'}),
        'files': {'request.json': 16384, 'allocation.json': 131072, 'inputs.json': 16384}},
    'native_upgrade_execution': {
        'actions': frozenset({'upgrade', 'upgrade-recover', 'upgrade-resume'}),
        'files': {'request.json': 16384, 'intent.json': 16384, 'inventory.json': 131072,
                  'plan.json': 16384}},
}
FILE_FIELDS = ('device', 'inode', 'bytes', 'uid', 'gid', 'mode', 'links', 'mtime_ns', 'ctime_ns')


def unique(pairs):
    value = {}
    for name, item in pairs:
        require(name not in value)
        value[name] = item
    return value


def document(raw):
    value = json.loads(raw, object_pairs_hook=unique)
    require(type(value) is dict and raw == canonical(value))
    return value


def parse_seal(raw, command, uid, gid):
    """Closed format check only; caller maps cannot establish Root custody."""
    value = document(raw)
    require(set(value) == {'protocol', 'kind', 'installation', 'operation', 'purpose',
                          'durable_binding_sha256', 'uid', 'gid', 'directory_identity', 'files'})
    require(type(value['protocol']) is int and value['protocol'] == 2)
    require(value['kind'] == 'native_operation_inputs_seal')
    require(value['installation'] == command['installation'] and value['operation'] == command['operation'])
    require(type(value['purpose']) is str and value['purpose'] in POLICIES)
    policy = POLICIES[value['purpose']]
    require(command['action'] in policy['actions'])
    require(type(uid) is int and type(gid) is int and uid > 0 and gid > 0)
    require(type(value['uid']) is int and value['uid'] == uid)
    require(type(value['gid']) is int and value['gid'] == gid)
    require(type(value['durable_binding_sha256']) is str and len(value['durable_binding_sha256']) == 64)
    require(all(char in '0123456789abcdef' for char in value['durable_binding_sha256']))
    identity = value['directory_identity']
    require(type(identity) is dict and set(identity) == {'device', 'inode', 'uid'})
    require(all(type(item) is int and 0 < item < 2**64 for item in identity.values()))
    require(identity['uid'] == uid)
    files = value['files']
    require(type(files) is dict and set(files) == set(policy['files']))
    for name, recorded in files.items():
        require(type(recorded) is dict and set(recorded) == set(FILE_FIELDS) | {'sha256'})
        require(type(recorded['bytes']) is int and 0 < recorded['bytes'] <= policy['files'][name])
        for field in ['device', 'inode']:
            require(type(recorded[field]) is int and 0 < recorded[field] < 2**64)
        for field, expected in [('uid', uid), ('gid', gid), ('mode', stat.S_IFREG | 0o600), ('links', 1)]:
            require(type(recorded[field]) is int and recorded[field] == expected)
        for field in ['mtime_ns', 'ctime_ns']:
            require(type(recorded[field]) is int and 0 <= recorded[field] < 2**63)
        require(type(recorded['sha256']) is str and len(recorded['sha256']) == 64)
        require(all(char in '0123456789abcdef' for char in recorded['sha256']))
    require(files['request.json']['sha256'] == command['request_sha256'])
    return value


def parse_request(raw, seal):
    value = document(raw)
    require(set(value) == {'protocol', 'kind', 'installation', 'operation', 'purpose',
                          'durable_binding_sha256', 'files'})
    require(type(value['protocol']) is int and value['protocol'] == 2)
    require(value['kind'] == 'native_lifecycle_request')
    for name in ['installation', 'operation', 'purpose', 'durable_binding_sha256']:
        require(value[name] == seal[name])
    require(type(value['files']) is dict)
    expected = {name: {field: observed[field] for field in ['bytes', 'sha256']}
                for name, observed in seal['files'].items() if name != 'request.json'}
    require(value['files'] == expected)
    # Equality alone accepts True as 1; preserve the exact canonical types.
    require(canonical(value['files']) == canonical(expected))
    return value


def file_identity(info, uid, gid, maximum):
    require(stat.S_ISREG(info.st_mode) and info.st_uid == uid and info.st_gid == gid)
    require(stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1)
    require(0 < info.st_size <= maximum)
    return tuple(getattr(info, name) for name in
                 ['st_dev', 'st_ino', 'st_size', 'st_uid', 'st_gid', 'st_mode', 'st_nlink',
                  'st_mtime_ns', 'st_ctime_ns'])


def directory_identity(info, uid, gid):
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == uid and info.st_gid == gid)
    require(stat.S_IMODE(info.st_mode) == 0o700)
    return tuple(getattr(info, name) for name in
                 ['st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode', 'st_mtime_ns', 'st_ctime_ns'])


def file_record(identity, raw):
    return {**dict(zip(FILE_FIELDS, identity)), 'sha256': hashlib.sha256(raw).hexdigest()}


class _PrivateInputSet:
    """Held private descriptors only; internal fixtures establish no Root authority."""
    def __init__(self, directory, uid, gid, expected, files, policy):
        self.usable = False
        self.directory_fd = None
        self.descriptors = {}
        try:
            require(type(uid) is int and type(gid) is int)
            require(os.getuid() == os.geteuid() == uid > 0 and os.getgid() == os.getegid() == gid > 0)
            self.owner, self.uid, self.gid = os.getpid(), uid, gid
            self.directory = Path(directory)
            require(self.directory.is_absolute() and self.directory.resolve(strict=True) == self.directory)
            self.policy = dict(policy)
            require(type(files) is dict and set(files) == set(self.policy) and 1 <= len(files) <= 4)
            require(all(type(name) is str and name in {'request.json', 'allocation.json', 'inputs.json',
                        'intent.json', 'inventory.json', 'plan.json'} for name in files))
            self.files = json.loads(canonical(files))
            self.directory_fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            info = os.fstat(self.directory_fd)
            self.directory_original = directory_identity(info, uid, gid)
            require({'device': info.st_dev, 'inode': info.st_ino, 'uid': info.st_uid} == expected)
            require(directory_identity(self.directory.lstat(), uid, gid) == self.directory_original)
            require(set(os.listdir(self.directory_fd)) == set(self.files))
            self.raw, self.original = {}, {}
            for name, maximum in self.policy.items():
                require(file_identity(os.stat(name, dir_fd=self.directory_fd, follow_symlinks=False), uid, gid, maximum))
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                             dir_fd=self.directory_fd)
                self.descriptors[name] = fd
                before = file_identity(os.fstat(fd), uid, gid, maximum)
                raw = bytearray()
                while len(raw) <= maximum:
                    chunk = os.read(fd, min(4096, maximum + 1 - len(raw)))
                    if not chunk:
                        break
                    raw.extend(chunk)
                require(len(raw) == before[2] <= maximum)
                require(file_identity(os.fstat(fd), uid, gid, maximum) == before)
                require(file_identity(os.stat(name, dir_fd=self.directory_fd, follow_symlinks=False), uid, gid, maximum) == before)
                require(self.files[name] == file_record(before, raw))
                self.raw[name], self.original[name] = bytes(raw), before
            self.usable = True
            self.check()
        except Exception:
            self.close()
            raise OperationInputsRefused('Native operation inputs unavailable or changed') from None

    def check(self):
        try:
            require(self.usable and os.getpid() == self.owner)
            require(os.getuid() == os.geteuid() == self.uid and os.getgid() == os.getegid() == self.gid)
            require(self.directory.resolve(strict=True) == self.directory)
            require(directory_identity(os.fstat(self.directory_fd), self.uid, self.gid) == self.directory_original)
            require(directory_identity(self.directory.lstat(), self.uid, self.gid) == self.directory_original)
            require(set(os.listdir(self.directory_fd)) == set(self.files))
            for name, maximum in self.policy.items():
                require(file_identity(os.fstat(self.descriptors[name]), self.uid, self.gid, maximum) == self.original[name])
                require(file_identity(os.stat(name, dir_fd=self.directory_fd, follow_symlinks=False),
                                      self.uid, self.gid, maximum) == self.original[name])
                require(self.files[name] == file_record(self.original[name], self.raw[name]))
            return dict(self.raw)
        except Exception:
            self.close()
            raise OperationInputsRefused('Native operation inputs unavailable or changed') from None

    def close(self):
        self.usable = False
        for fd in self.descriptors.values():
            os.close(fd)
        self.descriptors.clear()
        if self.directory_fd is not None:
            os.close(self.directory_fd)
            self.directory_fd = None
        # Preserve every input and Root seal, including after partial failure.


class NativeOperationInputs:
    """Fixed Root seal + original private inputs, observed by the actual controller.

    No caller paths, UID, authority maps, callbacks or engines enter this API.
    The lifecycle engine must separately validate payload semantics, durable
    continuity, generation, exclusion, retained responsibility and stage effects.
    """
    def __init__(self, installation, command_raw):
        self.usable = False
        self.scope = None
        self.inputs = None
        try:
            self.command_raw = command_raw
            self.command = decode_command(command_raw, installation)
            require(any(self.command['action'] in policy['actions'] for policy in POLICIES.values()))
            self.scope = NativeControllerScope(installation)
            self.scope.check()
            self.path = Path('/etc/gitgood/installations') / installation / 'operations' / (self.command['operation'] + '.json')
            self.fingerprint = _CapturedRootFiles._fingerprint(self.path, 8192, False)
            self.identity, self.raw = root_file(self.path, 8192)
            require(_CapturedRootFiles._fingerprint(self.path, 8192, False) == self.fingerprint)
            self.seal = parse_seal(self.raw, self.command, self.scope.seal['uid'], self.scope.seal['gid'])
            self.directory = Path('/var/lib/gitgood/operation-inputs') / installation / self.command['operation']
            self.directory_custody = private_directory(self.directory, self.seal['uid'], self.seal['gid'])
            require(self.directory_custody[0] == self.seal['directory_identity'])
            self.inputs = _PrivateInputSet(self.directory, self.seal['uid'], self.seal['gid'],
                                           self.seal['directory_identity'], self.seal['files'],
                                           POLICIES[self.seal['purpose']]['files'])
            self.request = parse_request(self.inputs.raw['request.json'], self.seal)
            for name, raw in self.inputs.raw.items():
                if name != 'request.json':
                    value = document(raw)
                    require(type(value.get('protocol')) is int and value['protocol'] == 2)
            self.usable = True
            self.check()
        except Exception:
            self.close()
            raise OperationInputsRefused('Native operation inputs unavailable or changed') from None

    def _seal_current(self):
        require(canonical(self.seal) == self.raw)
        require(_CapturedRootFiles._fingerprint(self.path, 8192, False) == self.fingerprint)
        require(root_file(self.path, 8192) == (self.identity, self.raw))
        require(_CapturedRootFiles._fingerprint(self.path, 8192, False) == self.fingerprint)
        require(private_directory(self.directory, self.seal['uid'], self.seal['gid']) == self.directory_custody)

    def check(self):
        try:
            require(self.usable)
            require(self.command == decode_command(self.command_raw, self.scope.installation))
            self.scope.check()
            self._seal_current()
            raw = self.inputs.check()
            require(parse_request(raw['request.json'], self.seal) == self.request)
            self._seal_current()
            self.scope.check()
            return {'request': json.loads(canonical(self.request)),
                    'inputs': {name: document(value) for name, value in raw.items() if name != 'request.json'},
                    'request_sha256': self.seal['files']['request.json']['sha256'], 'sealed_inputs_observed': True,
                    'operation_admitted': False, 'lifecycle_exclusion_established': False,
                    'generation_publication_established': False, 'installation_readiness_established': False}
        except Exception:
            self.close()
            raise OperationInputsRefused('Native operation inputs unavailable or changed') from None

    def close(self):
        self.usable = False
        if self.inputs is not None:
            self.inputs.close()
        if self.scope is not None:
            self.scope.close()
