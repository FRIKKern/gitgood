"""Read-only kernel binding for one original, already admitted database lease.

The caller must independently admit and retain the server's host/PID namespace
and account. A supplied scope or retained record is not allocator authority.
This module does not signal processes, acquire leases or authorize replacement.
"""
import copy
import hashlib
import os
import re
import sys
import uuid

from native_durable_database import DatabaseRefused, validate_database
from native_inventory import database_environment
from native_ownership_database import observe_held_session, validate_session
from native_prior_backend import observe_prior_backend_absence
from upgrade_journal import UpgradeRefused
from resource_generations import canonical


def require(value):
    if not value:
        raise DatabaseRefused('Original native database kernel identity unavailable')


def _read(path, maximum=16384):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as source:
        raw = source.read(maximum + 1)
    require(0 < len(raw) <= maximum)
    return raw.decode('ascii')


def _positive(value, maximum=2**64-1):
    require(type(value) is str and re.fullmatch(r'[1-9][0-9]{0,19}', value))
    require(int(value) <= maximum)


def _validate_scope(scope):
    require(type(scope) is dict and set(scope) == {'boot_id', 'pid_namespace', 'time_namespace', 'postgres_uid'})
    require(type(scope['boot_id']) is str and str(uuid.UUID(scope['boot_id'])) == scope['boot_id'])
    require(uuid.UUID(scope['boot_id']).int != 0)
    require(type(scope['pid_namespace']) is str and re.fullmatch(r'pid:\[[1-9][0-9]{0,19}\]', scope['pid_namespace']))
    require(type(scope['time_namespace']) is str and re.fullmatch(r'time:\[[1-9][0-9]{0,19}\]', scope['time_namespace']))
    require(type(scope['postgres_uid']) is int and 0 < scope['postgres_uid'] < 2**32)


def _status(raw):
    fields = {}
    for line in raw.splitlines():
        name, separator, value = line.partition(':')
        require(separator and name not in fields)
        fields[name] = value.split()
    return fields


def _check_scope(scope):
    _validate_scope(scope)
    require(sys.platform == 'linux')
    require(_read('/proc/sys/kernel/random/boot_id', 64).strip() == scope['boot_id'])
    require(os.readlink('/proc/self/ns/pid') == scope['pid_namespace'])
    require(os.readlink('/proc/self/ns/time') == scope['time_namespace'])
    # procfs start_time includes the observer's time-namespace boottime offset.
    # Admit only the same independently observed zero-offset native host clock.
    offsets = [line.split() for line in _read('/proc/self/timens_offsets', 256).splitlines()]
    require(offsets == [['monotonic', '0', '0'], ['boottime', '0', '0']])
    # This native host profile admits no nested PostgreSQL PID namespace.
    # NSpid is relative to procfs's mount namespace; a foreign/ancestor procfs
    # or nested namespace must not turn a server PID into an unrelated target.
    fields = _status(_read('/proc/self/status'))
    own = [str(os.getpid())]
    require(fields.get('Pid') == fields.get('Tgid') == fields.get('NSpid') == fields.get('NStgid') == own)


def _stat(pid):
    raw = _read('/proc/' + str(pid) + '/stat')
    end = raw.rfind(')')
    require(end > 0 and raw.startswith(str(pid) + ' (') and raw[end:end+2] == ') ')
    fields = raw[end+2:].split()
    require(len(fields) >= 20 and fields[0] in {'R', 'S', 'D', 'Z', 'T', 't', 'X', 'I', 'P'})
    _positive(fields[19])
    return fields[19], fields[0]


def _capture_process(pid, scope):
    before, state = _stat(pid)
    require(state not in {'Z', 'X'})
    fields = _status(_read('/proc/' + str(pid) + '/status'))
    expected = [str(pid)]
    require(fields.get('Pid') == fields.get('Tgid') == fields.get('NSpid') == fields.get('NStgid') == expected)
    require(fields.get('Uid') == [str(scope['postgres_uid'])] * 4)
    after, state = _stat(pid)
    require(after == before and state not in {'Z', 'X'})
    return before


def _validate_record(record, snapshot, expected_database, scope):
    require(type(record) is dict and set(record) == {'protocol', 'kind', 'server_scope', 'database_session', 'kernel_birth'})
    require(type(record['protocol']) is int and record['protocol'] == 2)
    require(record['kind'] == 'native_backend_kernel_identity')
    _validate_scope(record['server_scope']); _validate_scope(scope)
    require(record['server_scope'] == scope)
    validate_session(record['database_session'], expected_database)
    validate_session(snapshot, expected_database)
    require(record['database_session'] == snapshot)
    _positive(record['kernel_birth'])


def capture_backend_kernel_identity(psql, database_url, snapshot, expected_database, server_scope, *, owner=None):
    """Capture while the exact original lease is live, bracketing kernel reads.

    Independently admitted server_scope must describe this server's actual PID
    namespace and Unix account. SQL birth is microseconds; kernel birth is a
    distinct boot-relative tick value, never substituted for it.
    """
    try:
        validate_database(expected_database, database_environment(database_url))
        validate_session(snapshot, expected_database)
        _check_scope(server_scope)
        observe_held_session(psql, database_url, snapshot, expected_database, owner=owner)
        first = _capture_process(snapshot['backend_pid'], server_scope)
        observe_held_session(psql, database_url, snapshot, expected_database, owner=owner)
        require(_capture_process(snapshot['backend_pid'], server_scope) == first)
        _check_scope(server_scope)
        return copy.deepcopy({'protocol': 2, 'kind': 'native_backend_kernel_identity',
                              'server_scope': server_scope, 'database_session': snapshot, 'kernel_birth': first})
    except (DatabaseRefused, UpgradeRefused, OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise DatabaseRefused('Original native database kernel identity unavailable') from None


def observe_held_backend_kernel_identity(psql, database_url, record, expected_database, server_scope, *, owner=None):
    """Check the retained birth around a fresh original SQL/socket/lease read.

    Never recapture or adopt a current birth. The exact retained kernel process
    must be live before and after the held-session observation.
    """
    try:
        snapshot=record['database_session']
        validate_database(expected_database,database_environment(database_url))
        _validate_record(record,snapshot,expected_database,server_scope)
        _check_scope(server_scope)
        require(_capture_process(snapshot['backend_pid'],server_scope)==record['kernel_birth'])
        observed=observe_held_session(psql,database_url,snapshot,expected_database,owner=owner)
        require(observed['owner_connection_observed'] is True and observed['lease_acquired'] is False)
        require(_capture_process(snapshot['backend_pid'],server_scope)==record['kernel_birth'])
        _check_scope(server_scope)
        return {'original_backend_kernel_observed':True,
                'kernel_record_sha256':hashlib.sha256(canonical(record)).hexdigest(),
                'owner_connection_observed':True,'lease_acquired':False,'replacement_admitted':False}
    except (DatabaseRefused, UpgradeRefused, OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise DatabaseRefused('Original native database kernel identity unavailable') from None


def _kernel_absence(record, scope):
    _check_scope(scope)
    try:
        birth, _ = _stat(record['database_session']['backend_pid'])
    except FileNotFoundError:
        # Only a missing original PID/stat qualifies. Missing host/scope/status
        # observations above are refusal, not process absence.
        reused = False
    else:
        # A zombie still has its original kernel identity. Require exact
        # disappearance or a different birth, without adopting the new PID.
        require(birth != record['kernel_birth'])
        reused = True
    _check_scope(scope)
    return reused


def observe_prior_backend_identity_absence(psql, database_url, record, expected_database, server_scope):
    """Combine activity-view and same-boot kernel absence of the captured lease.

    Retained record custody and scope authority remain caller obligations. A
    changed host, boot or PID namespace refuses; reboot reconciliation requires
    independent durable continuity. No owner/descendant or exclusion is inferred.
    """
    try:
        require(type(record) is dict)
        snapshot = record['database_session']
        validate_database(expected_database, database_environment(database_url))
        _validate_record(record, snapshot, expected_database, server_scope)
        first = _kernel_absence(record, server_scope)
        observed = observe_prior_backend_absence(psql, database_url, snapshot, expected_database)
        second = _kernel_absence(record, server_scope)
        return {**observed, 'kernel_backend_absence_observed': True,
                'kernel_pid_reused': first or second, 'replacement_admitted': False}
    except (DatabaseRefused, UpgradeRefused, OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise DatabaseRefused('Original native database kernel identity unavailable') from None
