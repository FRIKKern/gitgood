"""Serialized Root policy allocation from original exclusion and inspected input.

This allocates a stage seal; it does not dispatch extraction or establish
interrupted-effect reconciliation, runtime readiness or complete installation.
"""
import ctypes
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat
import tarfile
import threading

from inspect_native_artifact import inspect_native_artifact
from native_durable_database import unique
from native_protected_artifact import (_BoundedTarHeaders, MAX_ARCHIVE, MAX_CONTENT,
    MAX_MEMBERS, RESERVE, fingerprint, parse_policy)
from native_root_database_exclusion import NativeRootDatabaseExclusionObservation
from native_root_controller_request import _held_lock
from native_service_scope import read_bytes
from resource_generations import canonical, digest, identifier
from upgrade_journal import fcntl


class RootArtifactPolicyRefused(Exception):
    pass


def require(value):
    if not value:
        raise RootArtifactPolicyRefused('Original artifact policy unavailable or changed; retain partial allocation')


def _declaration(value, observed):
    require(type(value) is dict and set(value) == {'protocol','kind','installation','operation','candidate','sha256','bytes'})
    require(type(value['protocol']) is int and value['protocol'] == 2 and value['kind'] == 'native_artifact_declaration')
    require(all(value[name] == observed[name] for name in ('installation','operation','candidate')))
    identifier(value['installation']);identifier(value['operation']);digest(value['sha256'])
    require(type(value['bytes']) is int and 0 < value['bytes'] <= MAX_ARCHIVE)
    return json.loads(canonical(value))


def _inspection_receipt(installation, operation, inspection):
    """Canonical actual inspection evidence; this value alone grants no effect."""
    require(type(inspection) is dict and inspection.get('status') == 'inspected')
    return {'protocol':2,'kind':'native_artifact_inspection','installation':installation,
        'operation':operation,'inspection':json.loads(canonical(inspection))}


def _root_directory(path):
    path = Path(path)
    require(path.resolve(strict=True) == path)
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == info.st_gid == 0 and not info.st_mode & 0o022)
    return (info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode)


def _published_policy_identity(before, opened, named):
    """Accept only rename's ctime change on this already retained descriptor."""
    require(all(type(value) is tuple and len(value) == 9 for value in (before,opened,named)))
    require(all(type(item) is int for value in (before,opened,named) for item in value))
    require(opened == named and opened[:-1] == before[:-1] and opened[-1] >= before[-1])
    return opened


class NativeRootArtifactPolicyAllocation:
    """Take original exclusion custody; no caller paths, policy maps or callbacks."""
    def __init__(self, exclusion):
        self.usable = False;self.exclusion = None;self.directories = {};self.lock = None;self.archive = None;self.policy_fd = None
        try:
            require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0 and fcntl is not None)
            require(type(exclusion) is NativeRootDatabaseExclusionObservation);self.exclusion = exclusion
            self.owner = (os.getpid(),threading.get_ident())
            self.observed = exclusion.check()
            require(self.observed['stage'] == 'stage' and self.observed['recorded_status'] == 'running')
            require(self.observed['database_writer_exclusion_verified'] is True)
            self.installation,self.operation = self.observed['installation'],self.observed['operation']
            self.live = exclusion.live;self.lifecycle = self.live.lifecycle
            self.record = self.lifecycle.original['lifecycle']
            require(self.record['completed'] == ['inspect'])
            name = 'inputs.json' if self.lifecycle.worker['purpose'] == 'native_initial_enrollment' else 'plan.json'
            document = json.loads(self.lifecycle.inputs.check()[name],object_pairs_hook=unique)
            require(type(document) is dict and type(document['protocol']) is int and document['protocol'] == 2)
            self.declaration = _declaration(document['artifact'],self.observed)
            self.policy_directory = Path('/etc/gitgood/installations')/self.installation/'artifacts'
            self.source_directory = Path('/var/lib/gitgood/artifact-inputs')/self.installation/self.operation
            self.destination = Path('/opt/gitgood/artifacts')/self.installation
            for path in (self.policy_directory,self.source_directory,self.destination):self._directory(path)
            self.lock_name = 'allocation-lock-v1'
            parent = self.directories[self.policy_directory][0]
            # This Root-only lock is independently provisioned. Missing locks
            # are never replaced here, including after interrupted allocation.
            self.lock = os.open(self.lock_name,os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK,dir_fd=parent)
            info = os.fstat(self.lock)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == info.st_gid == 0 and info.st_nlink == 1
                and stat.S_IMODE(info.st_mode) == 0o600 and info.st_size == 0)
            self.lock_original = fingerprint(info)
            require(fingerprint(os.stat(self.lock_name,dir_fd=parent,follow_symlinks=False)) == self.lock_original)
            fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.lock_info = _held_lock(read_bytes('/proc/self/fdinfo/'+str(self.lock),8192),os.getpid(),
                {'device':info.st_dev,'inode':info.st_ino,'uid':0})
            self.archive = os.open('archive.tar.gz',os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK,
                dir_fd=self.directories[self.source_directory][0])
            info = os.fstat(self.archive)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == info.st_gid == 0 and info.st_nlink == 1
                and not info.st_mode & 0o222 and info.st_size == self.declaration['bytes'])
            self.archive_original = fingerprint(info)
            self.state = 'ready';self.usable = True;self.check()
        except BaseException:
            self.close();raise RootArtifactPolicyRefused('Original artifact policy unavailable or changed; retain partial allocation') from None

    def _directory(self, path):
        path = Path(path)
        for ancestor in path.parents:_root_directory(ancestor)
        named = _root_directory(path)
        if path not in self.directories:
            fd = os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
            try:
                info = os.fstat(fd)
                opened = (info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode)
                require(opened == named);self.directories[path] = (fd,named)
            except BaseException:os.close(fd);raise
        fd,original = self.directories[path];info = os.fstat(fd)
        require((info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode) == original == named)
        return {'device':original[0],'inode':original[1],'uid':original[2]}

    def check(self):
        try:
            require(self.usable and self.owner == (os.getpid(),threading.get_ident()))
            require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0)
            require(self.exclusion.check() == self.observed)
            for path in tuple(self.directories):self._directory(path)
            parent = self.directories[self.policy_directory][0]
            require(fingerprint(os.fstat(self.lock)) == self.lock_original ==
                fingerprint(os.stat(self.lock_name,dir_fd=parent,follow_symlinks=False)))
            require(_held_lock(read_bytes('/proc/self/fdinfo/'+str(self.lock),8192),os.getpid(),
                {'device':self.lock_original[0],'inode':self.lock_original[1],'uid':0}) == self.lock_info)
            require(fingerprint(os.fstat(self.archive)) == self.archive_original ==
                fingerprint(os.stat('archive.tar.gz',dir_fd=self.directories[self.source_directory][0],follow_symlinks=False)))
            if self.state in {'allocating','allocated'}:
                name = self.operation+'.json' if self.state == 'allocated' else '.'+self.operation+'.allocation.partial'
                require(fingerprint(os.fstat(self.policy_fd)) == self.policy_original ==
                    fingerprint(os.stat(name,dir_fd=parent,follow_symlinks=False)))
            return {'installation':self.installation,'operation':self.operation,'candidate':self.observed['candidate'],
                'original_exclusion_and_root_allocation_lock_observed':True,'policy_allocated':self.state == 'allocated',
                'stage_effect_authorized':False,'complete_journey_acceptance':False}
        except BaseException:
            self.close();raise RootArtifactPolicyRefused('Original artifact policy unavailable or changed; retain partial allocation') from None

    def _inspect(self):
        self.check();os.lseek(self.archive,0,os.SEEK_SET)
        count = 0;total = 0
        with os.fdopen(os.dup(self.archive),'rb') as source,gzip.GzipFile(fileobj=source,mode='rb') as expanded:
            with tarfile.open(fileobj=_BoundedTarHeaders(expanded),mode='r:') as archive:
                for member in archive:
                    count += 1;total += member.size
                    require(count <= MAX_MEMBERS and 0 <= member.size <= 128*1024**2 and total <= MAX_CONTENT)
                    require(len(member.name) <= 1024 and (not member.issym() or member.name.startswith('forge/')))
        self.check()
        inspection = inspect_native_artifact(self.source_directory/'archive.tar.gz',self.declaration['sha256'],self.observed['candidate'])
        self.check();require(inspection['artifact_bytes'] == self.declaration['bytes'])
        receipt = _inspection_receipt(self.installation,self.operation,inspection)
        recorded = [event for event in self.record['events'] if event['stage'] == 'inspect'
            and (event['kind'] == 'succeeded' or (event['kind'] == 'reconciled' and event['evidence']['applied'] is True))]
        require(recorded and recorded[-1]['evidence']['receipt_sha256'] == hashlib.sha256(canonical(receipt)).hexdigest())
        return receipt

    def allocate(self):
        try:
            self.check();require(self.state == 'ready')
            self._inspect();self.check()
            parent = self.directories[self.policy_directory][0]
            try:os.stat(self.operation+'.json',dir_fd=parent,follow_symlinks=False)
            except FileNotFoundError:pass
            else:require(False)
            system = os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
            try:
                for volume in (system,parent):
                    space = os.fstatvfs(volume);require(space.f_bavail*space.f_frsize >= RESERVE+65536)
            finally:os.close(system)
            identities = self.lifecycle.history.custody
            journal = identities.directory/'lifecycle-responsibility-v2'
            policy = {'protocol':2,'kind':'native_protected_artifact_stage_seal',
                'installation':self.installation,'operation':self.operation,'candidate':self.observed['candidate'],
                'scope_sha256':hashlib.sha256(canonical(self.exclusion.scope)).hexdigest(),
                'request':self.lifecycle.request,'request_sha256':self.observed['request_sha256'],
                'snapshot_sha256':self.observed['snapshot_sha256'],
                'archive':dict(zip(('device','inode','bytes','mtime_ns','ctime_ns'),
                    (self.archive_original[0],self.archive_original[1],self.archive_original[6],self.archive_original[7],self.archive_original[8])),
                    sha256=self.declaration['sha256']),
                'destination':self._directory(self.destination),
                'directories':{'installation':self.live.binding['resources']['root'],
                    'history_container':identities._identity(identities.directory),'history':identities._identity(journal),
                    'records':identities._identity(journal/'records'),'heads':identities._identity(journal/'heads')}}
            policy['directories']['installation'] = {key:policy['directories']['installation'][key] for key in ('device','inode','uid')}
            raw = canonical(policy);require(len(raw) <= 32768);parse_policy(raw,self.installation,self.operation)
            self.check();partial = '.'+self.operation+'.allocation.partial'
            self.policy_fd = os.open(partial,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=parent)
            require(os.write(self.policy_fd,raw) == len(raw));os.fchmod(self.policy_fd,0o400);os.fsync(self.policy_fd)
            self.policy_original = fingerprint(os.fstat(self.policy_fd));self.state = 'allocating';self.check()
            rename = ctypes.CDLL(None,use_errno=True).renameat2
            rename.argtypes = [ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint];rename.restype = ctypes.c_int
            if rename(parent,os.fsencode(partial),parent,os.fsencode(self.operation+'.json'),1) != 0:require(False)
            opened = fingerprint(os.fstat(self.policy_fd))
            named = fingerprint(os.stat(self.operation+'.json',dir_fd=parent,follow_symlinks=False))
            moved = _published_policy_identity(self.policy_original,opened,named)
            require(os.pread(self.policy_fd,len(raw)+1,0) == raw)
            require(fingerprint(os.fstat(self.policy_fd)) == moved ==
                fingerprint(os.stat(self.operation+'.json',dir_fd=parent,follow_symlinks=False)))
            self.policy_original = moved
            os.fsync(parent);self.state = 'allocated';self.check()
            return {'protocol':2,'kind':'native_artifact_policy_allocation','installation':self.installation,
                'operation':self.operation,'candidate':self.observed['candidate'],'policy_sha256':hashlib.sha256(raw).hexdigest(),
                'policy_allocated':True,'artifact_staged':False,'stage_effect_authorized':False,'complete_journey_acceptance':False}
        except BaseException:
            self.close();raise RootArtifactPolicyRefused('Original artifact policy unavailable or changed; retain partial allocation') from None

    def close(self):
        self.usable = False
        for name in ('policy_fd','archive','lock'):
            descriptor = getattr(self,name,None)
            if descriptor is not None:os.close(descriptor);setattr(self,name,None)
        for descriptor,_ in self.directories.values():os.close(descriptor)
        self.directories.clear()
        if self.exclusion is not None:self.exclusion.close()
        # Existing policy/input/lock files and interrupted partials remain.
