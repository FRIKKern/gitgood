"""Fixed Root-only archive staging under an original controller and stage seal.

Root seal allocation and ordinary-controller dispatch are separate requirements.
No public caller can select paths, programs, callbacks or authority maps here.
"""
import ctypes
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tarfile
import threading

from inspect_native_artifact import inspect_native_artifact
from native_lifecycle_responsibility import validate_request
from native_root_controller import NativeRootControllerObservation
from native_service_scope import _CapturedRootFiles, _root_file_parents, root_file
from resource_generations import canonical, digest, identifier

RESERVE = 20 * 1024**3
MAX_ARCHIVE = 1024**3
MAX_CONTENT = 4 * 1024**3
MAX_MEMBERS = 30000
MAX_EXPANDED = MAX_CONTENT + MAX_MEMBERS*8192 + 1048576


class _BoundedTarHeaders:
    """Bound decompressed offsets and parser header reads before inspection."""
    def __init__(self, source):
        self.source = source

    def read(self, size):
        require(type(size) is int and 0 <= size <= 8192)
        require(self.tell() + size <= MAX_EXPANDED)
        return self.source.read(size)

    def tell(self):
        return self.source.tell()

    def seek(self, offset, whence=os.SEEK_SET):
        require(type(offset) is int and whence in {os.SEEK_SET,os.SEEK_CUR})
        position = offset if whence == os.SEEK_SET else self.tell()+offset
        require(0 <= position <= MAX_EXPANDED)
        return self.source.seek(position)


class ProtectedArtifactRefused(Exception):
    pass


def require(value):
    if not value:
        raise ProtectedArtifactRefused('Protected native artifact unavailable or changed; retain partial effects')


def fingerprint(info):
    return tuple(getattr(info, field) for field in
        ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def _artifact_path(path):
    """Canonical spelling and fresh link refusal; no path observations cached."""
    require(path.is_absolute() and path.anchor == '/' and '..' not in path.parts)
    for parent, _ in _root_file_parents(path):require(stat.S_ISDIR(parent.lstat().st_mode))
    require(not stat.S_ISLNK(path.lstat().st_mode))
    return path


def directory(path, uid, *, private=False):
    path = _artifact_path(Path(path))
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == uid and not info.st_mode & 0o022)
    require(not private or stat.S_IMODE(info.st_mode) == 0o700)
    return {'device': info.st_dev, 'inode': info.st_ino, 'uid': info.st_uid}


def parse_policy(raw, installation, operation):
    def unique(pairs):
        result = {}
        for name, value in pairs:
            require(name not in result);result[name] = value
        return result
    value = json.loads(raw, object_pairs_hook=unique)
    require(type(value) is dict and raw == canonical(value))
    require(set(value) == {'protocol', 'kind', 'installation', 'operation', 'candidate',
        'scope_sha256', 'request', 'request_sha256', 'snapshot_sha256', 'archive', 'destination', 'directories'})
    require(type(value['protocol']) is int and value['protocol'] == 2)
    require(value['kind'] == 'native_protected_artifact_stage_seal')
    require(value['installation'] == installation and value['operation'] == operation)
    require(type(value['candidate']) is str and len(value['candidate']) == 40)
    require(all(char in '0123456789abcdef' for char in value['candidate']))
    for name in ('scope_sha256', 'request_sha256', 'snapshot_sha256'):digest(value[name])
    validate_request(value['request'])
    require(value['request']['installation'] == installation and value['request']['operation'] == operation)
    require(value['request']['purpose'] in {'native_initial_enrollment', 'native_upgrade_execution'})
    require(hashlib.sha256(canonical(value['request'])).hexdigest() == value['request_sha256'])
    require(type(value['directories']) is dict and set(value['directories']) == {'installation', 'history_container', 'history', 'records', 'heads'})
    for identity in [value['destination'], *value['directories'].values()]:
        require(type(identity) is dict and set(identity) == {'device', 'inode', 'uid'})
        require(all(type(item) is int and 0 <= item < 2**64 for item in identity.values()))
        require(identity['device'] > 0 and identity['inode'] > 0)
    require(value['destination']['uid'] == 0)
    archive = value['archive']
    require(type(archive) is dict and set(archive) == {'device', 'inode', 'bytes', 'mtime_ns', 'ctime_ns', 'sha256'})
    require(all(type(archive[name]) is int and 0 <= archive[name] < 2**64
        for name in ('device', 'inode', 'bytes', 'mtime_ns', 'ctime_ns')))
    require(archive['device'] > 0 and archive['inode'] > 0 and 0 < archive['bytes'] <= MAX_ARCHIVE)
    digest(archive['sha256'])
    return value


class NativeProtectedArtifactStage:
    def __init__(self, installation, operation):
        self.usable = False;self.controller = None;self.parent_fd = None;self.archive_fd = None
        self.work_fd = None;self.code_fd = None;self.snapshot_fd = None;self.code_directories = {};self.output_files = {}
        try:
            identifier(installation);identifier(operation);require(installation != operation)
            require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0)
            self.owner = (os.getpid(), threading.get_ident())
            self.installation = installation;self.operation = operation
            self.controller = self._controller_observation()
            self.scope = self.controller.check()
            self.policy_path = Path('/etc/gitgood/installations') / installation / 'artifacts' / (operation + '.json')
            self.policy_fingerprint = _CapturedRootFiles._fingerprint(self.policy_path, 32768, False)
            self.policy_identity, self.raw = root_file(self.policy_path, 32768)
            self.policy = parse_policy(self.raw, installation, operation)
            require(hashlib.sha256(canonical(self.scope)).hexdigest() == self.policy['scope_sha256'])
            self.parent = Path('/opt/gitgood/artifacts') / installation
            for path in [self.parent, *self.parent.parents]:directory(path, 0)
            require(directory(self.parent, 0) == self.policy['destination'])
            self.parent_fd = os.open(self.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            parent_info = os.fstat(self.parent_fd)
            require({'device':parent_info.st_dev, 'inode':parent_info.st_ino, 'uid':parent_info.st_uid}
                == self.policy['destination'])
            self.parent_original = fingerprint(parent_info)[:5]
            self.source = Path('/var/lib/gitgood/artifact-inputs') / installation / operation / 'archive.tar.gz'
            for path in self.source.parents:directory(path, 0)
            self.archive_fd = os.open(self.source, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
            self.archive_original = fingerprint(os.fstat(self.archive_fd))
            self.journal = Path('/var/lib/gitgood/installations') / installation / 'history/lifecycle-responsibility-v2'
            self.journal_paths = {'installation': self.journal.parent.parent, 'history_container': self.journal.parent, 'history': self.journal,
                'records': self.journal / 'records', 'heads': self.journal / 'heads'}
            self.head_path = self.journal / 'heads' / (operation + '.json')
            self.snapshot_path = self.journal / 'records' / (self.policy['snapshot_sha256'] + '.json')
            self.head_original, self.head_raw = self._private(self.head_path, 16384)
            self.snapshot_original, self.snapshot_raw = self._private(self.snapshot_path, 1048576)
            self._validate_stage()
            self.usable = True;self.state = 'ready';self.check()
        except BaseException:
            self.close()
            raise ProtectedArtifactRefused('Protected native artifact unavailable or changed; retain partial effects') from None

    def _controller_observation(self):
        return NativeRootControllerObservation(self.installation)

    def _private(self, path, maximum):
        _artifact_path(path)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_uid == self.scope['uid']
                and before.st_gid == self.scope['gid'] and stat.S_IMODE(before.st_mode) == 0o600
                and before.st_nlink == 1 and 0 < before.st_size <= maximum)
            raw = os.read(fd, maximum + 1)
            require(len(raw) == before.st_size and fingerprint(os.fstat(fd)) == fingerprint(before))
            require(fingerprint(path.lstat()) == fingerprint(before))
            return fingerprint(before), raw
        finally:os.close(fd)

    def _validate_stage(self):
        head = json.loads(self.head_raw);snapshot = json.loads(self.snapshot_raw)
        require(self.head_raw == canonical(head) and self.snapshot_raw == canonical(snapshot))
        require(head == {'protocol': 2, 'kind': 'native_lifecycle_head', 'installation': self.installation,
            'operation': self.operation, 'snapshot_sha256': self.policy['snapshot_sha256']})
        require(hashlib.sha256(self.snapshot_raw).hexdigest() == self.policy['snapshot_sha256'])
        require(type(snapshot) is dict and set(snapshot) == {'protocol', 'kind', 'origin', 'predecessor_sha256',
            'generation_sha256', 'epoch', 'stage', 'status', 'completed', 'events'})
        require(type(snapshot['protocol']) is int and snapshot['protocol'] == 2 and snapshot['kind'] == 'native_lifecycle_snapshot')
        origin = snapshot['origin']
        require(origin['request'] == self.policy['request'] and origin['request_sha256'] == self.policy['request_sha256'])
        require(snapshot['status'] == 'running' and snapshot['stage'] == 'stage' and snapshot['completed'] == ['inspect'])
        # The independently allocated Root policy pins the exact admitted
        # snapshot. This view does not claim to replay or repair its history.

    def check(self):
        try:
            require(self.usable and self.owner == (os.getpid(), threading.get_ident()))
            require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0)
            require(self.controller.check() == self.scope and canonical(self.policy) == self.raw)
            require(_CapturedRootFiles._fingerprint(self.policy_path, 32768, False) == self.policy_fingerprint)
            require(root_file(self.policy_path, 32768) == (self.policy_identity, self.raw))
            if hasattr(self, 'work'):
                require(directory(self.work, 0) == self.work_identity)
                require(self._directory_identity(os.fstat(self.work_fd)) == self.work_identity)
            if self.code_fd is not None:
                require(self._directory_identity(os.fstat(self.code_fd)) == self.code_directories[''])
                require(self._directory_identity(os.stat('code', dir_fd=self.work_fd, follow_symlinks=False)) == self.code_directories[''])
            if self.snapshot_fd is not None:
                require(fingerprint(os.fstat(self.snapshot_fd)) == self.archive_snapshot_original)
                require(fingerprint(os.stat('archive.tar.gz', dir_fd=self.work_fd, follow_symlinks=False)) == self.archive_snapshot_original)
            require(directory(self.parent, 0) == self.policy['destination'])
            require(fingerprint(os.fstat(self.parent_fd))[:5] == self.parent_original)
            for path in self.parent.parents:directory(path, 0)
            for name, path in self.journal_paths.items():
                require(directory(path, self.scope['uid'], private=True) == self.policy['directories'][name])
            require(self._private(self.head_path, 16384) == (self.head_original, self.head_raw))
            require(self._private(self.snapshot_path, 1048576) == (self.snapshot_original, self.snapshot_raw))
            before = os.fstat(self.archive_fd)
            require(fingerprint(before) == self.archive_original and fingerprint(self.source.lstat()) == self.archive_original)
            require(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_gid == 0
                and before.st_nlink == 1 and not before.st_mode & 0o222)
            observed = {name: getattr(before, attr) for name, attr in
                [('device','st_dev'), ('inode','st_ino'), ('bytes','st_size'), ('mtime_ns','st_mtime_ns'), ('ctime_ns','st_ctime_ns')]}
            require(observed == {name: self.policy['archive'][name] for name in observed})
            for path in self.source.parents:directory(path, 0)
            if self.state == 'staged':self._check_output()
            return {'original_controller_and_running_stage_observed': True, 'artifact_staged': self.state == 'staged'}
        except BaseException:
            self.close()
            raise ProtectedArtifactRefused('Protected native artifact unavailable or changed; retain partial effects') from None

    def _budget(self, bytes_needed):
        require(type(bytes_needed) is int and 0 < bytes_needed <= MAX_ARCHIVE + MAX_CONTENT + MAX_MEMBERS*8192 + 33554432)
        root = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            for fd in (root, self.parent_fd):
                capacity = os.fstatvfs(fd)
                require(capacity.f_bavail * capacity.f_frsize >= RESERVE + bytes_needed)
        finally:os.close(root)

    @staticmethod
    def _directory_identity(info):
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) in {0o700,0o555})
        return {'device':info.st_dev, 'inode':info.st_ino, 'uid':info.st_uid}

    def _code_directory(self, name):
        """Traverse only original created directories beneath the held code FD."""
        descriptor = os.dup(self.code_fd)
        try:
            require(self._directory_identity(os.fstat(descriptor)) == self.code_directories[''])
            prefix = []
            for component in PurePosixPath(name).parts:
                require(component not in {'','.','..'} and '/' not in component)
                prefix.append(component);key = '/'.join(prefix)
                require(key in self.code_directories)
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=descriptor)
                previous, descriptor = descriptor, child
                os.close(previous)
                require(self._directory_identity(os.fstat(descriptor)) == self.code_directories[key])
            return descriptor
        except BaseException:
            os.close(descriptor);raise

    def _code_parent(self, name):
        path = PurePosixPath(name)
        parent = str(path.parent)
        return self._code_directory('' if parent == '.' else parent), path.name

    def _check_output(self):
        """Original staged metadata and exact entries; no content-based adoption."""
        require(stat.S_IMODE(os.fstat(self.work_fd).st_mode) == 0o555)
        with os.scandir(self.work_fd) as entries:
            require({entry.name for entry in entries} == {'code','archive.tar.gz','inventory.json','receipt.json'})
        expected = {name:set() for name in self.code_directories}
        for path in self.code_directories:
            if not path:continue
            parent = str(PurePosixPath(path).parent)
            expected['' if parent == '.' else parent].add(PurePosixPath(path).name)
        for path in self.output_files:
            if not path.startswith('code/'):continue
            relative = PurePosixPath(path.removeprefix('code/'));parent = str(relative.parent)
            expected['' if parent == '.' else parent].add(relative.name)
        for name in self.code_directories:
            descriptor = self._code_directory(name)
            try:
                require(stat.S_IMODE(os.fstat(descriptor).st_mode) == 0o555)
                with os.scandir(descriptor) as entries:actual = {entry.name for entry in entries}
                require(actual == expected[name])
            finally:os.close(descriptor)
        for path, original in self.output_files.items():
            if path.startswith('code/'):
                descriptor, name = self._code_parent(path.removeprefix('code/'))
            else:descriptor, name = os.dup(self.work_fd), path
            try:require(fingerprint(os.stat(name, dir_fd=descriptor, follow_symlinks=False)) == original)
            finally:os.close(descriptor)

    def _preflight_archive(self):
        # The shared inspector remains responsible for the complete inventory
        # and build identity. First bound its gzip/PAX inputs under this seal.
        # Parsing has no staging effects. Bracket it with full live custody,
        # as policy inspection does, and pin the archive at every member.
        self.check()
        os.lseek(self.archive_fd,0,os.SEEK_SET)
        count = 0;total = 0
        with os.fdopen(os.dup(self.archive_fd),'rb') as source, gzip.GzipFile(fileobj=source,mode='rb') as expanded:
            with tarfile.open(fileobj=_BoundedTarHeaders(expanded),mode='r:') as archive:
                for member in archive:
                    self._check_archive_input();count += 1;total += member.size
                    require(count <= MAX_MEMBERS and 0 <= total <= MAX_CONTENT)
                    require(len(member.name) <= 1024 and 0 <= member.size <= 128*1024**2)
                    require(not member.issym() or member.name.startswith('forge/'))
        self.check()

    def _check_archive_input(self):
        require(fingerprint(os.fstat(self.archive_fd)) == self.archive_original
            == fingerprint(self.source.lstat()))

    def stage(self):
        try:
            self.check();require(self.state == 'ready')
            self._preflight_archive()
            inspected = inspect_native_artifact(self.source, self.policy['archive']['sha256'], self.policy['candidate'])
            self.check()
            require(inspected['members'] <= MAX_MEMBERS and inspected['declared_bytes'] <= MAX_CONTENT)
            budget = inspected['artifact_bytes'] + inspected['declared_bytes'] + inspected['members']*8192 + 33554432
            self._budget(budget)
            partial = '.native-' + self.operation + '.partial';target = 'native-' + self.operation
            try:os.stat(target, dir_fd=self.parent_fd, follow_symlinks=False)
            except FileNotFoundError:pass
            else:require(False)
            os.mkdir(partial, 0o700, dir_fd=self.parent_fd);os.fsync(self.parent_fd)
            work = self.parent / partial
            self.work = work
            self.work_identity = directory(work, 0, private=True)
            self.work_fd = os.open(partial, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=self.parent_fd)
            require(self._directory_identity(os.fstat(self.work_fd)) == self.work_identity)
            snapshot = work / 'archive.tar.gz'
            output = os.open('archive.tar.gz', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o444, dir_fd=self.work_fd)
            os.lseek(self.archive_fd, 0, os.SEEK_SET);copied = 0;hashed = hashlib.sha256()
            with os.fdopen(output, 'wb') as destination:
                while data := os.read(self.archive_fd, 1048576):
                    self.check();copied += len(data);require(copied <= inspected['artifact_bytes'])
                    hashed.update(data);destination.write(data)
                destination.flush();os.fchmod(destination.fileno(),0o444);os.fsync(destination.fileno())
            require(copied == inspected['artifact_bytes'] and hashed.hexdigest() == self.policy['archive']['sha256'])
            self.snapshot_fd = os.open('archive.tar.gz', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=self.work_fd)
            self.archive_snapshot_original = fingerprint(os.fstat(self.snapshot_fd))
            inspect_native_artifact(snapshot, hashed.hexdigest(), self.policy['candidate'])
            self.check()
            os.mkdir('code', 0o700, dir_fd=self.work_fd)
            self.code_fd = os.open('code', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=self.work_fd)
            self.code_directories[''] = self._directory_identity(os.fstat(self.code_fd))
            inventory = []
            with os.fdopen(os.dup(self.snapshot_fd), 'rb') as original, tarfile.open(fileobj=original, mode='r:gz') as archive:
                members = archive.getmembers()
                for member in sorted((item for item in members if item.isdir()), key=lambda item:item.name.count('/')):
                    self.check();name = member.name.rstrip('/')
                    parent, leaf = self._code_parent(name)
                    try:
                        os.mkdir(leaf, 0o700, dir_fd=parent)
                        child = os.open(leaf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
                        try:self.code_directories[name] = self._directory_identity(os.fstat(child))
                        finally:os.close(child)
                    finally:os.close(parent)
                for member in members:
                    if not member.isfile():continue
                    self.check();parent, leaf = self._code_parent(member.name)
                    try:
                        fd = os.open(leaf, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                            0o555 if member.mode & 0o111 else 0o444, dir_fd=parent)
                    finally:os.close(parent)
                    written = 0;content = hashlib.sha256()
                    with os.fdopen(fd, 'wb') as destination, archive.extractfile(member) as source:
                        while data := source.read(1048576):
                            self.check();written += len(data);require(written <= member.size)
                            content.update(data);destination.write(data)
                        require(written == member.size);destination.flush()
                        os.fchmod(destination.fileno(),0o555 if member.mode & 0o111 else 0o444)
                        os.fsync(destination.fileno())
                        original = fingerprint(os.fstat(destination.fileno()))
                        self.output_files['code/'+member.name] = original
                    inventory.append({'path':member.name, 'bytes':written, 'sha256':content.hexdigest(),
                        'executable':bool(member.mode & 0o111), 'identity':list(original)})
                for member in members:
                    if member.issym():
                        require(member.name.startswith('forge/'))
                        self.check();parent, leaf = self._code_parent(member.name)
                        try:
                            os.symlink(member.linkname, leaf, dir_fd=parent)
                            original = fingerprint(os.stat(leaf, dir_fd=parent, follow_symlinks=False))
                            self.output_files['code/'+member.name] = original
                        finally:os.close(parent)
                        inventory.append({'path':member.name, 'symlink':member.linkname, 'identity':list(original)})
            inventory.sort(key=lambda item:item['path'])
            receipt = {'protocol':2, 'kind':'native_protected_artifact_stage_receipt', 'status':'staged',
                'installation':self.installation, 'operation':self.operation, 'candidate':self.policy['candidate'],
                'scope_sha256':self.policy['scope_sha256'], 'request_sha256':self.policy['request_sha256'],
                'snapshot_sha256':self.policy['snapshot_sha256'], 'artifact_sha256':hashed.hexdigest(),
                'inventory_sha256':hashlib.sha256(canonical(inventory)).hexdigest(), 'allocation_budget_bytes':budget,
                'output_directory_identity':dict(self.work_identity),
                'code_directories':{name:dict(identity) for name, identity in self.code_directories.items()},
                'root_controlled_code':True, 'complete_journey_acceptance':False}
            for name, value in [('inventory.json',inventory), ('receipt.json',receipt)]:
                fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                    0o444, dir_fd=self.work_fd)
                with os.fdopen(fd, 'wb') as output:
                    output.write(canonical(value));output.flush();os.fchmod(output.fileno(),0o444);os.fsync(output.fileno())
                    self.output_files[name] = fingerprint(os.fstat(output.fileno()))
            for name in sorted(self.code_directories, key=lambda name:len(PurePosixPath(name).parts), reverse=True):
                self.check();fd = self._code_directory(name)
                try:os.fchmod(fd,0o555);os.fsync(fd)
                finally:os.close(fd)
            os.fchmod(self.work_fd,0o555);os.fsync(self.work_fd)
            self.check()
            rename = ctypes.CDLL(None, use_errno=True).renameat2
            rename.argtypes = [ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
            rename.restype = ctypes.c_int
            if rename(self.parent_fd,os.fsencode(partial),self.parent_fd,os.fsencode(target),1) != 0:
                raise OSError(ctypes.get_errno(), 'Protected native publication refused')
            os.fsync(self.parent_fd);self.work = self.parent/target;self.state = 'staged';self.check();self._check_output()
            return receipt
        except BaseException:
            self.close()
            raise ProtectedArtifactRefused('Protected native artifact unavailable or changed; retain partial effects') from None

    def close(self):
        self.usable = False
        if self.controller is not None:self.controller.close()
        for name in ('snapshot_fd','code_fd','work_fd','archive_fd','parent_fd'):
            descriptor = getattr(self,name,None)
            if descriptor is not None:os.close(descriptor);setattr(self,name,None)
        # Every original input, seal and incomplete or published effect remains.
