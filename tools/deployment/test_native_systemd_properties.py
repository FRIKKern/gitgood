import ctypes
from pathlib import Path
import unittest
from unittest.mock import Mock

from native_systemd_properties import BusRefused, ReadOnlySystemdProperties


class SystemdPropertiesTest(unittest.TestCase):
    def subject(self, signature='s', value=b'255.4'):
        subject = ReadOnlySystemdProperties.__new__(ReadOnlySystemdProperties)
        subject.path = Path('/root-controlled/library')
        subject.original = {'inode': 17}
        subject.files = Mock(usable=True)
        subject.files.read.return_value = (subject.original, b'library')
        subject.bus = ctypes.c_void_p(1)
        subject.usable = True
        library = subject.library = Mock()
        def property_reply(*arguments):
            self.assertEqual(arguments[1], b'org.freedesktop.systemd1')
            self.assertEqual(arguments[-1], signature.encode())
            ctypes.cast(arguments[-2], ctypes.POINTER(ctypes.c_void_p))[0] = 2
            return 0
        def read_basic(message, kind, destination):
            if kind == b's':
                ctypes.cast(destination, ctypes.POINTER(ctypes.c_char_p))[0] = value
            else:
                field = ctypes.c_uint32 if kind == b'u' else ctypes.c_int
                ctypes.cast(destination, ctypes.POINTER(field))[0] = value
            return 1
        library.sd_bus_get_property.side_effect = property_reply
        library.sd_bus_message_read_basic.side_effect = read_basic
        library.sd_bus_message_at_end.return_value = 1
        return subject

    def assert_lost(self, subject):
        self.assertFalse(subject.usable)
        self.assertFalse(subject.files.usable)
        self.assertFalse(subject.bus)
        subject.library.sd_bus_flush_close_unref.assert_called_once()
        count = subject.library.sd_bus_get_property.call_count
        with self.assertRaises(BusRefused): subject.manager_version()
        self.assertEqual(subject.library.sd_bus_get_property.call_count, count)

    def test_manager_reads_are_live_and_library_custody_brackets_each_reply(self):
        subject = self.subject()
        self.assertEqual(subject.manager_version(), '255.4')
        self.assertEqual(subject.manager_version(), '255.4')
        self.assertEqual(subject.library.sd_bus_get_property.call_count, 2)
        self.assertEqual(subject.files.read.call_count, 4)
        self.assertEqual(subject.library.sd_bus_message_unref.call_count, 2)

    def test_library_replacement_before_request_poisoned_without_bus_call(self):
        subject = self.subject()
        subject.files.read.return_value = ({'inode': 18}, b'library')
        with self.assertRaises(BusRefused): subject.manager_version()
        subject.library.sd_bus_get_property.assert_not_called()
        self.assert_lost(subject)

    def test_library_replacement_after_reply_discards_response_and_poisoned(self):
        subject = self.subject()
        subject.files.read.side_effect = [(subject.original, b'library'), ({'inode': 18}, b'library')]
        with self.assertRaises(BusRefused): subject.manager_version()
        subject.library.sd_bus_message_unref.assert_called_once()
        self.assert_lost(subject)

    def test_bus_error_poisoned_and_cannot_reconnect(self):
        subject = self.subject()
        subject.library.sd_bus_get_property.side_effect = None
        subject.library.sd_bus_get_property.return_value = -5
        with self.assertRaises(BusRefused): subject.manager_version()
        self.assert_lost(subject)

    def test_extra_response_value_refuses(self):
        subject = self.subject()
        subject.library.sd_bus_message_at_end.return_value = 0
        with self.assertRaises(BusRefused): subject.manager_version()
        self.assert_lost(subject)

    def test_array_limit_and_container_errors_poison_connection(self):
        subject = self.subject('as')
        subject.library.sd_bus_message_enter_container.return_value = 1
        subject.library.sd_bus_message_exit_container.return_value = 1
        subject.library.sd_bus_message_at_end.side_effect = [0] * 32 + [1, 1]
        self.assertEqual(len(subject._get('/fixed', 'fixed', 'DelegateControllers', 'as').split()), 32)
        subject = self.subject('as')
        subject.library.sd_bus_message_enter_container.return_value = 1
        subject.library.sd_bus_message_at_end.return_value = 0
        with self.assertRaises(BusRefused): subject._get('/fixed', 'fixed', 'DelegateControllers', 'as')
        self.assert_lost(subject)
        subject = self.subject('as')
        subject.library.sd_bus_message_enter_container.return_value = -22
        with self.assertRaises(BusRefused): subject._get('/fixed', 'fixed', 'DelegateControllers', 'as')
        self.assert_lost(subject)

    def test_non_ascii_and_oversized_strings_refuse(self):
        for value in [b'\xff', b'x' * 2049]:
            with self.subTest(value_length=len(value)):
                subject = self.subject(value=value)
                with self.assertRaises((BusRefused, UnicodeError)): subject.manager_version()
                self.assert_lost(subject)

    def test_boolean_and_pid_types_are_decoded_without_coercing_invalid_boolean(self):
        for value, expected in [(0, 'no'), (1, 'yes')]:
            subject = self.subject('b', value)
            self.assertEqual(subject._get('/fixed', 'fixed', 'Delegate', 'b'), expected)
        subject = self.subject('b', 2)
        with self.assertRaises(BusRefused): subject._get('/fixed', 'fixed', 'Delegate', 'b')
        self.assert_lost(subject)
        subject = self.subject('u', 1234)
        self.assertEqual(subject._get('/fixed', 'fixed', 'MainPID', 'u'), '1234')

    def test_noncanonical_or_foreign_unit_refuses_before_call(self):
        for unit in ['other.service', 'gitgood-installation-' + 'a' * 36 + '.service',
                     'gitgood-installation-ABCDEFAB-1234-1234-1234-123456789ABC.service']:
            subject = self.subject()
            with self.assertRaises((BusRefused, ValueError)): subject.unit_properties(unit)
            self.assert_lost(subject)

    def test_unit_schema_and_path_are_fixed_and_every_property_read_is_live(self):
        subject = self.subject()
        subject._get = Mock(return_value='observed')
        unit = 'gitgood-installation-12345678-1234-1234-1234-123456789abc.service'
        first = subject.unit_properties(unit)
        self.assertEqual(len(first), 15)
        self.assertEqual(subject.unit_properties(unit), first)
        self.assertEqual(subject._get.call_count, 30)
        expected_path = '/org/freedesktop/systemd1/unit/' + unit.replace('-', '_2d').replace('.', '_2e')
        for call in subject._get.call_args_list:
            self.assertEqual(call.args[0], expected_path)
            self.assertIn(call.args[1], ['org.freedesktop.systemd1.Unit', 'org.freedesktop.systemd1.Service'])
        signatures = {call.args[2]: call.args[3] for call in subject._get.call_args_list}
        self.assertEqual(signatures['MainPID'], 'u')
        self.assertEqual(signatures['Delegate'], 'b')
        self.assertEqual(signatures['DelegateControllers'], 'as')
        self.assertEqual(signatures['DropInPaths'], 'as')


if __name__ == '__main__':
    unittest.main()
