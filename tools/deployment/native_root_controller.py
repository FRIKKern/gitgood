"""Root's fixed read-only view of one original ordinary installation controller.

No stage effect, endpoint peer authentication, generation publication, lifecycle
exclusion or replacement admission is supplied by this observation.
"""
import json
import copy
from functools import wraps
import os
from pathlib import Path
import platform
import threading
import sys

from native_controller_scope import private_directory
from native_durable_database import unique
from native_service_scope import _CapturedRootFiles, _observe_root_controller, root_file
from resource_generations import canonical, digest, identifier


class RootControllerRefused(Exception):
    pass


def require(value):
    if not value:
        raise RootControllerRefused('Original native controller unavailable or changed')


_observation_pass = threading.local()


def _root_observation_owner():
    require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0)
    return os.getpid(),threading.get_ident()


class _RootObservationPass:
    """Private no-effect pass; no results survive the next effect boundary."""
    def __init__(self):
        self.owner = None;self.values = {};self.failed = False;self.active = False

    def __enter__(self):
        require(not self.active and self.owner is None and getattr(_observation_pass,'current',None) is None)
        self.owner = _root_observation_owner();self.active = True
        _observation_pass.current = self
        return self

    def check(self):
        require(self.active and not self.failed and self.owner == _root_observation_owner()
            and getattr(_observation_pass,'current',None) is self)

    def __exit__(self, kind, *_):
        try:
            require(self.active and self.owner == _root_observation_owner()
                and getattr(_observation_pass,'current',None) is self)
            require(not self.failed or kind is not None)
        finally:
            self.active = False;self.failed = True;self.values.clear()
            if getattr(_observation_pass,'current',None) is self:_observation_pass.current = None


def _within_root_observation_pass(method):
    """Only fixed source checks participate; outside a pass behavior is intact."""
    @wraps(method)
    def observed(self):
        current = getattr(_observation_pass,'current',None)
        if current is None:return method(self)
        current.check()
        if not self.usable or self.owner != current.owner:
            current.failed = True;current.values.clear()
            return method(self)  # Existing typed refusal and owned-view cleanup.
        key = (self,method)
        if key in current.values:return copy.deepcopy(current.values[key])
        try:
            value = method(self);current.check()
            require(self.usable and self.owner == current.owner)
            require(len(current.values) < 32)
            current.values[key] = copy.deepcopy(value)
            return value
        except BaseException:
            current.failed = True;current.values.clear();raise
    return observed


class NativeRootControllerObservation:
    """Capture once from fixed Root policy; loss permanently closes this view.

    The public constructor accepts only an installation UUID. The allocator's
    original fixed seal selects unit identity, limits and private run directory.
    Any later process, service, namespace, policy or directory change refuses.
    """
    def __init__(self, installation):
        self.usable = False
        self.files = _CapturedRootFiles()
        try:
            identifier(installation)
            require(sys.platform == 'linux' and platform.machine() == 'x86_64')
            require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0)
            self.owner = (os.getpid(), threading.get_ident())
            self.installation = installation
            self.path = Path('/etc/gitgood/installations') / installation / 'controller-endpoint-v2.json'
            self.fingerprint = _CapturedRootFiles._fingerprint(self.path, 4096, False)
            self.identity, self.raw = root_file(self.path, 4096)
            require(_CapturedRootFiles._fingerprint(self.path, 4096, False) == self.fingerprint)
            self.seal = json.loads(self.raw, object_pairs_hook=unique)
            seal = self.seal
            require(self.raw == canonical(seal))
            require(type(seal) is dict and set(seal) == {
                'protocol', 'kind', 'installation', 'uid', 'gid', 'unit_sha256',
                'directory_identity', 'limits'})
            require(type(seal['protocol']) is int and seal['protocol'] == 2)
            require(seal['kind'] == 'native_controller_endpoint_seal' and seal['installation'] == installation)
            digest(seal['unit_sha256'])
            require(type(seal['uid']) is int and 0 < seal['uid'] < 2**32)
            require(type(seal['gid']) is int and 0 < seal['gid'] < 2**32)
            require(type(seal['limits']) is dict and set(seal['limits']) == {'cpu_quota_us', 'memory_bytes'})
            identity = seal['directory_identity']
            require(type(identity) is dict and set(identity) == {'device', 'inode', 'uid'})
            require(all(type(value) is int and 0 < value < 2**64 for value in identity.values()))
            require(identity['uid'] == seal['uid'])
            self.directory = Path('/run/gitgood/installations') / installation
            self.directory_custody = private_directory(self.directory, seal['uid'], seal['gid'])
            require(self.directory_custody[0] == identity)
            self.original = self._service()
            require(self.original['uid'] == seal['uid'] and self.original['gid'] == seal['gid'])
            self.files.freeze()
            self.usable = True
            self.check()
        except Exception:
            self.close()
            raise RootControllerRefused('Original native controller unavailable or changed') from None

    def _service(self):
        return _observe_root_controller(self.installation, self.seal['unit_sha256'],
            **self.seal['limits'], _root_files=self.files)

    def _policy(self):
        require(_CapturedRootFiles._fingerprint(self.path, 4096, False) == self.fingerprint)
        require(root_file(self.path, 4096) == (self.identity, self.raw))
        require(_CapturedRootFiles._fingerprint(self.path, 4096, False) == self.fingerprint)

    @_within_root_observation_pass
    def check(self):
        try:
            require(self.usable and self.owner == (os.getpid(), threading.get_ident()))
            require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0)
            require(canonical(self.seal) == self.raw)
            self._policy()
            require(private_directory(self.directory, self.seal['uid'], self.seal['gid']) == self.directory_custody)
            require(self._service() == self.original)
            self._policy()
            require(private_directory(self.directory, self.seal['uid'], self.seal['gid']) == self.directory_custody)
            return json.loads(canonical(self.original))
        except Exception:
            self.close()
            raise RootControllerRefused('Original native controller unavailable or changed') from None

    def close(self):
        self.usable = False
        self.files.close()
