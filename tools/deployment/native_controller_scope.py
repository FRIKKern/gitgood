"""Fixed Root-sealed controller/endpoint custody; no generation or operation grant."""
import json
import os
from pathlib import Path
import platform
import stat
import sys

from native_service_scope import _CapturedRootFiles, _observe_service, root_file
from resource_generations import canonical, identifier, digest
from native_durable_database import unique


class ControllerScopeRefused(Exception):
    pass


def require(value):
    if not value:
        raise ControllerScopeRefused('Native controller scope unavailable or changed')


def private_directory(path, uid, gid):
    path = Path(path)
    require(path.is_absolute() and path.resolve(strict=True) == path)
    parents = []
    for parent in path.parents:
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022)
        parents.append((str(parent), info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode))
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == uid and info.st_gid == gid)
    require(stat.S_IMODE(info.st_mode) == 0o700)
    return {'device': info.st_dev, 'inode': info.st_ino, 'uid': info.st_uid}, tuple(parents)


class NativeControllerScope:
    """Only the actual allocated systemd MainPID can open its fixed endpoint.

    The allocator must already have installed the Root seal and private run
    directory. A live service observation supplies no generation publication,
    lifecycle exclusion, sealed operation admission or functional readiness.
    """
    def __init__(self, installation):
        self.usable = False
        self.files = _CapturedRootFiles()
        try:
            identifier(installation)
            require(sys.platform == 'linux' and platform.machine() == 'x86_64')
            require(os.getuid() == os.geteuid() > 0 and os.getgid() == os.getegid() > 0)
            self.installation = installation
            self.path = Path('/etc/gitgood/installations') / installation / 'controller-endpoint-v2.json'
            self.fingerprint = _CapturedRootFiles._fingerprint(self.path, 4096, False)
            self.identity, self.raw = root_file(self.path, 4096)
            require(_CapturedRootFiles._fingerprint(self.path, 4096, False) == self.fingerprint)
            seal = json.loads(self.raw, object_pairs_hook=unique)
            require(self.raw == canonical(seal))
            require(type(seal) is dict and set(seal) == {
                'protocol', 'kind', 'installation', 'uid', 'gid', 'unit_sha256',
                'directory_identity', 'limits'})
            require(type(seal['protocol']) is int and seal['protocol'] == 2)
            require(seal['kind'] == 'native_controller_endpoint_seal' and seal['installation'] == installation)
            digest(seal['unit_sha256'])
            require(type(seal['uid']) is int and seal['uid'] == os.getuid())
            require(type(seal['gid']) is int and seal['gid'] == os.getgid())
            require(type(seal['limits']) is dict and set(seal['limits']) == {'cpu_quota_us', 'memory_bytes'})
            expected = seal['directory_identity']
            require(type(expected) is dict and set(expected) == {'device', 'inode', 'uid'})
            require(all(type(value) is int and value > 0 for value in expected.values()))
            require(expected['uid'] == seal['uid'])
            self.directory = Path('/run/gitgood/installations') / installation
            self.seal = json.loads(canonical(seal))
            self.directory_custody = private_directory(self.directory, seal['uid'], seal['gid'])
            require(self.directory_custody[0] == expected)
            self.original = self._service()
            require(self.original['manager']['pid'] == os.getpid())
            require(self.original['uid'] == seal['uid'] and self.original['gid'] == seal['gid'])
            self.files.freeze()
            self.usable = True
            self.check()
        except Exception:
            self.close()
            raise ControllerScopeRefused('Native controller scope unavailable or changed') from None

    def _service(self):
        return _observe_service(self.installation, self.seal['unit_sha256'],
                                **self.seal['limits'], _root_files=self.files)

    def check(self):
        try:
            require(self.usable and os.getpid() == self.original['manager']['pid'])
            require(canonical(self.seal) == self.raw)
            require(_CapturedRootFiles._fingerprint(self.path, 4096, False) == self.fingerprint)
            require(root_file(self.path, 4096) == (self.identity, self.raw))
            require(private_directory(self.directory, self.seal['uid'], self.seal['gid']) == self.directory_custody)
            require(self._service() == self.original)
            require(_CapturedRootFiles._fingerprint(self.path, 4096, False) == self.fingerprint)
            require(private_directory(self.directory, self.seal['uid'], self.seal['gid']) == self.directory_custody)
            return json.loads(canonical(self.original))
        except Exception:
            self.close()
            raise ControllerScopeRefused('Native controller scope unavailable or changed') from None

    def close(self):
        self.usable = False
        self.files.close()
