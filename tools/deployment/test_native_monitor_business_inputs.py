import copy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import native_monitor_business_inputs as module


def request(stage='migrate'):
    return json.dumps({'protocol': 2, 'action': 'private_business_inputs', 'stage': stage},
                      sort_keys=True, separators=(',', ':')).encode()+b'\n'


class PrivateInputExchangeTest(unittest.TestCase):
    def setUp(self):
        # Explicit original-attachment/guard stand-ins. Actual installed stream,
        # SQL lease, process births and input custody remain separate evidence.
        self.token = {'scope_sha256': 'a'*64, 'history_sha256': 'b'*64, 'persistent_files_sha256': 'c'*64}
        self.ownership = {'record_sha256': 'd'*64}
        self.current = {'current': {'current': True, **self.token}, 'ownership': self.ownership}
        self.inputs = {'fixture_only': True, 'password': 'synthetic-private-stream-secret'}
        guard = SimpleNamespace(private_business_inputs=Mock(side_effect=lambda stage:copy.deepcopy(self.inputs)))
        self.attachment = SimpleNamespace(guard=guard, check=Mock(side_effect=lambda:copy.deepcopy(self.current)), close=Mock())
        self.subject = module.MonitorBusinessInputs(self.attachment, self.token, self.ownership)

    def refused(self, raw):
        with self.assertRaises(ValueError) as error:self.subject.feed(raw)
        self.assertEqual(str(error.exception), 'Private native input exchange unavailable')
        self.assertNotIn(self.inputs['password'], str(error.exception))
        self.assertTrue(self.subject.poisoned)
        self.attachment.close.assert_called()

    def test_partial_request_returns_only_after_both_original_attachment_checks(self):
        raw = request('bootstrap')
        self.assertIsNone(self.subject.feed(raw[:-1]))
        self.attachment.guard.private_business_inputs.assert_not_called()
        result = self.subject.feed(raw[-1:])
        self.assertEqual(self.attachment.check.call_count, 2)
        self.attachment.guard.private_business_inputs.assert_called_once_with('bootstrap')
        self.assertEqual(result['guard'], self.token);self.assertEqual(result['ownership'], self.ownership)
        result['inputs']['password'] = 'caller edit'
        self.assertEqual(self.inputs['password'], 'synthetic-private-stream-secret')

    def test_extra_pipelined_repeated_and_noncanonical_requests_cannot_retrieve_data(self):
        for raw in [request()+request(), request()+b'x', b'{"stage":"migrate","protocol":2,"action":"private_business_inputs"}\n',
                    b'{"action":"private_business_inputs","protocol":2,"protocol":2,"stage":"migrate"}\n']:
            self.setUp();self.refused(raw)
            self.attachment.guard.private_business_inputs.assert_not_called()
        self.setUp();self.subject.feed(request());self.refused(request())
        self.assertEqual(self.attachment.guard.private_business_inputs.call_count, 1)

    def test_closed_action_stage_and_integer_protocol_are_required(self):
        for changes in [{'protocol': True}, {'protocol': 1}, {'action': 'attach_ownership'}, {'stage': 'runtime'},
                        {'stage': {'action': 'migrate'}}, {'program': 'shell'}, {'authority': self.token}]:
            self.setUp()
            value = {'protocol': 2, 'action': 'private_business_inputs', 'stage': 'migrate', **changes}
            self.refused(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()+b'\n')
            self.attachment.guard.private_business_inputs.assert_not_called()

    def test_eof_oversize_and_nonbinary_requests_permanently_refuse(self):
        for raw in [b'', b'x'*513, 'private', None]:
            self.setUp();self.refused(raw)
            self.attachment.guard.private_business_inputs.assert_not_called()

    def test_unknown_or_changed_original_ownership_refuses_before_private_read(self):
        for change in [{'ownership': None}, {'ownership': {'record_sha256': 'e'*64}}, {'current': {'current': False}}]:
            self.setUp();self.current.update(change);self.refused(request())
            self.attachment.guard.private_business_inputs.assert_not_called()

    def test_final_identity_or_guard_loss_cannot_emit_a_private_response(self):
        for changed in [{'ownership': {'record_sha256': 'e'*64}, 'current': self.current['current']},
                        {'ownership': self.ownership, 'current': {'current': True, **self.token, 'history_sha256': 'f'*64}}]:
            self.setUp();self.attachment.check.side_effect = [copy.deepcopy(self.current), changed]
            self.refused(request())
            self.attachment.guard.private_business_inputs.assert_called_once()
            self.attachment.check.side_effect = lambda:copy.deepcopy(self.current)
            self.refused(request())
            self.assertEqual(self.attachment.guard.private_business_inputs.call_count, 1)

    def test_private_parser_error_is_redacted_and_never_retried(self):
        self.attachment.guard.private_business_inputs.side_effect = ValueError(self.inputs['password'])
        self.refused(request())
        self.attachment.guard.private_business_inputs.side_effect = lambda stage:self.inputs
        self.refused(request())
        self.assertEqual(self.attachment.guard.private_business_inputs.call_count, 1)

    def test_partial_and_complete_requests_share_the_original_finite_deadline(self):
        with patch.object(module.time, 'monotonic', side_effect=[10, 10, 13]):
            self.assertIsNone(self.subject.feed(request()[:1]));self.refused(request()[1:])
        self.setUp()
        with patch.object(module.time, 'monotonic', side_effect=[10, 10, 13]):self.refused(request())


if __name__ == '__main__':unittest.main()
