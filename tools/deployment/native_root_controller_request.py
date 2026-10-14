"""Authenticate one original controller request and its held history descriptor.

No lock is acquired and no database exclusion or artifact effect is granted.
"""
import json
import os
from pathlib import Path
import re
import socket
import threading

from native_command_wire import _peer, receive_frame
from native_durable_database import unique
from native_root_live_binding import NativeRootLiveBindingObservation
from resource_generations import canonical, identifier


class RootControllerRequestRefused(Exception):
    pass


def require(value):
    if not value:
        raise RootControllerRequestRefused('Original native controller request unavailable or changed')


def _held_lock(raw, pid, identity):
    """Closed, bounded Linux fdinfo parser; this metadata supplies no admission."""
    require(type(raw) is bytes and 0 < len(raw) <= 8192)
    fields = {}
    for line in raw.decode('ascii').splitlines():
        name, separator, value = line.partition(':')
        require(separator and name not in fields);fields[name] = value.split()
    require(set(fields) == {'pos','flags','mnt_id','ino','lock'})
    for name in ('pos','mnt_id','ino'):
        require(len(fields[name]) == 1 and re.fullmatch('[0-9]{1,20}',fields[name][0]))
    require(int(fields['ino'][0]) == identity['inode'] and int(fields['mnt_id'][0]) > 0)
    require(len(fields['flags']) == 1 and re.fullmatch('[0-7]{1,16}',fields['flags'][0]))
    require(int(fields['flags'][0],8) & os.O_ACCMODE == os.O_RDWR)
    lock = fields['lock']
    require(len(lock) == 8 and re.fullmatch('[1-9][0-9]{0,19}:',lock[0]))
    require(lock[1:5] == ['FLOCK','ADVISORY','WRITE',str(pid)] and lock[6:] == ['0','EOF'])
    device = re.fullmatch('([0-9a-fA-F]{1,8}):([0-9a-fA-F]{1,8}):([1-9][0-9]{0,19})',lock[5])
    require(device and int(device[3]) == identity['inode'])
    require(int(device[1],16) == os.major(identity['device']) and int(device[2],16) == os.minor(identity['device']))
    return tuple((name,tuple(fields[name])) for name in sorted(fields))


class NativeRootControllerRequest:
    """Take custody of one connected Unix socket; capture once, never adopt loss."""
    def __init__(self, installation, operation, connection):
        self.usable = False;self.live = None;self.connection = None
        try:
            require(type(connection) is socket.socket);self.connection = connection
            identifier(installation);identifier(operation);require(installation != operation)
            require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0)
            self.owner = (os.getpid(),threading.get_ident())
            self.live = NativeRootLiveBindingObservation(installation,operation)
            self.observed = self.live.check();self.scope = self.live.scope
            self.peer = {'pid':self.scope['manager']['pid'],'uid':self.scope['uid'],'gid':self.scope['gid']}
            require(_peer(connection,self.scope['uid']) == self.peer)
            self.socket_original = self._socket()
            raw,peer = receive_frame(connection,uid=self.scope['uid'],maximum=512)
            require(peer == self.peer and self._socket() == self.socket_original)
            require(raw.endswith(b'\n') and raw.count(b'\n') == 1)
            value = json.loads(raw[:-1],object_pairs_hook=unique)
            require(type(value) is dict and set(value) == {'protocol','kind','installation','operation','history_lock_fd'})
            require(type(value['protocol']) is int and value['protocol'] == 2)
            require(value['kind'] == 'native_root_controller_request')
            require(value['installation'] == installation and value['operation'] == operation and raw == canonical(value)+b'\n')
            require(type(value['history_lock_fd']) is int and 2 < value['history_lock_fd'] < 1048576)
            self.descriptor = value['history_lock_fd']
            self.original_descriptor = self.descriptor
            require(self.live.check() == self.observed)
            self.original_lock = self._lock()
            self.usable = True;self.check()
        except BaseException:
            self.close();raise RootControllerRequestRefused('Original native controller request unavailable or changed') from None

    def _socket(self):
        info = os.fstat(self.connection.fileno())
        return (info.st_dev,info.st_ino,info.st_mode)

    def _lock(self):
        custody = self.live.lifecycle.history.custody
        custody.check()
        process = Path('/proc')/str(self.peer['pid'])
        # Intentional procfs descriptor observation; compare its target with
        # independently captured ordinary history metadata, not caller paths.
        def target():
            return custody._file((process/'fd'/str(self.descriptor)).stat())
        require(target() == custody.known[custody.lock_path])
        with (process/'fdinfo'/str(self.descriptor)).open('rb') as source:raw = source.read(8193)
        observed = _held_lock(raw,self.peer['pid'],custody.expected_lock_identity)
        require(target() == custody.known[custody.lock_path]);custody.check()
        return observed

    def check(self):
        try:
            require(self.usable and self.owner == (os.getpid(),threading.get_ident()))
            require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0)
            require(self.descriptor == self.original_descriptor)
            require(self.peer == {'pid':self.scope['manager']['pid'],'uid':self.scope['uid'],'gid':self.scope['gid']})
            require(self.live.check() == self.observed)
            require(_peer(self.connection,self.scope['uid']) == self.peer and self._socket() == self.socket_original)
            require(self._lock() == self.original_lock)
            require(self.live.check() == self.observed)
            require(_peer(self.connection,self.scope['uid']) == self.peer and self._socket() == self.socket_original)
            return {**self.observed,'original_controller_peer_authenticated':True,
                'original_controller_history_lock_observed':True,'database_writer_exclusion_verified':False,
                'lifecycle_exclusion_established':False,'stage_effect_authorized':False,'complete_journey_acceptance':False}
        except BaseException:
            self.close();raise RootControllerRequestRefused('Original native controller request unavailable or changed') from None

    def close(self):
        self.usable = False
        if self.connection is not None:self.connection.close()
        if self.live is not None:self.live.close()
        # The controller's descriptor, lock and every original resource remain.
