#!/usr/bin/env python3
"""Pidfd-only fault injection; actual children exist only on hosted Linux."""
from contextlib import ExitStack, contextmanager
import ctypes
import errno
import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

import root_runtime_probe as probe

spec = importlib.util.spec_from_file_location('native_owned_proof', Path(__file__).with_name('native-owned-proof.py'))
proof = importlib.util.module_from_spec(spec);spec.loader.exec_module(proof)


class PidfdCompatibilityTest(unittest.TestCase):
    def setUp(self):
        # Explicit Linux signal stand-in for pure Windows fixture tests only.
        signal_patch = patch.object(probe.signal, 'SIGKILL', 9, create=True)
        signal_patch.start();self.addCleanup(signal_patch.stop)

    def test_native_calls_forward_original_arguments_without_loading_libc(self):
        with patch.object(probe.os, 'pidfd_open', return_value=91, create=True) as opened, \
                patch.object(probe.signal, 'pidfd_send_signal', create=True) as killed, \
                patch.object(probe.ctypes, 'CDLL') as library:
            self.assertEqual(probe.pidfd_open(123), 91);self.assertIs(probe.pidfd_sigkill(91), killed.return_value)
            opened.assert_called_once_with(123, 0);killed.assert_called_once_with(91, signal.SIGKILL)
            library.assert_not_called()

    def test_bad_pid_or_descriptor_is_refused_before_any_effect(self):
        with patch.object(probe.ctypes, 'CDLL') as library, \
                patch.object(probe.os, 'pidfd_open', create=True) as opened, \
                patch.object(probe.signal, 'pidfd_send_signal', create=True) as killed:
            for value in (True, -1, 0, 2**31, '123'):
                with self.assertRaises(ValueError):probe.pidfd_open(value)
            for value in (True, -1, 1048576, '91'):
                with self.assertRaises(ValueError):probe.pidfd_sigkill(value)
            opened.assert_not_called();killed.assert_not_called();library.assert_not_called()

    def test_native_error_identity_is_preserved_without_libc_retry(self):
        failure = OSError(errno.ESRCH, 'synthetic')
        with patch.object(probe.os, 'pidfd_open', side_effect=failure, create=True), \
                patch.object(probe.signal, 'pidfd_send_signal', side_effect=failure, create=True), \
                patch.object(probe.ctypes, 'CDLL') as library:
            for call in (lambda: probe.pidfd_open(123), lambda: probe.pidfd_sigkill(91)):
                with self.assertRaises(OSError) as caught:call()
                self.assertIs(caught.exception, failure)
            library.assert_not_called()

    def test_libc_calls_have_exact_signatures_flags_and_errno(self):
        library = Mock();library.pidfd_open.return_value = 91;library.pidfd_send_signal.return_value = 0
        with patch.object(probe, 'host') as host, patch.object(probe.ctypes, 'CDLL', return_value=library) as load, \
                patch.object(probe.os, 'pidfd_open', None, create=True), \
                patch.object(probe.signal, 'pidfd_send_signal', None, create=True):
            self.assertEqual(probe.pidfd_open(123), 91);self.assertIsNone(probe.pidfd_sigkill(91))
            library.pidfd_open.assert_called_once_with(123, 0)
            library.pidfd_send_signal.assert_called_once_with(91, signal.SIGKILL, None, 0)
            self.assertEqual(library.pidfd_open.argtypes, [ctypes.c_int, ctypes.c_uint])
            self.assertEqual(library.pidfd_send_signal.argtypes, [ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint])
            self.assertIs(library.pidfd_open.restype, ctypes.c_int);self.assertIs(library.pidfd_send_signal.restype, ctypes.c_int)
            self.assertEqual(host.call_count, 2)
            self.assertTrue(all(call.args == ('libc.so.6',) and call.kwargs == {'use_errno': True} for call in load.call_args_list))
            with patch.object(probe.ctypes, 'get_errno', return_value=errno.ESRCH):
                library.pidfd_open.return_value = -1;library.pidfd_send_signal.return_value = -1
                for call in (lambda: probe.pidfd_open(123), lambda: probe.pidfd_sigkill(91)):
                    with self.assertRaises(OSError) as caught:call()
                    self.assertEqual(caught.exception.errno, errno.ESRCH)

    def test_original_process_is_revalidated_between_pidfd_open_and_signal(self):
        original = {'pid': 123, 'birth': 1, 'uid': 1000, 'parent': 2, 'cgroup': '/synthetic', 'state': 'S'}
        events = []
        with patch.object(probe, 'pidfd_open', side_effect=lambda pid: events.append(('open', pid)) or 91), \
                patch.object(proof, 'process', side_effect=lambda pid: events.append(('observe', pid)) or dict(original)), \
                patch.object(probe, 'pidfd_sigkill', side_effect=lambda fd: events.append(('signal', fd))), \
                patch.object(proof.os, 'close', side_effect=lambda fd: events.append(('close', fd))):
            proof.inject_loss('helper-loss', {'helper': original}, None, None)
        self.assertEqual(events, [('open', 123), ('observe', 123), ('signal', 91), ('close', 91)])

    def test_process_change_or_signal_failure_still_closes_original_descriptor(self):
        original = {'pid': 123, 'birth': 1, 'uid': 1000, 'parent': 2, 'cgroup': '/synthetic', 'state': 'S'}
        failure = OSError(errno.ESRCH, 'synthetic')
        for changed in (True, False):
            current = dict(original, birth=2) if changed else dict(original)
            with self.subTest(changed=changed), patch.object(probe, 'pidfd_open', return_value=91), \
                    patch.object(proof, 'process', return_value=current), \
                    patch.object(probe, 'pidfd_sigkill', side_effect=failure) as killed, \
                    patch.object(proof.os, 'close') as closed:
                with self.assertRaises(ValueError if changed else OSError) as caught:
                    proof.inject_loss('helper-loss', {'helper': original}, None, None)
                if changed:killed.assert_not_called()
                else:self.assertIs(caught.exception, failure);killed.assert_called_once_with(91)
                closed.assert_called_once_with(91)


@unittest.skipUnless(sys.platform == 'linux' and getattr(os, 'getuid', lambda: -1)() == 0,
    'Actual hosted Linux Root pidfd tests')
class ActualPidfdTest(unittest.TestCase):
    @contextmanager
    def backend(self, forced):
        probe.host()
        with ExitStack() as stack:
            if forced:
                stack.enter_context(patch.object(probe.os, 'pidfd_open', None, create=True))
                stack.enter_context(patch.object(probe.signal, 'pidfd_send_signal', None, create=True))
            yield

    def child(self):
        child = subprocess.Popen([sys.executable, '-B', '-I', '-S', '-c', 'import time; time.sleep(60)'],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        def cleanup():
            if child.poll() is None:child.kill()
            child.wait(timeout=10)
        self.addCleanup(cleanup);return child

    def test_pidfd_identifies_owned_target_and_kills_only_that_child(self):
        import fcntl
        for forced in (False, True):
            with self.subTest(forced=forced), self.backend(forced):
                child = self.child();other = self.child();descriptor = probe.pidfd_open(child.pid)
                try:
                    info = Path('/proc/self/fdinfo', str(descriptor)).read_text()
                    self.assertIn('Pid:\t' + str(child.pid) + '\n', info)
                    self.assertTrue(fcntl.fcntl(descriptor, fcntl.F_GETFD) & fcntl.FD_CLOEXEC)
                    probe.pidfd_sigkill(descriptor);self.assertEqual(child.wait(timeout=10), -signal.SIGKILL)
                    self.assertIsNone(other.poll())
                finally:os.close(descriptor)

    def test_dead_target_and_closed_descriptor_refuse_without_replacement(self):
        for forced in (False, True):
            with self.subTest(forced=forced), self.backend(forced):
                child = self.child();descriptor = probe.pidfd_open(child.pid)
                try:
                    child.kill();child.wait(timeout=10)
                    with self.assertRaises(OSError) as caught:probe.pidfd_sigkill(descriptor)
                    self.assertEqual(caught.exception.errno, errno.ESRCH)
                finally:os.close(descriptor)
                with self.assertRaises(OSError) as caught:probe.pidfd_sigkill(descriptor)
                self.assertEqual(caught.exception.errno, errno.EBADF)


if __name__ == '__main__':sys.dont_write_bytecode = True;unittest.main(verbosity=2)
