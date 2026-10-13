import copy
import os
from pathlib import Path
import sys
import unittest
import uuid
from unittest.mock import patch

from enrollment_journal import current_owner
from native_generation_reader import NativeGenerationReader, _ReadOnlyCustody, GenerationAdmissionRefused
import native_generation_reader as base_reader
import native_generation_lease_guard as guard_module
import native_lifecycle_generation_reader as reader
from native_lifecycle_responsibility import NativeLifecycleResponsibility, STAGES, sha
import test_generation_publication as publication_fixtures
import test_native_operation_inputs as input_fixtures


class Inputs:
    """Explicit Root/input boundary stand-in; actual custody is proved separately."""
    def __init__(self, request):
        self.request = copy.deepcopy(request);self.usable = True
        self.seal = {'uid': os.getuid(), 'gid': os.getgid()}
    def check(self):
        if not self.usable:raise GenerationAdmissionRefused('Synthetic input boundary closed')
        return {'request': copy.deepcopy(self.request), 'candidate': 'b'*40,
                'inputs_seal_sha256': 'c'*64, 'request_sha256': sha(self.request)}
    def fingerprint(self):return {'stand_in': True, 'request_sha256': self.check()['request_sha256']}
    def close(self):self.usable = False


@unittest.skipUnless(sys.platform == 'linux' and os.getuid() > 0, 'ordinary Linux stage worker history')
class LifecycleGenerationReaderTest(unittest.TestCase):
    def setUp(self):
        self.fixture = publication_fixtures.GenerationPublicationTest('test_completed_publication_and_exact_retry_preserve_immutable_custody')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        scope = self.fixture.scope;owner = current_owner()
        scope.update(uid=os.getuid(), gid=os.getgid(), boot_id=owner['boot_id'])
        scope['manager'].update({name:owner[name] for name in ['uid', 'pid', 'birth', 'mount_namespace', 'cgroup_namespace']})
        scope['manager']['security'].update(gid=os.getgid(), supplementary_groups=[])
        scope['parent']['uid'] = os.getuid()
        for item in scope['groups'].values():item['uid'] = os.getuid()
        self.fixture.observed['scope'] = scope
        self.result = self.fixture.controller().publish(**self.fixture.arguments)
        self.generation = self.result['pointer']['generation_sha256'];self.request = None
        self.worker = {'service_scope': scope, 'worker': 'native', 'owner': {'pid': 42, 'birth': '420'},
                       'caller': {'pid': 43, 'birth': '430'}, 'generation_publication_established': False,
                       'installation_readiness_established': False}
        for name, value in [('observe_worker', lambda *a, **kw: copy.deepcopy(self.worker)),
                            ('persistent_identity', lambda *a, **kw: copy.deepcopy(self.fixture.binding))]:
            mock = patch.object(base_reader, name, value);mock.start();self.addCleanup(mock.stop)

    def begin(self, stage, purpose='native_initial_enrollment'):
        if self.request is None:
            _,_,self.request,_ = input_fixtures.fixture(purpose)
            self.request['installation'] = self.fixture.installation;self.request['durable_binding_sha256'] = self.fixture.expected
        with self.fixture.controller().custody as custody:
            journal = NativeLifecycleResponsibility(custody, self.request, 'c'*64, self.generation)
            result = journal.claim()
            if result['recorded_status'] == 'uncertain':journal.reconcile(applied=True, receipt_sha256='d'*64)
            while len(journal.snapshot['completed']) < STAGES[purpose].index(stage):
                item = STAGES[purpose][len(journal.snapshot['completed'])];journal.begin(item);journal.succeed(item, 'd'*64)
            journal.begin(stage);journal.close()

    def finish(self):
        with self.fixture.controller().custody as custody:
            journal = NativeLifecycleResponsibility(custody, self.request, 'c'*64, self.generation)
            journal.claim();journal.reconcile(applied=True, receipt_sha256='d'*64)
            for stage in STAGES[self.request['purpose']][len(journal.snapshot['completed']):]:journal.begin(stage);journal.succeed(stage, 'd'*64)
            journal.close()

    def open(self, worker='native'):
        self.worker['worker'] = worker
        value = object.__new__(reader.NativeLifecycleGenerationReader)
        value.__dict__.update(self.fixture.controller().__dict__)
        value.custody = _ReadOnlyCustody(self.fixture.history, self.fixture.installation, self.fixture.identity, self.fixture.lock_identity)
        value.worker = worker;value.inputs = Inputs(self.request);self.addCleanup(value.close);return value

    def admit(self, worker='native'):return self.open(worker).admit(worker=worker, owner_pid=42)

    def test_fixed_enrollment_windows_admit_only_the_matching_worker_role(self):
        for stage, allowed in [('migrate', 'maintenance'), ('bootstrap', 'maintenance'), ('verify', 'native'), ('activate', 'native'), ('enroll', 'native')]:
            self.begin(stage)
            self.assertTrue(self.admit(allowed)['published_generation_admitted'])
            other = 'native' if allowed == 'maintenance' else 'maintenance'
            with self.subTest(stage=stage),self.assertRaises(GenerationAdmissionRefused):self.admit(other)

    def test_admission_projects_the_exact_recorded_stage_without_effect_authority(self):
        self.begin('bootstrap');result=self.admit('maintenance')
        observed=result['lifecycle_observation']
        self.assertEqual(observed['operation'],self.request['operation'])
        self.assertEqual(observed['purpose'],'native_initial_enrollment')
        self.assertEqual(observed['candidate'],'b'*40)
        self.assertEqual(observed['request_sha256'],sha(self.request))
        self.assertEqual(observed['generation_sha256'],self.generation)
        self.assertEqual((observed['stage'],observed['recorded_status'],observed['worker']),
                         ('bootstrap','running','maintenance'))
        self.assertEqual(set(observed),{'operation','purpose','candidate','request_sha256','origin_sha256',
            'snapshot_sha256','generation_sha256','epoch','stage','recorded_status','worker'})
        for field in ['lifecycle_responsibility_admitted','writer_exclusion_established','installation_readiness_established']:
            self.assertIs(result[field],False)

    def test_terminal_ancestor_projection_preserves_original_generation_and_status(self):
        self.begin('verify');self.finish();self.fixture.next_boot();self.fixture.controller().publish(**self.fixture.arguments)
        self.worker['service_scope']=self.fixture.scope
        result=self.admit();observed=result['lifecycle_observation']
        self.assertEqual((observed['stage'],observed['recorded_status'],observed['worker']),('enroll','complete','native'))
        self.assertEqual(observed['generation_sha256'],self.generation)
        self.assertNotEqual(observed['generation_sha256'],result['pointer']['generation_sha256'])
        self.assertIs(result['lifecycle_responsibility_admitted'],False)

    def test_fixed_upgrade_windows_admit_migration_and_candidate_verification_roles(self):
        for stage, allowed in [('migrate', 'maintenance'), ('verify', 'native'), ('activate', 'native'), ('public_verify', 'native')]:
            self.begin(stage, 'native_upgrade_execution')
            self.assertTrue(self.admit(allowed)['published_generation_admitted'])
            with self.assertRaises(GenerationAdmissionRefused):self.admit('maintenance' if allowed == 'native' else 'native')

    def test_inspection_pending_and_uncertain_states_cannot_revive_workers(self):
        self.begin('inspect')
        for worker in ['native', 'maintenance']:
            with self.assertRaises(GenerationAdmissionRefused):self.admit(worker)
        with self.fixture.controller().custody as custody:
            journal = NativeLifecycleResponsibility(custody, self.request, 'c'*64, self.generation);journal.claim();journal.close()
        with self.assertRaises(GenerationAdmissionRefused):self.admit()

    def test_terminal_replay_admits_only_runtime_without_fresh_readiness_or_effect_authority(self):
        self.begin('verify');self.finish();result = self.admit()
        self.assertTrue(result['published_generation_admitted'])
        for name in ['writer_exclusion_established', 'lifecycle_responsibility_admitted', 'installation_readiness_established']:self.assertFalse(result[name])
        with self.assertRaises(GenerationAdmissionRefused):self.admit('maintenance')

    def test_new_generation_cannot_adopt_old_running_stage_without_reconciliation(self):
        self.begin('verify');self.fixture.next_boot();self.fixture.controller().publish(**self.fixture.arguments)
        self.worker['service_scope'] = self.fixture.scope
        with self.assertRaises(GenerationAdmissionRefused):self.admit()

    def test_terminal_ancestor_requires_current_transition_to_retain_exact_snapshot(self):
        self.begin('verify');self.finish();self.fixture.next_boot();result = self.fixture.controller().publish(**self.fixture.arguments)
        self.worker['service_scope'] = self.fixture.scope
        self.assertTrue(self.admit()['published_generation_admitted'])
        self.assertNotEqual(result['pointer']['generation_sha256'], self.generation)

    def test_different_unfinished_operation_blocks_terminal_runtime_revival(self):
        self.begin('verify');self.finish()
        with self.fixture.controller().custody as custody:
            request = dict(self.request, operation=str(uuid.uuid4()))
            journal = NativeLifecycleResponsibility(custody, request, 'c'*64, self.generation)
            journal.claim();journal.begin('inspect');journal.close()
        with self.assertRaises(GenerationAdmissionRefused):self.admit()

    def test_changed_protected_request_and_wrong_requested_role_refuse(self):
        self.begin('verify');subject = self.open();subject.inputs.request['files']['inputs.json']['sha256'] = 'f'*64
        with self.assertRaises(GenerationAdmissionRefused):subject.admit(worker='native', owner_pid=42)
        subject = self.open('maintenance')
        with self.assertRaises(GenerationAdmissionRefused):subject.admit(worker='native', owner_pid=42)

    def test_guard_loses_admission_when_recorded_stage_advances_and_cannot_revive(self):
        self.begin('verify');subject = self.open()
        subject.executables = {name:'/fixture/'+name for name in ['python', 'node', 'git', 'psql', 'caddy']}
        guard = guard_module.NativeGenerationLeaseGuard(subject, worker='native', owner_pid=42);self.addCleanup(guard.close)
        patches = [('observe_worker', lambda *a, **kw:copy.deepcopy(self.worker)),
                   ('persistent_identity', lambda *a, **kw:copy.deepcopy(self.fixture.binding)),
                   ('persistent_fingerprint', lambda *a:{'stand_in': True}),
                   ('_observe_service', lambda *a, **kw:copy.deepcopy(self.worker['service_scope'])),
                   ('_ancestry', lambda *a:[copy.deepcopy(self.worker['caller']), copy.deepcopy(self.worker['owner'])])]
        for name, value in patches:
            mock = patch.object(guard_module, name, value);mock.start();self.addCleanup(mock.stop)
        for cache in [guard.root_files, guard.executable_files]:
            mock = patch.object(cache, 'freeze', return_value=None);mock.start();self.addCleanup(mock.stop)
        captured = guard.capture();self.assertTrue(guard.check()['current'])
        self.assertEqual(captured['admission']['lifecycle_observation'],guard.snapshot['lifecycle'])
        captured['admission']['lifecycle_observation']['stage']='untrusted-caller-edit'
        self.assertEqual(guard.snapshot['lifecycle']['stage'],'verify')
        self.assertTrue(guard.check()['current'])
        with patch.object(subject.lifecycle_view, '_read', side_effect=AssertionError('heartbeat must not reparse journal')) as journal_read, \
             patch.object(subject.custody, '_records', side_effect=AssertionError('heartbeat must not reparse generations')) as generation_read, \
             patch.object(guard_module, 'persistent_identity', side_effect=AssertionError('heartbeat must not query database')) as database:
            self.assertTrue(guard.check()['current'])
        journal_read.assert_not_called();generation_read.assert_not_called();database.assert_not_called()
        self.assertIn('lifecycle', guard.snapshot);self.assertEqual(guard.snapshot['lifecycle']['stage'], 'verify')
        self.assertEqual(captured['history_sha256'], sha(guard.snapshot))
        self.begin('activate')
        for _ in range(2):
            with self.assertRaises(guard_module.GenerationLeaseGuardRefused):guard.check()
        self.assertFalse(guard.usable);self.assertFalse(subject.inputs.usable)


if __name__ == '__main__':unittest.main()
