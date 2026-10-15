import os
from pathlib import Path, PurePosixPath
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import native_service_scope as service


class RootPathSpellingTest(unittest.TestCase):
    """POSIX spelling stand-in only; actual path custody needs Linux cases."""
    def test_noncanonical_absolute_parent_and_double_root_aliases_refuse(self):
        for path in ('relative/owned','/root/../owned','//root/owned','../owned',''):
            with patch.object(service,'Path',side_effect=PurePosixPath),self.subTest(path=path):
                with self.assertRaises(service.ServiceRefused):service._root_file_path(path)

    def test_normalized_posix_path_spelling_retains_existing_pathlib_semantics(self):
        with patch.object(service,'Path',side_effect=PurePosixPath):
            self.assertEqual(service._root_file_path('/root/./owned'),PurePosixPath('/root/owned'))
            self.assertEqual(service._root_file_path('/root//owned'),PurePosixPath('/root/owned'))


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

    def test_symlink_ancestor_refuses_with_the_original_leaf_inode_preserved(self):
        top=self.root/'top';top.mkdir(mode=0o700)
        parent=top/'parent';parent.mkdir(mode=0o700)
        self.path.rename(parent/'owned');self.path=parent/'owned'
        self.subject=service._CapturedRootFiles();self.subject.read(self.path)
        inode=self.path.stat().st_ino
        moved=self.root/'old-top';top.rename(moved);top.symlink_to(moved,target_is_directory=True)
        self.assertEqual(self.path.stat().st_ino,inode)
        self.lost();self.assertEqual((moved/'parent/owned').read_bytes(),b'original')

    def test_changed_parent_permissions_poison_even_with_original_leaf_intact(self):
        self.root.chmod(0o777);self.lost()
        self.root.chmod(0o700);self.lost()

    def test_hardlinked_original_refuses_without_modifying_either_name(self):
        other=self.root/'other';os.link(self.path,other)
        self.lost()
        self.assertEqual(other.read_bytes(),b'original');self.assertEqual(self.path.read_bytes(),b'original')

    def test_parent_alias_is_refused_by_content_and_metadata_paths(self):
        parent=self.root/'parent';parent.mkdir(mode=0o700)
        alias=parent/'..'/'owned'
        for observe in (lambda:service.root_file(alias),
                lambda:service._CapturedRootFiles._fingerprint(alias,16777216,False)):
            with self.assertRaises(service.ServiceRefused):observe()
        self.assertEqual(self.path.read_bytes(),b'original')

    def test_repeated_actual_metadata_and_content_observations_remain_fresh(self):
        expected=service._CapturedRootFiles._fingerprint(self.path,16777216,False)
        started=time.monotonic()
        for _ in range(20):
            self.assertEqual(service._CapturedRootFiles._fingerprint(self.path,16777216,False),expected)
            self.assertEqual(service.root_file(self.path),self.original)
        print('actual_root_file_observation_pairs=20 elapsed_ms='+str(int((time.monotonic()-started)*1000)))


if __name__ == '__main__': unittest.main()
