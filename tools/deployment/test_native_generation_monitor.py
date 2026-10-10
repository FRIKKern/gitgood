import copy
import io
import json
import unittest
import uuid
from unittest.mock import patch

import native_generation_monitor as monitor


class Stream:
    def __init__(self, value=b''):
        self.buffer = io.BytesIO(value)


class Guard:
    def __init__(self):
        self.closed = False
        self.checks = 0
        self.token = {'scope_sha256':'a'*64, 'history_sha256':'b'*64, 'persistent_files_sha256':'c'*64}
        self.admitted = {'published_generation_admitted':True, 'binding_sha256':'d'*64,
                         'writer_exclusion_established':False, 'installation_readiness_established':False,
                         'lifecycle_responsibility_admitted':False, 'pointer':{'fixture':True},
                         'worker_observation':{'fixture':True}}

    def capture(self): return {'admission':self.admitted, **self.token}

    def check(self):
        self.checks += 1
        if self.checks > 1: raise ValueError('private fixture value must never appear')
        return {'current':True, **self.token}

    def close(self): self.closed = True


class GenerationMonitorTest(unittest.TestCase):
    def setUp(self):
        self.request = {'protocol':2,'installation':str(uuid.uuid4()),'worker':'native','owner_pid':42}
        self.raw = json.dumps(self.request).encode() + b'\n'

    def test_closed_request_accepts_only_fixed_roles_and_actual_owner_shape(self):
        self.assertEqual(monitor.parse_request(self.raw), self.request)
        for worker in ['native','maintenance']:
            value = {**self.request,'worker':worker}
            self.assertEqual(monitor.parse_request(json.dumps(value).encode()), value)

    def test_request_refuses_authority_paths_commands_and_additional_fields(self):
        for name in ['program','shell','environment','seal','binding_sha256']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                monitor.parse_request(json.dumps({**self.request,name:'private fixture'}).encode())

    def test_request_refuses_duplicate_keys_bool_owner_and_unknown_roles(self):
        examples = [b'{"protocol":2,"protocol":2}',
                    json.dumps({**self.request,'owner_pid':True}).encode(),
                    json.dumps({**self.request,'owner_pid':1}).encode(),
                    json.dumps({**self.request,'owner_pid':2**31}).encode(),
                    json.dumps({**self.request,'worker':'driver'}).encode()]
        for raw in examples:
            with self.subTest(raw=raw), self.assertRaises(ValueError): monitor.parse_request(raw)

    def test_request_refuses_oversize_nul_and_nonbinary_input(self):
        for raw in [b'x'*4097, self.raw+b'\0', '', b'']:
            with self.subTest(raw_type=type(raw)), self.assertRaises(ValueError): monitor.parse_request(raw)

    def run_stream(self, *, changed_seal=False, changed_token=False, capture_failure=False, ticks=None):
        guard = Guard(); output = Stream()
        seal = {'binding_sha256':'d'*64,'database':{'fixture':True}}
        identity = {'path':'/fixed/root/seal','fixture':True}; sealed = b'private fixture seal'
        if changed_token:
            guard.check = lambda: {'current':True, **guard.token, 'history_sha256':'e'*64}
        if capture_failure:
            guard.capture = lambda: (_ for _ in ()).throw(ValueError('private fixture value'))
        values = [(identity,sealed), (identity,sealed+b'changed')] if changed_seal else None
        with patch.object(monitor.sys, 'argv', ['fixed-entry']), \
             patch.object(monitor.sys, 'stdin', Stream(self.raw)), \
             patch.object(monitor.sys, 'stdout', output), \
             patch.object(monitor, 'open_guard', return_value=(guard,self.request,seal,identity,sealed)), \
             patch.object(monitor, 'root_file', side_effect=values, return_value=(identity,sealed)), \
             patch.object(monitor.time, 'sleep', return_value=None) as sleeper, \
             patch.object(monitor.time, 'monotonic', side_effect=ticks, return_value=10):
            code = monitor.main()
        self.sleeps = [call.args[0] for call in sleeper.call_args_list]
        self.assertEqual(code, 1); self.assertTrue(guard.closed)
        raw = output.buffer.getvalue(); self.assertNotIn(b'private fixture', raw)
        self.assertNotIn(b'Traceback', raw)
        return [json.loads(line) for line in raw.splitlines()], guard

    def test_admission_current_and_loss_have_closed_messages_and_close_guard(self):
        values, guard = self.run_stream()
        self.assertEqual([item['status'] for item in values], ['admitted','current','refused'])
        self.assertEqual(set(values[0]), {'protocol','status','admission','guard'})
        self.assertEqual(set(values[1]), {'protocol','status','guard'})
        self.assertEqual(values[2], {'protocol':2,'status':'refused'})
        self.assertEqual(values[0]['guard'], values[1]['guard']); self.assertEqual(guard.checks, 2)

    def test_changed_seal_refuses_before_a_current_message(self):
        values, guard = self.run_stream(changed_seal=True)
        self.assertEqual([item['status'] for item in values], ['admitted','refused'])
        self.assertEqual(guard.checks, 0)

    def test_changed_guard_token_cannot_be_adopted(self):
        values, _ = self.run_stream(changed_token=True)
        self.assertEqual([item['status'] for item in values], ['admitted','refused'])

    def test_failed_capture_sends_only_generic_refusal_and_closes_guard(self):
        values, _ = self.run_stream(capture_failure=True)
        self.assertEqual(values, [{'protocol':2,'status':'refused'}])

    def test_slow_check_does_not_add_an_extra_second_before_next_observation(self):
        values, _ = self.run_stream(ticks=[10, 10, 10, 12, 12])
        self.assertEqual([value['status'] for value in values], ['admitted','current','refused'])
        self.assertEqual(self.sleeps, [0, 0])

    def test_fast_checks_wait_for_the_next_one_second_start_interval(self):
        self.run_stream(ticks=[10, 10, 10, 10.25, 11])
        self.assertEqual(self.sleeps, [0, .75])


if __name__ == '__main__': unittest.main()
