"""Original lifecycle responsibility under held OS custody; no stage authority."""
import copy
import hashlib
import itertools
import json
import os
import re
import stat
import uuid

from enrollment_journal import current_owner
from generation_custody import GenerationRecordCustody
from native_operation_inputs import POLICIES
from resource_generations import canonical, digest
from native_command_wire import identifier
from stage_native_artifact import publish_directory
from upgrade_journal import now, validate_time

STAGES = {
    'native_initial_enrollment': ('inspect', 'stage', 'migrate', 'bootstrap', 'verify', 'activate', 'enroll'),
    'native_upgrade_execution': ('inspect', 'stage', 'maintenance', 'migrate', 'verify', 'activate', 'public_verify'),
}
MAX_EVENTS, MAX_RECORDS, MAX_BYTES, MAX_OPERATIONS = 128, 1024, 131072, 128
HISTORY_NAMES = {'.upgrade-history-lock-v1', 'generation-records-v2', 'durable-binding-v2.json',
                 'current-generation-v2.json', 'generation-transitions-v2', 'generation-receipts-v2',
                 'lifecycle-responsibility-v2'}


class LifecycleResponsibilityRefused(Exception):
    pass


def require(value):
    if not value:
        raise LifecycleResponsibilityRefused('Native lifecycle responsibility unavailable or uncertain')


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def unique(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value)
        value[key] = item
    return value


def validate_request(value):
    require(type(value) is dict and set(value) == {'protocol', 'kind', 'installation', 'operation',
                                                'purpose', 'durable_binding_sha256', 'files'})
    require(type(value['protocol']) is int and value['protocol'] == 2 and value['kind'] == 'native_lifecycle_request')
    identifier(value['installation']);identifier(value['operation'])
    require(value['installation'] != value['operation'])
    require(type(value['purpose']) is str and value['purpose'] in STAGES)
    digest(value['durable_binding_sha256'])
    files = value['files'];policy = POLICIES[value['purpose']]['files']
    require(type(files) is dict and set(files) == set(policy) - {'request.json'})
    for name, item in files.items():
        require(type(item) is dict and set(item) == {'bytes', 'sha256'})
        require(type(item['bytes']) is int and 0 < item['bytes'] <= policy[name])
        digest(item['sha256'])
    require(len(canonical(value)) <= 16384)


def generation_owner(record):
    scope = record['scope'];manager = scope['manager']
    return {**{field: manager[field] for field in ['uid', 'pid', 'birth', 'mount_namespace', 'cgroup_namespace']},
            'boot_id': scope['boot_id']}


def validate_inventory(rows, heads, *, allow_incomplete=False):
    """Validate the complete retained graph, including operations off the tip."""
    operations = {row['operation'] for row in rows.values()}
    require(len(operations) <= MAX_OPERATIONS)
    children = {}
    for key, row in rows.items():
        previous = row['previous']
        if previous is None:require(row['events'] == 1)
        else:
            require(previous in rows and previous not in children)
            parent = rows[previous];require((row['operation'], row['origin'], row['events']-1, row['prefix_sha256']) ==
                                           (parent['operation'], parent['origin'], parent['events'], parent['events_sha256']))
            children[previous] = key
    for operation in operations:
        chain = {key: row for key, row in rows.items() if row['operation'] == operation}
        require(sum(row['previous'] is None for row in chain.values()) == 1 and len(chain) <= MAX_EVENTS)
        tips = [key for key in chain if key not in children];require(len(tips) == 1)
        if operation in heads:require(heads[operation]['snapshot_sha256'] in chain)
        if not allow_incomplete:require(operation in heads and heads[operation]['snapshot_sha256'] == tips[0])
    require(set(heads) <= operations)
    if not allow_incomplete:require(set(heads) == operations)


def replay(value, generations):
    """Validate recorded metadata only; a receipt hash proves no stage effect."""
    require(type(value) is dict and set(value) == {'protocol', 'kind', 'origin', 'predecessor_sha256',
            'generation_sha256', 'epoch', 'stage', 'status', 'completed', 'events'})
    require(type(value['protocol']) is int and value['protocol'] == 2 and value['kind'] == 'native_lifecycle_snapshot')
    origin = value['origin']
    require(type(origin) is dict and set(origin) == {'request', 'request_sha256', 'inputs_seal_sha256',
                                                  'generation_sha256', 'owner', 'created_at'})
    validate_request(origin['request']);digest(origin['inputs_seal_sha256'])
    require(sha(origin['request']) == origin['request_sha256'])
    require(origin['generation_sha256'] in generations)
    first = generations[origin['generation_sha256']]
    require(first['installation'] == origin['request']['installation'])
    require(first['durable_binding_sha256'] == origin['request']['durable_binding_sha256'])
    require(origin['owner'] == generation_owner(first));validate_time(origin['created_at'])
    if value['predecessor_sha256'] is not None:digest(value['predecessor_sha256'])
    events = value['events'];require(type(events) is list and 1 <= len(events) <= MAX_EVENTS)
    stages = STAGES[origin['request']['purpose']]
    status, stage, completed, epoch, generation = 'pending', None, [], 0, None
    for event in events:
        require(type(event) is dict and set(event) == {'kind', 'at', 'stage', 'epoch', 'generation_sha256', 'evidence'})
        validate_time(event['at']);require(type(event['epoch']) is int)
        observed = event['generation_sha256'];require(observed in generations)
        require(generations[observed]['durable_binding_sha256'] == first['durable_binding_sha256'])
        require(generations[observed]['installation'] == first['installation'])
        kind, evidence = event['kind'], event['evidence']
        require(type(evidence) is dict)
        if kind == 'claimed':
            require(status != 'complete' and event['epoch'] == epoch + 1 and event['stage'] == stage)
            require(set(evidence) == {'inputs_seal_sha256', 'continuity_sha256'})
            digest(evidence['inputs_seal_sha256'])
            if epoch == 0:
                require(observed == origin['generation_sha256'] and evidence['continuity_sha256'] is None)
                require(evidence['inputs_seal_sha256'] == origin['inputs_seal_sha256'])
            elif observed != generation:
                digest(evidence['continuity_sha256'])
                ancestor = observed;seen = set()
                while ancestor != generation:
                    require(ancestor in generations and ancestor not in seen and len(seen) < 128)
                    seen.add(ancestor);ancestor = generations[ancestor]['predecessor_sha256']
            else:require(evidence['continuity_sha256'] is None)
            epoch, generation = event['epoch'], observed
            if status == 'running':status = 'uncertain'
        else:
            require(epoch > 0 and event['epoch'] == epoch and observed == generation)
            if kind == 'started':
                require(status == 'pending' and len(completed) < len(stages) and evidence == {})
                stage = stages[len(completed)];require(event['stage'] == stage);status = 'running'
            elif kind in {'succeeded', 'reconciled'}:
                require(status == ('running' if kind == 'succeeded' else 'uncertain'))
                require(event['stage'] == stage and stage == stages[len(completed)])
                require(set(evidence) == ({'receipt_sha256'} if kind == 'succeeded' else {'receipt_sha256', 'applied'}))
                digest(evidence['receipt_sha256'])
                if kind == 'reconciled':require(type(evidence['applied']) is bool)
                if kind == 'succeeded' or evidence['applied']:completed.append(stage)
                status = 'complete' if len(completed) == len(stages) else 'pending'
            elif kind == 'failed':
                require(status == 'running' and event['stage'] == stage and evidence == {'code': 'stage_failed'})
                status = 'uncertain'
            else:require(False)
    require(type(value['epoch']) is int and value['epoch'] == epoch)
    require((value['generation_sha256'], value['stage'], value['status'], value['completed']) ==
            (generation, stage, status, completed))
    require(type(value['completed']) is list and len(canonical(value)) <= MAX_BYTES)
    return value


class NativeLifecycleResponsibility:
    """Low-level store borrowing original OS custody, never a controller API.

    Protected inputs/current publication, Root continuity, actual service and
    database/descendant fencing remain independent caller obligations. A claim
    or supplied receipt digest records responsibility; neither authorizes effects.
    """
    def __init__(self, custody, request, inputs_seal_sha256, generation_sha256, *, recover_publication=False):
        self.usable = False;self.descriptors = {};self.claimed = False
        try:
            require(type(custody) is GenerationRecordCustody);custody.check()
            require(type(recover_publication) is bool)
            validate_request(request);digest(inputs_seal_sha256);digest(generation_sha256)
            self.custody, self.request = custody, json.loads(canonical(request))
            self.inputs_seal = inputs_seal_sha256;self.generation = generation_sha256
            self.operation = request['operation'];self.owner = current_owner()
            self.generations = custody._records();require(generation_sha256 in self.generations)
            require(generation_owner(self.generations[generation_sha256]) == self.owner)
            require(request['installation'] == custody.installation)
            require(request['durable_binding_sha256'] == self.generations[generation_sha256]['durable_binding_sha256'])
            names = list(itertools.islice(custody.directory.iterdir(), 8))
            require(len(names) <= 7 and {path.name for path in names} <= HISTORY_NAMES)
            self._layout()
            self.usable = True;self.snapshot = None;self.head = None
            self.check()
            if recover_publication:self._recover_publication()
            self._load()
        except Exception:
            self.close()
            raise LifecycleResponsibilityRefused('Native lifecycle responsibility unavailable or uncertain') from None

    def _directory(self, fd):
        info = os.fstat(fd)
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700)
        return tuple(getattr(info, field) for field in ['st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode'])

    def _names(self, role, maximum):
        with os.scandir(self.descriptors[role]) as entries:
            names = [entry.name for entry in itertools.islice(entries, maximum+1)]
        require(len(names) <= maximum)
        return names

    def _layout(self):
        path = self.custody.directory
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        self.descriptors['history'] = fd
        require(dict(zip(['device', 'inode', 'uid'], self._directory(fd)[:3])) == self.custody.identity)
        parents = [('lifecycle', 'history', 'lifecycle-responsibility-v2'),
                   ('records', 'lifecycle', 'records'), ('heads', 'lifecycle', 'heads')]
        self.paths = {'history': path}
        for role, parent, name in parents:
            try:os.mkdir(name, 0o700, dir_fd=self.descriptors[parent]);os.fsync(self.descriptors[parent])
            except FileExistsError:pass
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=self.descriptors[parent])
            self.descriptors[role] = child;self.paths[role] = self.paths[parent]/name
        require(set(self._names('lifecycle', 2)) == {'records', 'heads'})
        self.identities = {role: self._directory(fd) for role, fd in self.descriptors.items()}
        self.custody.check()

    def check(self):
        try:
            require(self.usable and current_owner() == self.owner)
            self.custody.check()
            for role, fd in self.descriptors.items():
                require(self._directory(fd) == self.identities[role])
                info = self.paths[role].lstat()
                require(self.paths[role].resolve(strict=True) == self.paths[role])
                require(tuple(getattr(info, field) for field in ['st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode']) == self.identities[role])
            require(set(self._names('history', 7)) <= HISTORY_NAMES)
            require(set(self._names('lifecycle', 2)) == {'records', 'heads'})
            require(self.custody._records() == self.generations)
        except Exception:
            self.close();raise LifecycleResponsibilityRefused('Native lifecycle responsibility unavailable or uncertain') from None

    def _file(self, role, name, flags):
        fd = os.open(name, flags | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                     0o600, dir_fd=self.descriptors[role])
        try:
            opened = os.fstat(fd);named = os.stat(name, dir_fd=self.descriptors[role], follow_symlinks=False)
            require(stat.S_ISREG(opened.st_mode) and opened.st_uid == os.getuid() and opened.st_nlink == 1)
            require(stat.S_IMODE(opened.st_mode) == 0o600 and (opened.st_dev, opened.st_ino) == (named.st_dev, named.st_ino))
            return fd
        except Exception:os.close(fd);raise

    def _read(self, role, name):
        fd = self._file(role, name, os.O_RDONLY)
        with os.fdopen(fd, 'rb') as source:
            before = os.fstat(source.fileno());require(0 < before.st_size <= MAX_BYTES)
            raw = source.read(MAX_BYTES+1);after = os.fstat(source.fileno())
        fields = ['st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns']
        named = os.stat(name, dir_fd=self.descriptors[role], follow_symlinks=False)
        require(len(raw) == before.st_size and all(getattr(before, field) == getattr(after, field) == getattr(named, field) for field in fields))
        value = json.loads(raw, object_pairs_hook=unique);require(raw == canonical(value))
        return value

    def _inventory(self, *, allow_incomplete=False, skip_partials=False):
        self.check();rows = {};heads = {}
        for role, maximum in [('records', MAX_RECORDS), ('heads', MAX_OPERATIONS)]:
            names = self._names(role, maximum)
            for name in names:
                # Retain all partials. Their unresolved publication blocks new
                # responsibility; names/complete-looking bytes grant no replay.
                if name.startswith('.partial-'):
                    require(skip_partials);continue
                require(name.endswith('.json'))
                value = self._read(role, name)
                if role == 'records':
                    require(re.fullmatch(r'[0-9a-f]{64}\.json', name) and sha(value)+'.json' == name)
                    replay(value, self.generations)
                    operation = value['origin']['request']['operation']
                    rows[name[:-5]] = {'operation': operation, 'origin': sha(value['origin']),
                                      'previous': value['predecessor_sha256'], 'events': len(value['events']),
                                      'events_sha256': sha(value['events']), 'prefix_sha256': sha(value['events'][:-1])}
                else:
                    identifier(name[:-5]);require(type(value) is dict and set(value) == {'protocol', 'kind', 'installation', 'operation', 'snapshot_sha256'})
                    require(type(value['protocol']) is int and value['protocol'] == 2 and value['kind'] == 'native_lifecycle_head')
                    require(value['installation'] == self.custody.installation and value['operation'] == name[:-5])
                    digest(value['snapshot_sha256']);heads[name[:-5]] = value
        validate_inventory(rows, heads, allow_incomplete=allow_incomplete)
        self.check();return rows, heads

    def _load(self):
        rows, heads = self._inventory()
        for operation, head in heads.items():
            if operation != self.operation:
                require(self._read('records', head['snapshot_sha256']+'.json')['status'] == 'complete')
        mine = {key: row for key, row in rows.items() if row['operation'] == self.operation}
        if not mine:return
        require(self.operation in heads)
        head = heads[self.operation];require(not any(row['previous'] == head['snapshot_sha256'] for row in mine.values()))
        snapshot = self._read('records', head['snapshot_sha256']+'.json')
        require(snapshot['origin']['request'] == self.request and snapshot['origin']['inputs_seal_sha256'] == self.inputs_seal)
        self.snapshot, self.head = snapshot, head

    def _write(self, role, name, value, *, replace=False):
        self.check();raw = canonical(value);require(len(raw) <= MAX_BYTES)
        maximum = MAX_RECORDS if role == 'records' else MAX_OPERATIONS
        count = len(self._names(role, maximum))
        require(count <= maximum if replace else count < maximum)
        temporary = '.partial-'+str(uuid.uuid4());fd = self._file(role, temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        with os.fdopen(fd, 'wb') as output:output.write(raw);output.flush();os.fsync(output.fileno())
        self.check()
        # Both paths address the held original directory. No renamed pathname
        # can redirect a write into a replacement directory.
        fixed = '/proc/self/fd/'+str(self.descriptors[role])+'/'
        if replace:os.replace(temporary, name, src_dir_fd=self.descriptors[role], dst_dir_fd=self.descriptors[role])
        else:publish_directory(fixed+temporary, fixed+name)
        os.fsync(self.descriptors[role]);require(self._read(role, name) == value);self.check()

    def _recover_publication(self):
        """Repair exact retained metadata only; never infer or repeat an effect."""
        self.check()
        # Validate every candidate before moving any partial. Incomplete or
        # foreign bytes remain untouched and refuse recovery.
        partials = []
        for role, maximum in [('records', MAX_RECORDS), ('heads', MAX_OPERATIONS)]:
            for name in self._names(role, maximum):
                if not name.startswith('.partial-'):continue
                identifier(name.removeprefix('.partial-'))
                value = self._read(role, name)
                if role == 'records':
                    replay(value, self.generations)
                    require(value['origin']['request'] == self.request and value['origin']['inputs_seal_sha256'] == self.inputs_seal)
                else:
                    require(type(value) is dict and set(value) == {'protocol', 'kind', 'installation', 'operation', 'snapshot_sha256'})
                    require(type(value['protocol']) is int and value['protocol'] == 2 and value['kind'] == 'native_lifecycle_head')
                    require(value['installation'] == self.custody.installation and value['operation'] == self.operation)
                    digest(value['snapshot_sha256'])
                partials.append((role, name, value))
        require(len(partials) <= 1)
        rows, heads = self._inventory(allow_incomplete=True, skip_partials=True)
        for role, name, value in partials:
            if role == 'records':
                previous = value['predecessor_sha256']
                if previous is None:require(not any(row['operation'] == self.operation for row in rows.values()))
                else:
                    require(previous in rows and not any(row['previous'] == previous for row in rows.values()))
                    parent = rows[previous]
                    require((parent['operation'], parent['origin'], parent['events']+1, parent['events_sha256']) ==
                            (self.operation, sha(value['origin']), len(value['events']), sha(value['events'][:-1])))
                target = sha(value)+'.json'
            else:
                key = value['snapshot_sha256'];require(key in rows and rows[key]['operation'] == self.operation)
                require(not any(row['previous'] == key for row in rows.values()))
                snapshot = self._read('records', key+'.json')
                require(snapshot['origin']['request'] == self.request and snapshot['origin']['inputs_seal_sha256'] == self.inputs_seal)
                old = heads.get(self.operation)
                require(snapshot['predecessor_sha256'] == (old['snapshot_sha256'] if old else None))
                target = self.operation+'.json'
            # No overwrite or removal. The original partial inode becomes the
            # immutable record (or mutable head) after synchronization.
            fd = self._file(role, name, os.O_RDONLY)
            try:os.fsync(fd)
            finally:os.close(fd)
            self.check()
            if role == 'records':
                fixed = '/proc/self/fd/'+str(self.descriptors[role])+'/'
                publish_directory(fixed+name, fixed+target)
            else:os.replace(name, target, src_dir_fd=self.descriptors[role], dst_dir_fd=self.descriptors[role])
            os.fsync(self.descriptors[role]);require(self._read(role, target) == value)
        rows, heads = self._inventory(allow_incomplete=True)
        mine = {key: row for key, row in rows.items() if row['operation'] == self.operation}
        for operation, head in heads.items():
            if operation != self.operation:
                require(self._read('records', head['snapshot_sha256']+'.json')['status'] == 'complete')
                require(not any(row['previous'] == head['snapshot_sha256'] for row in rows.values()))
        require(set(row['operation'] for row in rows.values()) <= set(heads) | {self.operation})
        if not mine:return
        parents = {row['previous'] for row in mine.values()}
        tips = [key for key in mine if key not in parents];require(len(tips) == 1)
        key = tips[0];value = self._read('records', key+'.json')
        require(value['origin']['request'] == self.request and value['origin']['inputs_seal_sha256'] == self.inputs_seal)
        head = heads.get(self.operation)
        if head and head['snapshot_sha256'] == key:return
        require(value['predecessor_sha256'] == (head['snapshot_sha256'] if head else None))
        pointer = {'protocol': 2, 'kind': 'native_lifecycle_head', 'installation': self.custody.installation,
                   'operation': self.operation, 'snapshot_sha256': key}
        self._write('heads', self.operation+'.json', pointer, replace=head is not None)

    def _owned(self):
        self.check();require(self.claimed and self.snapshot is not None)
        rows, heads = self._inventory();require(heads.get(self.operation) == self.head)
        require(self._read('records', self.head['snapshot_sha256']+'.json') == self.snapshot)
        require(self.snapshot['generation_sha256'] == self.generation and self.snapshot['status'] != 'complete')
        require(len(self.snapshot['events']) < MAX_EVENTS)

    def _append(self, kind, *, stage=None, evidence=None):
        before = copy.deepcopy(self.snapshot)
        value = copy.deepcopy(before)
        value['predecessor_sha256'] = sha(before) if before['events'] else None
        epoch = before['epoch']+1 if kind == 'claimed' else before['epoch']
        event = {'kind': kind, 'at': now(), 'stage': before['stage'] if kind == 'claimed' else stage,
                 'epoch': epoch, 'generation_sha256': self.generation, 'evidence': evidence or {}}
        value['events'].append(event)
        if kind == 'claimed':
            value.update(epoch=epoch, generation_sha256=self.generation)
            if value['status'] == 'running':value['status'] = 'uncertain'
        elif kind == 'started':value.update(stage=stage, status='running')
        elif kind == 'failed':value['status'] = 'uncertain'
        else:
            if kind == 'succeeded' or evidence['applied']:value['completed'].append(stage)
            value['status'] = 'complete' if len(value['completed']) == len(STAGES[self.request['purpose']]) else 'pending'
        replay(value, self.generations)
        try:
            key = sha(value);self._write('records', key+'.json', value)
            head = {'protocol': 2, 'kind': 'native_lifecycle_head', 'installation': self.custody.installation,
                    'operation': self.operation, 'snapshot_sha256': key}
            self._write('heads', self.operation+'.json', head, replace=self.head is not None)
            self.snapshot, self.head = value, head
        except Exception:
            self.close();raise LifecycleResponsibilityRefused('Native lifecycle responsibility unavailable or uncertain') from None

    def claim(self, *, continuity_sha256=None, current_inputs_seal_sha256=None):
        self.check()
        if self.snapshot is not None and self.snapshot['status'] == 'complete':return self.status()
        if self.claimed:self._owned();return self.status()
        sealed = self.inputs_seal if current_inputs_seal_sha256 is None else current_inputs_seal_sha256;digest(sealed)
        if self.snapshot is None:
            require(continuity_sha256 is None and sealed == self.inputs_seal)
            self.snapshot = {'protocol': 2, 'kind': 'native_lifecycle_snapshot',
                'origin': {'request': self.request, 'request_sha256': sha(self.request), 'inputs_seal_sha256': self.inputs_seal,
                           'generation_sha256': self.generation, 'owner': self.owner, 'created_at': now()},
                'predecessor_sha256': None, 'generation_sha256': self.generation, 'epoch': 0,
                'stage': None, 'status': 'pending', 'completed': [], 'events': []}
        self._append('claimed', evidence={'continuity_sha256': continuity_sha256, 'inputs_seal_sha256': sealed})
        self.claimed = True;return self.status()

    def begin(self, stage):
        self._owned();require(self.snapshot['status'] == 'pending')
        rows, _ = self._inventory()
        require(len(rows)+3 <= MAX_RECORDS and len(self.snapshot['events'])+3 <= MAX_EVENTS)
        require(stage == STAGES[self.request['purpose']][len(self.snapshot['completed'])])
        self._append('started', stage=stage)

    def succeed(self, stage, receipt_sha256):
        self._owned();digest(receipt_sha256)
        require(self.snapshot['status'] == 'running' and self.snapshot['stage'] == stage)
        self._append('succeeded', stage=stage, evidence={'receipt_sha256': receipt_sha256})

    def fail(self, stage):
        self._owned();require(self.snapshot['status'] == 'running' and self.snapshot['stage'] == stage)
        self._append('failed', stage=stage, evidence={'code': 'stage_failed'})

    def reconcile(self, *, applied, receipt_sha256):
        self._owned();require(type(applied) is bool and self.snapshot['status'] == 'uncertain');digest(receipt_sha256)
        self._append('reconciled', stage=self.snapshot['stage'], evidence={'applied': applied, 'receipt_sha256': receipt_sha256})

    def status(self):
        self.check();require(self.snapshot is not None)
        _, heads = self._inventory();require(heads.get(self.operation) == self.head)
        return {'operation': self.operation, 'recorded_status': self.snapshot['status'], 'stage': self.snapshot['stage'],
                'completed': list(self.snapshot['completed']), 'epoch': self.snapshot['epoch'],
                'snapshot_sha256': self.head['snapshot_sha256'], 'responsibility_recorded': True,
                'writer_exclusion_established': False, 'stage_effect_authorized': False,
                'generation_publication_established': False, 'installation_readiness_established': False}

    def close(self):
        self.usable = False
        for fd in self.descriptors.values():os.close(fd)
        self.descriptors.clear()
        # Borrowed original OS custody belongs to its caller. Retain every file.
