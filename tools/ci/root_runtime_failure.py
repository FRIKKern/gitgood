"""Failure-only source-site diagnostics for the hosted Root runtime trial.

No exception text, arguments, locals, filesystem observations or private paths
are recorded. This reruns only a fixed synthetic component test scope after its
original invocation failed; it cannot turn that failure into a passing gate.
"""
from collections import deque
from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import re
import sys
import unittest


SCOPES = (
    'test_native_protected_artifact', 'test_native_root_lifecycle', 'test_native_root_controller_request', 'test_native_root_artifact_policy',
    'test_native_artifact_controller', 'test_native_root_artifact_dispatch', 'test_native_artifact_canonical_paths',
    'test_native_root_observation_pass', 'test_native_root_database_reader', 'test_native_tcp_socket_observation',
    'test_native_service_file_custody', 'test_native_root_file_parent_plan', 'test_native_process_status',
    'test_native_systemd_properties', 'test_native_executable_capture', 'test_native_durable_binding',
    'test_native_persistent_fingerprint', 'test_native_private_directory', 'test_native_root_configuration',
    'test_native_stage_controller_observer', 'test_native_root_live_binding',
)
EXCEPTIONS = frozenset(('AssertionError', 'AttributeError', 'FileNotFoundError', 'NotImplementedError',
    'OSError', 'PermissionError', 'RuntimeError', 'TypeError', 'ValueError', 'KeyError', 'OverflowError'))


class ExceptionSites:
    def __init__(self, sources):
        self.sources = dict(sources);self.sites = deque(maxlen=64);self.events = 0

    def trace(self, frame, event, argument):
        module = self.sources.get(frame.f_code.co_filename)
        if module is None:return None
        if event == 'exception':
            name = frame.f_code.co_name;line = frame.f_lineno
            if re.fullmatch('[A-Za-z_][A-Za-z_0-9]{0,99}', name) and type(line) is int and 0 < line <= 1000000:
                kind = argument[0]
                label = kind.__name__ if kind.__module__ == 'builtins' and kind.__name__ in EXCEPTIONS else 'OtherException'
                self.events += 1
                self.sites.append({'module': module, 'function': name, 'line': line, 'exception': label})
        return self.trace

    @contextmanager
    def active(self):
        original = sys.gettrace()
        if original is not None:raise RuntimeError('An existing trace must be preserved')
        try:
            sys.settrace(self.trace)
            yield self
        finally:sys.settrace(original)

    def values(self):
        return {'events': self.events, 'omitted': self.events - len(self.sites), 'sites': list(self.sites)}


class FailureSitesResult(unittest.TextTestResult):
    def __init__(self, *args, sources, **kwargs):
        super().__init__(*args, **kwargs);self.sources = sources;self.first_failure = None

    def startTest(self, test):
        super().startTest(test)
        self.capture = ExceptionSites(self.sources);self.context = self.capture.active();self.context.__enter__()
        self.failed = False

    def addError(self, test, error):
        self.failed = True;super().addError(test, error)

    def addFailure(self, test, error):
        self.failed = True;super().addFailure(test, error)

    def addSubTest(self, test, subtest, error):
        if error is not None:self.failed = True
        super().addSubTest(test, subtest, error)

    def stopTest(self, test):
        try:
            if self.failed and self.first_failure is None:self.first_failure = self.capture.values()
        finally:
            self.context.__exit__(None, None, None);super().stopTest(test)


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in SCOPES:raise SystemExit('A fixed component scope is required')
    if sys.platform != 'linux' or os.getuid() != 0:raise SystemExit('Actual isolated Linux Root is required')
    deployment = Path(__file__).resolve().parents[1] / 'deployment'
    sys.path.insert(0, str(deployment))
    # Exact repository source paths, never basename matching against foreign code.
    sources = {str(path): path.name for path in deployment.glob('native_*.py') if path.is_file()}
    suite = unittest.defaultTestLoader.discover(str(deployment), pattern=sys.argv[1] + '.py')
    # Original failing invocation already logged its traceback. Emit only a
    # closed source-site receipt from this separate diagnostic invocation.
    stream = io.StringIO()
    runner = unittest.TextTestRunner(stream=stream, resultclass=lambda *a, **kw: FailureSitesResult(*a, sources=sources, **kw))
    result = runner.run(suite)
    print(json.dumps({'protocol': 1, 'diagnostic_only': True, 'production_runtime_adopted': False,
        'scope': sys.argv[1], 'tests': result.testsRun, 'errors': len(result.errors),
        'failures': len(result.failures), 'skipped': len(result.skipped),
        'first_failure': result.first_failure}, sort_keys=True))
    # Failure-only invocation never admits the dependent staging proof, even
    # if the repeated component happens to pass.
    return 1


if __name__ == '__main__':sys.dont_write_bytecode = True;raise SystemExit(main())
