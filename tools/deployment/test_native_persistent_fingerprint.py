"""Metadata-only observations; binding/content admission is an explicit stand-in."""
import copy
import hashlib
import os
from pathlib import Path, PurePosixPath
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import native_generation_lease_guard as guard


class FingerprintPathSpellingTest(unittest.TestCase):
    def test_relative_parent_traversal_double_root_and_nul_refuse_before_io(self):
        with patch.object(guard,'Path',PurePosixPath):
            for path in ['relative','../private','/var/../private','//etc/machine-id','/var/\0private']:
                with self.subTest(path=path),self.assertRaises(guard.PublicationRefused):guard._fingerprint_path(path)

    def test_binding_root_cannot_traverse_relative_input_before_directory_reads(self):
        resources={name:{} for name in ['root','configuration','storage','ssh-host','history','staging']}
        resources['root']['path']='relative'
        with patch.object(guard,'Path',PurePosixPath):
            with self.assertRaises(guard.PublicationRefused):
                guard.persistent_fingerprint({'account':{'uid':1000},'resources':resources})


@unittest.skipUnless(sys.platform=='linux' and getattr(os,'getuid',lambda:1)()==0,
    'actual Root metadata over isolated ordinary-owned resources')
class RootPersistentFingerprintTest(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='gitgood-fingerprint-',dir='/var/lib')
        self.addCleanup(temporary.cleanup);self.base=Path(temporary.name)
        self.uid,self.gid=65503,1000;self.root=self.base/'installation'
        self.root.mkdir(mode=0o700);os.chown(self.root,self.uid,self.gid)
        self.binding={'account':{'uid':self.uid},'resources':{'root':self.directory_record(self.root)},
            'configuration':{},'ssh_host_keys':{},'executables':{},'host':{}}
        for name in ['configuration','storage','ssh-host','history','staging']:
            path=self.root/name;path.mkdir(mode=0o700);os.chown(path,self.uid,self.gid)
            self.binding['resources'][name]=self.directory_record(path)
        for name in ['installation.json','tls-certificate.pem','tls-key.pem']:
            self.binding['configuration'][name]=self.write(self.root/'configuration'/name,self.uid)
        for name in ['ssh_host_ed25519_key','ssh_host_ed25519_key.pub']:
            self.binding['ssh_host_keys'][name]=self.write(self.root/'ssh-host'/name,self.uid)
        self.binaries=self.base/'binaries';self.binaries.mkdir(mode=0o700)
        for name in ['python','node','git','psql','caddy']:
            self.binding['executables'][name]=self.write(self.binaries/name,0,executable=True)
        self.binding['host']['os_release']=self.write(self.base/'os-release',0)
        self.private=self.root/'configuration'/'installation.json'

    def directory_record(self,path):
        info=path.lstat()
        return {'path':str(path),'device':info.st_dev,'inode':info.st_ino,'uid':info.st_uid}

    def write(self,path,uid,*,executable=False,raw=b'synthetic metadata fixture'):
        path.write_bytes(raw);path.chmod(0o555 if executable else 0o444 if uid==0 else 0o600)
        os.chown(path,uid,0 if uid==0 else self.gid);info=path.lstat()
        return {'path':str(path),'device':info.st_dev,'inode':info.st_ino,'uid':uid,
            'bytes':info.st_size,'sha256':hashlib.sha256(raw).hexdigest()}

    @staticmethod
    def file_metadata(path):
        info=path.lstat()
        return tuple(getattr(info,name) for name in
            ['st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_uid','st_mode','st_nlink'])

    @staticmethod
    def directory_metadata(path):
        info=path.lstat();return info.st_dev,info.st_ino,info.st_uid,info.st_mode

    def test_complete_original_output_keys_and_metadata_fields_are_unchanged(self):
        expected={record['path']:self.directory_metadata(Path(record['path']))
            for record in self.binding['resources'].values()}
        records=[record for name in ['configuration','ssh_host_keys','executables']
            for record in self.binding[name].values()]+[self.binding['host']['os_release']]
        expected.update({record['path']:self.file_metadata(Path(record['path'])) for record in records})
        expected['/etc/machine-id']=self.file_metadata(Path('/etc/machine-id'))
        expected.update({str(path):self.directory_metadata(path)
            for path in [self.base,self.base.parent,Path('/var'),Path('/'),self.binaries]})
        self.assertEqual(guard.persistent_fingerprint(self.binding),expected)
        self.assertNotIn('/etc',expected) # Additional alias checks do not expand the recorded schema.

    def test_leaf_symlink_refuses_while_retaining_original_private_bytes(self):
        original=self.base/'retained-private';self.private.rename(original)
        self.private.symlink_to(original)
        with self.assertRaises(guard.PublicationRefused):guard.persistent_fingerprint(self.binding)
        self.assertEqual(original.read_bytes(),b'synthetic metadata fixture')

    def test_file_ancestor_alias_refuses_even_when_the_original_leaf_inode_matches(self):
        alias=self.base/'alias';alias.symlink_to(self.root/'configuration',target_is_directory=True)
        changed=copy.deepcopy(self.binding);changed['configuration']['installation.json']['path']=str(alias/'installation.json')
        self.assertEqual((alias/'installation.json').stat().st_ino,self.private.stat().st_ino)
        with self.assertRaises(guard.PublicationRefused):guard.persistent_fingerprint(changed)

    def test_resource_ancestor_alias_refuses_even_when_the_original_directory_matches(self):
        alias=self.base/'alias';alias.symlink_to(self.root,target_is_directory=True)
        changed=copy.deepcopy(self.binding);changed['resources']['storage']['path']=str(alias/'storage')
        self.assertEqual((alias/'storage').stat().st_ino,(self.root/'storage').stat().st_ino)
        with self.assertRaises(guard.PublicationRefused):guard.persistent_fingerprint(changed)

    def test_parent_traversal_cannot_select_the_original_private_file(self):
        changed=copy.deepcopy(self.binding)
        changed['configuration']['installation.json']['path']=str(self.root/'configuration'/'..'/'configuration'/'installation.json')
        with self.assertRaises(guard.PublicationRefused):guard.persistent_fingerprint(changed)

    def test_same_content_replacement_refuses_without_adopting_a_new_inode(self):
        original=self.base/'retained-private';raw=self.private.read_bytes();self.private.rename(original)
        self.write(self.private,self.uid,raw=raw)
        with self.assertRaises(guard.PublicationRefused):guard.persistent_fingerprint(self.binding)
        self.assertEqual(original.read_bytes(),raw);self.assertEqual(self.private.read_bytes(),raw)

    def test_in_place_edit_with_restored_mtime_changes_the_retained_metadata(self):
        before=guard.persistent_fingerprint(self.binding);info=self.private.stat()
        self.private.write_bytes(b'x'*info.st_size);os.utime(self.private,ns=(info.st_atime_ns,info.st_mtime_ns))
        after=guard.persistent_fingerprint(self.binding)
        self.assertEqual(before[str(self.private)][:4],after[str(self.private)][:4])
        self.assertNotEqual(before[str(self.private)][4],after[str(self.private)][4])
        self.assertNotEqual(before,after)

    def test_private_file_mode_owner_and_hardlink_changes_refuse(self):
        self.private.chmod(0o644)
        with self.assertRaises(guard.PublicationRefused):guard.persistent_fingerprint(self.binding)
        self.private.chmod(0o600);os.chown(self.private,self.uid+1,self.gid)
        with self.assertRaises(guard.PublicationRefused):guard.persistent_fingerprint(self.binding)
        os.chown(self.private,self.uid,self.gid);os.link(self.private,self.base/'hardlink')
        with self.assertRaises(guard.PublicationRefused):guard.persistent_fingerprint(self.binding)

    def test_resource_mode_owner_and_replacement_changes_refuse(self):
        path=self.root/'storage';path.chmod(0o750)
        with self.assertRaises(guard.PublicationRefused):guard.persistent_fingerprint(self.binding)
        path.chmod(0o700);os.chown(path,self.uid+1,self.gid)
        with self.assertRaises(guard.PublicationRefused):guard.persistent_fingerprint(self.binding)
        os.chown(path,self.uid,self.gid);path.rename(self.base/'retained-storage')
        path.mkdir(mode=0o700);os.chown(path,self.uid,self.gid)
        with self.assertRaises(guard.PublicationRefused):guard.persistent_fingerprint(self.binding)

    def test_protected_ancestor_writable_mode_and_alias_refuse(self):
        self.binaries.chmod(0o777)
        with self.assertRaises(guard.PublicationRefused):guard.persistent_fingerprint(self.binding)
        self.binaries.chmod(0o700);original=self.base/'retained-binaries';self.binaries.rename(original)
        self.binaries.symlink_to(original,target_is_directory=True)
        with self.assertRaises(guard.PublicationRefused):guard.persistent_fingerprint(self.binding)

    def test_parent_replacement_preserving_all_executable_inodes_changes_fingerprint(self):
        before=guard.persistent_fingerprint(self.binding)
        original=self.base/'retained-binaries';self.binaries.rename(original);self.binaries.mkdir(mode=0o700)
        for name in self.binding['executables']:(original/name).rename(self.binaries/name)
        after=guard.persistent_fingerprint(self.binding)
        for record in self.binding['executables'].values():
            self.assertEqual(before[record['path']][:3],after[record['path']][:3])
        self.assertNotEqual(before[str(self.binaries)],after[str(self.binaries)])

    def test_twenty_complete_fingerprints_read_fresh_original_metadata(self):
        before=guard.persistent_fingerprint(self.binding);started=time.monotonic_ns()
        for _ in range(20):self.assertEqual(guard.persistent_fingerprint(self.binding),before)
        print('actual_persistent_fingerprints=20 elapsed_ms='+str((time.monotonic_ns()-started)//1000000),flush=True)


if __name__=='__main__':unittest.main()
