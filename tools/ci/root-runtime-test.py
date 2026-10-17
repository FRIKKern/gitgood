#!/usr/bin/env python3
"""Bounded archive/identity checks; downloading/installing is never a test."""
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
import root_runtime_probe as probe


class RuntimeArchiveTest(unittest.TestCase):
    def file(self, name=None, size=1):
        value = tarfile.TarInfo(name or probe.NAME + '/lib/file');value.size = size
        return value

    def test_pinned_release_and_public_checksum_are_exact_without_network(self):
        self.assertEqual(probe.URL, 'https://downloads.python.org/pypy/pypy3.11-v8.0.1-linux64.tar.gz')
        self.assertEqual(probe.ARCHIVE_SHA256, '706965bcf372752ba69dafd59d860e51bc2fadbb0f8a47cec3426125d7058ceb')

    def test_absolute_traversal_alias_duplicate_and_wrong_prefix_refuse(self):
        for name in ['/outside', '../outside', probe.NAME + '/../outside', './' + probe.NAME + '/file',
                probe.NAME + '//file', 'other/file', probe.NAME + '/nul\0file']:
            with self.subTest(name=name),self.assertRaises(ValueError):probe.members([self.file(name)])
        with self.assertRaises(ValueError):probe.members([self.file(), self.file()])

    def test_only_internal_links_and_regular_types_are_admitted(self):
        original = self.file(probe.NAME + '/file')
        link = self.file(probe.NAME + '/alias', 0);link.type = tarfile.SYMTYPE;link.linkname = 'file'
        hard = self.file(probe.NAME + '/hard', 0);hard.type = tarfile.LNKTYPE;hard.linkname = probe.NAME + '/file'
        self.assertEqual(len(probe.members([original, link, hard])), 3)
        for target in ['/etc/passwd', '../outside']:
            link.linkname = target
            with self.assertRaises(ValueError):probe.members([original, link])
        special = self.file(probe.NAME + '/fifo', 0);special.type = tarfile.FIFOTYPE
        with self.assertRaises(ValueError):probe.members([original, special])

    def test_entry_implicit_directory_and_byte_bounds_refuse_before_extraction(self):
        with patch.object(probe, 'MAX_ENTRIES', 2),self.assertRaises(ValueError):
            probe.members([self.file(probe.NAME + '/a/b/file')])
        with patch.object(probe, 'MAX_ENTRIES', 2),self.assertRaises(ValueError):
            probe.members(self.file(probe.NAME + '/file' + str(number)) for number in range(3))
        for size in [True, -1, 128 * 1024**2 + 1]:
            with self.subTest(size=size),self.assertRaises(ValueError):probe.members([self.file(size=size)])
        with patch.object(probe, 'MAX_BYTES', 1),self.assertRaises(ValueError):probe.members([self.file(size=2)])

    def test_closed_runtime_identity_refuses_unknown_private_fields_and_bad_types(self):
        identity = {'protocol': 1, 'implementation': 'pypy', 'python_major': 3, 'python_minor': 11,
            'pypy_version': '8.0.1', 'archive_sha256': probe.ARCHIVE_SHA256,
            'executable_sha256': 'a' * 64, 'tree_sha256': 'b' * 64, 'file_count': 2, 'unpacked_bytes': 10}
        self.assertEqual(probe.validate_identity(identity), identity)
        for changes in [{'private_path': '/synthetic/private'}, {'file_count': True}, {'unpacked_bytes': -1},
                {'python_minor': 12}, {'pypy_version': 'unselected'}, {'tree_sha256': 'not-a-hash'}]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):probe.validate_identity({**identity, **changes})


@unittest.skipUnless(sys.platform == 'linux' and getattr(os, 'getuid', lambda: -1)() == 0,
    'Actual owned Root namespace required')
class OwnedRuntimeTreeTest(unittest.TestCase):
    def test_owned_tree_hash_changes_on_content_and_accepts_only_internal_symlink(self):
        with tempfile.TemporaryDirectory(prefix='gitgood-runtime-test-', dir='/var/lib') as directory:
            root = Path(directory);path = root / 'file';path.write_bytes(b'owned');path.chmod(0o600)
            link = root / 'link';link.symlink_to('file')
            first = probe.tree_identity(root)
            self.assertEqual(first, probe.tree_identity(root));self.assertEqual(first['file_count'], 2)
            path.write_bytes(b'changed');self.assertNotEqual(probe.tree_identity(root)['tree_sha256'], first['tree_sha256'])

    def test_writable_files_and_escaping_links_refuse_without_reading_external_content(self):
        with tempfile.TemporaryDirectory(prefix='gitgood-runtime-test-', dir='/var/lib') as directory:
            root = Path(directory);path = root / 'file';path.write_bytes(b'owned');path.chmod(0o666)
            with self.assertRaises(ValueError):probe.tree_identity(root)
            path.chmod(0o600);(root / 'link').symlink_to('/etc/passwd')
            with self.assertRaises(ValueError):probe.tree_identity(root)


if __name__ == '__main__':unittest.main(verbosity=2)
