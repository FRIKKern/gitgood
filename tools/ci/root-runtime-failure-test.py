#!/usr/bin/env python3
"""Source-site privacy, bounds and trace custody without runtime installation."""
import io
import json
import sys
from types import SimpleNamespace
import unittest

import root_runtime_failure as diagnostic


class ExceptionSiteTest(unittest.TestCase):
    def test_exception_identity_and_original_trace_are_preserved(self):
        scope = {};exec(compile('def fail(error):\n    raise error\n', '/synthetic/source', 'exec'), scope)
        capture = diagnostic.ExceptionSites({'/synthetic/source': 'native_synthetic.py'})
        error = ValueError('private exception text')
        with self.assertRaises(ValueError) as caught:
            with capture.active():scope['fail'](error)
        self.assertIs(caught.exception, error);self.assertIsNone(sys.gettrace())
        self.assertEqual(capture.values()['sites'], [{'module': 'native_synthetic.py', 'function': 'fail',
            'line': 2, 'exception': 'ValueError'}])

    def test_existing_trace_is_refused_without_replacement(self):
        def original(frame, event, argument):return None
        sys.settrace(original)
        try:
            with self.assertRaises(RuntimeError):
                with diagnostic.ExceptionSites({}).active():self.fail('Must not run')
            self.assertIs(sys.gettrace(), original)
        finally:sys.settrace(None)

    def test_only_exact_source_and_closed_exception_label_are_emitted(self):
        capture = diagnostic.ExceptionSites({'/synthetic/source': 'native_synthetic.py'})
        frame = SimpleNamespace(f_code=SimpleNamespace(co_filename='/foreign/source', co_name='fail'), f_lineno=2)
        self.assertIsNone(capture.trace(frame, 'exception', (ValueError, ValueError('private'), None)))
        frame.f_code.co_filename = '/synthetic/source'
        class PrivateException(Exception):pass
        capture.trace(frame, 'exception', (PrivateException, PrivateException('private'), None))
        encoded = json.dumps(capture.values())
        self.assertNotIn('private', encoded);self.assertNotIn('/synthetic', encoded)
        self.assertEqual(capture.values()['sites'][0]['exception'], 'OtherException')

    def test_latest_sites_are_bounded_with_explicit_omission_count(self):
        capture = diagnostic.ExceptionSites({'/synthetic/source': 'native_synthetic.py'})
        frame = SimpleNamespace(f_code=SimpleNamespace(co_filename='/synthetic/source', co_name='fail'), f_lineno=2)
        for number in range(100):
            frame.f_lineno = number + 1;capture.trace(frame, 'exception', (ValueError, None, None))
        value = capture.values()
        self.assertEqual((value['events'], value['omitted'], len(value['sites'])), (100, 36, 64))
        self.assertEqual(value['sites'][0]['line'], 37)

    def test_diagnostic_result_retains_failure_and_restores_trace(self):
        class Failing(unittest.TestCase):
            def runTest(self):raise ValueError('private')
        result = unittest.TextTestRunner(stream=io.StringIO(), resultclass=lambda *a, **kw:
            diagnostic.FailureSitesResult(*a, sources={}, **kw)).run(unittest.TestSuite([Failing(), Failing()]))
        self.assertEqual((result.testsRun, len(result.errors)), (2, 2));self.assertFalse(result.wasSuccessful())
        self.assertEqual(result.first_failure, {'events': 0, 'omitted': 0, 'sites': []})
        self.assertIsNone(sys.gettrace())

    def test_failed_subtest_is_retained_as_first_failure(self):
        class Failing(unittest.TestCase):
            def runTest(self):
                with self.subTest(case='synthetic'):self.fail('private')
        result = unittest.TextTestRunner(stream=io.StringIO(), resultclass=lambda *a, **kw:
            diagnostic.FailureSitesResult(*a, sources={}, **kw)).run(unittest.TestSuite([Failing()]))
        self.assertFalse(result.wasSuccessful());self.assertEqual(len(result.failures), 1)
        self.assertEqual(result.first_failure, {'events': 0, 'omitted': 0, 'sites': []})
        self.assertIsNone(sys.gettrace())


if __name__ == '__main__':unittest.main(verbosity=2)
