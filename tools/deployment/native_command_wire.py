"""Bounded local command framing and kernel peer identity; no lifecycle dispatch."""
import json
import re
import socket
import struct
import sys
import time
import uuid

MAXIMUM = 4096
RECEIVE_SECONDS = 2.0
MUTATIONS = frozenset({'enroll', 'enroll-resume', 'upgrade', 'upgrade-recover',
                       'upgrade-resume', 'backup', 'restore', 'export', 'retire'})


class CommandWireRefused(Exception):
    pass


def require(value):
    if not value:
        raise CommandWireRefused('Native local command unavailable')


def identifier(value):
    require(type(value) is str and str(uuid.UUID(value)) == value and uuid.UUID(value).int != 0)


def unique(pairs):
    result = {}
    for name, value in pairs:
        require(name not in result)
        result[name] = value
    return result


def decode_command(raw, installation):
    """Decode untrusted bytes; the resulting request remains unadmitted."""
    try:
        identifier(installation)
        require(type(raw) is bytes and 0 < len(raw) <= MAXIMUM)
        require(raw.endswith(b'\n') and raw.count(b'\n') == 1 and b'\0' not in raw)
        value = json.loads(raw[:-1], object_pairs_hook=unique)
        require(type(value) is dict)
        require(type(value.get('protocol')) is int and value['protocol'] == 2)
        require(value.get('kind') == 'native_controller_command')
        require(value.get('installation') == installation)
        action = value.get('action')
        require(type(action) is str and action in MUTATIONS | {'status'})
        fields = {'protocol', 'kind', 'installation', 'action'}
        if action != 'status':
            fields |= {'operation', 'request_sha256'}
            identifier(value.get('operation'))
            require(type(value.get('request_sha256')) is str and
                    re.fullmatch('[0-9a-f]{64}', value['request_sha256']) is not None)
        require(set(value) == fields)
        expected = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode() + b'\n'
        require(raw == expected)
        return value
    except (CommandWireRefused, ValueError, TypeError, AttributeError, UnicodeError, RecursionError):
        raise CommandWireRefused('Native local command unavailable') from None


def _peer(connection, uid):
    require(sys.platform == 'linux' and type(connection) is socket.socket)
    require(type(uid) is int and 0 < uid < 2**31)
    require(connection.family == socket.AF_UNIX and
            connection.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) == socket.SOCK_STREAM)
    raw = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i'))
    require(len(raw) == struct.calcsize('3i'))
    pid, actual_uid, gid = struct.unpack('3i', raw)
    require(1 < pid < 2**31 and actual_uid == uid and 0 <= gid < 2**31)
    return {'pid': pid, 'uid': actual_uid, 'gid': gid}


def receive_frame(connection, *, uid, maximum=MAXIMUM):
    """Read one half-closed stream from an independently admitted account.

    The caller owns a successful connection. Every refusal closes it. Neither
    peer identity nor decoded data admits a sealed operation or grants effects.
    """
    try:
        require(type(maximum) is int and 1<=maximum<=32768)
        peer = _peer(connection, uid)
        original_timeout = connection.gettimeout()
        deadline = time.monotonic() + RECEIVE_SECONDS
        raw = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            require(remaining > 0)
            connection.settimeout(remaining)
            chunk = connection.recv(maximum + 1 - len(raw))
            if not chunk:
                break
            raw.extend(chunk)
            require(len(raw) <= maximum)
        require(time.monotonic() < deadline)
        require(_peer(connection, uid) == peer)
        connection.settimeout(original_timeout)
        return bytes(raw),peer
    except (CommandWireRefused, OSError, ValueError, TypeError, AttributeError):
        if type(connection) is socket.socket:
            connection.close()
        raise CommandWireRefused('Native local command unavailable') from None


def receive_command(connection, *, installation, uid):
    try:
        identifier(installation)
        raw,peer=receive_frame(connection,uid=uid)
        return {'request':decode_command(raw,installation),'peer':peer}
    except Exception:
        if type(connection) is socket.socket:connection.close()
        raise CommandWireRefused('Native local command unavailable') from None
