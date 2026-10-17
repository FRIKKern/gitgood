#!/usr/bin/env python3
"""Owned Linux equivalence and fixture lifecycle checks; no product effects."""
import importlib
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch

sys.dont_write_bytecode = True
import native_fingerprint_probe as probe


class FixtureComparisonTest(unittest.TestCase):
    def setUp(self):
        class Files:
            @staticmethod
            def _fingerprint(path, maximum, executable):return ('same',)
        self.descriptor = vars(Files)['_fingerprint']
        self.service = SimpleNamespace(_CapturedRootFiles=Files,
            _root_file_path=PurePosixPath,
            _root_file_parents=lambda path: tuple((parent, str(parent)) for parent in path.parents),
            require=probe.require)
        self.native = SimpleNamespace(fingerprint=Mock(return_value=('same',)))
        class Stage:
            state = 'ready';usable = True
            def __init__(self):self.allocation = SimpleNamespace(close=Mock())
            def check(stage):return Files._fingerprint('/root/leaf', 4, False)
            def close(stage):stage.usable = False
        self.Stage = Stage;self.stage = Stage()

    def test_pairs_alternate_and_restore_original_without_profile_or_results_in_receipt(self):
        selected = []
        def check(stage):
            selected.append(vars(self.service._CapturedRootFiles)['_fingerprint'] is self.descriptor)
            return self.Stage.check(stage)
        with patch.object(probe.sys, 'getprofile', return_value=None):
            result = probe.compare_guard(self.service, self.native, check, self.stage)
        self.assertEqual(selected, [value for pair in range(20) for value in
            ((True, False) if pair % 2 == 0 else (False, True))])
        self.assertEqual(result['extra_read_only_checks'], 40)
        self.assertEqual(result['native_fingerprint_calls'], 20)
        self.assertEqual(len(result['pairs']), 20)
        self.assertEqual(set(result), {'diagnostic_only', 'pairs', 'extra_read_only_checks',
            'native_fingerprint_calls', 'elapsed_ms', 'original_fingerprint_restored', 'production_adoption'})
        self.assertTrue(all(set(row) == {'baseline_us', 'prototype_us'} for row in result['pairs']))
        self.assertIs(vars(self.service._CapturedRootFiles)['_fingerprint'], self.descriptor)

    def test_fallback_keeps_original_unsupported_domain_and_native_refusal_is_typed(self):
        original = Mock(return_value='fallback')
        fingerprint = probe.adapter(self.service, self.native, original)
        for maximum, executable in [(True, False), (0, False), (2**63, False), (4, 1), (1.5, False)]:
            self.assertEqual(fingerprint('/root/leaf', maximum, executable), 'fallback')
        for path in ['/' + 'a' * 1025, '/' + '/'.join(['a'] * 66)]:
            self.assertEqual(fingerprint(path, 4, False), 'fallback')
        self.native.fingerprint.assert_not_called()
        self.native.fingerprint.return_value = None
        with self.assertRaises(ValueError):fingerprint('/root/leaf', 4, False)

    def test_interruption_and_mismatch_restore_descriptor(self):
        for failure in [KeyboardInterrupt(), OSError(2, 'synthetic')]:
            self.native.fingerprint.side_effect = failure
            with self.assertRaises(type(failure)):
                probe.compare_guard(self.service, self.native, self.Stage.check, self.stage)
            self.assertIs(vars(self.service._CapturedRootFiles)['_fingerprint'], self.descriptor)
        self.native.fingerprint.side_effect = None
        self.native.fingerprint.return_value = ('changed',)
        with self.assertRaises(ValueError):
            probe.compare_guard(self.service, self.native, self.Stage.check, self.stage)
        self.assertIs(vars(self.service._CapturedRootFiles)['_fingerprint'], self.descriptor)

    def test_existing_profiler_and_unready_stage_refuse_before_extra_checks(self):
        with patch.object(probe.sys, 'getprofile', return_value=object()),self.assertRaises(ValueError):
            probe.compare_guard(self.service, self.native, self.Stage.check, self.stage)
        self.stage.state = 'staged'
        with self.assertRaises(ValueError):
            probe.compare_guard(self.service, self.native, self.Stage.check, self.stage)
        self.native.fingerprint.assert_not_called()

    def test_timers_start_after_pairs_and_original_method_is_restored_before_effect(self):
        measurements = MagicMock();original = vars(self.Stage)['check']
        experiment = probe.BeforeStageComparison(self.service, self.native, self.Stage, measurements)
        with experiment:
            self.assertEqual(self.stage.check(), ('same',))
            measurements.__enter__.assert_called_once()
            self.assertIs(vars(self.service._CapturedRootFiles)['_fingerprint'], self.descriptor)
            self.assertIs(vars(self.Stage)['check'], original)
        measurements.__exit__.assert_called_once()
        self.assertIs(vars(self.Stage)['check'], original)
        self.assertTrue(self.stage.usable)

    def test_mismatch_poisoning_and_partial_timer_setup_restore_without_revival(self):
        for mismatch in (True, False):
            with self.subTest(mismatch=mismatch):
                self.stage = self.Stage();measurements = MagicMock()
                if mismatch:self.native.fingerprint.return_value = ('different',)
                else:
                    self.native.fingerprint.return_value = ('same',)
                    measurements.__enter__.side_effect = RuntimeError('partial setup')
                original = vars(self.Stage)['check']
                with self.assertRaises((ValueError, RuntimeError)):
                    with probe.BeforeStageComparison(self.service, self.native, self.Stage, measurements):
                        self.stage.check()
                self.assertFalse(self.stage.usable)
                self.stage.allocation.close.assert_called_once()
                self.assertIs(vars(self.Stage)['check'], original)
                self.assertIs(vars(self.service._CapturedRootFiles)['_fingerprint'], self.descriptor)


@unittest.skipUnless(sys.platform == 'linux' and getattr(os, 'geteuid', lambda: -1)() == 0,
    'Compiled prototype and actual Root-owned Linux namespace required')
class ActualRootFingerprintTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'deployment'))
        cls.service = importlib.import_module('native_service_scope')
        cls.namespace = tempfile.TemporaryDirectory(prefix='gitgood-fingerprint-', dir='/var/lib')
        cls.addClassCleanup(cls.namespace.cleanup)
        cls.root = Path(cls.namespace.name);cls.root.chmod(0o700)
        compiled = Path(__file__).resolve().parents[2] / '.gitgood/native-fingerprint-probe' / probe.extension_name()
        for source in [compiled, Path(__file__).with_name('native-fingerprint-probe.c'),
                Path(__file__).with_name('native_fingerprint_probe.py')]:
            destination = cls.root / source.name
            shutil.copyfile(source, destination);destination.chmod(0o644)
        cls.native, cls.hashes = probe.load_native(cls.root)
        cls.original = staticmethod(cls.service._CapturedRootFiles._fingerprint)
        cls.fast = staticmethod(probe.adapter(cls.service, cls.native, cls.original))

    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix='case-', dir=self.root)
        self.addCleanup(self.scratch.cleanup)
        self.directory = Path(self.scratch.name);self.directory.chmod(0o700)
        self.parent = self.directory / 'parent';self.parent.mkdir(mode=0o700)
        self.path = self.parent / 'leaf';self.path.write_bytes(b'owned');self.path.chmod(0o600)

    def observe(self, method, path=None, maximum=4096, executable=False):
        try:return ('value', method(path or self.path, maximum, executable))
        except (self.service.ServiceRefused, OSError, ValueError) as error:
            return ('error', type(error), getattr(error, 'errno', None), getattr(error, 'filename', None))

    def same(self, **options):
        old = self.observe(self.original, **options);new = self.observe(self.fast, **options)
        self.assertEqual(new, old)
        return new

    def test_exact_fields_fresh_repeat_and_public_source_elf_identity(self):
        self.assertEqual(set(self.hashes), {'c_sha256', 'adapter_sha256', 'elf_sha256'})
        for value in self.hashes.values():self.assertRegex(value, r'^[0-9a-f]{64}$')
        original = self.same();self.assertEqual(original[0], 'value')
        for _ in range(20):self.assertEqual(self.same(), original)
        self.assertEqual(len(original[1][0]), 8)
        self.assertTrue(all(len(row) == 5 for row in original[1][1]))
        self.path.write_bytes(b'new owned content')
        self.assertNotEqual(self.same(), original)

    def test_leaf_owner_permissions_type_links_size_and_executable(self):
        for mode in (0o622, 0o666):
            self.path.chmod(mode);self.assertEqual(self.same()[0], 'error')
        self.path.chmod(0o600);os.chown(self.path, 1, 0)
        self.assertEqual(self.same()[0], 'error');os.chown(self.path, 0, 0)
        link = self.parent / 'hardlink';os.link(self.path, link)
        self.assertEqual(self.same()[0], 'error');link.unlink()
        for data, maximum in [(b'', 4096), (b'too big', 2)]:
            self.path.write_bytes(data);self.assertEqual(self.same(maximum=maximum)[0], 'error')
        self.path.write_bytes(b'owned');self.assertEqual(self.same(executable=True)[0], 'error')
        self.path.chmod(0o700);self.assertEqual(self.same(executable=True)[0], 'value')
        self.path.unlink();self.path.mkdir();self.assertEqual(self.same()[0], 'error')
        self.path.rmdir();self.path.symlink_to(self.parent)
        self.assertEqual(self.same()[0], 'error')

    def test_parent_mutations_and_early_predicate_refusal_precede_missing_leaf(self):
        self.path.unlink()
        for mode in (0o722, 0o777):
            self.parent.chmod(mode);self.assertEqual(self.same()[1], self.service.ServiceRefused)
        self.parent.chmod(0o700);os.chown(self.parent, 1, 0)
        self.assertEqual(self.same()[1], self.service.ServiceRefused);os.chown(self.parent, 0, 0)
        self.parent.rmdir();self.parent.symlink_to(self.directory)
        self.assertEqual(self.same()[1], self.service.ServiceRefused)
        self.parent.unlink();self.parent.write_bytes(b'not directory')
        self.assertEqual(self.same()[1], self.service.ServiceRefused)

    def test_missing_paths_embedded_nul_and_filesystem_surrogate_encoding(self):
        self.assertEqual(self.same(path=self.parent/'missing')[1], FileNotFoundError)
        self.assertEqual(self.same(path=str(self.parent/'nul')+'\0leaf')[1], ValueError)
        path = self.parent / os.fsdecode(b'leaf-\xff')
        path.write_bytes(b'owned');path.chmod(0o600)
        self.assertEqual(self.same(path=path)[0], 'value')
        for name in ['relative/leaf', '//root/leaf', '/root/../leaf']:
            self.assertEqual(self.same(path=name)[1], self.service.ServiceRefused)

    def test_timestamp_integer_equivalence_for_actual_filesystem_values(self):
        for value in (-1000000001, 1700000000123456789, 10000000000123456789):
            os.utime(self.path, ns=(value, value))
            actual = self.path.stat().st_mtime_ns
            result = self.same();self.assertEqual(result[0], 'value')
            self.assertEqual(result[1][0][3], actual)

    def test_captured_reader_refuses_warm_replacement_and_restoration_cannot_revive_it(self):
        owner = self.service._CapturedRootFiles;descriptor = vars(owner)['_fingerprint']
        subject = owner()
        try:
            owner._fingerprint = staticmethod(self.fast)
            original = subject.read(self.path)
            self.assertEqual(subject.read(self.path), original)
            self.path.write_bytes(b'replaced after capture')
            with self.assertRaises(self.service.ServiceRefused):subject.read(self.path)
            self.assertFalse(subject.usable)
        finally:owner._fingerprint = descriptor
        with self.assertRaises(self.service.ServiceRefused):subject.read(self.path)
        self.assertFalse(subject.usable)

    def test_adapter_fallback_and_c_input_bounds(self):
        for maximum, executable in [(True, False), (2**80, False), (4, 1), (4.5, False)]:
            self.same(maximum=maximum, executable=executable)
        for arguments, error in [((str(self.path), [], 4, False), TypeError),
                ((str(self.path), tuple(['/'] * 65), 4, False), ValueError),
                ((str(self.path), (), 2**80, False), OverflowError),
                ((str(self.path), (), True, False), TypeError),
                ((str(self.path), (), 0, False), ValueError),
                ((str(self.path), (), 4, 1), TypeError)]:
            with self.assertRaises(error):self.native.fingerprint(*arguments)
        self.assertEqual(len(self.native.fingerprint(str(self.path), tuple(['/'] * 64), 4096, False)[1]), 64)


if __name__ == '__main__':unittest.main(verbosity=2)
