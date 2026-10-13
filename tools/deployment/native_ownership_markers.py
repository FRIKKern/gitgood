"""Durable marker custody; live admission and old-owner reconciliation are separate.

A marker references one already retained immutable ownership record. Publishing
it grants no service, database, replacement, lifecycle or readiness authority.
"""
import hashlib
import os
import stat
import uuid

from native_ownership_records import NativeOwnershipRecords, OwnershipRecordRefused, require, validate_record, record_name
from resource_generations import canonical, GenerationRefused
from native_durable_database import DatabaseRefused
from upgrade_journal import fcntl


class NativeOwnershipMarkers(NativeOwnershipRecords):
    def _marker(self, record):
        marker = {'protocol':4 if record['protocol']==4 else 2, 'kind':'native_application_marker', 'installation':self.installation,
                'operation':record['operation'], 'mode':record['mode'],
                'record_sha256':hashlib.sha256(canonical(record)).hexdigest()}
        if record['protocol']==4: marker['claim']=record['claim']
        return marker

    def _marker_bytes(self, descriptor, name):
        fd = os.open(name, os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK, dir_fd=descriptor)
        with os.fdopen(fd, 'rb') as source:
            before = os.fstat(source.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_uid==os.getuid() and before.st_nlink==1)
            require(stat.S_IMODE(before.st_mode)==0o600 and 0<before.st_size<=4096)
            raw = source.read(4097)
            after = os.fstat(source.fileno())
        fields = ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_uid','st_mode','st_nlink')
        named = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        require(len(raw)==before.st_size and all(getattr(before,key)==getattr(after,key)==getattr(named,key) for key in fields))
        return raw, tuple(getattr(after,key) for key in fields)

    def _absent_marker(self, descriptor, name):
        try:
            os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            return
        raise OwnershipRecordRefused('Other ownership marker requires reconciliation')

    def publish(self, record):
        """Publish a pointer only; retain every uncertain partial or prior marker.

        The fixed application writer must supply independently admitted context
        and reconcile prior owners before invoking this filesystem component.
        """
        storage_fd = directory_fd = None
        try:
            require(fcntl is not None)
            validate_record(record)
            # Version 4 publication belongs to the live controller's retained
            # reservation and journal, never this initial-only legacy writer.
            require(record['protocol']==3)
            require(record['installation']==self.installation and record['scope']['uid']==self.identity['uid'])
            require(self.storage.resolve(strict=True)==self.storage)
            storage_fd = os.open(self.storage, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
            require(self._identity(os.fstat(storage_fd))==self.identity==self._identity(self.storage.lstat()))
            directory_fd = os.open('.gitgood-ownership-v2', os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC, dir_fd=storage_fd)
            identity = self._identity(os.fstat(directory_fd))
            # The existing directory inode is the common publication lock for
            # both modes. No lock file or new pathname supplies authority.
            fcntl.flock(directory_fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
            self._check(storage_fd, directory_fd, identity)
            entries = self._layout(directory_fd)
            require(record_name(record) in entries)
            fields = ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_uid','st_mode','st_nlink')
            def record_fingerprint():
                result = {}
                for entry in entries:
                    info = os.stat(entry,dir_fd=directory_fd,follow_symlinks=False)
                    result[entry] = tuple(getattr(info,key) for key in fields)
                return result
            captured_records = record_fingerprint()
            require(self._read(directory_fd, record_name(record))==record)
            name = '.gitgood-runtime-v2.json' if record['mode']=='runtime' else '.gitgood-maintenance-v2.json'
            other = '.gitgood-maintenance-v2.json' if record['mode']=='runtime' else '.gitgood-runtime-v2.json'
            self._absent_marker(storage_fd, other)
            raw = canonical(self._marker(record))
            try:
                existing = self._marker_bytes(storage_fd, name)
            except FileNotFoundError:
                temporary = '.marker-partial-'+str(uuid.uuid4())
                fd = os.open(temporary, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC, 0o600, dir_fd=directory_fd)
                with os.fdopen(fd, 'wb') as target:
                    target.write(raw)
                    target.flush()
                    os.fsync(target.fileno())
                    original = os.fstat(target.fileno())
                    published_inode = (original.st_dev, original.st_ino)
                os.fsync(directory_fd)
                self._check(storage_fd, directory_fd, identity)
                require(self._read(directory_fd, record_name(record))==record)
                require(record_fingerprint()==captured_records)
                os.link(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=storage_fd, follow_symlinks=False)
                os.fsync(storage_fd)
                os.unlink(temporary, dir_fd=directory_fd)
                os.fsync(directory_fd)
                os.fsync(storage_fd)
                existing = self._marker_bytes(storage_fd, name)
                require(existing[1][:2]==published_inode)
            else:
                require(existing[0]==raw)
                os.fsync(storage_fd)
            self._check(storage_fd, directory_fd, identity)
            require(self._layout(directory_fd)==entries)
            require(self._read(directory_fd, record_name(record))==record)
            require(record_fingerprint()==captured_records)
            require(existing[0]==raw and self._marker_bytes(storage_fd, name)==existing)
            self._absent_marker(storage_fd, other)
            self._check(storage_fd, directory_fd, identity)
            require(self._marker_bytes(storage_fd, name)==existing)
            require(record_fingerprint()==captured_records)
            return {'ownership_marker_retained':True, 'operation':record['operation'],
                    'marker_sha256':hashlib.sha256(raw).hexdigest(), 'record_sha256':self._marker(record)['record_sha256'],
                    'installation_readiness_established':False, 'replacement_admitted':False}
        except (OwnershipRecordRefused, GenerationRefused, DatabaseRefused, OSError, ValueError,
                TypeError, KeyError, UnicodeError, RecursionError):
            raise OwnershipRecordRefused('Native ownership marker unavailable') from None
        finally:
            if directory_fd is not None:
                os.close(directory_fd)
            if storage_fd is not None:
                os.close(storage_fd)
