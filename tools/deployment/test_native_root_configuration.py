"""Private parsing scope only; lifecycle, SQL and reader admission are stand-ins."""
import copy
from contextlib import ExitStack
import os
from pathlib import Path
import shutil
import stat
import sys
import threading
import time
import unittest
from unittest.mock import Mock, patch
import uuid

import native_durable_binding as binding
import native_root_database_reader as reader
from native_root_controller import RootControllerRefused, _RootObservationPass
from resource_generations import canonical


def view(installation,files,url,*,child=None):
    # Explicit constructor/SQL stand-in; never establishes reader admission.
    value=reader.NativeRootDatabaseReader.__new__(reader.NativeRootDatabaseReader)
    value.usable=True;value.owner=(os.getpid(),threading.get_ident());value.child=child
    value.installation=installation;value.root=Path('/var/lib/gitgood/installations')/installation
    value.scope={'installation':installation,'uid':65503}
    value.files=copy.deepcopy(files);value.url=url
    return value


class RootConfigurationPassTest(unittest.TestCase):
    def setUp(self):
        stack=self.stack=ExitStack();self.addCleanup(stack.close)
        for name in ('getuid','geteuid','getgid','getegid'):
            stack.enter_context(patch.object(os,name,return_value=0,create=True))
        self.installation='12345678-1234-4234-8234-123456789abc'
        self.files={'installation.json':{'inode':19,'sha256':'synthetic'}}
        self.url='synthetic-private-database-url'
        self.parse=stack.enter_context(patch.object(reader,'configuration',
            side_effect=lambda *_:(copy.deepcopy(self.files),self.url)))
        self.spawn=stack.enter_context(patch.object(reader.subprocess,'Popen'))

    def make(self):return view(self.installation,self.files,self.url)

    def test_one_parse_per_pass_and_fresh_next_pass_and_standalone(self):
        value=self.make()
        for _ in range(2):
            with _RootObservationPass():
                self.assertEqual(value._configuration(),(self.files,self.url))
                self.assertEqual(value._configuration(),(self.files,self.url))
        value._configuration();value._configuration()
        self.assertEqual(self.parse.call_count,4);self.spawn.assert_not_called()

    def test_returned_mutation_cannot_change_shared_or_original_private_records(self):
        value=self.make()
        with _RootObservationPass():
            files,_=value._configuration();files['installation.json']['inode']=88
            self.assertEqual(value._configuration(),(self.files,self.url))
        self.assertEqual(value.files,self.files);self.assertEqual(self.parse.call_count,1)

    def test_changed_configuration_refuses_in_the_separate_final_pass(self):
        value=self.make()
        with _RootObservationPass():value._configuration()
        self.files['installation.json']['inode']=77
        with self.assertRaises(reader.RootDatabaseReaderRefused):
            with _RootObservationPass():value._configuration()
        self.assertFalse(value.usable);self.assertEqual(self.parse.call_count,2)

    def test_closed_original_cannot_return_shared_success_or_revive_failed_pass(self):
        value=self.make()
        with self.assertRaises(RootControllerRefused):
            with _RootObservationPass():
                value._configuration();value.close()
                with self.assertRaises(reader.RootDatabaseReaderRefused):value._configuration()
                value.usable=True;value._configuration()
        self.assertEqual(self.parse.call_count,1);self.spawn.assert_not_called()

    def test_foreign_owner_refuses_before_private_parse(self):
        value=self.make();value.owner=(os.getpid()+1,threading.get_ident())
        with self.assertRaises(reader.RootDatabaseReaderRefused):value._configuration()
        self.assertFalse(value.usable);self.parse.assert_not_called();self.spawn.assert_not_called()

    def test_ordinary_identity_refuses_before_private_parse(self):
        value=self.make()
        with patch.object(os,'getuid',return_value=1000):
            with self.assertRaises(reader.RootDatabaseReaderRefused):value._configuration()
        self.parse.assert_not_called();self.spawn.assert_not_called()

    def test_parser_failure_poison_closes_only_owned_child_without_replacement(self):
        child=Mock();child.poll.return_value=None;child.wait.return_value=0
        value=view(self.installation,self.files,self.url,child=child)
        self.parse.side_effect=ValueError('synthetic private parser error')
        with self.assertRaises(reader.RootDatabaseReaderRefused):value._configuration()
        self.assertFalse(value.usable);child.terminate.assert_called_once()
        child.stdin.close.assert_called_once();child.stdout.close.assert_called_once()
        self.assertIsNone(value.child);self.spawn.assert_not_called()

    def test_changed_records_or_url_refuse_without_adopting_values(self):
        for result in [({'replacement':{}},self.url),(self.files,'changed-private-url')]:
            with self.subTest(result=result):
                value=self.make();self.parse.side_effect=None;self.parse.return_value=copy.deepcopy(result)
                with self.assertRaises(reader.RootDatabaseReaderRefused):value._configuration()
                self.assertFalse(value.usable);self.assertEqual(value.files,self.files);self.assertEqual(value.url,self.url)

    def test_different_original_readers_do_not_share_configuration(self):
        first,second=self.make(),self.make()
        with _RootObservationPass():first._configuration();second._configuration()
        self.assertEqual(self.parse.call_count,2)

    def test_foreign_path_or_installation_refuses_before_private_parse(self):
        for change in ('path','installation'):
            with self.subTest(change=change):
                value=self.make()
                if change=='path':value.root=Path('/synthetic/foreign')
                else:value.scope['installation']='foreign'
                with self.assertRaises(reader.RootDatabaseReaderRefused):value._configuration()
        self.parse.assert_not_called();self.spawn.assert_not_called()


@unittest.skipUnless(sys.platform=='linux' and getattr(os,'getuid',lambda:1)()==0,
    'actual Root configuration files; lifecycle and SQL admission remain stand-ins')
class RootConfigurationFilesystemTest(unittest.TestCase):
    def setUp(self):
        container=Path('/var/lib/gitgood/installations');container.mkdir(mode=0o755,parents=True,exist_ok=True)
        for path in (container,*container.parents):
            info=path.lstat()
            self.assertTrue(stat.S_ISDIR(info.st_mode) and info.st_uid==0 and not info.st_mode & 0o022)
        self.installation=str(uuid.uuid4());self.root=container/self.installation;self.root.mkdir(mode=0o700)
        self.addCleanup(shutil.rmtree,self.root);self.uid,self.gid=65503,1000
        os.chown(self.root,self.uid,self.gid)
        self.directory=self.root/'configuration';self.directory.mkdir(mode=0o700);os.chown(self.directory,self.uid,self.gid)
        forge={'GITGOOD_INSTALLATION_ID':self.installation,'GITGOOD_STORAGE':str(self.root/'storage'),
            'GITGOOD_SSH_HOST_KEY_DIRECTORY':str(self.root/'ssh-host'),'GITGOOD_PROXY_KEY':'synthetic-proxy',
            'DATABASE_URL':'postgresql://synthetic:synthetic@127.0.0.1:5432/synthetic'}
        web={name:'synthetic' for name in binding.WEB_KEYS};web.update(NODE_ENV='production',GITGOOD_PROXY_KEY='synthetic-proxy')
        self.write(self.directory/'installation.json',canonical({'protocol':1,'installation':self.installation,
            'forge':forge,'web':web,'edge':{'tls_certificate':'tls-certificate.pem','tls_key':'tls-key.pem'}}))
        self.write(self.directory/'tls-certificate.pem',b'synthetic TLS certificate')
        self.private=self.directory/'tls-key.pem';self.write(self.private,b'synthetic TLS private key')
        self.files,self.url=binding.configuration(self.root,self.installation,self.uid)
        self.value=view(self.installation,self.files,self.url)

    def write(self,path,raw):
        path.write_bytes(raw);path.chmod(0o600);os.chown(path,self.uid,self.gid)

    def refuse(self):
        with self.assertRaises(reader.RootDatabaseReaderRefused):
            with _RootObservationPass():self.value._configuration()
        self.assertFalse(self.value.usable)

    def test_twenty_fresh_complete_private_configuration_observations(self):
        started=time.monotonic_ns()
        for _ in range(20):
            with _RootObservationPass():self.assertEqual(self.value._configuration(),(self.files,self.url))
        print('actual_root_configuration_observations=20 elapsed_ms='+str((time.monotonic_ns()-started)//1000000),flush=True)

    def test_leaf_alias_refuses_and_retains_original_bytes(self):
        original=self.root/'retained-key';self.private.rename(original);self.private.symlink_to(original)
        self.refuse();self.assertEqual(original.read_bytes(),b'synthetic TLS private key')

    def test_ancestor_alias_refuses_even_with_original_leaf_inode(self):
        original=self.root/'retained-configuration';self.directory.rename(original)
        self.directory.symlink_to(original,target_is_directory=True)
        self.assertEqual(self.private.stat().st_ino,(original/'tls-key.pem').stat().st_ino)
        self.refuse();self.assertTrue((original/'tls-key.pem').is_file())

    def test_same_bytes_replacement_refuses_on_next_pass(self):
        with _RootObservationPass():self.value._configuration()
        original=self.root/'retained-key';raw=self.private.read_bytes();self.private.rename(original);self.write(self.private,raw)
        self.refuse();self.assertEqual(original.read_bytes(),raw)

    def test_in_place_edit_with_restored_mtime_refuses_on_next_pass(self):
        with _RootObservationPass():self.value._configuration()
        info=self.private.stat();self.private.write_bytes(b'x'*info.st_size)
        os.utime(self.private,ns=(info.st_atime_ns,info.st_mtime_ns));self.refuse()
        self.assertEqual(self.private.stat().st_mtime_ns,info.st_mtime_ns)

    def test_private_mode_change_refuses(self):
        self.private.chmod(0o644);self.refuse()

    def test_private_owner_change_refuses(self):
        os.chown(self.private,self.uid+1,self.gid);self.refuse()

    def test_private_hardlink_refuses_and_retains_original(self):
        os.link(self.private,self.root/'retained-hardlink');self.refuse()
        self.assertEqual(self.private.read_bytes(),b'synthetic TLS private key')

    def test_extra_private_configuration_entry_refuses(self):
        self.write(self.directory/'unexpected.json',b'synthetic');self.refuse()

    def test_closed_original_does_not_readmit_intact_files(self):
        with _RootObservationPass():self.value._configuration()
        self.value.close();self.refuse();self.assertEqual(self.private.read_bytes(),b'synthetic TLS private key')


if __name__=='__main__':unittest.main()
