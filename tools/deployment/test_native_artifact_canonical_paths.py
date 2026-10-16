"""Canonical artifact paths: portable models and owned Root filesystem cases."""
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import native_protected_artifact as protected
import native_root_artifact_policy as policy
import native_service_scope as service


UID=65503
GID=1000


class ArtifactPathGrammarTest(unittest.TestCase):
    def setUp(self):
        service._root_file_parent_plan.cache_clear()
        self.addCleanup(service._root_file_parent_plan.cache_clear)

    def test_invalid_spelling_refuses_before_metadata_or_open(self):
        subject=policy.NativeRootArtifactPolicyAllocation.__new__(policy.NativeRootArtifactPolicyAllocation)
        subject.directories={}
        with patch.object(policy,'Path',side_effect=PurePosixPath),patch.object(policy.os,'open') as opened:
            for raw in ['relative','/root/../owned','//root/owned','']:
                with self.subTest(raw=raw):
                    with self.assertRaises(policy.RootArtifactPolicyRefused):subject._directory(raw)
                    with self.assertRaises(protected.ProtectedArtifactRefused):protected._artifact_path(PurePosixPath(raw))
            opened.assert_not_called()

    def test_allocation_repeats_ordered_root_metadata_and_original_descriptor_check(self):
        events=[];changed={}
        class ModelPath(PurePosixPath):
            def lstat(self):
                events.append(str(self))
                values=dict(st_dev=1,st_ino=2,st_uid=0,st_gid=0,st_mode=stat.S_IFDIR|0o700)
                values.update(changed.get(str(self),{}));return SimpleNamespace(**values)
        path=ModelPath('/root/parent/leaf');original=(1,2,0,0,stat.S_IFDIR|0o700)
        subject=policy.NativeRootArtifactPolicyAllocation.__new__(policy.NativeRootArtifactPolicyAllocation)
        subject.directories={path:(42,original)}
        with patch.object(policy,'Path',ModelPath),patch.object(policy.os,'fstat',return_value=path.lstat()) as opened:
            events.clear()
            for _ in range(2):
                self.assertEqual(subject._directory(path),{'device':1,'inode':2,'uid':0})
                self.assertEqual(events,['/root/parent','/root','/','/root/parent/leaf']);events.clear()
            self.assertEqual(opened.call_count,2)
            for mutation in [{'st_uid':1},{'st_gid':1},{'st_mode':stat.S_IFDIR|0o777},{'st_mode':stat.S_IFLNK|0o777}]:
                changed['/root/parent']=mutation
                with self.assertRaises(policy.RootArtifactPolicyRefused):subject._directory(path)
                self.assertEqual(events,['/root/parent']);events.clear()

    def test_protected_directory_and_long_walks_observe_fresh_parents_and_leaf(self):
        events=[];changed={}
        class ModelPath(PurePosixPath):
            def lstat(self):
                events.append(str(self))
                return SimpleNamespace(st_dev=1,st_ino=2,st_uid=UID if self.name=='leaf' else 0,
                    st_mode=changed.get(str(self),stat.S_IFDIR|0o700))
        with patch.object(protected,'Path',ModelPath):
            path=ModelPath('/root/parent/leaf')
            for _ in range(2):
                self.assertEqual(protected.directory(path,UID,private=True),{'device':1,'inode':2,'uid':UID})
                self.assertEqual(events,['/root/parent','/root','/','/root/parent/leaf','/root/parent/leaf']);events.clear()
            changed['/root/parent']=stat.S_IFLNK|0o777
            with self.assertRaises(protected.ProtectedArtifactRefused):protected.directory(path,UID,private=True)
            self.assertEqual(events,['/root/parent']);changed.clear();events.clear()
            for path in [ModelPath('/'+'a'*1025+'/leaf'),ModelPath('/'+'/'.join(['a']*65)+'/leaf')]:
                before=service._root_file_parent_plan.cache_info()
                self.assertEqual(protected.directory(path,UID,private=True)['uid'],UID)
                self.assertEqual(service._root_file_parent_plan.cache_info(),before)

    def test_private_read_keeps_original_fstat_named_identity_bounds_and_close(self):
        events=[];after={}
        values=dict(st_dev=1,st_ino=2,st_uid=UID,st_gid=GID,st_mode=stat.S_IFREG|0o600,
            st_nlink=1,st_size=8,st_mtime_ns=3,st_ctime_ns=4)
        class ModelPath(PurePosixPath):
            def lstat(self):
                events.append(str(self))
                return SimpleNamespace(**values) if self.name=='leaf' else SimpleNamespace(st_mode=stat.S_IFDIR|0o700)
        subject=protected.NativeProtectedArtifactStage.__new__(protected.NativeProtectedArtifactStage)
        subject.scope={'uid':UID,'gid':GID};path=ModelPath('/root/parent/leaf')
        # Flag stand-ins only on platforms lacking the native constants; the
        # actual Linux Root cases below use the real no-follow descriptor path.
        with (patch.object(protected.os,'O_NOFOLLOW',getattr(os,'O_NOFOLLOW',0),create=True),
                patch.object(protected.os,'O_CLOEXEC',getattr(os,'O_CLOEXEC',0),create=True),
                patch.object(protected.os,'O_NONBLOCK',getattr(os,'O_NONBLOCK',0),create=True),
                patch.object(protected.os,'open',return_value=17) as opened,
                patch.object(protected.os,'read',return_value=b'original') as read,
                patch.object(protected.os,'close') as closed):
            for mutation in [{},{'st_ino':9},{'st_size':9},{'st_ctime_ns':9}]:
                events.clear();closed.reset_mock();read.reset_mock();after=dict(values,**mutation)
                with patch.object(protected.os,'fstat',side_effect=[SimpleNamespace(**values),SimpleNamespace(**after)]):
                    if mutation:
                        with self.assertRaises(protected.ProtectedArtifactRefused):subject._private(path,4096)
                    else:self.assertEqual(subject._private(path,4096),(protected.fingerprint(SimpleNamespace(**values)),b'original'))
                read.assert_called_once_with(17,4097);closed.assert_called_once_with(17)
            self.assertEqual(opened.call_count,4)


@unittest.skipUnless(sys.platform=='linux' and getattr(os,'getuid',lambda:1)()==0,
    'actual isolated Root-owned canonical artifact filesystem')
class RootArtifactCanonicalPathTest(unittest.TestCase):
    def setUp(self):
        service._root_file_parent_plan.cache_clear()
        self.addCleanup(service._root_file_parent_plan.cache_clear)
        temporary=tempfile.TemporaryDirectory(prefix='gitgood-artifact-canonical-',dir='/var/lib')
        self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        self.addCleanup(os.chown,self.root,0,0);self.addCleanup(self.root.chmod,0o700)
        self.parent=self.root/'parent';self.parent.mkdir(mode=0o700)
        self.allocation_path=self.parent/'allocation';self.allocation_path.mkdir(mode=0o700)
        (self.allocation_path/'retained').write_bytes(b'evidence')
        self.private_dir=self.parent/'private';self.private_dir.mkdir(mode=0o700)
        os.chown(self.private_dir,UID,GID)
        self.private_path=self.private_dir/'record';self.private_path.write_bytes(b'original')
        self.private_path.chmod(0o600);os.chown(self.private_path,UID,GID)
        self.allocation=policy.NativeRootArtifactPolicyAllocation.__new__(policy.NativeRootArtifactPolicyAllocation)
        self.allocation.directories={};self.allocation.exclusion=None
        self.addCleanup(self.allocation.close)
        self.original=self.allocation._directory(self.allocation_path)
        self.stage=protected.NativeProtectedArtifactStage.__new__(protected.NativeProtectedArtifactStage)
        self.stage.scope={'uid':UID,'gid':GID}
        self.private_original=self.stage._private(self.private_path,4096)

    def test_twenty_fresh_walk_sets_retain_original_directory_fd_and_private_bytes(self):
        started=time.monotonic_ns()
        for _ in range(20):
            self.assertEqual(self.allocation._directory(self.allocation_path),self.original)
            self.assertEqual(protected.directory(self.private_dir,UID,private=True)['uid'],UID)
            self.assertEqual(self.stage._private(self.private_path,4096),self.private_original)
        print('actual_artifact_canonical_walk_sets=20 elapsed_ms='+str((time.monotonic_ns()-started)//1000000),flush=True)

    def test_parent_alias_spelling_refuses_and_preserves_owned_files(self):
        for observe in [lambda:self.allocation._directory(self.allocation_path/'..'/'allocation'),
                lambda:protected.directory(self.private_dir/'..'/'private',UID,private=True),
                lambda:self.stage._private(self.private_dir/'..'/'private/record',4096)]:
            with self.assertRaises((policy.RootArtifactPolicyRefused,protected.ProtectedArtifactRefused)):observe()
        self.assertEqual(self.private_path.read_bytes(),b'original')

    def test_selected_allocation_directory_symlink_refuses_even_to_original_inode(self):
        moved=self.parent/'old-allocation';self.allocation_path.rename(moved);self.allocation_path.symlink_to(moved)
        with self.assertRaises(policy.RootArtifactPolicyRefused):self.allocation._directory(self.allocation_path)
        self.assertEqual((moved/'retained').read_bytes(),b'evidence')

    def test_ancestor_symlink_refuses_all_walks_and_unchanged_standalone_helper(self):
        moved=self.root/'old-parent';self.parent.rename(moved);self.parent.symlink_to(moved)
        for observe in [lambda:self.allocation._directory(self.allocation_path),lambda:policy._root_directory(self.allocation_path),
                lambda:protected.directory(self.private_dir,UID,private=True),lambda:self.stage._private(self.private_path,4096)]:
            with self.assertRaises((policy.RootArtifactPolicyRefused,protected.ProtectedArtifactRefused)):observe()
        self.assertEqual((moved/'private/record').read_bytes(),b'original')

    def test_root_ancestor_writable_mode_refuses_allocation(self):
        self.root.chmod(0o777)
        with self.assertRaises(policy.RootArtifactPolicyRefused):self.allocation._directory(self.allocation_path)

    def test_root_ancestor_foreign_owner_refuses_allocation(self):
        os.chown(self.root,UID,0)
        with self.assertRaises(policy.RootArtifactPolicyRefused):self.allocation._directory(self.allocation_path)

    def test_root_ancestor_foreign_group_refuses_allocation(self):
        os.chown(self.root,0,GID)
        with self.assertRaises(policy.RootArtifactPolicyRefused):self.allocation._directory(self.allocation_path)

    def test_replaced_named_directory_cannot_adopt_original_held_descriptor(self):
        moved=self.parent/'old-allocation';self.allocation_path.rename(moved);self.allocation_path.mkdir(mode=0o700)
        with self.assertRaises(policy.RootArtifactPolicyRefused):self.allocation._directory(self.allocation_path)
        self.assertEqual((moved/'retained').read_bytes(),b'evidence')

    def test_private_leaf_symlink_refuses_without_reading_or_changing_target(self):
        moved=self.private_dir/'old-record';self.private_path.rename(moved);self.private_path.symlink_to(moved)
        with self.assertRaises(protected.ProtectedArtifactRefused):self.stage._private(self.private_path,4096)
        self.assertEqual(moved.read_bytes(),b'original')

    def test_hardlinked_private_file_refuses_without_changing_either_name(self):
        other=self.private_dir/'other';os.link(self.private_path,other)
        with self.assertRaises(protected.ProtectedArtifactRefused):self.stage._private(self.private_path,4096)
        self.assertEqual(other.read_bytes(),b'original');self.assertEqual(self.private_path.read_bytes(),b'original')

    def test_change_during_private_read_refuses_original_fstat_fence(self):
        read=os.read
        def changed(fd,maximum):
            raw=read(fd,maximum);self.private_path.write_bytes(b'changed!!');return raw
        with patch.object(protected.os,'read',side_effect=changed):
            with self.assertRaises(protected.ProtectedArtifactRefused):self.stage._private(self.private_path,4096)
        self.assertEqual(self.private_path.read_bytes(),b'changed!!')

    def test_private_directory_and_file_predicates_remain_required(self):
        self.private_dir.chmod(0o755)
        with self.assertRaises(protected.ProtectedArtifactRefused):protected.directory(self.private_dir,UID,private=True)
        self.private_dir.chmod(0o700)
        for uid,gid,mode in [(0,GID,0o600),(UID,0,0o600),(UID,GID,0o644)]:
            os.chown(self.private_path,uid,gid);self.private_path.chmod(mode)
            with self.assertRaises(protected.ProtectedArtifactRefused):self.stage._private(self.private_path,4096)
        self.assertEqual(self.private_path.read_bytes(),b'original')


if __name__=='__main__':unittest.main()
