"""Actual ordinary controller inspection under original history/writer custody.

This does not admit application workers, dispatch Root staging or reconcile
interrupted stage effects. A stage request remains unexecuted until Root accepts.
"""
import gzip
import hashlib
import itertools
import json
import os
from pathlib import Path, PurePosixPath
import socket
import stat
import tarfile
import threading

from generation_custody import GenerationRecordCustody
from generation_publication import stopped
from inspect_native_artifact import inspect_native_artifact
from native_command_endpoint import NativeCommandEndpoint
from native_durable_binding import configuration, persistent_identity
from native_generation_lease_guard import persistent_fingerprint
from native_generation_reader import NativeGenerationReader
from native_lifecycle_generation_reader import NativeLifecycleGenerationReader
from native_lifecycle_responsibility import NativeLifecycleResponsibility
from native_protected_artifact import _BoundedTarHeaders, MAX_CONTENT, MAX_MEMBERS, fingerprint
from native_root_artifact_policy import _declaration, _inspection_receipt
from native_root_lifecycle import parse_generation_seal
from native_service_scope import _CapturedRootFiles, root_file
from native_writer_exclusion import NativeWriterExclusion
from resource_generations import canonical, identifier


class ArtifactControllerRefused(Exception):
    pass


def require(value):
    if not value:
        raise ArtifactControllerRefused('Original native artifact controller unavailable or changed')


def _owned_journal_refresh(previous, current, journal):
    """Only the controller's one just-published event may refresh observation."""
    for name in ('binding','pointer','record','records','transitions','receipts'):
        require(current[name] == previous[name] and canonical(current[name]) == canonical(previous[name]))
    before,after = previous['lifecycle'],current['lifecycle']
    require(after == journal.snapshot and canonical(after) == canonical(journal.snapshot))
    require(after['predecessor_sha256'] == hashlib.sha256(canonical(before)).hexdigest())
    require(len(after['events']) == len(before['events'])+1 and after['events'][:-1] == before['events'])
    require(after['events'][-1]['kind'] in {'succeeded','started'})
    require(journal.head['snapshot_sha256'] == hashlib.sha256(canonical(after)).hexdigest())
    require(set(previous['files']) == set(current['files']))
    for name in previous['files']:
        if name != '@lifecycle':require(current['files'][name] == previous['files'][name])
    old,new = previous['files']['@lifecycle'],current['files']['@lifecycle']
    require(set(old['directories']) == set(new['directories']))
    for role in old['directories']:require(old['directories'][role][:-2] == new['directories'][role][:-2])
    head = 'heads/'+journal.operation+'.json';record = 'records/'+journal.head['snapshot_sha256']+'.json'
    require(set(new['files']) == set(old['files']) | {record})
    require(record not in old['files'] and head in old['files'])
    for name in old['files']:
        if name != head:require(new['files'][name] == old['files'][name])


class _ArtifactControllerReader(NativeLifecycleGenerationReader):
    """Separate controller window; ordinary worker admission is unchanged."""
    def _snapshot(self, scope):
        snapshot = NativeGenerationReader._snapshot(self,scope)
        inputs = self.inputs.check();request = inputs['request']
        require(request['durable_binding_sha256'] == self.expected)
        require((scope['uid'],scope['gid']) == (self.inputs.seal['uid'],self.inputs.seal['gid']))
        view = self._view();record = view.snapshot(request['operation'])
        require(record['origin']['request'] == request)
        require(record['origin']['inputs_seal_sha256'] == inputs['inputs_seal_sha256'])
        require(record['origin']['request_sha256'] == inputs['request_sha256'])
        require(record['generation_sha256'] == snapshot['pointer']['generation_sha256'])
        require((record['status'],record['stage'],record['completed']) in (
            ('running','inspect',[]),('pending','inspect',['inspect']),('running','stage',['inspect']),
            ('pending','stage',['inspect','stage'])))
        for operation in view.heads:
            if operation != request['operation']:require(view.snapshot(operation)['status'] == 'complete')
        snapshot['lifecycle'] = json.loads(canonical(record))
        require(self.inputs.check() == inputs and self._fingerprint() == snapshot['files'])
        view.check();self._check();return snapshot

    def admit(self, **_):raise ArtifactControllerRefused('Controller inspection supplies no worker admission')


class NativeArtifactInspectionController:
    """Borrow original controller resources; own only this inspection session."""
    def __init__(self, installation, custody, endpoint, journal):
        self.usable = False;self.reader = None;self.exclusion = None;self.archive = None;self.source_parents = {}
        try:
            identifier(installation)
            require(os.getuid() == os.geteuid() > 0 and os.getgid() == os.getegid() > 0)
            require(type(custody) is GenerationRecordCustody and type(endpoint) is NativeCommandEndpoint
                and type(journal) is NativeLifecycleResponsibility)
            custody.check();endpoint.check();journal._owned()
            require(journal.custody is custody and custody.installation == endpoint.scope.installation == installation)
            self.installation = installation;self.custody,self.endpoint,self.journal = custody,endpoint,journal
            self.owner = (os.getpid(),threading.get_ident());self.scope = endpoint.scope.check()
            require(self.scope['manager']['pid'] == os.getpid())
            self.policy_path = Path('/etc/gitgood/installations')/installation/'generation-admission-v2.json'
            self.policy_metadata = _CapturedRootFiles._fingerprint(self.policy_path,16384,False)
            self.policy_identity,self.policy_raw = root_file(self.policy_path,16384)
            require(_CapturedRootFiles._fingerprint(self.policy_path,16384,False) == self.policy_metadata)
            self.seal = parse_generation_seal(self.policy_raw,installation,self.scope)
            self.root = Path('/var/lib/gitgood/installations')/installation
            self._open_reader()
            require(self.snapshot['lifecycle']['status'] == 'running' and self.snapshot['lifecycle']['stage'] == 'inspect')
            self.inputs = self.reader.inputs.check();self.operation = self.inputs['request']['operation']
            require(journal.request == self.inputs['request'] and journal.inputs_seal == self.inputs['inputs_seal_sha256'])
            require(journal.generation == self.snapshot['pointer']['generation_sha256'])
            self.binding = self.snapshot['binding'];self.files = persistent_fingerprint(self.binding)
            require(self.binding['database'] == self.seal['database'])
            require(persistent_identity(self.root,self.scope,self.seal['executables']) == self.binding)
            self.configuration,self.url = configuration(self.root,installation,self.scope['uid'])
            require(self.configuration == self.binding['configuration'])
            observed = {'installation':installation,'operation':self.operation,'candidate':self.inputs['candidate']}
            name = 'inputs.json' if self.journal.request['purpose'] == 'native_initial_enrollment' else 'plan.json'
            self.declaration = _declaration(self.reader.inputs._private_payloads()[name]['artifact'],observed)
            self.source = Path('/var/lib/gitgood/artifact-inputs')/installation/self.operation/'archive.tar.gz'
            for path in self.source.parents:
                info = path.lstat();require(path.resolve(strict=True) == path and stat.S_ISDIR(info.st_mode)
                    and info.st_uid == info.st_gid == 0 and not info.st_mode & 0o022)
                self.source_parents[path] = (info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode)
            self.archive = os.open(self.source,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
            info = os.fstat(self.archive)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == info.st_gid == 0 and info.st_nlink == 1
                and not info.st_mode & 0o222 and info.st_size == self.declaration['bytes'])
            self.archive_original = fingerprint(info)
            stopped(self.scope)
            self.exclusion = NativeWriterExclusion(self.seal['executables']['psql'],self.url,self.binding['database'])
            self.exclusion.__enter__();self.held = self.exclusion.check()
            self.state = 'inspect';self.usable = True;self.check()
        except BaseException:
            self.close();raise ArtifactControllerRefused('Original native artifact controller unavailable or changed') from None

    def _open_reader(self):
        previous = getattr(self,'snapshot',None)
        if self.reader is not None:self.reader.close()
        self.reader = _ArtifactControllerReader(str(self.root),self.installation,self.seal['binding_sha256'],
            self.seal['history_identity'],self.seal['lock_identity'],self.seal['unit_sha256'],self.seal['executables'],
            worker='maintenance',**self.seal['limits'])
        self.reader.borrow_custody(self.custody);current = self.reader._snapshot(self.scope)
        if previous is not None:_owned_journal_refresh(previous,current,self.journal)
        self.snapshot = current

    def check(self):
        try:
            require(self.usable and self.owner == (os.getpid(),threading.get_ident()))
            require(os.getuid() == os.geteuid() == self.scope['uid'] and os.getgid() == os.getegid() == self.scope['gid'])
            self.custody.check();self.endpoint.check();self.journal._owned()
            require(self.endpoint.scope.check() == self.scope)
            require(_CapturedRootFiles._fingerprint(self.policy_path,16384,False) == self.policy_metadata)
            require(root_file(self.policy_path,16384) == (self.policy_identity,self.policy_raw))
            require(self.reader._snapshot(self.scope) == self.snapshot)
            require(self.reader.inputs.check() == self.inputs)
            require(self.journal.head['snapshot_sha256'] == hashlib.sha256(canonical(self.snapshot['lifecycle'])).hexdigest())
            require(persistent_fingerprint(self.binding) == self.files)
            require(configuration(self.root,self.installation,self.scope['uid']) == (self.configuration,self.url))
            for path,original in self.source_parents.items():
                info = path.lstat();require(path.resolve(strict=True) == path and
                    (info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode) == original)
            require(fingerprint(os.fstat(self.archive)) == self.archive_original == fingerprint(self.source.lstat()))
            stopped(self.scope);require(self.exclusion.check() == self.held)
            return {'installation':self.installation,'operation':self.operation,'candidate':self.inputs['candidate'],
                'stage':self.state,'original_controller_and_exclusion_observed':True,
                'artifact_inspected':self.state in {'inspected','stage','staged'},'artifact_staged':self.state == 'staged',
                'stage_effect_authorized':False,'complete_journey_acceptance':False}
        except BaseException:
            self.close();raise ArtifactControllerRefused('Original native artifact controller unavailable or changed') from None

    def inspect(self):
        try:
            self.check();require(self.state == 'inspect');os.lseek(self.archive,0,os.SEEK_SET)
            count = 0;total = 0
            with os.fdopen(os.dup(self.archive),'rb') as source,gzip.GzipFile(fileobj=source,mode='rb') as expanded:
                with tarfile.open(fileobj=_BoundedTarHeaders(expanded),mode='r:') as archive:
                    for member in archive:
                        count += 1;total += member.size
                        require(count <= MAX_MEMBERS and 0 <= member.size <= 128*1024**2 and total <= MAX_CONTENT)
                        require(len(member.name) <= 1024 and (not member.issym() or member.name.startswith('forge/')))
            inspected = inspect_native_artifact(self.source,self.declaration['sha256'],self.inputs['candidate'])
            self.check()
            receipt = _inspection_receipt(self.installation,self.operation,inspected)
            self.inspection_result = json.loads(canonical(inspected))
            self.journal.succeed('inspect',hashlib.sha256(canonical(receipt)).hexdigest())
            self._open_reader();self.state = 'inspected';self.check()
            return receipt
        except BaseException:
            self.close();raise ArtifactControllerRefused('Original native artifact inspection failed; retain running responsibility') from None

    def begin_stage(self):
        try:
            self.check();require(self.state == 'inspected')
            self.journal.begin('stage');self._open_reader();self.state = 'stage';self.check()
            return canonical({'protocol':2,'kind':'native_root_controller_request','installation':self.installation,
                'operation':self.operation,'history_lock_fd':self.custody.lock})+b'\n'
        except BaseException:
            self.close();raise ArtifactControllerRefused('Original native artifact stage request unavailable; retain responsibility') from None

    def _staged_output(self, response):
        """Independently read fixed Root output before the owned journal advances."""
        require(type(response) is dict and set(response) == {'protocol','kind','status','installation',
            'operation','candidate','receipt_sha256'})
        require(type(response['protocol']) is int and response['protocol'] == 2
            and response['kind'] == 'native_root_artifact_result' and response['status'] == 'staged')
        require((response['installation'],response['operation'],response['candidate']) ==
            (self.installation,self.operation,self.inputs['candidate']))
        require(type(response['receipt_sha256']) is str and len(response['receipt_sha256']) == 64
            and all(char in '0123456789abcdef' for char in response['receipt_sha256']))
        base = Path('/opt/gitgood/artifacts')/self.installation/('native-'+self.operation)
        directories = {}
        def directory(path):
            info = path.lstat()
            require(path.resolve(strict=True) == path and stat.S_ISDIR(info.st_mode)
                and info.st_uid == info.st_gid == 0 and not info.st_mode & 0o222)
            directories[path] = fingerprint(info)
            return {'device':info.st_dev,'inode':info.st_ino,'uid':0}
        for path in base.parents:
            info = path.lstat();require(path.resolve(strict=True) == path and stat.S_ISDIR(info.st_mode)
                and info.st_uid == info.st_gid == 0 and not info.st_mode & 0o022)
            directories[path] = fingerprint(info)[:5]
        output_identity = directory(base)
        def document(name,maximum):
            path = base/name;before = fingerprint(path.lstat());_,raw = root_file(path,maximum)
            require(before == fingerprint(path.lstat()) and before[2] == before[3] == 0 and not before[4] & 0o222)
            value = json.loads(raw);require(canonical(value) == raw)
            return value,raw,before
        receipt,raw,receipt_identity = document('receipt.json',8*1024**2)
        inventory,inventory_raw,inventory_identity = document('inventory.json',16*1024**2)
        require(set(receipt) == {'protocol','kind','status','installation','operation','candidate','scope_sha256',
            'request_sha256','snapshot_sha256','artifact_sha256','inventory_sha256','allocation_budget_bytes',
            'output_directory_identity','code_directories','root_controlled_code','complete_journey_acceptance'})
        require(type(receipt['protocol']) is int and receipt['protocol'] == 2
            and receipt['kind'] == 'native_protected_artifact_stage_receipt' and receipt['status'] == 'staged')
        require((receipt['installation'],receipt['operation'],receipt['candidate']) ==
            (self.installation,self.operation,self.inputs['candidate']))
        require(hashlib.sha256(raw).hexdigest() == response['receipt_sha256'])
        require(receipt['artifact_sha256'] == self.declaration['sha256']
            and receipt['scope_sha256'] == hashlib.sha256(canonical(self.scope)).hexdigest()
            and receipt['request_sha256'] == self.inputs['request_sha256']
            and receipt['snapshot_sha256'] == self.journal.head['snapshot_sha256'])
        require(receipt['root_controlled_code'] is True and receipt['complete_journey_acceptance'] is False
            and receipt['output_directory_identity'] == output_identity)
        require(hashlib.sha256(inventory_raw).hexdigest() == receipt['inventory_sha256'])
        require(type(inventory) is list and 0 < len(inventory) <= MAX_MEMBERS)
        indexed = {}
        for item in inventory:
            require(type(item) is dict and type(item.get('path')) is str and item['path'] not in indexed)
            indexed[item['path']] = item
        code = base/'code';declared_directories = receipt['code_directories']
        require(type(declared_directories) is dict and '' in declared_directories
            and len(declared_directories) <= MAX_MEMBERS)
        def relative(name,empty=False):
            require(type(name) is str and len(name) <= 1024 and '\\' not in name and '\0' not in name)
            require(empty and name == '' or name and not name.startswith('/')
                and str(PurePosixPath(name)) == name and all(part not in {'.','..'} for part in name.split('/')))
            return name
        expected = {name:set() for name in declared_directories}
        for name,identity in declared_directories.items():
            relative(name,empty=True);require(directory(code/name) == identity)
            if name:
                parent = str(PurePosixPath(name).parent);parent = '' if parent == '.' else parent
                require(parent in expected);expected[parent].add(PurePosixPath(name).name)
        files = {};total = 0;names = []
        for item in inventory:
            require(type(item) is dict and set(item) in ({'path','bytes','sha256','executable','identity'},
                {'path','symlink','identity'}))
            name = relative(item['path']);require(name not in files and name not in declared_directories)
            names.append(name);parent = str(PurePosixPath(name).parent);parent = '' if parent == '.' else parent
            require(parent in expected);expected[parent].add(PurePosixPath(name).name)
            path = code/name;before = fingerprint(path.lstat())
            require(list(before) == item['identity'] and before[2] == before[3] == 0 and before[5] == 1)
            if 'symlink' in item:
                require(name.startswith('forge/') and stat.S_ISLNK(before[4])
                    and os.readlink(path) == item['symlink'])
                resolved = path.resolve(strict=True);require(resolved.is_relative_to(code))
                target = str(resolved.relative_to(code));require(target in indexed and 'bytes' in indexed[target])
            else:
                require(stat.S_ISREG(before[4]) and type(item['bytes']) is int
                    and 0 <= item['bytes'] <= 128*1024**2 and item['bytes'] == before[6]
                    and type(item['executable']) is bool
                    and stat.S_IMODE(before[4]) == (0o555 if item['executable'] else 0o444))
                fd = os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
                with os.fdopen(fd,'rb') as source:
                    require(fingerprint(os.fstat(source.fileno())) == before)
                    require(hashlib.file_digest(source,'sha256').hexdigest() == item['sha256'])
                    require(fingerprint(os.fstat(source.fileno())) == before)
                total += item['bytes'];require(total <= MAX_CONTENT)
            require(fingerprint(path.lstat()) == before);files[path] = before
        require(names == sorted(names))
        for name in declared_directories:
            with os.scandir(code/name) as entries:
                observed = {entry.name for entry in itertools.islice(entries,MAX_MEMBERS+1)}
            require(observed == expected[name])
        inspection = self.inspection_result
        actual_inspect_sha = hashlib.sha256(canonical(_inspection_receipt(self.installation,self.operation,inspection))).hexdigest()
        require(any(event['stage'] == 'inspect' and event['kind'] == 'succeeded'
            and event['evidence']['receipt_sha256'] == actual_inspect_sha for event in self.snapshot['lifecycle']['events']))
        require(total <= inspection['declared_bytes'] and len(inventory)+len(declared_directories)-1 == inspection['members'])
        require(type(receipt['allocation_budget_bytes']) is int and receipt['allocation_budget_bytes'] ==
            self.declaration['bytes']+inspection['declared_bytes']+inspection['members']*8192+33554432)
        archive = base/'archive.tar.gz';before = fingerprint(archive.lstat())
        require(stat.S_ISREG(before[4]) and before[2] == before[3] == 0 and before[5] == 1
            and stat.S_IMODE(before[4]) == 0o444 and before[6] == self.declaration['bytes'])
        fd = os.open(archive,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as source:
            require(fingerprint(os.fstat(source.fileno())) == before)
            require(hashlib.file_digest(source,'sha256').hexdigest() == self.declaration['sha256'])
            require(fingerprint(os.fstat(source.fileno())) == before)
        files[archive] = before;files[base/'receipt.json'] = receipt_identity;files[base/'inventory.json'] = inventory_identity
        with os.scandir(base) as entries:require({entry.name for entry in itertools.islice(entries,5)} == {'code','archive.tar.gz','receipt.json','inventory.json'})
        for path,original in directories.items():require(fingerprint(path.lstat())[:len(original)] == original)
        for path,original in files.items():require(fingerprint(path.lstat()) == original)
        self.check();return receipt

    def stage(self):
        """Fixed Root endpoint, actual peer and output; no caller authority data."""
        try:
            frame = self.begin_stage()
            path = Path('/run/gitgood/root-artifacts')/(self.installation+'.sock')
            parents = {}
            for parent in path.parents:
                info = parent.lstat();require(parent.resolve(strict=True) == parent and stat.S_ISDIR(info.st_mode)
                    and info.st_uid == info.st_gid == 0 and not info.st_mode & 0o022)
                parents[parent] = fingerprint(info)[:5]
            original = fingerprint(path.lstat())
            require(stat.S_ISSOCK(original[4]) and original[2] == 0 and original[3] == self.scope['gid']
                and stat.S_IMODE(original[4]) == 0o620 and original[5] == 1)
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
                connection.settimeout(240);connection.connect(str(path))
                import struct
                peer = struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                require(peer[0] > 0 and peer[1:] == (0,0))
                require(fingerprint(path.lstat()) == original);self.check()
                connection.sendall(frame);connection.shutdown(socket.SHUT_WR)
                raw = bytearray()
                while b'\n' not in raw:
                    block = connection.recv(513-len(raw));require(block);raw.extend(block);require(len(raw) <= 512)
                require(raw.endswith(b'\n') and raw.count(b'\n') == 1)
                response = json.loads(raw);require(canonical(response)+b'\n' == raw)
                require(struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12)) == peer)
            require(fingerprint(path.lstat()) == original)
            for parent,identity in parents.items():require(fingerprint(parent.lstat())[:5] == identity)
            self.check();receipt = self._staged_output(response)
            self.journal.succeed('stage',hashlib.sha256(canonical(receipt)).hexdigest())
            self._open_reader();self.state = 'staged';self.check();return receipt
        except BaseException:
            self.close();raise ArtifactControllerRefused('Original native artifact stage unavailable; retain responsibility and effects') from None

    def close(self):
        self.usable = False
        if self.archive is not None:os.close(self.archive);self.archive = None
        if self.reader is not None:self.reader.close()
        if self.exclusion is not None:self.exclusion.close()
        # Borrowed endpoint, journal and original history custody remain owned
        # by the actual controller; every input, archive and record remains.
