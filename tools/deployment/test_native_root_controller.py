import copy
from contextlib import ExitStack
import unittest
from unittest.mock import Mock, patch

from native_root_controller import NativeRootControllerObservation, RootControllerRefused
from native_service_scope import ServiceRefused, _observe_root_controller, observe_service
from resource_generations import canonical

INSTALLATION = 'f053c00f-1076-43ea-b510-2c6aabbbf79b'


class RootControllerObservationTest(unittest.TestCase):
    def fixture(self, change=None):
        stack = ExitStack();self.addCleanup(stack.close)
        for name in ('getuid', 'geteuid', 'getgid', 'getegid'):
            stack.enter_context(patch('native_root_controller.os.' + name, return_value=0, create=True))
        stack.enter_context(patch('native_root_controller.sys.platform', 'linux'))
        stack.enter_context(patch('native_root_controller.platform.machine', return_value='x86_64'))
        self.seal = {'protocol': 2, 'kind': 'native_controller_endpoint_seal', 'installation': INSTALLATION,
            'uid': 1000, 'gid': 1000, 'unit_sha256': 'a'*64,
            'directory_identity': {'device': 1, 'inode': 2, 'uid': 1000},
            'limits': {'cpu_quota_us': 200000, 'memory_bytes': 268435456}}
        if change:self.seal.update(change)
        self.raw = canonical(self.seal)
        self.file = stack.enter_context(patch('native_root_controller.root_file', return_value=({'inode': 7}, self.raw)))
        self.fingerprint = stack.enter_context(patch('native_root_controller._CapturedRootFiles._fingerprint', return_value=('original',)))
        self.files = Mock()
        stack.enter_context(patch('native_root_controller._CapturedRootFiles', return_value=self.files))
        # Patching the class above also replaces its static fingerprint member.
        from native_root_controller import _CapturedRootFiles
        _CapturedRootFiles._fingerprint = self.fingerprint
        self.directory = stack.enter_context(patch('native_root_controller.private_directory',
            return_value=(self.seal['directory_identity'], ('original-parents',))))
        self.scope = {'uid': 1000, 'gid': 1000, 'manager': {'pid': 4321, 'birth': '100'},
            'boot_id': 'original', 'groups': {'driver': {'inode': 20}}, 'installation': INSTALLATION}
        self.service = stack.enter_context(patch('native_root_controller._observe_root_controller', return_value=copy.deepcopy(self.scope)))
        return NativeRootControllerObservation(INSTALLATION)

    def test_observations_are_detached_and_only_fixed_root_policy_selects_service(self):
        view = self.fixture()
        result = view.check();result['manager']['birth'] = 'caller-change'
        self.assertEqual(view.check(), self.scope)
        self.service.assert_called_with(INSTALLATION, 'a'*64, cpu_quota_us=200000,
            memory_bytes=268435456, _root_files=self.files)
        self.files.freeze.assert_called_once()
        view.close()
        with self.assertRaises(RootControllerRefused):view.check()
        self.files.close.assert_called()

    def test_original_controller_loss_replacement_or_namespace_change_permanently_refuses(self):
        for change in ({'manager': {'pid': 4321, 'birth': 'new'}}, {'boot_id': 'new'},
                       {'groups': {'driver': {'inode': 21}}}):
            with self.subTest(change=change):
                view = self.fixture()
                self.service.return_value = dict(self.scope, **change)
                with self.assertRaises(RootControllerRefused):view.check()
                self.service.return_value = copy.deepcopy(self.scope)
                with self.assertRaises(RootControllerRefused):view.check()
                self.assertFalse(view.usable)

    def test_same_byte_policy_replacement_and_private_directory_loss_poison(self):
        view = self.fixture()
        self.fingerprint.return_value = ('replacement',)
        with self.assertRaises(RootControllerRefused):view.check()
        self.fingerprint.return_value = ('original',)
        with self.assertRaises(RootControllerRefused):view.check()
        view = self.fixture()
        self.directory.return_value = ({'device': 1, 'inode': 99, 'uid': 1000}, ('original-parents',))
        with self.assertRaises(RootControllerRefused):view.check()

    def test_cross_thread_or_forked_observer_cannot_reuse_original_view(self):
        view = self.fixture()
        with patch('native_root_controller.threading.get_ident', return_value=-1):
            with self.assertRaises(RootControllerRefused):view.check()
        with self.assertRaises(RootControllerRefused):view.check()
        view = self.fixture()
        with patch('native_root_controller.os.getpid', return_value=-1):
            with self.assertRaises(RootControllerRefused):view.check()

    def test_closed_seal_rejects_unknown_fields_boolean_ids_and_wrong_unit_policy(self):
        for change in ({'protocol': True}, {'uid': True}, {'gid': 0}, {'unit_sha256': 'A'*64},
                       {'installation': '00000000-0000-4000-8000-000000000001'},
                       {'program': '/caller-selected'}, {'limits': {'cpu_quota_us': 200000}},
                       {'directory_identity': {'device': True, 'inode': 2, 'uid': 1000}}):
            with self.subTest(change=change), self.assertRaises(RootControllerRefused):self.fixture(change)

    def test_invalid_platform_identity_and_ordinary_credentials_refuse_before_policy(self):
        with patch('native_root_controller.root_file') as read:
            for identity in (None, True, '../outside', INSTALLATION.upper()):
                with self.assertRaises(RootControllerRefused):NativeRootControllerObservation(identity)
            with patch('native_root_controller.sys.platform', 'linux'), \
                 patch('native_root_controller.platform.machine', return_value='x86_64'), \
                 patch('native_root_controller.os.getuid', return_value=1000, create=True):
                with self.assertRaises(RootControllerRefused):NativeRootControllerObservation(INSTALLATION)
            read.assert_not_called()


class SeparateCredentialBoundaryTest(unittest.TestCase):
    def test_root_observer_refuses_ordinary_or_mixed_root_credentials_before_account_lookup(self):
        for credentials in ((1000,1000,1000,1000), (0,1000,0,0), (0,0,1000,0)):
            with ExitStack() as stack:
                stack.enter_context(patch('native_service_scope.platform.system', return_value='Linux'))
                stack.enter_context(patch('native_service_scope.platform.machine', return_value='x86_64'))
                for name, value in zip(('getuid','geteuid','getgid','getegid'), credentials):
                    stack.enter_context(patch('native_service_scope.os.' + name, return_value=value, create=True))
                account = stack.enter_context(patch('native_service_scope.pwd.getpwnam'))
                with self.assertRaises(ServiceRefused):
                    _observe_root_controller(INSTALLATION, 'a'*64, 200000, 268435456, _root_files=Mock())
                account.assert_not_called()

    def test_ordinary_admission_still_refuses_root_before_account_or_manager(self):
        with patch('native_service_scope.platform.system', return_value='Linux'), \
             patch('native_service_scope.platform.machine', return_value='x86_64'), \
             patch('native_service_scope.os.getuid', return_value=0, create=True), \
             patch('native_service_scope.pwd.getpwnam') as account:
            with self.assertRaises(ServiceRefused):
                observe_service(INSTALLATION, 'a'*64, cpu_quota_us=200000, memory_bytes=268435456)
            account.assert_not_called()


if __name__ == '__main__':
    unittest.main()
