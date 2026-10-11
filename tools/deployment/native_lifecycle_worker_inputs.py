"""Fixed Root worker policy and protected original inputs; no stage effects."""
import hashlib
import os
from pathlib import Path
import platform
import re
import sys

from native_controller_scope import private_directory
from native_operation_inputs import (POLICIES, _PrivateInputSet, document,
                                     parse_request, parse_seal)
from native_service_scope import _CapturedRootFiles, root_file
from resource_generations import canonical, digest, identifier


class LifecycleWorkerInputsRefused(Exception):
    pass


def require(value):
    if not value:
        raise LifecycleWorkerInputsRefused('Native lifecycle worker inputs unavailable or changed')


def worker_seal_path(installation):
    identifier(installation)
    return Path('/etc/gitgood/installations')/installation/'lifecycle-worker-admission-v2.json'


def parse_worker_seal(raw, installation, uid, gid):
    value = document(raw)
    require(set(value) == {'protocol', 'kind', 'installation', 'operation', 'purpose',
            'candidate', 'durable_binding_sha256', 'request_sha256', 'inputs_seal_sha256', 'uid', 'gid'})
    require(type(value['protocol']) is int and value['protocol'] == 2 and value['kind'] == 'native_lifecycle_worker_seal')
    identifier(value['installation']);identifier(value['operation'])
    require(value['installation'] == installation and value['operation'] != installation)
    require(type(value['purpose']) is str and value['purpose'] in POLICIES)
    require(type(value['candidate']) is str and re.fullmatch(r'[0-9a-f]{40}', value['candidate']))
    for name in ['durable_binding_sha256', 'request_sha256', 'inputs_seal_sha256']:digest(value[name])
    for name, expected in [('uid', uid), ('gid', gid)]:
        require(type(expected) is int and expected > 0 and type(value[name]) is int and value[name] == expected)
    return value


class NativeLifecycleWorkerInputs:
    """Only fixed protected paths are read; no caller authority or input paths.

    This role-independent input reader does not impersonate the service MainPID.
    Actual worker scope, current generation and its recorded stage are separate
    admission requirements. Payload contents never appear in its result.
    """
    def __init__(self, installation):
        self.usable = False;self.inputs = None;self.root_files = {}
        try:
            identifier(installation)
            require(sys.platform == 'linux' and platform.machine() == 'x86_64')
            require(os.getuid() == os.geteuid() > 0 and os.getgid() == os.getegid() > 0)
            self.installation = installation;self.owner = os.getpid()
            self.path = worker_seal_path(installation)
            raw = self._root(self.path, 8192)
            self.seal = parse_worker_seal(raw, installation, os.getuid(), os.getgid())
            self.original_raw = raw
            self.operation_path = self.path.parent/'operations'/(self.seal['operation']+'.json')
            operation_raw = self._root(self.operation_path, 8192)
            require(hashlib.sha256(operation_raw).hexdigest() == self.seal['inputs_seal_sha256'])
            command = {'protocol': 2, 'installation': installation, 'operation': self.seal['operation'],
                       'action': 'enroll' if self.seal['purpose'] == 'native_initial_enrollment' else 'upgrade',
                       'request_sha256': self.seal['request_sha256']}
            self.operation_seal = parse_seal(operation_raw, command, os.getuid(), os.getgid())
            require(self.operation_seal['purpose'] == self.seal['purpose'])
            require(self.operation_seal['durable_binding_sha256'] == self.seal['durable_binding_sha256'])
            self.ownership_path = self.path.parent/'ownership-admission-v3.json'
            ownership = document(self._root(self.ownership_path, 16384))
            require(set(ownership) == {'protocol', 'kind', 'installation', 'operation', 'candidate', 'binding_sha256'})
            require(type(ownership['protocol']) is int and ownership['protocol'] == 3 and ownership['kind'] == 'native_application_ownership_seal')
            for name in ['installation', 'operation', 'candidate']:require(ownership[name] == self.seal[name])
            require(ownership['binding_sha256'] == self.seal['durable_binding_sha256'])
            self.directory = Path('/var/lib/gitgood/operation-inputs')/installation/self.seal['operation']
            self.directory_custody = private_directory(self.directory, os.getuid(), os.getgid())
            require(self.directory_custody[0] == self.operation_seal['directory_identity'])
            self.inputs = _PrivateInputSet(self.directory, os.getuid(), os.getgid(),
                self.operation_seal['directory_identity'], self.operation_seal['files'], POLICIES[self.seal['purpose']]['files'])
            self.request = parse_request(self.inputs.raw['request.json'], self.operation_seal)
            for name, payload in self.inputs.raw.items():
                if name != 'request.json':
                    value = document(payload);require(type(value.get('protocol')) is int and value['protocol'] == 2)
            self.usable = True;self.check()
        except Exception:
            self.close();raise LifecycleWorkerInputsRefused('Native lifecycle worker inputs unavailable or changed') from None

    def _root(self, path, maximum):
        fingerprint = _CapturedRootFiles._fingerprint(path, maximum, False)
        identity, raw = root_file(path, maximum)
        require(_CapturedRootFiles._fingerprint(path, maximum, False) == fingerprint)
        self.root_files[str(path)] = (maximum, fingerprint, identity, raw)
        return raw

    def check(self):
        try:
            require(self.usable and os.getpid() == self.owner and canonical(self.seal) == self.original_raw)
            require(os.getuid() == os.geteuid() == self.seal['uid'] and os.getgid() == os.getegid() == self.seal['gid'])
            for name, (maximum, fingerprint, identity, raw) in self.root_files.items():
                path = Path(name)
                require(_CapturedRootFiles._fingerprint(path, maximum, False) == fingerprint)
                require(root_file(path, maximum) == (identity, raw))
                require(_CapturedRootFiles._fingerprint(path, maximum, False) == fingerprint)
            require(private_directory(self.directory, os.getuid(), os.getgid()) == self.directory_custody)
            payloads = self.inputs.check()
            require(parse_request(payloads['request.json'], self.operation_seal) == self.request)
            require(canonical(self.operation_seal) == self.root_files[str(self.operation_path)][3])
            return {'request': document(canonical(self.request)), 'candidate': self.seal['candidate'],
                    'inputs_seal_sha256': self.seal['inputs_seal_sha256'], 'request_sha256': self.seal['request_sha256']}
        except Exception:
            self.close();raise LifecycleWorkerInputsRefused('Native lifecycle worker inputs unavailable or changed') from None

    def fingerprint(self):
        self.check()
        return {'root': {name: value[1] for name, value in self.root_files.items()},
                'directory': self.directory_custody, 'inputs': dict(self.inputs.original)}

    def close(self):
        self.usable = False
        if self.inputs is not None:self.inputs.close()
        # Retain original inputs, Root policy and ownership seals on every path.
