import copy
import os
from pathlib import Path
import sys
import unittest
import uuid
from unittest.mock import patch

import native_generation_reader as reader
from resource_generations import canonical, make_generation
from upgrade_journal import fcntl
import test_generation_publication as publication_fixtures


@unittest.skipUnless(sys.platform == "linux" and os.getuid() != 0, "ordinary Linux generation reader")
class NativeGenerationReaderTest(unittest.TestCase):
    def setUp(self):
        # Actual ordinary filesystem publication; service/DB observations are
        # explicit stand-ins. Actual worker/VM experiments remain separate.
        self.fixture = publication_fixtures.GenerationPublicationTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.result = self.fixture.controller().publish(**self.fixture.arguments)
        self.worker = {"service_scope": self.fixture.scope, "worker": "native",
                       "owner": {"pid": 42, "birth": "420"}, "caller": {"pid": 43, "birth": "430"},
                       "generation_publication_established": False, "installation_readiness_established": False}
        for name, value in [('observe_worker', lambda *a, **kw: copy.deepcopy(self.worker)),
                            ('persistent_identity', lambda *a: copy.deepcopy(self.fixture.binding))]:
            mock = patch.object(reader, name, value);mock.start();self.addCleanup(mock.stop)

    def open(self):
        value = object.__new__(reader.NativeGenerationReader)
        original = self.fixture.controller()
        value.__dict__.update(original.__dict__)
        value.custody = reader._ReadOnlyCustody(self.fixture.history, self.fixture.installation,
                                              self.fixture.identity, self.fixture.lock_identity)
        return value

    def admit(self):
        return self.open().admit(worker="native", owner_pid=42)

    def snapshot(self):
        return {str(path.relative_to(self.fixture.history)): (path.stat().st_ino, path.read_bytes())
                for path in self.fixture.history.rglob('*') if path.is_file()}

    def receipt(self):
        return self.fixture.history/'generation-receipts-v2'/(self.fixture.arguments['operation']+'.json')

    def test_complete_current_publication_admits_without_writer_or_readiness_authority(self):
        before=self.snapshot();result=self.admit()
        self.assertTrue(result['published_generation_admitted'])
        self.assertEqual(result['pointer'],self.result['pointer'])
        self.assertEqual(result['worker_observation'],self.worker)
        for name in ['writer_exclusion_established','installation_readiness_established','lifecycle_responsibility_admitted']:
            self.assertFalse(result[name])
        self.assertEqual(self.snapshot(),before)

    def test_controller_lifecycle_lock_does_not_deadlock_or_get_acquired_by_reader(self):
        fd=os.open(self.fixture.history/'.upgrade-history-lock-v1',os.O_RDWR)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with patch.object(fcntl,'flock',side_effect=AssertionError('reader must not acquire flock')) as lock:
                self.assertTrue(self.admit()['published_generation_admitted'])
            lock.assert_not_called()
        finally:os.close(fd)

    def test_missing_completion_refuses_without_repairing_original_history(self):
        self.receipt().unlink();before=self.snapshot()
        with self.assertRaises(reader.GenerationAdmissionRefused):self.admit()
        self.assertEqual(self.snapshot(),before)

    def test_partial_or_unknown_responsibility_refuses_without_cleanup(self):
        for directory in [self.fixture.history,self.fixture.history/'generation-records-v2',self.fixture.history/'generation-transitions-v2',self.fixture.history/'generation-receipts-v2']:
            path=directory/('.partial-'+str(uuid.uuid4()));path.write_bytes(b'uncertain');path.chmod(0o600)
            with self.subTest(directory=directory.name),self.assertRaises(reader.GenerationAdmissionRefused):self.admit()
            self.assertEqual(path.read_bytes(),b'uncertain');path.unlink()
        path=self.fixture.history/'initial-install-journal-v1.json';path.write_bytes(b'{}');path.chmod(0o600)
        with self.assertRaises(reader.GenerationAdmissionRefused):self.admit()
        self.assertEqual(path.read_bytes(),b'{}')

    def test_boot_manager_or_group_replacement_refuses_the_old_publication(self):
        for mutate in [lambda s:s.update(boot_id=str(uuid.uuid4())),lambda s:s['manager'].update(birth='999'),lambda s:s['groups']['native'].update(inode=999)]:
            replacement=copy.deepcopy(self.worker);mutate(replacement['service_scope'])
            with patch.object(reader,'observe_worker',return_value=replacement),self.assertRaises(reader.GenerationAdmissionRefused):self.admit()

    def test_retained_successor_before_pointer_refuses_current_runtime(self):
        scope=copy.deepcopy(self.fixture.scope);scope['boot_id']=str(uuid.uuid4())
        with self.fixture.controller().custody as custody:
            previous=custody._records()[self.result['pointer']['generation_sha256']]
            custody.retain(make_generation(scope,self.fixture.expected,generation=str(uuid.uuid4()),created_at='2026-10-10T07:02:00.000000Z',previous=previous))
        before=self.snapshot()
        with self.assertRaises(reader.GenerationAdmissionRefused):self.admit()
        self.assertEqual(self.snapshot(),before)

    def test_changed_live_binding_or_worker_between_observations_refuses(self):
        changed={**self.fixture.binding,'changed':True}
        with patch.object(reader,'persistent_identity',return_value=changed),self.assertRaises(reader.GenerationAdmissionRefused):self.admit()
        replacement=copy.deepcopy(self.worker);replacement['owner']['birth']='421'
        with patch.object(reader,'observe_worker',side_effect=[self.worker,replacement]),self.assertRaises(reader.GenerationAdmissionRefused):self.admit()

    def test_identical_receipt_replaced_between_snapshots_refuses(self):
        calls=0
        def observe(*args):
            nonlocal calls
            calls+=1
            if calls==1:
                path=self.receipt();temporary=path.with_suffix('.replacement');temporary.write_bytes(path.read_bytes());temporary.chmod(0o600);os.replace(temporary,path)
            return copy.deepcopy(self.fixture.binding)
        with patch.object(reader,'persistent_identity',side_effect=observe),self.assertRaises(reader.GenerationAdmissionRefused):self.admit()

    def test_noncanonical_or_changed_completion_and_transition_refuse(self):
        receipt=self.receipt();original=receipt.read_bytes()
        for raw in [original+b'\n',canonical({'protocol':2,'installation':self.fixture.installation,'pointer_sha256':'a'*64,'status':'complete'})]:
            receipt.write_bytes(raw)
            with self.assertRaises(reader.GenerationAdmissionRefused):self.admit()
        receipt.write_bytes(original)
        path=self.fixture.history/'generation-transitions-v2'/(self.fixture.arguments['operation']+'.json')
        import json
        value=json.loads(path.read_bytes());value['lifecycle_responsibilities']=[{'unknown':True}];path.write_bytes(canonical(value))
        with self.assertRaises(reader.GenerationAdmissionRefused):self.admit()

    def test_missing_store_or_replaced_lock_refuses_without_manufacturing_authority(self):
        lock=self.fixture.history/'.upgrade-history-lock-v1';old=lock.with_suffix('.old');lock.rename(old);lock.write_bytes(b'');lock.chmod(0o600)
        with self.assertRaises(reader.GenerationAdmissionRefused):self.admit()
        lock.unlink();old.rename(lock)
        store=self.fixture.history/'generation-records-v2';store.rename(store.with_suffix('.retained'))
        with self.assertRaises(reader.GenerationAdmissionRefused):self.admit()
        self.assertFalse(store.exists())

    def test_reader_mutators_are_unavailable(self):
        value=self.open();before=self.snapshot()
        for effect in [lambda:value.publish(),lambda:value._write(self.receipt(),{}),lambda:value.custody.retain({})]:
            with self.assertRaises(reader.GenerationAdmissionRefused):effect()
        self.assertEqual(self.snapshot(),before)


if __name__ == '__main__':unittest.main()
