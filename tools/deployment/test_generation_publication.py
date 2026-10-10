import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

import generation_publication as publication
from generation_custody import GenerationRecordCustody, CustodyRefused
from resource_generations import canonical
import test_resource_generations as fixtures


class Lease:
    """Boundary stand-in; actual PostgreSQL exclusion has separate proof."""
    def __init__(self, *args):
        self.checks = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def check(self):
        self.checks += 1


@unittest.skipUnless(sys.platform == "linux" and os.getuid() != 0, "ordinary Linux publication custody")
class GenerationPublicationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.history = self.root / "history"
        self.history.mkdir(mode=0o700)
        lock = self.history / ".upgrade-history-lock-v1"
        lock.write_bytes(b"")
        lock.chmod(0o600)
        self.identity = self.identity_of(self.history)
        self.lock_identity = self.identity_of(lock)
        fixture = fixtures.ResourceGenerationRecordTest()
        fixture.setUp()
        self.installation = fixture.installation
        self.scope = fixture.scope
        self.binding = {"executables": {"psql": {"path": "/fixed/psql"}}, "database": {"fixture": True}}
        self.expected = publication.sha(self.binding)
        self.observed = {"binding": self.binding, "binding_sha256": self.expected, "scope": self.scope,
                         "installation_readiness_established": False, "generation_publication_established": False}
        self.arguments = {"operation": str(uuid.uuid4()), "generation": str(uuid.uuid4()), "created_at": "2026-10-10T07:00:00.000000Z"}
        for target, value in [("observe_durable_binding", lambda *a, **kw: copy.deepcopy(self.observed)),
                              ("stopped", lambda scope: None), ("configuration", lambda *a: ({}, "postgres://fixture")),
                              ("NativeWriterExclusion", Lease)]:
            mock = patch.object(publication, target, value)
            mock.start()
            self.addCleanup(mock.stop)

    @staticmethod
    def identity_of(path):
        value = path.stat()
        return {"device": value.st_dev, "inode": value.st_ino, "uid": value.st_uid}

    def controller(self):
        # Isolate actual filesystem state-machine behavior from host admission.
        # The fixed-root constructor and real service/database are proved separately.
        value = object.__new__(publication.GenerationPublication)
        value.root, value.installation, value.expected = self.root, self.installation, self.expected
        value.unit, value.executables, value.options = "a" * 64, {}, {}
        value.custody = GenerationRecordCustody(self.history, self.installation, self.identity, self.lock_identity)
        value.directory = self.history
        value.pointer = self.history / "current-generation-v2.json"
        value.transitions = self.history / "generation-transitions-v2"
        value.receipts = self.history / "generation-receipts-v2"
        value.directory_identities = {}
        return value

    def next_boot(self):
        self.scope = copy.deepcopy(self.scope)
        self.scope["boot_id"] = str(uuid.uuid4())
        self.observed["scope"] = self.scope
        self.arguments = {"operation": str(uuid.uuid4()), "generation": str(uuid.uuid4()), "created_at": "2026-10-10T07:01:00.000000Z"}

    def snapshot(self):
        return {str(path.relative_to(self.history)): (path.stat().st_ino, path.read_bytes())
                for path in self.history.rglob("*.json") if path.name != "current-generation-v2.json"}

    def test_completed_publication_and_exact_retry_preserve_immutable_custody(self):
        result = self.controller().publish(**self.arguments)
        original = self.snapshot()
        self.assertTrue(result["generation_publication_established"])
        self.assertFalse(result["installation_readiness_established"])
        self.assertEqual(self.controller().publish(**self.arguments), result)
        self.assertEqual(self.snapshot(), original)

    def test_lost_acknowledgements_at_each_retained_stage_resume_without_duplicate(self):
        for stage in ["durable-binding-v2.json", "transition", "current-generation-v2.json", "receipt"]:
            with self.subTest(stage=stage):
                # Each case uses a separate ordinary private installation fixture.
                other = GenerationPublicationTest("test_completed_publication_and_exact_retry_preserve_immutable_custody")
                other.setUp()
                try:
                    controller = other.controller()
                    original_write = controller._write
                    def lose_ack(path, value, **kw):
                        original_write(path, value, **kw)
                        if path.name == stage or (stage == "transition" and path.parent == controller.transitions) or (stage == "receipt" and path.parent == controller.receipts):
                            raise OSError("injected lost acknowledgement")
                    with patch.object(controller, "_write", lose_ack):
                        with self.assertRaises(OSError):
                            controller.publish(**other.arguments)
                    before = other.snapshot()
                    result = other.controller().publish(**other.arguments)
                    self.assertTrue(result["generation_publication_established"])
                    after = other.snapshot()
                    self.assertTrue(all(after[name] == value for name, value in before.items()))
                    self.assertEqual(len(list((other.history / "generation-records-v2").glob("*.json"))), 1)
                finally:
                    other.doCleanups()

    def test_new_boot_preserves_unacknowledged_pointer_and_original_transition(self):
        controller = self.controller()
        write = controller._write
        def interrupt(path, value, **kw):
            write(path, value, **kw)
            if path == controller.pointer:
                raise OSError("owner lost after pointer")
        with patch.object(controller, "_write", interrupt), self.assertRaises(OSError):
            controller.publish(**self.arguments)
        before = self.snapshot()
        self.next_boot()
        result = self.controller().publish(**self.arguments)
        after = self.snapshot()
        self.assertTrue(all(after[name] == value for name, value in before.items()))
        transition = json.loads((controller.transitions / (self.arguments["operation"] + ".json")).read_bytes())
        self.assertFalse(transition["previous_publication_complete"])
        original_transition = next(path for path in controller.transitions.glob("*.json") if path.name != self.arguments["operation"] + ".json")
        self.assertEqual(transition["old_pointer"]["transition_sha256"], publication.sha(json.loads(original_transition.read_bytes())))
        self.assertNotEqual(transition["old_pointer"], result["pointer"])

    def test_staged_generation_before_pointer_survives_reboot_without_branching(self):
        self.controller().publish(**self.arguments)
        self.next_boot()
        pending = self.arguments.copy()
        controller = self.controller()
        write = controller._write
        def interrupt(path, value, **kw):
            write(path, value, **kw)
            if path.parent == controller.transitions:
                raise OSError("owner lost before pointer")
        with patch.object(controller, "_write", interrupt), self.assertRaises(OSError):
            controller.publish(**pending)
        before = self.snapshot()
        self.next_boot()
        self.controller().publish(**self.arguments)
        after = self.snapshot()
        self.assertTrue(all(after[name] == value for name, value in before.items()))
        with GenerationRecordCustody(self.history, self.installation, self.identity, self.lock_identity) as store:
            records = store._records()
            self.assertEqual(len(records), 3)
            self.assertEqual(len({value["predecessor_sha256"] for value in records.values()}), 3)

    def test_database_lease_loss_after_pointer_keeps_uncertain_receipt_absent(self):
        class LostLease(Lease):
            def check(self):
                super().check()
                if self.checks == 3:
                    raise publication.PublicationRefused("lease lost")
        with patch.object(publication, "NativeWriterExclusion", LostLease), self.assertRaises(publication.PublicationRefused):
            self.controller().publish(**self.arguments)
        self.assertTrue((self.history / "current-generation-v2.json").exists())
        self.assertFalse(list((self.history / "generation-receipts-v2").glob("*.json")))
        self.assertTrue(self.controller().publish(**self.arguments)["generation_publication_established"])

    def test_changed_binding_refuses_before_generation_or_pointer(self):
        self.observed["binding_sha256"] = "f" * 64
        with self.assertRaises(publication.PublicationRefused):
            self.controller().publish(**self.arguments)
        self.assertFalse((self.history / "current-generation-v2.json").exists())
        self.assertFalse(list((self.history / "generation-records-v2").glob("*.json")))

    def test_competing_publisher_cannot_bypass_existing_os_owner(self):
        with GenerationRecordCustody(self.history, self.installation, self.identity, self.lock_identity):
            with self.assertRaises(CustodyRefused):
                self.controller().publish(**self.arguments)
        self.assertTrue(self.controller().publish(**self.arguments)["generation_publication_established"])

    def test_unknown_legacy_responsibility_and_replaced_directory_refuse(self):
        unknown = self.history / "upgrade-history-v1.json"
        unknown.write_bytes(b"{}")
        unknown.chmod(0o600)
        with self.assertRaises(publication.PublicationRefused):
            self.controller().publish(**self.arguments)
        unknown.rename(self.root / "retained-legacy")
        controller = self.controller()
        with controller.custody:
            controller._layout()
            controller.transitions.rename(self.root / "retained-transitions")
            controller.transitions.mkdir(mode=0o700)
            with self.assertRaises(publication.PublicationRefused):
                controller._check()

    def test_changed_receipt_and_transition_are_never_replayed_as_complete(self):
        controller = self.controller()
        controller.publish(**self.arguments)
        receipt = controller.receipts / (self.arguments["operation"] + ".json")
        original = receipt.read_bytes()
        receipt.write_bytes(canonical({"protocol": 2, "installation": self.installation, "pointer_sha256": "f" * 64, "status": "complete"}))
        with self.assertRaises(publication.PublicationRefused):
            self.controller().publish(**self.arguments)
        receipt.write_bytes(original)
        transition = controller.transitions / (self.arguments["operation"] + ".json")
        transition.write_bytes(transition.read_bytes() + b"\n")
        with self.assertRaises(publication.PublicationRefused):
            self.controller().publish(**self.arguments)

    def test_same_generation_cannot_hide_a_new_request_or_scope(self):
        self.controller().publish(**self.arguments)
        changed = dict(self.arguments, operation=str(uuid.uuid4()))
        with self.assertRaises(publication.PublicationRefused):
            self.controller().publish(**changed)
        self.observed["scope"] = copy.deepcopy(self.scope)
        self.observed["scope"]["boot_id"] = str(uuid.uuid4())
        with self.assertRaises(publication.PublicationRefused):
            self.controller().publish(**self.arguments)

    def test_old_operation_reuse_cannot_retain_another_generation(self):
        first = self.arguments.copy()
        self.controller().publish(**first)
        self.next_boot()
        self.controller().publish(**self.arguments)
        before = self.snapshot()
        self.next_boot()
        reused = dict(self.arguments, operation=first['operation'])
        with self.assertRaises(publication.PublicationRefused):
            self.controller().publish(**reused)
        self.assertEqual(self.snapshot(), before)

    def test_corrupted_older_receipt_cannot_disappear_behind_current_publication(self):
        first = self.arguments.copy()
        self.controller().publish(**first)
        self.next_boot()
        self.controller().publish(**self.arguments)
        path = self.history / 'generation-receipts-v2' / (first['operation'] + '.json')
        path.write_bytes(canonical({'protocol': 2, 'installation': self.installation, 'pointer_sha256': 'f' * 64, 'status': 'complete'}))
        with self.assertRaises(publication.PublicationRefused):
            self.controller().publish(**self.arguments)

    def test_unknown_canonical_operation_cannot_be_ignored_as_unrelated_history(self):
        self.controller().publish(**self.arguments)
        path = self.history / 'generation-transitions-v2' / (str(uuid.uuid4()) + '.json')
        path.write_bytes(canonical({'unexpected': 'responsibility'}))
        path.chmod(0o600)
        with self.assertRaises(publication.PublicationRefused):
            self.controller().publish(**self.arguments)


class PublicationProcessBoundaryTest(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.ResourceGenerationRecordTest()
        fixture.setUp()
        self.scope = fixture.scope

    def test_stopped_requires_actual_manager_and_empty_descendant_groups(self):
        self.scope['manager']['pid'] = os.getpid()
        groups = self.scope['groups']
        with patch.object(publication, 'process_identity', return_value=self.scope['manager']), \
             patch.object(publication, 'group_identity', side_effect=lambda path, uid: next(value for value in groups.values() if value['path'] == path)), \
             patch.object(publication, 'read_bytes', return_value=b'populated 0\nfrozen 0\n'):
            publication.stopped(self.scope)
            with patch.object(publication, 'read_bytes', return_value=b'populated 1\nfrozen 0\n'), self.assertRaises(publication.PublicationRefused):
                publication.stopped(self.scope)
            with patch.object(publication, 'process_identity', return_value={}), self.assertRaises(publication.PublicationRefused):
                publication.stopped(self.scope)

    def test_new_boot_never_reads_or_signals_current_process_and_same_boot_needs_absence(self):
        current = copy.deepcopy(self.scope)
        current['boot_id'] = str(uuid.uuid4())
        with patch.object(publication, 'read_bytes', side_effect=AssertionError('New boot must not inspect a reused PID')):
            publication.old_gone(self.scope, current)
        current = copy.deepcopy(self.scope)
        with self.assertRaises(publication.PublicationRefused):
            publication.old_gone(self.scope, current)
        current['parent']['inode'] += 100
        with patch.object(publication, 'read_bytes', side_effect=FileNotFoundError):
            publication.old_gone(self.scope, current)
        fields = ['S'] + ['0'] * 18 + [self.scope['manager']['birth']]
        raw = ('2000 (fixture process) ' + ' '.join(fields)).encode()
        with patch.object(publication, 'read_bytes', return_value=raw), self.assertRaises(publication.PublicationRefused):
            publication.old_gone(self.scope, current)
        fields[-1] = str(int(fields[-1]) + 1)
        with patch.object(publication, 'read_bytes', return_value=('2000 (fixture process) ' + ' '.join(fields)).encode()):
            publication.old_gone(self.scope, current)
