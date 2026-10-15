"""Root's fixed read-only original lifecycle view; no exclusion or stage grant."""
import copy
import hashlib
import itertools
import os
from pathlib import Path
import stat
import threading

from generation_custody import GenerationRecordCustody
from native_controller_scope import private_directory
from native_durable_database import validate_database
from native_generation_reader import NativeGenerationReader
from native_lifecycle_history import NativeLifecycleHistory
from native_lifecycle_responsibility import HISTORY_NAMES, generation_owner
from native_lifecycle_worker_inputs import parse_worker_seal
from native_operation_inputs import (POLICIES, directory_identity, document,
    file_identity, file_record, parse_request, parse_seal)
from native_root_controller import NativeRootControllerObservation, _within_root_observation_pass
from native_service_scope import _CapturedRootFiles, root_file
from resource_generations import canonical, digest, identifier


class RootLifecycleRefused(Exception):
    pass


def require(value):
    if not value:
        raise RootLifecycleRefused('Original native lifecycle unavailable or changed')


def root_owner():
    require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0)
    return os.getpid(), threading.get_ident()


def parse_generation_seal(raw, installation, scope):
    """Closed recorded policy only; caller data supplies no Root custody."""
    value = document(raw)
    require(set(value) == {'protocol','kind','installation','binding_sha256','history_identity',
        'lock_identity','unit_sha256','executables','limits','database'})
    require(type(value['protocol']) is int and value['protocol'] == 2)
    require(value['kind'] == 'native_generation_admission_seal' and value['installation'] == installation)
    digest(value['binding_sha256']);digest(value['unit_sha256'])
    require(value['unit_sha256'] == scope['unit_definition']['sha256'])
    for name in ('history_identity','lock_identity'):
        identity = value[name]
        require(type(identity) is dict and set(identity) == {'device','inode','uid'})
        require(all(type(item) is int and 0 < item < 2**64 for item in identity.values()))
        require(identity['uid'] == scope['uid'])
    limits = value['limits']
    require(type(limits) is dict and set(limits) == {'cpu_quota_us','memory_bytes'})
    require(canonical({**limits,'cpu_period_us':100000,'swap_bytes':0}) == canonical(scope['limits']))
    executables = value['executables']
    require(type(executables) is dict and set(executables) == {'python','node','git','psql','caddy'})
    require(all(type(path) is str and path.startswith('/') and 0 < len(path) <= 4096
        and '\0' not in path for path in executables.values()))
    database = value['database']
    require(type(database) is dict)
    validate_database(database, {'PGDATABASE':database.get('database'), 'PGUSER':database.get('role'),
        'PGPORT':str(database.get('port'))})
    return value


class _RootReadOnlyCustody(GenerationRecordCustody):
    """Internal original ordinary-file custody observed by Root, never locked."""
    def __init__(self, installation, scope, seal):
        self.usable = False;self.directories = {};self.known = {};self.lock = None
        self.retained = {};self.entries = None;self.directory_metadata = {}
        self.owner = root_owner();self.installation = installation
        self.uid, self.gid = scope['uid'], scope['gid']
        self.root = Path('/var/lib/gitgood/installations')/installation
        self.directory = self.root/'history';self.store = self.directory/'generation-records-v2'
        self.lock_path = self.directory/'.upgrade-history-lock-v1'
        self.identity = copy.deepcopy(seal['history_identity'])
        self.expected_lock_identity = copy.deepcopy(seal['lock_identity'])
        try:
            self.root_custody = private_directory(self.root,self.uid,self.gid)
            require(self._identity(self.directory) == self.identity)
            self.usable = True
            self.lock = self._open(self.lock_path,os.O_RDONLY)
            info = os.fstat(self.lock)
            require({'device':info.st_dev,'inode':info.st_ino,'uid':info.st_uid} == self.expected_lock_identity)
            self.lock_identity = (info.st_dev,info.st_ino,info.st_uid)
            self.store_identity = self._identity(self.store)
            self.check()
        except BaseException:
            self.__exit__(None,None,None);raise

    def _identity(self, path):
        path = Path(path)
        require(path == self.directory or path.is_relative_to(self.directory))
        require(path.resolve(strict=True) == path)
        named = directory_identity(path.lstat(),self.uid,self.gid)
        if path not in self.directories:
            if path == self.directory:
                fd = os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
            else:
                self._identity(path.parent)
                fd = os.open(path.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,
                    dir_fd=self.directories[path.parent][0])
            try:
                original = directory_identity(os.fstat(fd),self.uid,self.gid)
                require(original == named)
                self.directories[path] = (fd,original)
            except BaseException:os.close(fd);raise
        fd,original = self.directories[path]
        require(directory_identity(os.fstat(fd),self.uid,self.gid) == original == named)
        return {'device':original[0],'inode':original[1],'uid':original[2]}

    def _file(self, info):
        require(stat.S_ISREG(info.st_mode) and info.st_uid == self.uid and info.st_gid == self.gid)
        require(stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1 and info.st_size <= 131072)
        return tuple(getattr(info,name) for name in ('st_dev','st_ino','st_uid','st_gid','st_mode',
            'st_nlink','st_size','st_mtime_ns','st_ctime_ns'))

    def _open(self, path, flags):
        require(flags == os.O_RDONLY);self.check()
        path = Path(path);self._identity(path.parent)
        parent = self.directories[path.parent][0]
        fd = os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK,dir_fd=parent)
        try:
            original = self._file(os.fstat(fd))
            require(self._file(os.stat(path.name,dir_fd=parent,follow_symlinks=False)) == original)
            require(self.known.get(path,original) == original);self.known[path] = original
            return fd
        except BaseException:os.close(fd);raise

    @_within_root_observation_pass
    def check(self):
        require(self.usable and root_owner() == self.owner)
        require(private_directory(self.root,self.uid,self.gid) == self.root_custody)
        # Check the complete held parent chain once, rather than resolving that
        # same chain again for every file and every already captured directory.
        for path,(fd,original) in self.directories.items():
            named = path.lstat() if path == self.directory else os.stat(path.name,
                dir_fd=self.directories[path.parent][0],follow_symlinks=False)
            require(directory_identity(os.fstat(fd),self.uid,self.gid) == original
                == directory_identity(named,self.uid,self.gid))
            if self.entries is not None:
                require(self._directory_metadata(os.fstat(fd)) == self.directory_metadata[path]
                    == self._directory_metadata(named))
                require(self._names(fd) == self.entries[path])
        for path,original in self.known.items():
            parent = self.directories[path.parent][0]
            require(self._file(os.stat(path.name,dir_fd=parent,follow_symlinks=False)) == original)
            if path in self.retained:require(self._file(os.fstat(self.retained[path])) == original)
        if self.lock is not None:require(self._file(os.fstat(self.lock)) == self.known[self.lock_path])

    @staticmethod
    def _directory_metadata(info):
        return tuple(getattr(info,name) for name in ('st_dev','st_ino','st_uid','st_gid','st_mode',
            'st_nlink','st_size','st_mtime_ns','st_ctime_ns'))

    @staticmethod
    def _names(fd):
        with os.scandir(fd) as entries:
            names = [entry.name for entry in itertools.islice(entries,1025)]
        require(len(names) <= 1024);return sorted(names)

    def _pin_snapshot(self, snapshot):
        """Retain only files from the fully replayed, unchanged original view."""
        require(self.entries is None and not self.retained);self.check()
        generation = snapshot['generation']['files']
        lifecycle = snapshot['lifecycle_files']
        paths = {self.directory/name: ('generation',identity) for name,identity in generation.items()}
        lifecycle_root = self.directory/'lifecycle-responsibility-v2'
        paths.update({lifecycle_root/name: ('lifecycle',identity) for name,identity in lifecycle['files'].items()})
        expected_names = {self.directory:sorted(HISTORY_NAMES),
            lifecycle_root:['heads','records'],lifecycle_root/'heads':[],lifecycle_root/'records':[],
            self.store:[],self.directory/'generation-transitions-v2':[],self.directory/'generation-receipts-v2':[]}
        for path in paths:
            require(path.parent in expected_names)
            if path.parent != self.directory:expected_names[path.parent].append(path.name)
        for path in expected_names:self._identity(path)
        for role,original in lifecycle['directories'].items():
            path = lifecycle_root if role == 'lifecycle' else lifecycle_root/role
            info = os.fstat(self.directories[path][0])
            # The shared directory identity already includes mtime and ctime.
            require(directory_identity(info,self.uid,self.gid) == original)
        generation_fields = ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_uid','st_mode','st_nlink')
        for path,(kind,original) in paths.items():
            fd = self._open(path,os.O_RDONLY)
            try:
                info = os.fstat(fd)
                require((tuple(getattr(info,name) for name in generation_fields) if kind == 'generation'
                    else self._file(info)) == original)
                self.retained[path] = fd
            except BaseException:os.close(fd);raise
        require(set(self.known) == set(paths))
        self.directory_metadata = {self.directory/name:identity for name,identity in snapshot['directories'].items()}
        self.entries = {path:sorted(names) for path,names in expected_names.items()}
        require(set(self.entries) == set(self.directories));self.check()

    def __enter__(self):self.check();return self

    def __exit__(self, *_):
        self.usable = False
        descriptors = [*self.retained.values(),*(fd for fd,_ in self.directories.values())]
        if self.lock is not None:descriptors.append(self.lock)
        self.lock = None;self.retained.clear();self.directories.clear()
        # Original descriptor loss is itself a refusal, but must not stop
        # closure of the other owned observers or mask the public refusal.
        for fd in descriptors:
            try:os.close(fd)
            except OSError:pass

    def retain(self, *_):raise RootLifecycleRefused('Read-only Root observation cannot retain records')


class _RootLifecycleHistory(NativeLifecycleHistory):
    def __init__(self, custody):
        self.uid,self.gid = custody.uid,custody.gid
        try:super().__init__(custody)
        except BaseException:
            self.close();raise

    def _directory(self, info):
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == self.uid and info.st_gid == self.gid)
        require(stat.S_IMODE(info.st_mode) == 0o700)
        return tuple(getattr(info,name) for name in ('st_dev','st_ino','st_uid','st_gid','st_mode'))

    def _file(self, info):
        return self.custody._file(info) if 0 < info.st_size <= 131072 else require(False)


class _RootGenerationHistory(NativeGenerationReader):
    def __init__(self, installation, scope, seal):
        # No ordinary constructor bypass: this separate internal view supplies
        # no worker admission, writes, live binding check or publication API.
        self.root = Path('/var/lib/gitgood/installations')/installation
        self.installation = installation;self.expected = seal['binding_sha256']
        self.custody = _RootReadOnlyCustody(installation,scope,seal)
        self.directory = self.root/'history';self.pointer = self.directory/'current-generation-v2.json'
        self.transitions = self.directory/'generation-transitions-v2'
        self.receipts = self.directory/'generation-receipts-v2'
        self.directory_identities = {};self.lifecycle_present = True;self._owns_custody = True

    def _layout(self):
        require({path.name for path in self._entries(self.directory)} == HISTORY_NAMES)
        for path in (self.custody.store,self.transitions,self.receipts,self.directory/'lifecycle-responsibility-v2'):
            identity = self.custody._identity(path)
            require(self.directory_identities.get(path,identity) == identity)
            self.directory_identities[path] = identity;self._entries(path)
        self._check()

    def _lifecycle_view(self):
        self._check();return _RootLifecycleHistory(self.custody)

    def _write(self, *_args, **_options):raise RootLifecycleRefused('Read-only Root history cannot write')
    def publish(self, **_options):raise RootLifecycleRefused('Read-only Root history cannot publish')
    def admit(self, **_options):raise RootLifecycleRefused('Root history supplies no ordinary worker admission')
    def borrow_custody(self, *_):raise RootLifecycleRefused('Root history cannot borrow caller custody')


class _RootPrivateInputs:
    """Fixed sealed files, read by Root without changing ordinary admission."""
    def __init__(self, directory, uid, gid, seal):
        self.directory = directory;self.uid,self.gid = uid,gid
        self.directory_fd = None;self.files = {};self.original = {};self.raw = {}
        self.policy = POLICIES[seal['purpose']]['files'];self.seal = copy.deepcopy(seal)
        try:
            self.custody = private_directory(directory,uid,gid)
            require(self.custody[0] == seal['directory_identity'])
            self.directory_fd = os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
            self.directory_original = directory_identity(os.fstat(self.directory_fd),uid,gid)
            require(directory_identity(directory.lstat(),uid,gid) == self.directory_original)
            require({'device':self.directory_original[0],'inode':self.directory_original[1],
                'uid':self.directory_original[2]} == seal['directory_identity'])
            for name,maximum in self.policy.items():
                fd = os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK,dir_fd=self.directory_fd)
                self.files[name] = fd
                before = file_identity(os.fstat(fd),uid,gid,maximum)
                raw = os.read(fd,maximum+1)
                require(len(raw) == before[2] and file_identity(os.fstat(fd),uid,gid,maximum) == before)
                require(file_record(before,raw) == seal['files'][name])
                self.original[name],self.raw[name] = before,raw
            self.check()
        except BaseException:self.close();raise

    def check(self):
        require(private_directory(self.directory,self.uid,self.gid) == self.custody)
        require(directory_identity(self.directory.lstat(),self.uid,self.gid) == self.directory_original)
        require(directory_identity(os.fstat(self.directory_fd),self.uid,self.gid) == self.directory_original)
        with os.scandir(self.directory_fd) as entries:
            names = [entry.name for entry in itertools.islice(entries,len(self.policy)+1)]
        require(set(names) == set(self.policy) and len(names) == len(self.policy))
        for name,maximum in self.policy.items():
            require(file_identity(os.fstat(self.files[name]),self.uid,self.gid,maximum) == self.original[name])
            require(file_identity(os.stat(name,dir_fd=self.directory_fd,follow_symlinks=False),self.uid,self.gid,maximum)
                == self.original[name])
            require(file_record(self.original[name],self.raw[name]) == self.seal['files'][name])
        return dict(self.raw)

    def close(self):
        for fd in self.files.values():os.close(fd)
        self.files.clear()
        if self.directory_fd is not None:os.close(self.directory_fd);self.directory_fd = None


class NativeRootLifecycleObservation:
    """UUID-only read-only view; any original-resource loss poisons this instance."""
    def __init__(self, installation, operation):
        self.usable = False;self.controller = None;self.history = None;self.inputs = None;self.root_files = {}
        try:
            identifier(installation);identifier(operation);require(installation != operation)
            self.owner = root_owner();self.installation = installation;self.operation = operation
            self.controller = NativeRootControllerObservation(installation);self.scope = self.controller.check()
            self.seal_directory = Path('/etc/gitgood/installations')/installation
            self.generation_seal = parse_generation_seal(self._root('generation-admission-v2.json',16384),installation,self.scope)
            self.worker = parse_worker_seal(self._root('lifecycle-worker-admission-v2.json',8192),installation,
                self.scope['uid'],self.scope['gid'])
            require(self.worker['operation'] == operation and self.worker['durable_binding_sha256'] == self.generation_seal['binding_sha256'])
            ownership = document(self._root('ownership-admission-v3.json',16384))
            require(set(ownership) == {'protocol','kind','installation','operation','candidate','binding_sha256'})
            require(type(ownership['protocol']) is int and ownership['protocol'] == 3
                and ownership['kind'] == 'native_application_ownership_seal')
            require(all(ownership[name] == self.worker[name] for name in ('installation','operation','candidate')))
            require(ownership['binding_sha256'] == self.worker['durable_binding_sha256'])
            operation_raw = self._root('operations/'+operation+'.json',8192)
            require(hashlib.sha256(operation_raw).hexdigest() == self.worker['inputs_seal_sha256'])
            command = {'protocol':2,'installation':installation,'operation':operation,
                'action':'enroll' if self.worker['purpose'] == 'native_initial_enrollment' else 'upgrade',
                'request_sha256':self.worker['request_sha256']}
            self.operation_seal = parse_seal(operation_raw,command,self.scope['uid'],self.scope['gid'])
            require(self.operation_seal['purpose'] == self.worker['purpose']
                and self.operation_seal['durable_binding_sha256'] == self.worker['durable_binding_sha256'])
            directory = Path('/var/lib/gitgood/operation-inputs')/installation/operation
            self.inputs = _RootPrivateInputs(directory,self.scope['uid'],self.scope['gid'],self.operation_seal)
            self.request = parse_request(self.inputs.raw['request.json'],self.operation_seal)
            for name,raw in self.inputs.raw.items():
                if name != 'request.json':require(type(document(raw).get('protocol')) is int and document(raw)['protocol'] == 2)
            self.history = _RootGenerationHistory(installation,self.scope,self.generation_seal)
            self.usable = True;self.original = self._snapshot()
            self.original_raw = canonical(self.original)
            self.history.custody._pin_snapshot(self.original);self.check()
        except BaseException:
            self.close();raise RootLifecycleRefused('Original native lifecycle unavailable or changed') from None

    def _root(self, relative, maximum):
        path = self.seal_directory/relative
        before = _CapturedRootFiles._fingerprint(path,maximum,False)
        identity,raw = root_file(path,maximum)
        require(_CapturedRootFiles._fingerprint(path,maximum,False) == before)
        self.root_files[path] = (maximum,before,identity,raw)
        return raw

    @_within_root_observation_pass
    def _current(self):
        require(self.usable and root_owner() == self.owner and self.controller.check() == self.scope)
        for path,(maximum,original,identity,raw) in self.root_files.items():
            require(_CapturedRootFiles._fingerprint(path,maximum,False) == original)
            require(root_file(path,maximum) == (identity,raw))
        require(canonical(self.generation_seal) == self.root_files[self.seal_directory/'generation-admission-v2.json'][3])
        require(canonical(self.worker) == self.root_files[self.seal_directory/'lifecycle-worker-admission-v2.json'][3])
        require(canonical(self.operation_seal) == self.root_files[self.seal_directory/'operations'/(self.operation+'.json')][3])
        require(parse_request(self.inputs.check()['request.json'],self.operation_seal) == self.request)
        self.history.custody.check()

    def _snapshot(self):
        self._current();custody = self.history.custody
        lifecycle_root = custody.directory/'lifecycle-responsibility-v2'
        for path in (custody.directory,custody.store,self.history.transitions,self.history.receipts,
                lifecycle_root,lifecycle_root/'records',lifecycle_root/'heads'):custody._identity(path)
        directories = {str(path.relative_to(custody.directory)):custody._directory_metadata(os.fstat(fd))
            for path,(fd,_) in custody.directories.items()}
        generation = self.history._snapshot(self.scope)
        view = self.history._lifecycle_view()
        try:
            record = view.snapshot(self.operation)
            require(record['origin']['request'] == self.request)
            require(record['origin']['request_sha256'] == self.worker['request_sha256'])
            require(record['origin']['inputs_seal_sha256'] == self.worker['inputs_seal_sha256'])
            require(record['status'] == 'running' and record['generation_sha256'] == generation['pointer']['generation_sha256'])
            require(generation_owner(generation['record']) == generation_owner({'scope':self.scope}))
            for operation in view.heads:
                if operation != self.operation:require(view.snapshot(operation)['status'] == 'complete')
            lifecycle_files = view.fingerprint();view.check()
        finally:view.close()
        self._current()
        require({str(path.relative_to(custody.directory)):custody._directory_metadata(os.fstat(fd))
            for path,(fd,_) in custody.directories.items()} == directories)
        return {'generation':generation,'lifecycle':record,'lifecycle_files':lifecycle_files,'directories':directories}

    @_within_root_observation_pass
    def check(self):
        try:
            require(self.usable and root_owner() == self.owner)
            self._current()
            require(canonical(self.original) == self.original_raw)
            self.history.custody.check()
            self._current()
            record = self.original['lifecycle']
            return {'installation':self.installation,'operation':self.operation,'candidate':self.worker['candidate'],
                'request_sha256':self.worker['request_sha256'],'generation_sha256':record['generation_sha256'],
                'snapshot_sha256':hashlib.sha256(canonical(record)).hexdigest(),
                'epoch':record['epoch'],'stage':record['stage'],'recorded_status':record['status'],
                'original_controller_and_complete_history_observed':True,
                'live_durable_resource_identity_verified':False,'lifecycle_exclusion_established':False,
                'stage_effect_authorized':False,'complete_journey_acceptance':False}
        except BaseException:
            self.close();raise RootLifecycleRefused('Original native lifecycle unavailable or changed') from None

    def close(self):
        self.usable = False
        if self.inputs is not None:self.inputs.close()
        if self.history is not None:self.history.close()
        if self.controller is not None:self.controller.close()
        # Original policies, private inputs, locks and histories remain intact.
