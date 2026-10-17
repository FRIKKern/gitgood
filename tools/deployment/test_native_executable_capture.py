import hashlib
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import native_durable_binding as binding


class ExecutableCaptureInputTest(unittest.TestCase):
    def test_closed_path_contract_refuses_unknown_missing_relative_and_duplicate_inputs(self):
        paths = {name: '/trusted/' + name for name in ['python', 'node', 'git', 'psql', 'caddy']}
        for value in [{**paths, 'other': '/trusted/other'}, {k:v for k,v in paths.items() if k != 'git'},
                      {**paths, 'python': 'relative'}, {**paths, 'python': '/trusted/node'},
                      {**paths, 'python': '/trusted/\0python'}]:
            with self.subTest(value=value), self.assertRaises(binding.BindingRefused):
                binding._CapturedExecutableDigests(value)


@unittest.skipUnless(sys.platform == 'linux' and os.getuid() == 0, 'actual protected Root executable files')
class ExecutableCaptureRootTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='gitgood-executable-capture-', dir='/var/lib')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.paths = {name: str(self.root/name) for name in ['python', 'node', 'git', 'psql', 'caddy']}
        for name, path in self.paths.items():
            Path(path).write_bytes(('synthetic-not-executed-' + name).encode() * 64)
            Path(path).chmod(0o755)
        self.subject = binding._CapturedExecutableDigests(self.paths)
        self.addCleanup(self.subject.close)

    def lost(self):
        with self.assertRaises((binding.BindingRefused, OSError)):
            self.subject.read(self.paths['python'])
        self.assertFalse(self.subject.usable)

    def test_hash_once_and_repeated_checks_preserve_actual_digests(self):
        original = binding.executable
        with patch.object(binding, 'executable', wraps=original) as streamed:
            first = {name: self.subject.read(path) for name,path in self.paths.items()}
            self.subject.freeze()
            second = {name: self.subject.read(path) for name,path in self.paths.items()}
        self.assertEqual(first, second)
        self.assertEqual(streamed.call_count, 5)
        for name, value in first.items():
            self.assertEqual(value['sha256'], hashlib.sha256(Path(self.paths[name]).read_bytes()).hexdigest())

    def test_same_content_replacement_refuses_and_cannot_adopt_restored_original(self):
        path = Path(self.paths['python']); self.subject.read(str(path))
        old = path.with_name('original-python'); path.rename(old)
        path.write_bytes(old.read_bytes()); path.chmod(0o755)
        self.lost()
        path.unlink(); old.rename(path)
        self.lost()

    def test_same_inode_edit_with_restored_mtime_refuses(self):
        path = Path(self.paths['python']); self.subject.read(str(path)); before = path.stat()
        raw = path.read_bytes(); path.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.lost()

    def test_permission_owner_and_hard_link_changes_refuse(self):
        for change in ['permissions', 'owner', 'hard-link']:
            with self.subTest(change=change):
                path = Path(self.paths['python'])
                self.subject = binding._CapturedExecutableDigests(self.paths); self.subject.read(str(path))
                if change == 'permissions': path.chmod(0o775)
                elif change == 'owner': os.chown(path, 1000, 1000)
                else: os.link(path, self.root/'extra-link')
                self.lost()
                if change == 'permissions': path.chmod(0o755)
                elif change == 'owner': os.chown(path, 0, 0)
                else: (self.root/'extra-link').unlink()

    def test_changed_parent_permissions_refuse(self):
        self.subject.read(self.paths['python']); self.root.chmod(0o777)
        self.lost(); self.root.chmod(0o700)

    def test_changed_parent_identity_refuses(self):
        self.subject.read(self.paths['python'])
        previous = self.root.with_name(self.root.name + '-previous')
        self.root.rename(previous)
        self.root.mkdir(mode=0o700)
        try:
            path = Path(self.paths['python']); path.write_bytes((previous/'python').read_bytes()); path.chmod(0o755)
            self.lost()
        finally:
            path.unlink(); self.root.rmdir(); previous.rename(self.root)

    def test_parent_alias_substitution_refuses_with_original_executable_inode(self):
        parent=self.root/'parent';parent.mkdir(mode=0o700)
        path=parent/'python';Path(self.paths['python']).rename(path)
        paths={**self.paths,'python':str(path)}
        subject=binding._CapturedExecutableDigests(paths);self.addCleanup(subject.close)
        subject.read(str(path));inode=path.stat().st_ino
        previous=self.root/'original-parent';parent.rename(previous);parent.symlink_to(previous,target_is_directory=True)
        self.assertEqual(path.stat().st_ino,inode)
        with self.assertRaises(binding.BindingRefused):subject.read(str(path))
        self.assertFalse(subject.usable)
        self.assertEqual((previous/'python').stat().st_ino,inode)

    def test_repeated_actual_metadata_checks_preserve_five_original_digests(self):
        original={name:self.subject.read(path) for name,path in self.paths.items()}
        self.subject.freeze();started=time.monotonic()
        with patch.object(binding,'executable',side_effect=AssertionError('Unexpected rehash')):
            for _ in range(20):
                self.assertEqual({name:self.subject.read(path) for name,path in self.paths.items()},original)
        print('actual_executable_metadata_reads=100 elapsed_ms='+str(int((time.monotonic()-started)*1000)))

    def test_alias_retargeting_refuses(self):
        real = Path(self.paths['python'])
        alias = self.root/'python-alias'; alias.symlink_to(real)
        paths = {**self.paths, 'python': str(alias)}
        self.subject = binding._CapturedExecutableDigests(paths)
        self.subject.read(str(alias))
        alias.unlink(); alias.symlink_to(self.paths['node'])
        with self.assertRaises(binding.BindingRefused): self.subject.read(str(alias))
        self.assertFalse(self.subject.usable)

    def test_changed_content_during_initial_hash_discards_result(self):
        original = binding.executable
        def changed(path):
            result = original(path)
            file = Path(path); file.write_bytes(file.read_bytes() + b'changed')
            return result
        with patch.object(binding, 'executable', side_effect=changed): self.lost()

    def test_returned_record_and_original_input_are_not_adopted_from_caller_mutation(self):
        value = self.subject.read(self.paths['python']); original = dict(value)
        value['sha256'] = '0' * 64
        self.paths['node'] = '/foreign/node'
        self.assertEqual(self.subject.read(self.paths['python']), original)
        with self.assertRaises(binding.BindingRefused): self.subject.read('/foreign/node')

    def test_partial_capture_cannot_freeze_and_closed_capture_cannot_resume(self):
        self.subject.read(self.paths['python'])
        with self.assertRaises(binding.BindingRefused): self.subject.freeze()
        self.lost()

    def test_frozen_capture_cannot_expand_its_original_contract(self):
        for path in self.paths.values(): self.subject.read(path)
        self.subject.freeze()
        self.subject.paths['foreign'] = str(self.root/'foreign')
        (self.root/'foreign').write_bytes(b'never admitted'); (self.root/'foreign').chmod(0o755)
        with self.assertRaises(binding.BindingRefused): self.subject.read(str(self.root/'foreign'))
        self.assertFalse(self.subject.usable)


if __name__ == '__main__': unittest.main()
