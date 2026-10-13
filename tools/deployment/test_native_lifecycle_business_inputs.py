import copy
import hashlib
import json
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from native_lifecycle_business_inputs import _project, LifecycleBusinessInputsRefused


INSTALLATION = '11111111-1111-4111-8111-111111111111'
OPERATION = '22222222-2222-4222-8222-222222222222'
PASSWORD = 'synthetic-secret-éé'


class LifecycleBusinessInputsTest(unittest.TestCase):
    def setUp(self):
        self.observed = {'worker': 'maintenance', 'recorded_status': 'running', 'stage': 'migrate',
            'operation': OPERATION, 'candidate': 'b'*40, 'purpose': 'native_initial_enrollment',
            'request_sha256': 'c'*64}
        self.bootstrap = {'installation': INSTALLATION, 'request': OPERATION, 'username': 'owner',
                          'team': 'pilot', 'password': PASSWORD}
        self.business = {'kind': 'native_initial_business_inputs', 'installation': INSTALLATION,
            'operation': OPERATION, 'candidate': 'b'*40,
            'migrations': {'before_versions': [], 'target_versions': [20261001000000, 20261002000000]},
            'bootstrap': self.bootstrap}
        self.payloads = {'inputs.json': {'protocol': 2, 'business': self.business}}

    def project(self, action='migrate'):
        return _project(self.payloads, self.observed, action, INSTALLATION)

    def test_migration_projection_does_not_expose_bootstrap_material(self):
        result = self.project()
        self.assertNotIn('bootstrap', result)
        self.assertNotIn(PASSWORD, json.dumps(result, ensure_ascii=False))
        result['migrations']['target_versions'].clear()
        self.assertEqual(len(self.business['migrations']['target_versions']), 2)

    def test_bootstrap_digest_matches_existing_ordered_owner_entry_contract(self):
        self.observed['stage'] = 'bootstrap'
        result = self.project('bootstrap')
        payload = ['gitgood-installation-owner-v1', INSTALLATION, OPERATION, 'owner', 'pilot', PASSWORD]
        expected = hashlib.sha256(json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(expected, '7c88ecc40ded65bf7c1b507bd8712a6c61c5e8afac39177aec4689cf56444fc2')
        self.assertEqual(result['bootstrap_request_sha256'], expected)
        result['bootstrap']['password'] = 'untrusted caller edit'
        self.assertEqual(self.bootstrap['password'], PASSWORD)

    def test_unknown_commands_roles_and_nested_fields_refuse_without_secret_diagnostics(self):
        for target, key, value in [(self.business, 'command', 'shell'), (self.bootstrap, 'role', 'owner'),
                                   (self.business['migrations'], 'callback', 'shell')]:
            with self.subTest(key=key):
                target[key] = value
                with self.assertRaises(LifecycleBusinessInputsRefused) as error:self.project()
                self.assertEqual(str(error.exception), 'Native lifecycle business inputs unavailable')
                self.assertNotIn(PASSWORD, str(error.exception))
                del target[key]

    def test_wrong_stage_purpose_identity_candidate_and_terminal_windows_refuse(self):
        for key, value in [('stage', 'bootstrap'), ('worker', 'native'), ('recorded_status', 'complete'),
                           ('purpose', 'native_upgrade_execution'), ('candidate', 'd'*40), ('operation', INSTALLATION)]:
            with self.subTest(key=key):
                original = self.observed[key];self.observed[key] = value
                with self.assertRaises(LifecycleBusinessInputsRefused):self.project()
                self.observed[key] = original
        for action in ('runtime', 'shell', {'action': 'migrate'}):
            with self.assertRaises(LifecycleBusinessInputsRefused):self.project(action)

    def test_migration_versions_are_closed_bounded_and_forward_only(self):
        for value in [[], [True], [0], [-1], [2**63], [2, 1], [1, 1], [1]*1025, 'all']:
            with self.subTest(value_type=type(value).__name__):
                self.business['migrations']['target_versions'] = value
                with self.assertRaises(LifecycleBusinessInputsRefused):self.project()
        self.business['migrations'] = {'before_versions': [1], 'target_versions': [1, 2]}
        with self.assertRaises(LifecycleBusinessInputsRefused):self.project()

    def test_upgrade_migration_has_no_bootstrap_and_cannot_remove_previous_versions(self):
        self.observed['purpose'] = 'native_upgrade_execution'
        self.business.pop('bootstrap');self.business['kind'] = 'native_upgrade_business_inputs'
        self.business['migrations'] = {'before_versions': [1], 'target_versions': [1, 2]}
        self.payloads = {'plan.json': {'protocol': 2, 'business': self.business}}
        self.assertEqual(self.project()['migrations']['before_versions'], [1])
        self.business['migrations']['target_versions'] = [2]
        with self.assertRaises(LifecycleBusinessInputsRefused):self.project()
        self.observed['stage'] = 'bootstrap'
        with self.assertRaises(LifecycleBusinessInputsRefused):self.project('bootstrap')

    def test_bootstrap_names_password_bytes_nul_and_original_request_are_required(self):
        for key, value in [('password', 'é'*129), ('password', 'short'), ('password', PASSWORD+'\0'),
                           ('username', 'Owner'), ('team', 'team\n'), ('request', INSTALLATION), ('password', '\ud800')]:
            with self.subTest(key=key):
                original = self.bootstrap[key];self.bootstrap[key] = value
                with self.assertRaises(LifecycleBusinessInputsRefused):self.project()
                self.bootstrap[key] = original

    def test_fixture_metadata_and_legacy_payloads_cannot_become_business_inputs(self):
        for document in [{'protocol': 2, 'fixture_only': True}, {'protocol': 1, 'business': self.business},
                         {'protocol': True, 'business': self.business}]:
            self.payloads = {'inputs.json': document}
            with self.assertRaises(LifecycleBusinessInputsRefused):self.project()

    def guard(self):
        # Explicit held-guard/input custody stand-ins. These tests exercise the
        # projection brackets and poisoning, not filesystem/systemd admission.
        from native_generation_lease_guard import NativeGenerationLeaseGuard
        value = object.__new__(NativeGenerationLeaseGuard)
        metadata = {'request_sha256': 'c'*64, 'candidate': 'b'*40, 'request': {'operation': OPERATION}}
        inputs = SimpleNamespace(check=Mock(return_value=metadata),
                                 _private_payloads=Mock(side_effect=lambda:copy.deepcopy(self.payloads)))
        value.worker = 'maintenance';value.snapshot = {'lifecycle': copy.deepcopy(self.observed)}
        value.reader = SimpleNamespace(inputs=inputs, installation=INSTALLATION)
        value.usable = True
        value.check = Mock(side_effect=lambda:{'current': True} if value.usable else (_ for _ in ()).throw(ValueError()))
        value.close = Mock(side_effect=lambda:setattr(value, 'usable', False))
        return value

    @unittest.skipUnless(sys.platform == 'linux', 'Linux guard imports; explicit custody stand-ins')
    def test_guard_brackets_original_inputs_and_returns_no_borrowed_data(self):
        subject = self.guard();result = subject.private_business_inputs('migrate')
        self.assertEqual(subject.check.call_count, 2)
        self.assertEqual(subject.reader.inputs._private_payloads.call_count, 1)
        self.assertTrue(subject.usable)
        result['migrations']['target_versions'].clear()
        self.assertEqual(len(self.business['migrations']['target_versions']), 2)

    @unittest.skipUnless(sys.platform == 'linux', 'Linux guard imports; explicit custody stand-ins')
    def test_changed_final_guard_poisoning_prevents_retry_after_restoration(self):
        subject = self.guard();subject.check.side_effect = [{'current': True}, {'current': False}]
        with self.assertRaises(LifecycleBusinessInputsRefused):subject.private_business_inputs('migrate')
        self.assertFalse(subject.usable)
        subject.check.side_effect = lambda:{'current': True} if subject.usable else (_ for _ in ()).throw(ValueError())
        with self.assertRaises(LifecycleBusinessInputsRefused):subject.private_business_inputs('migrate')

    @unittest.skipUnless(sys.platform == 'linux', 'Linux guard imports; explicit custody stand-ins')
    def test_wrong_original_request_or_stage_refuses_before_private_payload_read(self):
        for kind in ('request', 'stage'):
            subject = self.guard()
            if kind == 'request':subject.reader.inputs.check.return_value['request_sha256'] = 'd'*64
            else:subject.snapshot['lifecycle']['stage'] = 'bootstrap'
            with self.assertRaises(LifecycleBusinessInputsRefused):subject.private_business_inputs('migrate')
            subject.reader.inputs._private_payloads.assert_not_called()
            self.assertFalse(subject.usable)


if __name__ == '__main__':unittest.main()
