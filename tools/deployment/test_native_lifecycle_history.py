import copy
import os
from pathlib import Path
import sys
import unittest
import uuid
from unittest.mock import patch

import native_lifecycle_history as history
import native_lifecycle_responsibility as lifecycle
import test_native_lifecycle_responsibility as fixtures
from resource_generations import make_generation, generation_sha256


@unittest.skipUnless(sys.platform == 'linux' and os.getuid() > 0, 'ordinary Linux lifecycle history custody')
class NativeLifecycleHistoryTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.LifecycleResponsibilityTest('test_failure_never_means_the_stage_had_no_effect')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.store = self.fixture.open()

    def journal(self):return self.fixture.journal(self.store)

    def view(self):
        value = history.NativeLifecycleHistory(self.store);self.addCleanup(value.close);return value

    def test_missing_layout_refuses_without_creating_or_releasing_custody(self):
        with self.assertRaises(lifecycle.LifecycleResponsibilityRefused):self.view()
        self.assertFalse((self.fixture.history/'lifecycle-responsibility-v2').exists());self.store.check()

    def test_view_preserves_pending_running_and_uncertain_metadata_without_claiming(self):
        journal = self.journal();journal.claim()
        for advance in [lambda:None, lambda:journal.begin('inspect'), lambda:journal.fail('inspect')]:
            advance();original = self.fixture.records();view = self.view()
            references = view.references();view.validate_references(references, self.fixture.generation)
            self.assertEqual(len(references), 1)
            self.assertEqual(references[0]['snapshot_sha256'], journal.head['snapshot_sha256'])
            self.assertEqual(references[0]['origin_sha256'], lifecycle.sha(journal.snapshot['origin']))
            self.assertEqual(self.fixture.records(), original);view.close();self.store.check()

    def test_historic_reference_remains_valid_after_later_claim_and_stage_outcome(self):
        journal = self.journal();journal.claim();view = self.view();original = view.references();view.close()
        journal.begin('inspect');journal.succeed('inspect', 'd'*64)
        later = self.view();self.assertNotEqual(later.references(), original)
        self.assertEqual(later.validate_references(original, self.fixture.generation), original)

    def test_changed_head_permanently_poisoned_view_cannot_adopt_new_progress(self):
        journal = self.journal();journal.claim();view = self.view();journal.begin('inspect')
        with self.assertRaises(lifecycle.LifecycleResponsibilityRefused):view.references()
        with self.assertRaises(lifecycle.LifecycleResponsibilityRefused):view.check()
        self.assertEqual(len(self.view().references()), 1)

    def test_same_byte_record_replacement_is_detected_by_original_view(self):
        journal = self.journal();journal.claim();view = self.view()
        path = self.fixture.history/'lifecycle-responsibility-v2/records'/(journal.head['snapshot_sha256']+'.json')
        raw = path.read_bytes();path.rename(self.fixture.history/'retained-original-snapshot')
        path.write_bytes(raw);path.chmod(0o600)
        with self.assertRaises(lifecycle.LifecycleResponsibilityRefused):view.check()
        self.assertEqual(path.read_bytes(), raw)

    def test_partials_and_detached_heads_refuse_without_recovery(self):
        journal = self.journal();journal.claim()
        root = self.fixture.history/'lifecycle-responsibility-v2'
        partial = root/'records'/('.partial-'+str(uuid.uuid4()))
        partial.write_bytes(b'{}');partial.chmod(0o600)
        with self.assertRaises(lifecycle.LifecycleResponsibilityRefused):self.view()
        self.assertEqual(partial.read_bytes(), b'{}')
        partial.rename(self.fixture.history/'retained-partial')
        head = root/'heads'/(self.fixture.request['operation']+'.json');head.rename(self.fixture.history/'retained-head')
        with self.assertRaises(lifecycle.LifecycleResponsibilityRefused):self.view()
        self.assertFalse(head.exists())

    def test_replaced_directory_and_fork_cannot_borrow_original_view(self):
        journal = self.journal();journal.claim();view = self.view()
        pid = os.fork()
        if pid == 0:
            try:view.check()
            except lifecycle.LifecycleResponsibilityRefused:os._exit(0)
            os._exit(1)
        _,status = os.waitpid(pid, 0);self.assertEqual(os.waitstatus_to_exitcode(status), 0)
        view.check();path = self.fixture.history/'lifecycle-responsibility-v2/records'
        path.rename(self.fixture.history/'retained-records');path.mkdir(mode=0o700)
        with self.assertRaises(lifecycle.LifecycleResponsibilityRefused):view.check()
        self.assertEqual(list(path.iterdir()), [])

    def test_reference_schema_origin_and_future_generation_cannot_be_substituted(self):
        journal = self.journal();journal.claim();view = self.view();reference = view.references()[0]
        for name in ['request_sha256', 'origin_sha256', 'snapshot_sha256']:
            changed = dict(reference);changed[name] = 'f'*64
            with self.subTest(name=name),self.assertRaises(Exception):view.validate_references([changed], self.fixture.generation)
        with self.assertRaises(Exception):view.validate_references([dict(reference, unexpected=True)], self.fixture.generation)
        with self.assertRaises(Exception):view.validate_references([reference, reference], self.fixture.generation)
        view.close();journal.close()
        scope = copy.deepcopy(self.fixture.scope);scope['parent']['inode'] += 100
        for item in scope['groups'].values():item['inode'] += 100
        successor = make_generation(scope, 'a'*64, generation=str(uuid.uuid4()),
            created_at='2026-10-11T08:00:00.000000Z', previous=self.fixture.first)
        self.store.retain(successor)
        later = self.fixture.journal(self.store, generation_sha256=generation_sha256(successor))
        later.claim(continuity_sha256='e'*64);later.close();view = self.view()
        with self.assertRaises(lifecycle.LifecycleResponsibilityRefused):view.validate_references(view.references(), self.fixture.generation)
        view.validate_references([reference], generation_sha256(successor))

    def test_all_terminal_and_unfinished_operations_are_sorted_and_retained(self):
        journal = self.journal();journal.claim()
        for stage in lifecycle.STAGES[self.fixture.request['purpose']]:journal.begin(stage);journal.succeed(stage, 'd'*64)
        journal.close();request = dict(self.fixture.request, operation=str(uuid.uuid4()))
        later = self.fixture.journal(self.store, request=request);later.claim();later.begin('inspect');later.close()
        references = self.view().references()
        self.assertEqual([row['operation'] for row in references], sorted([request['operation'], self.fixture.request['operation']]))
        self.assertEqual(len(references), 2)

    def test_bounded_inventory_refuses_before_adopting_excess_records(self):
        journal = self.journal();journal.claim();journal.begin('inspect')
        with patch.object(history, 'MAX_RECORDS', 1),self.assertRaises(lifecycle.LifecycleResponsibilityRefused):self.view()
        self.assertEqual(len(self.fixture.records()), 2)


if __name__ == '__main__':unittest.main()
