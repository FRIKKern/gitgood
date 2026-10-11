"""Closed scope-seal and original-custody boundaries with explicit Root-reader stand-ins."""
import copy
import unittest
from unittest.mock import patch
from native_backend_scope import NativeBackendScope
from resource_generations import canonical
from test_native_kernel_backend import SCOPE


class BackendScopeTest(unittest.TestCase):
    installation='00000000-0000-4000-8000-000000000001'
    def setUp(self):
        self.fingerprint=patch('native_backend_scope._CapturedRootFiles._fingerprint',return_value=('fixed-file','fixed-parents'))
        self.fingerprint.start();self.addCleanup(self.fingerprint.stop)
    def seal(self):
        return {'protocol':2,'kind':'native_backend_kernel_scope_seal','installation':self.installation,'server_scope':copy.deepcopy(SCOPE)}

    def test_fixed_path_and_detached_scope_preserve_original_identity(self):
        value=self.seal();raw=canonical(value)
        with patch('native_backend_scope.root_file',return_value=({'inode':7},raw)) as reader:
            subject=NativeBackendScope(self.installation,SCOPE['boot_id'])
            returned=subject.check();returned['postgres_uid']=7
            self.assertEqual(subject.check(),SCOPE)
            self.assertEqual(str(reader.call_args.args[0]),'/etc/gitgood/installations/'+self.installation+'/backend-kernel-'+SCOPE['boot_id']+'.json')

    def test_malformed_aliased_foreign_or_noncanonical_seal_refuses(self):
        for value in [None,{**self.seal(),'protocol':True},{**self.seal(),'installation':'unknown'},
                      {**self.seal(),'extra':True},{**self.seal(),'server_scope':{**SCOPE,'postgres_uid':True}},
                      {**self.seal(),'server_scope':{**SCOPE,'boot_id':'00000000-0000-4000-8000-000000000002'}}]:
            with self.subTest(value_type=type(value)),patch('native_backend_scope.root_file',return_value=({},canonical(value))):
                with self.assertRaises(Exception):NativeBackendScope(self.installation,SCOPE['boot_id'])
        with patch('native_backend_scope.root_file',return_value=({},canonical(self.seal())+b' ')):
            with self.assertRaises(Exception):NativeBackendScope(self.installation,SCOPE['boot_id'])

    def test_identical_bytes_replacement_or_change_is_permanent_refusal(self):
        raw=canonical(self.seal())
        for changed in [({'inode':8},raw),({'inode':7},raw+b' ')]:
            with patch('native_backend_scope.root_file',return_value=({'inode':7},raw)):
                subject=NativeBackendScope(self.installation,SCOPE['boot_id'])
            with patch('native_backend_scope.root_file',return_value=changed):
                with self.assertRaises(ValueError):subject.check()
            with patch('native_backend_scope.root_file',return_value=({'inode':7},raw)):
                with self.assertRaises(ValueError):subject.check()

    def test_original_metadata_or_parent_change_refuses_before_read_and_stays_poisoned(self):
        raw=canonical(self.seal())
        with patch('native_backend_scope.root_file',return_value=({'inode':7},raw)):
            subject=NativeBackendScope(self.installation,SCOPE['boot_id'])
        with patch('native_backend_scope._CapturedRootFiles._fingerprint',return_value=('changed-file','changed-parents')), \
             patch('native_backend_scope.root_file') as reader:
            with self.assertRaises(ValueError):subject.check()
            reader.assert_not_called()
        with patch('native_backend_scope.root_file',return_value=({'inode':7},raw)):
            with self.assertRaises(ValueError):subject.check()


if __name__=='__main__':unittest.main()
