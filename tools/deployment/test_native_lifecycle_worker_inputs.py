import copy
import unittest
from unittest.mock import patch

from native_lifecycle_worker_inputs import (NativeLifecycleWorkerInputs,
    LifecycleWorkerInputsRefused, parse_worker_seal)
from resource_generations import canonical
import test_native_operation_inputs as fixtures


def worker_seal(purpose='native_initial_enrollment'):
    _,_,request,_ = fixtures.fixture(purpose)
    return {'protocol': 2, 'kind': 'native_lifecycle_worker_seal', 'installation': request['installation'],
            'operation': request['operation'], 'purpose': purpose, 'candidate': 'b'*40,
            'durable_binding_sha256': 'a'*64, 'request_sha256': 'c'*64,
            'inputs_seal_sha256': 'd'*64, 'uid': 1000, 'gid': 1000}


class LifecycleWorkerSealTest(unittest.TestCase):
    def test_closed_root_policy_supports_fixed_purposes_without_stage_or_command_inputs(self):
        for purpose in ['native_initial_enrollment', 'native_upgrade_execution']:
            seal = worker_seal(purpose)
            self.assertEqual(parse_worker_seal(canonical(seal), seal['installation'], 1000, 1000), seal)

    def test_foreign_identifiers_candidate_and_boolean_aliases_refuse(self):
        original = worker_seal()
        for changes in [{'protocol': True}, {'uid': True}, {'gid': 1001}, {'protocol': 1},
                        {'installation': original['operation']}, {'operation': original['installation']},
                        {'candidate': 'A'*40}, {'candidate': 'b'*64}, {'purpose': 'native_retirement'}]:
            with self.subTest(changes=changes),self.assertRaises(Exception):
                parse_worker_seal(canonical(dict(original, **changes)), original['installation'], 1000, 1000)

    def test_policy_cannot_accept_a_caller_stage_worker_map_program_or_paths(self):
        original = worker_seal()
        for name in ['stage', 'workers', 'program', 'shell', 'path', 'environment', 'binding']:
            with self.subTest(name=name),self.assertRaises(Exception):
                parse_worker_seal(canonical(dict(original, **{name:'synthetic'})), original['installation'], 1000, 1000)

    def test_duplicate_noncanonical_nonobject_and_wrong_digest_refuse(self):
        seal = worker_seal();raw = canonical(seal)
        values = [raw+b'\n', b'[]', raw.replace(b'"protocol":2', b'"protocol":2,"protocol":2')]
        values.extend(canonical(dict(seal, **{field:'A'*64})) for field in ['durable_binding_sha256', 'request_sha256', 'inputs_seal_sha256'])
        for value in values:
            with self.assertRaises(Exception):parse_worker_seal(value, seal['installation'], 1000, 1000)

    def test_invalid_installation_refuses_before_root_or_private_input_reads(self):
        with patch('native_lifecycle_worker_inputs.root_file') as root,self.assertRaises(LifecycleWorkerInputsRefused):
            NativeLifecycleWorkerInputs('../foreign')
        root.assert_not_called()


if __name__ == '__main__':unittest.main()
