import copy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import native_generation_lease_guard as guard
import test_native_generation_reader as reader_fixtures


@unittest.skipUnless(sys.platform == 'linux' and os.getuid() != 0, 'ordinary Linux generation guard')
class GenerationLeaseGuardTest(unittest.TestCase):
    def setUp(self):
        # Actual ordinary publication/history custody. Live service, persistent
        # metadata and database observation are explicit boundary stand-ins.
        self.fixture = reader_fixtures.NativeGenerationReaderTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.worker = copy.deepcopy(self.fixture.worker)
        self.metadata = {'fixture': [1, 2, 3]}
        for name, value in [('observe_worker', lambda *a, **kw: copy.deepcopy(self.worker)),
                            ('persistent_identity', lambda *a: copy.deepcopy(self.fixture.fixture.binding)),
                            ('persistent_fingerprint', lambda *a: copy.deepcopy(self.metadata))]:
            mock = patch.object(guard, name, value); mock.start(); self.addCleanup(mock.stop)
        self.subject = guard.NativeGenerationLeaseGuard(self.fixture.open(), worker='native', owner_pid=42)
        # Root file content custody has separate actual root-fixture tests.
        # The service observation here deliberately remains a stand-in.
        mock = patch.object(self.subject.root_files, 'freeze', return_value=None)
        mock.start(); self.addCleanup(mock.stop)
        for name, value in [('_observe_service', lambda *a, **kw: copy.deepcopy(self.worker['service_scope'])),
                            ('_ancestry', lambda *a: [copy.deepcopy(self.worker['caller']), copy.deepcopy(self.worker['owner'])])]:
            mock = patch.object(guard, name, value); mock.start(); self.addCleanup(mock.stop)
        self.addCleanup(self.subject.close)

    def assert_lost(self):
        with self.assertRaises(guard.GenerationLeaseGuardRefused): self.subject.check()
        self.assertFalse(self.subject.usable)
        self.assertIsNone(self.subject.reader.custody.lock)

    def test_stable_checks_keep_original_digests_and_read_only_history(self):
        before = self.fixture.snapshot(); captured = self.subject.capture()
        for _ in range(3):
            current = self.subject.check()
            self.assertTrue(current['current'])
            for name in ['scope_sha256', 'history_sha256', 'persistent_files_sha256']:
                self.assertEqual(current[name], captured[name])
        self.assertEqual(before, self.fixture.snapshot())

    def test_periodic_checks_open_no_database_and_take_no_lifecycle_lock(self):
        self.subject.capture()
        with patch.object(guard, 'persistent_identity', side_effect=AssertionError('no database observation')) as database, \
             patch.object(reader_fixtures.fcntl, 'flock', side_effect=AssertionError('no lifecycle flock')) as flock:
            self.assertTrue(self.subject.check()['current'])
        database.assert_not_called(); flock.assert_not_called()

    def test_new_helper_birth_is_allowed_with_same_validated_owner_and_scope(self):
        self.subject.capture()
        self.worker['caller'].update(pid=44, birth='440')
        self.assertTrue(self.subject.check()['current'])

    def test_changed_owner_birth_poisoning_survives_restored_observation(self):
        self.subject.capture(); self.worker['owner']['birth'] = '421'
        self.assert_lost()
        self.worker['owner']['birth'] = '420'
        self.assert_lost()
        with self.assertRaises(guard.GenerationLeaseGuardRefused): self.subject.capture()

    def test_changed_manager_birth_refuses_same_pointer(self):
        self.subject.capture(); self.worker['service_scope']['manager']['birth'] = '999'
        self.assert_lost()

    def test_identical_completion_replacement_refuses_without_cleanup(self):
        self.subject.capture(); path = self.fixture.receipt()
        replacement = path.with_suffix('.replacement')
        replacement.write_bytes(path.read_bytes()); replacement.chmod(0o600)
        os.replace(replacement, path); before = self.fixture.snapshot()
        self.assert_lost(); self.assertEqual(before, self.fixture.snapshot())

    def test_new_partial_responsibility_is_preserved_and_refuses(self):
        self.subject.capture()
        path = self.fixture.fixture.history / '.partial-uncertain'
        path.write_bytes(b'uncertain'); path.chmod(0o600)
        self.assert_lost(); self.assertEqual(path.read_bytes(), b'uncertain')

    def test_in_place_edit_with_restored_mtime_still_refuses(self):
        self.subject.capture(); path = self.fixture.receipt(); before = path.stat()
        raw = path.read_bytes()
        path.write_bytes(b' ' + raw[1:])
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assert_lost()

    def test_owner_change_during_periodic_observation_refuses(self):
        self.subject.capture()
        original = self.subject._current_worker
        calls = 0
        def changed():
            nonlocal calls
            calls += 1
            value, chain = original()
            if calls == 2: chain[0]['birth'] = 'changed'
            return value, chain
        with patch.object(self.subject, '_current_worker', side_effect=changed):
            self.assert_lost()

    def test_periodic_checks_do_not_reparse_already_validated_history(self):
        self.subject.capture()
        with patch.object(self.subject.reader, '_snapshot', side_effect=AssertionError('no reparse')):
            self.assertTrue(self.subject.check()['current'])

    def test_changed_persistent_metadata_refuses_without_adopting_new_value(self):
        self.subject.capture(); self.metadata['fixture'] = [1, 2, 4]
        self.assert_lost(); self.metadata['fixture'] = [1, 2, 3]; self.assert_lost()

    def test_failed_capture_cannot_retry_and_closes_its_own_descriptor(self):
        with patch.object(guard, 'persistent_identity', side_effect=guard.DatabaseRefused('private detail')):
            with self.assertRaisesRegex(guard.GenerationLeaseGuardRefused, '^Native generation lease guard unavailable$'):
                self.subject.capture()
        self.assertFalse(self.subject.usable)
        self.assertIsNone(self.subject.reader.custody.lock)
        with self.assertRaises(guard.GenerationLeaseGuardRefused): self.subject.capture()

    def test_binding_change_between_full_capture_observations_refuses(self):
        binding = copy.deepcopy(self.fixture.fixture.binding)
        changed = {**binding, 'changed_fixture_identity':True}
        with patch.object(guard, 'persistent_identity', side_effect=[binding, changed]):
            with self.assertRaises(guard.GenerationLeaseGuardRefused): self.subject.capture()
        self.assertFalse(self.subject.usable)
        self.assertIsNone(self.subject.reader.custody.lock)

    def test_initial_partial_responsibility_refuses_without_cleanup(self):
        path = self.fixture.fixture.history / '.partial-initial-uncertain'
        path.write_bytes(b'uncertain'); path.chmod(0o600)
        before = self.fixture.snapshot()
        with self.assertRaises(guard.GenerationLeaseGuardRefused): self.subject.capture()
        self.assertEqual(before, self.fixture.snapshot())
        self.assertIsNone(self.subject.reader.custody.lock)

    def test_service_command_timeout_poisoning_closes_retained_custody(self):
        self.subject.capture()
        with patch.object(guard, '_observe_service', side_effect=guard.subprocess.TimeoutExpired('fixed command', 5)):
            self.assert_lost()

    def test_explicit_close_refuses_all_subsequent_checks_and_recapture(self):
        self.subject.capture(); self.subject.close(); self.assert_lost()
        with self.assertRaises(guard.GenerationLeaseGuardRefused): self.subject.capture()


if __name__ == '__main__': unittest.main()
