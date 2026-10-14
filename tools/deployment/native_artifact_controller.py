"""Actual ordinary controller inspection under original history/writer custody.

This does not admit application workers, dispatch Root staging or reconcile
interrupted stage effects. A stage request remains unexecuted until Root accepts.
"""
import gzip
import hashlib
import json
import os
from pathlib import Path
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
            ('running','inspect',[]),('pending','inspect',['inspect']),('running','stage',['inspect'])))
        for operation in view.heads:
            if operation != request['operation']:require(view.snapshot(operation)['status'] == 'complete')
        snapshot['lifecycle'] = json.loads(canonical(record))
        require(self.inputs.check() == inputs and self._fingerprint() == snapshot['files'])
        view.check();self._check();return snapshot

    def admit(self, **_):raise ArtifactControllerRefused('Controller inspection supplies no worker admission')


class NativeArtifactInspectionController:
    """Borrow original controller resources; own only this inspection session."""
    def __init__(self, installation, custody, endpoint, journal):
        self.usable = False;self.reader = None;self.exclusion = None;self.archive = None
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
        if self.reader is not None:self.reader.close()
        self.reader = _ArtifactControllerReader(str(self.root),self.installation,self.seal['binding_sha256'],
            self.seal['history_identity'],self.seal['lock_identity'],self.seal['unit_sha256'],self.seal['executables'],
            worker='maintenance',**self.seal['limits'])
        self.reader.borrow_custody(self.custody);self.snapshot = self.reader._snapshot(self.scope)

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
            require(fingerprint(os.fstat(self.archive)) == self.archive_original == fingerprint(self.source.lstat()))
            stopped(self.scope);require(self.exclusion.check() == self.held)
            return {'installation':self.installation,'operation':self.operation,'candidate':self.inputs['candidate'],
                'stage':self.state,'original_controller_and_exclusion_observed':True,
                'artifact_inspected':self.state in {'inspected','stage'},'artifact_staged':False,
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

    def close(self):
        self.usable = False
        if self.archive is not None:os.close(self.archive);self.archive = None
        if self.reader is not None:self.reader.close()
        if self.exclusion is not None:self.exclusion.close()
        # Borrowed endpoint, journal and original history custody remain owned
        # by the actual controller; every input, archive and record remains.
