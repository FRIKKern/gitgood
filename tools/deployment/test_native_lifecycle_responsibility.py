import copy
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

from enrollment_journal import current_owner
from generation_custody import GenerationRecordCustody
import native_lifecycle_responsibility as lifecycle
from resource_generations import canonical, make_generation, generation_sha256
from test_native_operation_inputs import fixture
import test_resource_generations as generation_fixtures


@unittest.skipUnless(sys.platform == 'linux' and os.getuid() > 0, 'Actual ordinary Linux responsibility custody')
class LifecycleResponsibilityTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.history = Path(self.temporary.name);self.history.chmod(0o700)
        lock = self.history/'.upgrade-history-lock-v1';lock.write_bytes(b'');lock.chmod(0o600)
        original = generation_fixtures.ResourceGenerationRecordTest();original.setUp();self.installation = original.installation
        scope = copy.deepcopy(original.scope);owner = current_owner()
        scope.update(uid=os.getuid(), gid=os.getgid(), boot_id=owner['boot_id'])
        scope['manager'].update({name: owner[name] for name in ['uid', 'pid', 'birth', 'mount_namespace', 'cgroup_namespace']})
        scope['manager']['security'].update(gid=os.getgid(), supplementary_groups=[])
        scope['parent']['uid'] = os.getuid()
        for item in scope['groups'].values():item['uid'] = os.getuid()
        self.scope = scope
        self.first = make_generation(scope, 'a'*64, generation=str(uuid.uuid4()), created_at='2026-10-11T07:00:00.000000Z')
        self.generation = generation_sha256(self.first)
        _, _, self.request, _ = fixture();self.request['installation'] = self.installation
        self.request['durable_binding_sha256'] = 'a'*64

    def custody(self):
        def identity(path):
            info = path.stat();return {'device': info.st_dev, 'inode': info.st_ino, 'uid': info.st_uid}
        return GenerationRecordCustody(self.history, self.installation, identity(self.history), identity(self.history/'.upgrade-history-lock-v1'))

    def journal(self, custody, **changes):
        arguments = {'custody': custody, 'request': self.request, 'inputs_seal_sha256': 'c'*64, 'generation_sha256': self.generation}
        arguments.update(changes)
        value = lifecycle.NativeLifecycleResponsibility(**arguments);self.addCleanup(value.close);return value

    def open(self):
        store = self.custody();store.__enter__();self.addCleanup(lambda:store.__exit__(None,None,None))
        store.retain(self.first);return store

    def records(self):
        folder = self.history/'lifecycle-responsibility-v2/records'
        return {path.name: (path.stat().st_ino, path.read_bytes()) for path in folder.iterdir()}

    def test_fixed_stage_sequence_retains_origin_and_terminal_replay_without_duplicate_claim(self):
        store = self.open();journal = self.journal(store);result = journal.claim()
        self.assertFalse(result['stage_effect_authorized']);self.assertFalse(result['writer_exclusion_established'])
        origin = copy.deepcopy(journal.snapshot['origin'])
        for stage in lifecycle.STAGES[self.request['purpose']]:
            journal.begin(stage);journal.succeed(stage, 'd'*64)
        self.assertEqual(journal.snapshot['origin'], origin)
        self.assertEqual(journal.status()['recorded_status'], 'complete')
        originals = self.records();journal.close()
        replay = self.journal(store)
        self.assertEqual(replay.claim()['recorded_status'], 'complete')
        self.assertEqual(self.records(), originals)

    def test_reopen_running_stage_is_uncertain_and_requires_explicit_reconciliation(self):
        store = self.open();journal = self.journal(store);journal.claim();journal.begin('inspect')
        original = self.records();journal.close();later = self.journal(store)
        self.assertEqual(later.claim()['recorded_status'], 'uncertain')
        with self.assertRaises(lifecycle.LifecycleResponsibilityRefused):later.begin('inspect')
        later.reconcile(applied=False, receipt_sha256='d'*64)
        later.begin('inspect');later.succeed('inspect', 'e'*64)
        self.assertEqual(later.status()['completed'], ['inspect'])
        self.assertTrue(all(self.records()[name] == value for name,value in original.items()))

    def test_failure_never_means_the_stage_had_no_effect(self):
        journal = self.journal(self.open());journal.claim();journal.begin('inspect');journal.fail('inspect')
        self.assertEqual(journal.status()['recorded_status'], 'uncertain')
        with self.assertRaises(lifecycle.LifecycleResponsibilityRefused):journal.begin('inspect')
        with self.assertRaises(lifecycle.LifecycleResponsibilityRefused):journal.reconcile(applied=1, receipt_sha256='d'*64)
        journal.reconcile(applied=True, receipt_sha256='d'*64)
        self.assertEqual(journal.status()['completed'], ['inspect'])

    def test_wrong_stage_and_unsealed_request_rebind_refuse(self):
        store = self.open();journal = self.journal(store);journal.claim()
        with self.assertRaises(lifecycle.LifecycleResponsibilityRefused):journal.begin('migrate')
        journal.close();changed = copy.deepcopy(self.request);changed['files']['inputs.json']['sha256'] = 'f'*64
        with self.assertRaises(lifecycle.LifecycleResponsibilityRefused):self.journal(store, request=changed)
        with self.assertRaises(lifecycle.LifecycleResponsibilityRefused):self.journal(store, inputs_seal_sha256='f'*64)

    def test_different_unfinished_operation_cannot_start_over_original_responsibility(self):
        store = self.open();journal = self.journal(store);journal.claim();journal.close()
        changed = dict(self.request, operation=str(uuid.uuid4()))
        with self.assertRaises(lifecycle.LifecycleResponsibilityRefused):self.journal(store, request=changed)

    def test_successor_claim_references_continuity_without_replacing_origin_or_old_events(self):
        store = self.open();journal = self.journal(store);journal.claim();journal.begin('inspect')
        origin = copy.deepcopy(journal.snapshot['origin']);events = copy.deepcopy(journal.snapshot['events']);journal.close()
        scope = copy.deepcopy(self.scope);scope['parent']['inode'] += 100
        for item in scope['groups'].values():item['inode'] += 100
        successor = make_generation(scope, 'a'*64, generation=str(uuid.uuid4()), created_at='2026-10-11T07:01:00.000000Z', previous=self.first)
        store.retain(successor)
        later = self.journal(store, generation_sha256=generation_sha256(successor))
        with self.assertRaises(Exception):later.claim()
        later.claim(continuity_sha256='e'*64, current_inputs_seal_sha256='f'*64)
        self.assertEqual(later.snapshot['origin'], origin)
        self.assertEqual(later.snapshot['events'][:len(events)], events)
        self.assertEqual(later.snapshot['status'], 'uncertain')

    def test_partial_snapshot_is_retained_and_blocks_new_claim(self):
        store = self.open();journal = self.journal(store);journal.claim();original = self.records()
        with patch.object(lifecycle, 'publish_directory', side_effect=OSError('synthetic interrupted rename')):
            with self.assertRaises(lifecycle.LifecycleResponsibilityRefused):journal.begin('inspect')
        after = self.records();self.assertTrue(any(name.startswith('.partial-') for name in after))
        self.assertTrue(all(after[name] == value for name,value in original.items()))
        with self.assertRaises(lifecycle.LifecycleResponsibilityRefused):self.journal(store)
        recovered = self.journal(store, recover_publication=True)
        self.assertEqual(recovered.claim()['recorded_status'],'uncertain')
        self.assertTrue(all(self.records()[name] == value for name,value in original.items()))

    def test_snapshot_without_head_is_retained_and_cannot_authorize_stage_replay(self):
        store = self.open();journal = self.journal(store);journal.claim()
        original_write = journal._write
        def interrupted(role,*args,**kwargs):
            if role == 'heads':raise OSError('synthetic interruption before head publication')
            return original_write(role,*args,**kwargs)
        with patch.object(journal, '_write', interrupted):
            with self.assertRaises(lifecycle.LifecycleResponsibilityRefused):journal.begin('inspect')
        self.assertEqual(len(self.records()), 2)
        with self.assertRaises(lifecycle.LifecycleResponsibilityRefused):self.journal(store)
        recovered = self.journal(store, recover_publication=True)
        self.assertEqual(recovered.claim()['recorded_status'],'uncertain')
        with self.assertRaises(lifecycle.LifecycleResponsibilityRefused):recovered.begin('inspect')

    def test_complete_head_partial_can_recover_exact_metadata_without_repeating_stage(self):
        store = self.open();journal = self.journal(store);journal.claim()
        with patch.object(lifecycle.os,'replace',side_effect=OSError('synthetic interruption before head rename')):
            with self.assertRaises(lifecycle.LifecycleResponsibilityRefused):journal.begin('inspect')
        with self.assertRaises(lifecycle.LifecycleResponsibilityRefused):self.journal(store)
        recovered = self.journal(store,recover_publication=True)
        self.assertEqual(recovered.claim()['recorded_status'],'uncertain')
        self.assertEqual(recovered.status()['completed'],[])

    def test_incomplete_partial_is_retained_and_never_inferred_complete(self):
        store = self.open();journal = self.journal(store);journal.claim();journal.close()
        path = self.history/'lifecycle-responsibility-v2/records'/('.partial-'+str(uuid.uuid4()))
        path.write_bytes(b'{"protocol":2');path.chmod(0o600);original=(path.stat().st_ino,path.read_bytes())
        with self.assertRaises(lifecycle.LifecycleResponsibilityRefused):self.journal(store,recover_publication=True)
        self.assertEqual((path.stat().st_ino,path.read_bytes()),original)

    def test_lost_head_acknowledgement_preserves_committed_stage_without_reapplying_it(self):
        store = self.open();journal = self.journal(store);journal.claim();journal.begin('inspect')
        original_write = journal._write
        def lost_ack(role,*args,**kwargs):
            original_write(role,*args,**kwargs)
            if role == 'heads':raise OSError('synthetic lost committed acknowledgement')
        with patch.object(journal, '_write', lost_ack):
            with self.assertRaises(lifecycle.LifecycleResponsibilityRefused):journal.succeed('inspect','d'*64)
        later = self.journal(store);later.claim()
        self.assertEqual(later.status()['completed'], ['inspect'])
        with self.assertRaises(lifecycle.LifecycleResponsibilityRefused):later.begin('inspect')

    def test_forked_process_cannot_borrow_original_custody(self):
        store = self.open();journal = self.journal(store);journal.claim();original = self.records()
        pid = os.fork()
        if pid == 0:
            try:journal.begin('inspect')
            except lifecycle.LifecycleResponsibilityRefused:os._exit(0)
            os._exit(1)
        _,status = os.waitpid(pid,0);self.assertEqual(os.waitstatus_to_exitcode(status),0)
        self.assertEqual(self.records(), original);journal.begin('inspect')

    def test_replaced_store_directory_cannot_redirect_a_write(self):
        store = self.open();journal = self.journal(store);journal.claim()
        folder = self.history/'lifecycle-responsibility-v2/records';saved = folder.with_name('retained-records')
        folder.rename(saved);folder.mkdir(mode=0o700)
        with self.assertRaises(lifecycle.LifecycleResponsibilityRefused):journal.begin('inspect')
        self.assertEqual(list(folder.iterdir()),[])
        self.assertTrue(any(saved.iterdir()))

    def test_generation_and_event_capacity_refuse_before_starting_an_effect(self):
        store = self.open();journal = self.journal(store);journal.claim()
        with patch.object(lifecycle,'MAX_RECORDS',2):
            with self.assertRaises(lifecycle.LifecycleResponsibilityRefused):journal.begin('inspect')
        self.assertEqual(journal.status()['recorded_status'],'pending')
        scope = copy.deepcopy(self.scope);scope['manager']['pid'] += 1
        wrong = make_generation(scope, 'a'*64, generation=str(uuid.uuid4()), created_at='2026-10-11T07:01:00.000000Z', previous=self.first)
        store.retain(wrong)
        # The actual current-process owner must match the supplied generation.
        with self.assertRaises(lifecycle.LifecycleResponsibilityRefused):self.journal(store,generation_sha256=generation_sha256(wrong))


if __name__ == '__main__':unittest.main()
