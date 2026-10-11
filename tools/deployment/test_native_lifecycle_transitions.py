import copy
import json
import os
from pathlib import Path
import sys
import unittest
import uuid
from unittest.mock import patch

from enrollment_journal import current_owner
import generation_publication as publication
from native_lifecycle_history import NativeLifecycleHistory
from native_lifecycle_responsibility import NativeLifecycleResponsibility, LifecycleResponsibilityRefused, sha
from native_generation_reader import NativeGenerationReader, _ReadOnlyCustody, GenerationAdmissionRefused
from resource_generations import canonical
import test_generation_publication as fixtures
import test_native_operation_inputs as input_fixtures


@unittest.skipUnless(sys.platform == 'linux' and os.getuid() > 0, 'ordinary Linux transition custody')
class NativeLifecycleTransitionsTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.GenerationPublicationTest('test_completed_publication_and_exact_retry_preserve_immutable_custody')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        owner = current_owner();scope = self.fixture.scope
        scope.update(uid=os.getuid(), gid=os.getgid(), boot_id=owner['boot_id'])
        scope['manager'].update({name:owner[name] for name in ['uid', 'pid', 'birth', 'mount_namespace', 'cgroup_namespace']})
        scope['manager']['security'].update(gid=os.getgid(), supplementary_groups=[])
        scope['parent']['uid'] = os.getuid()
        for item in scope['groups'].values():item['uid'] = os.getuid()
        self.fixture.observed['scope'] = scope
        self.initial = self.fixture.controller().publish(**self.fixture.arguments)
        _,_,self.request,_ = input_fixtures.fixture()
        self.request['installation'] = self.fixture.installation;self.request['durable_binding_sha256'] = self.fixture.expected
        with self.fixture.controller().custody as custody:
            journal = NativeLifecycleResponsibility(custody, self.request, 'c'*64, self.initial['pointer']['generation_sha256'])
            journal.claim();journal.begin('inspect');journal.close()
        self.references = self.references_now()

    def references_now(self):
        with self.fixture.controller().custody as custody:
            view = NativeLifecycleHistory(custody)
            try:return view.references()
            finally:view.close()

    def advance(self):
        # Service replacement/absence and database admission are boundary stand-ins.
        self.fixture.next_boot()

    def transition(self, result):
        return json.loads((self.fixture.history/'generation-transitions-v2'/(result['pointer']['operation']+'.json')).read_bytes())

    def test_unfinished_original_request_is_retained_in_new_generation_transition(self):
        original = self.fixture.snapshot();self.advance()
        result = self.fixture.controller().publish(**self.fixture.arguments)
        transition = self.transition(result)
        self.assertEqual(transition['lifecycle_responsibilities'], self.references)
        self.assertEqual(self.references_now(), self.references)
        after = self.fixture.snapshot();self.assertTrue(all(after[name] == value for name,value in original.items()))
        self.assertTrue(result['generation_publication_established']);self.assertFalse(result['installation_readiness_established'])
        self.assertEqual(self.fixture.controller().publish(**self.fixture.arguments), result)

    def test_lost_pointer_ack_resumes_exact_references_without_rewriting_journal(self):
        self.advance();controller = self.fixture.controller();original_write = controller._write
        def interrupt(path, value, **options):
            original_write(path, value, **options)
            if path == controller.pointer:raise OSError('synthetic lost pointer acknowledgement')
        with patch.object(controller, '_write', interrupt),self.assertRaises(OSError):controller.publish(**self.fixture.arguments)
        original = self.fixture.snapshot();result = self.fixture.controller().publish(**self.fixture.arguments)
        self.assertEqual(self.transition(result)['lifecycle_responsibilities'], self.references)
        self.assertTrue(all(self.fixture.snapshot()[name] == value for name,value in original.items()))

    def test_changed_responsibility_before_receipt_refuses_completion(self):
        controller = self.fixture.controller();original_write = controller._write;self.advance()
        def changed(path, value, **options):
            original_write(path, value, **options)
            if path == controller.pointer:
                head = self.fixture.history/'lifecycle-responsibility-v2/heads'/(self.request['operation']+'.json')
                raw = head.read_bytes();head.write_bytes(raw)
        with patch.object(controller, '_write', changed),self.assertRaises(publication.PublicationRefused):controller.publish(**self.fixture.arguments)
        self.assertFalse((controller.receipts/(self.fixture.arguments['operation']+'.json')).exists())
        self.assertEqual(self.references_now(), self.references)

    def test_partial_lifecycle_publication_refuses_before_new_generation(self):
        self.advance();folder = self.fixture.history/'lifecycle-responsibility-v2/records'
        path = folder/('.partial-'+str(uuid.uuid4()));path.write_bytes(b'{}');path.chmod(0o600)
        original = self.fixture.snapshot()
        with self.assertRaises(LifecycleResponsibilityRefused):self.fixture.controller().publish(**self.fixture.arguments)
        self.assertEqual(self.fixture.snapshot(), original);self.assertEqual(path.read_bytes(), b'{}')

    def test_future_or_modified_historic_reference_is_rejected_even_when_pointer_rehashed(self):
        self.advance();controller = self.fixture.controller();result = controller.publish(**self.fixture.arguments)
        path = controller.transitions/(self.fixture.arguments['operation']+'.json')
        transition = self.transition(result);transition['lifecycle_responsibilities'][0]['request_sha256'] = 'f'*64
        path.write_bytes(canonical(transition));pointer = dict(result['pointer'], transition_sha256=sha(transition))
        controller.pointer.write_bytes(canonical(pointer))
        with self.assertRaises(LifecycleResponsibilityRefused):self.fixture.controller().publish(**self.fixture.arguments)

    def test_worker_reader_still_refuses_lifecycle_history_without_stage_admission(self):
        self.advance();self.fixture.controller().publish(**self.fixture.arguments)
        reader = object.__new__(NativeGenerationReader);reader.__dict__.update(self.fixture.controller().__dict__)
        reader.custody = _ReadOnlyCustody(self.fixture.history, self.fixture.installation, self.fixture.identity, self.fixture.lock_identity)
        with reader.custody,self.assertRaises(publication.PublicationRefused):reader._layout()
        self.assertEqual(self.references_now(), self.references)


if __name__ == '__main__':unittest.main()
