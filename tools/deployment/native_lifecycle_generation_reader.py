"""Explicit stage worker admission; no lifecycle effects or readiness grant."""
import itertools
from pathlib import Path

from generation_publication import require, sha
from native_generation_reader import NativeGenerationReader, GenerationAdmissionRefused
from native_lifecycle_history import NativeLifecycleHistory
from native_lifecycle_worker_inputs import NativeLifecycleWorkerInputs, worker_seal_path

STAGE_WORKERS = {
    'native_initial_enrollment': {'native': frozenset({'verify', 'activate', 'enroll'}),
                                 'maintenance': frozenset({'migrate', 'bootstrap'})},
    'native_upgrade_execution': {'native': frozenset({'verify', 'activate', 'public_verify'}),
                                'maintenance': frozenset({'migrate'})},
}


class NativeLifecycleGenerationReader(NativeGenerationReader):
    """Opt-in reader with fixed Root policy, original inputs and recorded window.

    The resulting generation admission still grants no database lease or stage
    effect authority. A journal/input change invalidates the original guard.
    """
    def __init__(self, *args, worker, **options):
        self.inputs = None;self.lifecycle_view = None
        try:
            require(type(worker) is str and worker in {'native', 'maintenance'})
            super().__init__(*args, **options);self.worker = worker
            self.inputs = NativeLifecycleWorkerInputs(self.installation)
            require(self.inputs.seal['durable_binding_sha256'] == self.expected)
        except Exception:
            self.close();raise GenerationAdmissionRefused('Native lifecycle worker admission unavailable') from None

    def close(self):
        if getattr(self, 'lifecycle_view', None) is not None:self.lifecycle_view.close()
        if self.inputs is not None:self.inputs.close()
        if getattr(self, 'custody', None) is not None:super().close()

    def admit(self, *, worker, owner_pid):
        if worker != self.worker:
            self.close();raise GenerationAdmissionRefused('Native lifecycle worker role changed')
        try:return super().admit(worker=worker, owner_pid=owner_pid)
        finally:self.close()

    def _view(self):
        if getattr(self, 'lifecycle_view', None) is None:
            self.lifecycle_view = NativeLifecycleHistory(self.custody)
        require(self.lifecycle_view.custody is self.custody)
        return self.lifecycle_view

    def _layout(self):
        try:
            self.inputs.check()
            expected = {'.upgrade-history-lock-v1', 'generation-records-v2', 'durable-binding-v2.json',
                        'current-generation-v2.json', 'generation-transitions-v2', 'generation-receipts-v2',
                        'lifecycle-responsibility-v2'}
            paths = list(itertools.islice(self.directory.iterdir(), 8))
            require(len(paths) == 7 and {path.name for path in paths} == expected)
            lifecycle = self.directory/'lifecycle-responsibility-v2'
            for path in [self.custody.store, self.transitions, self.receipts, lifecycle, lifecycle/'records', lifecycle/'heads']:
                identity = self.custody._identity(path)
                if path in self.directory_identities:require(self.directory_identities[path] == identity)
                else:self.directory_identities[path] = identity
                self._entries(path)
            self._check()
        except Exception:
            self.close();raise GenerationAdmissionRefused('Native lifecycle history unavailable or changed') from None

    def _fingerprint(self):
        try:
            files = super()._fingerprint()
            view = self._view()
            files['@lifecycle'] = view.metadata_fingerprint()
            files['@lifecycle_inputs'] = self.inputs.fingerprint()
            self._check();return files
        except Exception:
            self.close();raise GenerationAdmissionRefused('Native lifecycle custody unavailable or changed') from None

    def _snapshot(self, scope):
        try:
            snapshot = super()._snapshot(scope)
            inputs = self.inputs.check();request = inputs['request']
            require(request['durable_binding_sha256'] == self.expected)
            require(scope['uid'] == self.inputs.seal['uid'] and scope['gid'] == self.inputs.seal['gid'])
            view = self._view()
            operation = request['operation'];record = view.snapshot(operation)
            require(record['origin']['request'] == request)
            require(record['origin']['inputs_seal_sha256'] == inputs['inputs_seal_sha256'])
            require(record['origin']['request_sha256'] == inputs['request_sha256'])
            generation = snapshot['pointer']['generation_sha256']
            if record['status'] == 'complete':
                require(self.worker == 'native')
                if record['generation_sha256'] != generation:
                    reference = {'operation': operation, 'request_sha256': inputs['request_sha256'],
                                 'origin_sha256': sha(record['origin']), 'snapshot_sha256': sha(record)}
                    transition = snapshot['transitions'][snapshot['pointer']['operation']+'.json']
                    require(reference in transition['lifecycle_responsibilities'])
                    view.validate_references([reference], generation)
            else:
                require(record['status'] == 'running' and record['generation_sha256'] == generation)
                require(record['stage'] in STAGE_WORKERS[request['purpose']][self.worker])
            for other in view.heads:
                if other != operation:require(view.snapshot(other)['status'] == 'complete')
            snapshot['lifecycle'] = {'operation': operation, 'purpose': request['purpose'],
                'candidate': inputs['candidate'], 'request_sha256': inputs['request_sha256'],
                'origin_sha256': sha(record['origin']), 'snapshot_sha256': sha(record),
                'generation_sha256': record['generation_sha256'], 'epoch': record['epoch'],
                'stage': record['stage'], 'recorded_status': record['status'], 'worker': self.worker}
            require(self.inputs.check() == inputs and self._fingerprint() == snapshot['files'])
            view.check();self._check();return snapshot
        except Exception:
            self.close();raise GenerationAdmissionRefused('Native lifecycle stage unavailable or changed') from None


def open_reader(*args, worker, **options):
    """The fixed Root policy path selects explicit lifecycle admission."""
    path = worker_seal_path(args[1])
    if path.exists() or path.is_symlink():
        return NativeLifecycleGenerationReader(*args, worker=worker, **options)
    return NativeGenerationReader(*args, **options)
