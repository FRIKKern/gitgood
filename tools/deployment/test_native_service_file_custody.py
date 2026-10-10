import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import native_service_scope as service


@unittest.skipUnless(sys.platform == 'linux', 'native file identities require Linux')
class InstalledFileCustodyTest(unittest.TestCase):
    def test_fixed_leaf_observation_rejects_replaced_parent_and_symlink_leaf(self):
        with tempfile.TemporaryDirectory(prefix='gitgood-leaf-custody-') as directory:
            root = Path(directory).resolve(strict=True)
            parent = root / 'parent'; parent.mkdir(mode=0o700)
            leaf = parent / 'native'; leaf.mkdir(mode=0o700)
            expected = service.group_identity(parent, os.getuid())
            self.assertEqual(service.group_identity(leaf, os.getuid(), _parent=expected),
                             service.group_identity(leaf, os.getuid()))
            moved_leaf = parent / 'old-native'; leaf.rename(moved_leaf); leaf.symlink_to(moved_leaf)
            with self.assertRaises(service.ServiceRefused):
                service.group_identity(leaf, os.getuid(), _parent=expected)
            leaf.unlink(); moved_leaf.rename(leaf)
            moved = root / 'old-parent'; parent.rename(moved)
            parent.mkdir(mode=0o700); (moved / 'native').rename(leaf)
            with self.assertRaises(service.ServiceRefused):
                service.group_identity(leaf, os.getuid(), _parent=expected)

    def test_content_cache_rechecks_actual_root_file_identity_and_does_not_adopt_unknown_paths(self):
        paths = [Path('/etc/os-release').resolve(strict=True), Path('/usr/lib/systemd/systemd').resolve(strict=True),
                 Path('/usr/bin/systemctl'), Path('/usr/bin/python3.12').resolve(strict=True)]
        subject = service._CapturedRootFiles()
        with patch.object(service, 'root_file', wraps=service.root_file) as read:
            for path in paths: subject.read(path)
            self.assertEqual(read.call_count, 4)
            for path in paths: subject.read(path)
            self.assertEqual(read.call_count, 4)
        subject.version = b'systemd 255\n'  # Explicit CLI-version boundary stand-in.
        subject.freeze()
        with self.assertRaises(service.ServiceRefused):
            subject.read(Path('/etc/machine-id'))
        self.assertFalse(subject.usable)

    def test_installed_version_is_bound_to_the_actual_root_executable(self):
        subject = service._CapturedRootFiles()
        with patch.object(service, 'bounded_command', wraps=service.bounded_command) as command:
            first = subject.installed_version(Path('/usr/bin/systemctl'))
            self.assertEqual(subject.installed_version(Path('/usr/bin/systemctl')), first)
            self.assertEqual(command.call_count, 1)


@unittest.skipUnless(sys.platform == 'linux' and os.getuid() == 0, 'root-owned disposable mutation fixtures')
class RootFileReplacementTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='gitgood-root-file-custody-', dir='/var/lib')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / 'owned'
        self.path.write_bytes(b'original')
        self.path.chmod(0o600)
        self.subject = service._CapturedRootFiles()
        self.original = self.subject.read(self.path)

    def lost(self):
        with self.assertRaises(service.ServiceRefused): self.subject.read(self.path)
        self.assertFalse(self.subject.usable)

    def test_identical_bytes_replacement_refuses(self):
        replacement = self.root / 'replacement'
        replacement.write_bytes(b'original'); replacement.chmod(0o600)
        os.replace(replacement, self.path)
        self.lost()

    def test_in_place_change_with_restored_mtime_refuses_and_cannot_revive(self):
        before = self.path.stat()
        self.path.write_bytes(b'changed!')
        os.utime(self.path, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.lost()
        self.path.write_bytes(b'original')
        self.lost()

    def test_permissions_change_is_permanent_refusal(self):
        self.path.chmod(0o666); self.lost()
        self.path.chmod(0o600); self.lost()

    def test_symlink_replacement_refuses_without_following_it(self):
        destination = self.root / 'destination'
        self.path.rename(destination)
        self.path.symlink_to(destination)
        self.lost()
        self.assertEqual(destination.read_bytes(), b'original')

    def test_parent_replacement_refuses_even_with_same_file_inode(self):
        parent = self.root / 'parent'; parent.mkdir(mode=0o700)
        self.path.rename(parent / 'owned')
        self.path = parent / 'owned'; self.subject = service._CapturedRootFiles()
        self.subject.read(self.path)
        moved = self.root / 'old-parent'; parent.rename(moved)
        parent.mkdir(mode=0o700); (moved / 'owned').rename(self.path)
        self.lost()

    def test_a_different_file_contract_cannot_reuse_validated_content(self):
        with self.assertRaises(service.ServiceRefused): self.subject.read(self.path, maximum=4096)
        self.assertFalse(self.subject.usable)


if __name__ == '__main__': unittest.main()
