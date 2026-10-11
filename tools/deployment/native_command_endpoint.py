"""One retained private local listener; decoded commands remain unadmitted."""
import math
import os
from pathlib import Path
import socket
import stat
import sys

from native_command_wire import CommandWireRefused, identifier, receive_command
from native_controller_scope import NativeControllerScope


class CommandEndpointRefused(Exception):
    pass


def require(value):
    if not value:
        raise CommandEndpointRefused('Native local endpoint unavailable or changed')


def directory_identity(info):
    require(stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o700)
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode)


class _OwnedCommandEndpoint:
    """Descriptor custody only. Internal fixtures do not establish Root admission."""
    def __init__(self, directory, installation, uid, gid, expected):
        self.usable = False
        self.descriptor = None
        self.listener = None
        try:
            identifier(installation)
            require(sys.platform == 'linux' and type(uid) is int and type(gid) is int)
            require(os.getuid() == os.geteuid() == uid > 0 and os.getgid() == os.getegid() == gid > 0)
            require(type(expected) is dict and set(expected) == {'device', 'inode', 'uid'})
            require(all(type(value) is int and value > 0 for value in expected.values()))
            self.directory = Path(directory)
            require(self.directory.is_absolute() and self.directory.resolve(strict=True) == self.directory)
            self.uid, self.gid, self.installation, self.owner = uid, gid, installation, os.getpid()
            self.descriptor = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            info = os.fstat(self.descriptor)
            self.directory_original = directory_identity(info)
            require(info.st_uid == uid and info.st_gid == gid)
            require({'device': info.st_dev, 'inode': info.st_ino, 'uid': info.st_uid} == expected)
            require(directory_identity(self.directory.lstat()) == self.directory_original)
            # Bind beneath the held directory rather than following a later
            # replacement of the pathname. Existing nodes are never removed.
            self.bound_name = '/proc/self/fd/' + str(self.descriptor) + '/controller.sock'
            self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.listener.bind(self.bound_name)
            os.chmod('controller.sock', 0o600, dir_fd=self.descriptor, follow_symlinks=False)
            self.socket_original = self._node()
            self.listener.listen(1)
            self.listener_original = self._listener()
            self.usable = True
            self.check()
        except Exception:
            self.close()
            raise CommandEndpointRefused('Native local endpoint unavailable or changed') from None

    def _node(self):
        info = os.stat('controller.sock', dir_fd=self.descriptor, follow_symlinks=False)
        require(stat.S_ISSOCK(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600)
        require(info.st_uid == self.uid and info.st_gid == self.gid and info.st_nlink == 1)
        return tuple(getattr(info, name) for name in
                     ['st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode', 'st_nlink', 'st_ctime_ns'])

    def _listener(self):
        require(type(self.listener) is socket.socket and self.listener.family == socket.AF_UNIX)
        require(self.listener.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) == socket.SOCK_STREAM)
        require(self.listener.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) == 1)
        require(self.listener.getsockname() == self.bound_name)
        info = os.fstat(self.listener.fileno())
        return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode)

    def check(self):
        try:
            require(self.usable and os.getpid() == self.owner)
            require(os.getuid() == os.geteuid() == self.uid and os.getgid() == os.getegid() == self.gid)
            require(self.directory.resolve(strict=True) == self.directory)
            require(directory_identity(os.fstat(self.descriptor)) == self.directory_original)
            require(directory_identity(self.directory.lstat()) == self.directory_original)
            require(self._node() == self.socket_original and self._listener() == self.listener_original)
        except Exception:
            self.close()
            raise CommandEndpointRefused('Native local endpoint unavailable or changed') from None

    def accept(self, timeout):
        require(type(timeout) in {int, float} and math.isfinite(timeout) and 0 < timeout <= 2)
        self.check()
        self.listener.settimeout(timeout)
        try:
            connection, _ = self.listener.accept()
        except socket.timeout:
            self.check()
            return None
        except OSError:
            self.close()
            raise CommandEndpointRefused('Native local endpoint unavailable or changed') from None
        try:
            self.check()
            return connection
        except Exception:
            connection.close()
            raise

    def close(self):
        self.usable = False
        if self.listener is not None:
            self.listener.close()
        if self.descriptor is not None:
            os.close(self.descriptor)
            self.descriptor = None
        # Retain the original node, including on normal close. Restart cleanup
        # requires separate exact-death/reconciliation admission, never unlink
        # whatever happens to occupy an unchanged path.


class NativeCommandEndpoint:
    """Open a fixed Root-admitted endpoint. No caller authority maps or callbacks."""
    def __init__(self, installation):
        self.scope = None
        self.endpoint = None
        self.usable = False
        try:
            self.scope = NativeControllerScope(installation)
            self.scope.check()
            seal = self.scope.seal
            self.endpoint = _OwnedCommandEndpoint(self.scope.directory, installation,
                                                 seal['uid'], seal['gid'], seal['directory_identity'])
            self.usable = True
            self.check()
        except Exception:
            self.close()
            raise CommandEndpointRefused('Native local endpoint unavailable or changed') from None

    def check(self):
        try:
            require(self.usable)
            self.scope.check()
            self.endpoint.check()
            self.scope.check()
        except Exception:
            self.close()
            raise CommandEndpointRefused('Native local endpoint unavailable or changed') from None

    def receive(self, timeout=0.25):
        self.check()
        try:
            connection = self.endpoint.accept(timeout)
        except CommandEndpointRefused:
            self.close()
            raise
        if connection is None:
            self.check()
            return None
        try:
            self.check()
            value = receive_command(connection, installation=self.scope.installation, uid=self.scope.seal['uid'])
            self.check()
            return {**value, 'operation_admitted': False, 'lifecycle_exclusion_established': False,
                    'generation_publication_established': False, 'installation_readiness_established': False}
        except CommandWireRefused:
            self.check()
            raise
        finally:
            connection.close()

    def close(self):
        self.usable = False
        if self.endpoint is not None:
            self.endpoint.close()
        if self.scope is not None:
            self.scope.close()
