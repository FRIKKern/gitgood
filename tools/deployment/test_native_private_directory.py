"""Real directory metadata only; controller admission remains outside this scope."""
import os
from pathlib import Path, PurePosixPath
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import native_controller_scope as scope


class PrivateDirectorySpellingTest(unittest.TestCase):
    def test_relative_parent_traversal_and_nul_refuse_before_io(self):
        with patch.object(scope,'Path',PurePosixPath):
            for path in ['relative','../private','/var/../private','/var/\0private']:
                with self.subTest(path=path),self.assertRaises(scope.ControllerScopeRefused):
                    scope.private_directory(path,1000,1000)

    def test_double_root_unc_and_windows_drive_spellings_refuse_before_io(self):
        with patch.object(scope,'Path',PurePosixPath):
            for path in ['//etc/private','//server/share','C:/private','C:\\private']:
                with self.subTest(path=path),self.assertRaises(scope.ControllerScopeRefused):
                    scope.private_directory(path,1000,1000)


@unittest.skipUnless(sys.platform=='linux' and getattr(os,'getuid',lambda:1)()==0,
    'actual Root metadata over an isolated ordinary-owned private directory')
class RootPrivateDirectoryTest(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='gitgood-private-directory-',dir='/var/lib')
        self.addCleanup(temporary.cleanup);self.base=Path(temporary.name)
        self.parent=self.base/'parent';self.parent.mkdir(mode=0o700)
        self.path=self.parent/'private';self.path.mkdir(mode=0o700)
        self.uid,self.gid=65503,1000;os.chown(self.path,self.uid,self.gid)

    def observe(self,path=None):
        return scope.private_directory(self.path if path is None else path,self.uid,self.gid)

    def test_complete_identity_and_all_original_parent_fields(self):
        leaf=self.path.lstat()
        expected={'device':leaf.st_dev,'inode':leaf.st_ino,'uid':leaf.st_uid}
        parents=[]
        for path in self.path.parents:
            info=path.lstat()
            parents.append((str(path),info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode))
        self.assertEqual(self.observe(),(expected,tuple(parents)))

    def test_leaf_alias_refuses_even_when_original_inode_matches(self):
        original=self.base/'retained-private';self.path.rename(original)
        self.path.symlink_to(original,target_is_directory=True)
        self.assertEqual(self.path.stat().st_ino,original.stat().st_ino)
        with self.assertRaises(scope.ControllerScopeRefused):self.observe()
        self.assertTrue(original.is_dir())

    def test_ancestor_alias_refuses_even_when_original_leaf_inode_matches(self):
        original=self.base/'retained-parent';self.parent.rename(original)
        self.parent.symlink_to(original,target_is_directory=True)
        self.assertEqual(self.path.stat().st_ino,(original/'private').stat().st_ino)
        with self.assertRaises(scope.ControllerScopeRefused):self.observe()
        self.assertTrue((original/'private').is_dir())

    def test_parent_traversal_cannot_select_original_leaf(self):
        with self.assertRaises(scope.ControllerScopeRefused):
            self.observe(self.parent/'..'/'parent'/'private')

    def test_leaf_mode_changes_refuse(self):
        for mode in [0o750,0o755,0o777]:
            self.path.chmod(mode)
            with self.subTest(mode=mode),self.assertRaises(scope.ControllerScopeRefused):self.observe()

    def test_leaf_owner_change_refuses(self):
        os.chown(self.path,self.uid+1,self.gid)
        with self.assertRaises(scope.ControllerScopeRefused):self.observe()

    def test_leaf_group_change_refuses(self):
        os.chown(self.path,self.uid,self.gid+1)
        with self.assertRaises(scope.ControllerScopeRefused):self.observe()

    def test_writable_ancestor_refuses(self):
        self.parent.chmod(0o777)
        with self.assertRaises(scope.ControllerScopeRefused):self.observe()

    def test_non_root_ancestor_refuses(self):
        os.chown(self.parent,self.uid,self.gid)
        with self.assertRaises(scope.ControllerScopeRefused):self.observe()

    def test_leaf_replacement_changes_original_directory_identity(self):
        before=self.observe();original=self.base/'retained-private';self.path.rename(original)
        self.path.mkdir(mode=0o700);os.chown(self.path,self.uid,self.gid)
        after=self.observe()
        self.assertNotEqual(before[0],after[0]);self.assertEqual(before[1],after[1])
        self.assertTrue(original.is_dir())

    def test_parent_replacement_retaining_leaf_inode_changes_parent_custody(self):
        before=self.observe();original=self.base/'retained-parent';self.parent.rename(original)
        self.parent.mkdir(mode=0o700);(original/'private').rename(self.path)
        after=self.observe()
        self.assertEqual(before[0],after[0]);self.assertNotEqual(before[1],after[1])

    def test_twenty_observations_read_fresh_complete_original_metadata(self):
        before=self.observe();started=time.monotonic_ns()
        for _ in range(20):self.assertEqual(self.observe(),before)
        print('actual_private_directory_observations=20 elapsed_ms='+str((time.monotonic_ns()-started)//1000000),flush=True)


if __name__=='__main__':unittest.main()
