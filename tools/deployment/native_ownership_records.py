"""Immutable application ownership custody; retention grants no live authority.

The caller must independently admit the generation and held database session.
This component preserves their closed record. It does not publish a live marker,
reconcile an older owner, acquire a lease, or establish installation readiness.
"""
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import stat
import sys
import uuid

from native_durable_database import DatabaseRefused, unique, validate_database
from native_kernel_backend import _validate_record as validate_kernel_record
from resource_generations import (GenerationRefused, canonical, closed, digest,
                                  identifier, integer, validate_scope)


class OwnershipRecordRefused(Exception):
    pass


def require(value):
    if not value:
        raise OwnershipRecordRefused('Native ownership record unavailable')


def validate_record(record, *, allow_legacy=False):
    require(type(record) is dict and type(record.get('protocol')) is int)
    require(record['protocol'] in {3,4} or (allow_legacy is True and record['protocol']==2))
    fields=('protocol', 'kind', 'installation', 'operation', 'candidate',
            'mode', 'binding_sha256', 'pointer', 'scope', 'owner', 'database_session', 'guard')
    closed(record, fields + (('backend_kernel',) if record['protocol']>=3 else ()) +
           (('claim','predecessor_sha256','reservation_sha256') if record['protocol']==4 else ()))
    require(record['kind'] == 'native_application_ownership')
    identifier(record['installation']); identifier(record['operation'])
    require(record['operation'] != record['installation'])
    require(type(record['candidate']) is str and re.fullmatch(r'[0-9a-f]{40}', record['candidate']))
    require(type(record['mode']) is str and record['mode'] in {'runtime','backup','restore','migrate'})
    digest(record['binding_sha256'])
    pointer = record['pointer']
    closed(pointer, ('protocol','installation','operation','generation_sha256','transition_sha256'))
    require(type(pointer['protocol']) is int and pointer['protocol'] == 2)
    require(pointer['installation'] == record['installation'])
    identifier(pointer['operation']); digest(pointer['generation_sha256']); digest(pointer['transition_sha256'])
    require(record['operation'] != pointer['operation'])
    if record['protocol']==4:
        identifier(record['claim'])
        require(record['claim'] not in {record['installation'],record['operation'],pointer['operation']})
        if record['predecessor_sha256'] is not None: digest(record['predecessor_sha256'])
        digest(record['reservation_sha256'])
    scope, owner = record['scope'], record['owner']
    validate_scope(scope)
    require(scope['installation'] == record['installation'])
    # Reuse the closed process grammar only. This substitution does not observe
    # or replace the actual service manager in the retained record.
    validate_scope({**scope, 'manager':owner})
    require(owner['pid'] > 1 and owner['pid'] != scope['manager']['pid'])
    require(all(owner[name] == scope['manager'][name] for name in ['mount_namespace','cgroup_namespace']))
    session = record['database_session']
    closed(session, ('database','backend_pid','backend_birth'))
    integer(session['backend_pid'], 1, 2**31-1)
    birth = session['backend_birth']
    require(type(birth) is str and re.fullmatch(r'[1-9][0-9]{0,19}', birth))
    integer(int(birth))
    database = session['database']
    require(type(database) is dict)
    for name in ['database','role','session_role']:
        value = database.get(name)
        require(type(value) is str and 1 <= len(value.encode('utf-8')) <= 63 and '\0' not in value)
    integer(database.get('port'), 1, 65535)
    validate_database(database, {'PGDATABASE':database['database'], 'PGUSER':database['role'],
                                 'PGPORT':str(database['port'])})
    if record['protocol']>=3:
        kernel=record['backend_kernel']
        require(type(kernel) is dict and type(kernel.get('server_scope')) is dict)
        validate_kernel_record(kernel,session,database,kernel['server_scope'])
        require(kernel['server_scope']['boot_id']==scope['boot_id'])
    guard = record['guard']
    closed(guard, ('scope_sha256','history_sha256','persistent_files_sha256'))
    for value in guard.values(): digest(value)
    worker = 'native' if record['mode'] == 'runtime' else 'maintenance'
    expected = {'scope':scope, 'owner':owner, 'worker':worker}
    require(guard['scope_sha256'] == hashlib.sha256(canonical(expected)).hexdigest())
    require(len(canonical(record)) <= 16384)
    return record


def record_name(record):
    """Version 3 filenames remain unchanged; version 4 names each BEAM claim."""
    validate_record(record,allow_legacy=True)
    return record['claim' if record['protocol']==4 else 'operation']+'.json'


class NativeOwnershipRecords:
    def __init__(self, storage, installation, expected_storage_identity):
        identifier(installation)
        closed(expected_storage_identity, ('device','inode','uid'))
        for name, value in expected_storage_identity.items():
            integer(value, 1, 2**32-1 if name == 'uid' else 2**64-1)
        require(sys.platform == 'linux' and os.getuid() == os.geteuid() == expected_storage_identity['uid'])
        self.storage = Path(storage)
        require(self.storage.is_absolute())
        self.installation = installation
        self.identity = dict(expected_storage_identity)

    def _identity(self, info):
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700)
        return {'device':info.st_dev, 'inode':info.st_ino, 'uid':info.st_uid}

    def _check(self, storage_fd, directory_fd, directory_identity):
        require(self.storage.resolve(strict=True) == self.storage)
        require(self._identity(self.storage.lstat()) == self._identity(os.fstat(storage_fd)) == self.identity)
        named = os.stat('.gitgood-ownership-v2', dir_fd=storage_fd, follow_symlinks=False)
        require(self._identity(named) == self._identity(os.fstat(directory_fd)) == directory_identity)

    def _read(self, descriptor, name):
        fd = os.open(name, os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK, dir_fd=descriptor)
        with os.fdopen(fd, 'rb') as source:
            before = os.fstat(source.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid() and before.st_nlink == 1)
            require(stat.S_IMODE(before.st_mode) == 0o600 and 0 < before.st_size <= 16384)
            raw = source.read(16385); after = os.fstat(source.fileno())
        fields = ['st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_uid','st_mode','st_nlink']
        require(len(raw) == before.st_size and all(getattr(before,key) == getattr(after,key) for key in fields))
        named = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        require(all(getattr(after,key) == getattr(named,key) for key in fields))
        value = json.loads(raw, object_pairs_hook=unique)
        # Legacy claims stay observable as immutable history. No writer or live
        # guard admits their missing kernel identity; never synthesize one.
        validate_record(value,allow_legacy=True)
        require(raw == canonical(value) and name == record_name(value))
        require(value['installation'] == self.installation and value['scope']['uid'] == self.identity['uid'])
        return value

    def _layout(self, descriptor):
        with os.scandir(descriptor) as iterator:
            entries = list(itertools.islice(iterator, 129))
        require(len(entries) <= 128)
        for entry in entries:
            require(not entry.name.startswith('.partial-') and entry.name.endswith('.json'))
            identifier(entry.name[:-5])
            self._read(descriptor, entry.name)
        return {entry.name for entry in entries}

    def inspect(self):
        """Observe retained responsibility without creating, locking or repairing.

        A complete record describes an earlier claim. This observation cannot
        establish that its owner/backend exited or authorize a replacement.
        """
        storage_fd = directory_fd = None
        try:
            require(self.storage.resolve(strict=True) == self.storage)
            storage_fd = os.open(self.storage, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
            require(self._identity(os.fstat(storage_fd)) == self.identity == self._identity(self.storage.lstat()))
            name = '.gitgood-ownership-v2'
            try:
                directory_fd = os.open(name, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC, dir_fd=storage_fd)
            except FileNotFoundError:
                require(self.storage.resolve(strict=True) == self.storage)
                require(self._identity(os.fstat(storage_fd)) == self.identity == self._identity(self.storage.lstat()))
                try:
                    os.stat(name, dir_fd=storage_fd, follow_symlinks=False)
                except FileNotFoundError:
                    return {'ownership_directory_present':False, 'records':[],
                            'installation_readiness_established':False, 'replacement_admitted':False}
                raise OwnershipRecordRefused('Native ownership directory changed')
            directory_identity = self._identity(os.fstat(directory_fd))
            self._check(storage_fd, directory_fd, directory_identity)
            names = self._layout(directory_fd)
            fields = ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_uid','st_mode','st_nlink')
            def fingerprint():
                result = {}
                for entry in names:
                    info = os.stat(entry, dir_fd=directory_fd, follow_symlinks=False)
                    result[entry] = tuple(getattr(info, field) for field in fields)
                return result
            before = fingerprint()
            values = [self._read(directory_fd, entry) for entry in sorted(names)]
            require(self._layout(directory_fd) == names and fingerprint() == before)
            self._check(storage_fd, directory_fd, directory_identity)
            require([self._read(directory_fd, entry) for entry in sorted(names)] == values)
            require(self._layout(directory_fd) == names and fingerprint() == before)
            self._check(storage_fd, directory_fd, directory_identity)
            return {'ownership_directory_present':True, 'records':values,
                    'installation_readiness_established':False, 'replacement_admitted':False}
        except (OwnershipRecordRefused, GenerationRefused, DatabaseRefused, OSError, ValueError,
                TypeError, KeyError, UnicodeError, RecursionError):
            raise OwnershipRecordRefused('Native ownership inspection unavailable') from None
        finally:
            if directory_fd is not None: os.close(directory_fd)
            if storage_fd is not None: os.close(storage_fd)

    def retain(self, record):
        storage_fd = directory_fd = None
        try:
            validate_record(record)
            require(record['installation'] == self.installation and record['scope']['uid'] == self.identity['uid'])
            require(self.storage.resolve(strict=True) == self.storage)
            storage_fd = os.open(self.storage, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
            require(self._identity(os.fstat(storage_fd)) == self.identity)
            try:
                os.mkdir('.gitgood-ownership-v2', 0o700, dir_fd=storage_fd)
                os.fsync(storage_fd)
            except FileExistsError:
                pass
            directory_fd = os.open('.gitgood-ownership-v2', os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC, dir_fd=storage_fd)
            directory_identity = self._identity(os.fstat(directory_fd))
            self._check(storage_fd, directory_fd, directory_identity)
            entries = self._layout(directory_fd)
            name = record_name(record)
            if name in entries:
                require(self._read(directory_fd, name) == record)
            else:
                require(len(entries) < 128)
                temporary = '.partial-' + str(uuid.uuid4())
                fd = os.open(temporary, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC, 0o600, dir_fd=directory_fd)
                with os.fdopen(fd, 'wb') as target:
                    target.write(canonical(record)); target.flush(); os.fsync(target.fileno())
                os.fsync(directory_fd)
                self._check(storage_fd, directory_fd, directory_identity)
                # Link publication is atomic and cannot replace a record. A
                # crash before unlink leaves a partial/hard-link responsibility
                # that refuses further retention and is never silently removed.
                os.link(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd, follow_symlinks=False)
                os.fsync(directory_fd)
                os.unlink(temporary, dir_fd=directory_fd)
            os.fsync(directory_fd)
            self._check(storage_fd, directory_fd, directory_identity)
            require(self._read(directory_fd, name) == record)
            self._layout(directory_fd)
            self._check(storage_fd, directory_fd, directory_identity)
            require(self._read(directory_fd, name) == record)
            return {'ownership_record_retained':True, 'operation':record['operation'],
                    'record_sha256':hashlib.sha256(canonical(record)).hexdigest(),
                    'installation_readiness_established':False}
        except (OwnershipRecordRefused, GenerationRefused, DatabaseRefused, OSError, ValueError,
                TypeError, KeyError, UnicodeError, RecursionError):
            raise OwnershipRecordRefused('Native ownership record unavailable') from None
        finally:
            if directory_fd is not None: os.close(directory_fd)
            if storage_fd is not None: os.close(storage_fd)
