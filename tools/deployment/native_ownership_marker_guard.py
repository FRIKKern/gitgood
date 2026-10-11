"""Observe original ownership custody without repair, recapture or live authority."""
import hashlib
import json
import os

from native_durable_database import DatabaseRefused
from native_ownership_markers import NativeOwnershipMarkers, fcntl
from native_ownership_records import OwnershipRecordRefused, require, validate_record
from resource_generations import GenerationRefused, canonical


class NativeOwnershipMarkerGuard(NativeOwnershipMarkers):
    fields = ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_uid','st_mode','st_nlink')

    def __init__(self, storage, installation, expected_storage_identity, record):
        self.storage_fd = self.directory_fd = None
        self.poisoned = False
        try:
            super().__init__(storage,installation,expected_storage_identity)
            require(fcntl is not None)
            validate_record(record)
            require(record['installation']==self.installation and record['scope']['uid']==self.identity['uid'])
            self.record = json.loads(canonical(record))
            self.name = '.gitgood-runtime-v2.json' if record['mode']=='runtime' else '.gitgood-maintenance-v2.json'
            self.other = '.gitgood-maintenance-v2.json' if record['mode']=='runtime' else '.gitgood-runtime-v2.json'
            self.expected_marker = canonical(self._marker(self.record))
            require(self.storage.resolve(strict=True)==self.storage)
            self.storage_fd = os.open(self.storage,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
            require(self._identity(os.fstat(self.storage_fd))==self.identity==self._identity(self.storage.lstat()))
            self.directory_fd = os.open('.gitgood-ownership-v2',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=self.storage_fd)
            self.directory_identity = self._identity(os.fstat(self.directory_fd))
            self.captured = self._observe()
            require(self._observe()==self.captured)
        except Exception:
            self.close()
            raise OwnershipRecordRefused('Native ownership custody guard unavailable') from None

    def _fingerprint(self, info):
        return tuple(getattr(info,name) for name in self.fields)

    def _observe(self):
        require(not self.poisoned and self.storage_fd is not None and self.directory_fd is not None)
        fcntl.flock(self.directory_fd,fcntl.LOCK_SH|fcntl.LOCK_NB)
        try:
            self._check(self.storage_fd,self.directory_fd,self.directory_identity)
            directory = self._fingerprint(os.fstat(self.directory_fd))
            names = self._layout(self.directory_fd)
            require(self.record['operation']+'.json' in names)
            def fingerprints():
                return {name:self._fingerprint(os.stat(name,dir_fd=self.directory_fd,follow_symlinks=False)) for name in names}
            before = fingerprints()
            values = {name:self._read(self.directory_fd,name) for name in names}
            require(values[self.record['operation']+'.json']==self.record)
            self._absent_marker(self.storage_fd,self.other)
            marker = self._marker_bytes(self.storage_fd,self.name)
            require(marker[0]==self.expected_marker)
            require(self._layout(self.directory_fd)==names and fingerprints()==before)
            require({name:self._read(self.directory_fd,name) for name in names}==values)
            self._check(self.storage_fd,self.directory_fd,self.directory_identity)
            require(self._fingerprint(os.fstat(self.directory_fd))==directory)
            self._absent_marker(self.storage_fd,self.other)
            require(self._marker_bytes(self.storage_fd,self.name)==marker)
            require(fingerprints()==before)
            self._check(self.storage_fd,self.directory_fd,self.directory_identity)
            return {'directory':directory,'records':before,'record_values':values,'marker':marker}
        finally:
            fcntl.flock(self.directory_fd,fcntl.LOCK_UN)

    def check(self):
        """Keep the original descriptors and fingerprints; one refusal is terminal."""
        try:
            require(not self.poisoned)
            require(self._observe()==self.captured and self._observe()==self.captured)
            return {'ownership_marker_observed':True,'operation':self.record['operation'],
                    'record_sha256':hashlib.sha256(canonical(self.record)).hexdigest(),
                    'marker_sha256':hashlib.sha256(self.expected_marker).hexdigest(),
                    'live_owner_observed':False,'replacement_admitted':False,
                    'installation_readiness_established':False}
        except (OwnershipRecordRefused,GenerationRefused,DatabaseRefused,OSError,ValueError,
                TypeError,KeyError,UnicodeError,RecursionError):
            self.close()
            raise OwnershipRecordRefused('Native ownership custody guard lost') from None

    def close(self):
        self.poisoned = True
        for name in ['directory_fd','storage_fd']:
            descriptor = getattr(self,name,None)
            setattr(self,name,None)
            if descriptor is not None:
                os.close(descriptor)
