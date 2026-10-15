import ctypes
import os
from pathlib import Path
import sys
import time
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
        subject._read_property = Mock(return_value='observed')
        unit = 'gitgood-installation-12345678-1234-1234-1234-123456789abc.service'
        first = subject.unit_properties(unit)
        self.assertEqual(len(first), 15)
        self.assertEqual(subject.unit_properties(unit), first)
        self.assertEqual(subject._read_property.call_count, 30)
        self.assertEqual(subject.files.read.call_count, 4)
        expected_path = '/org/freedesktop/systemd1/unit/' + unit.replace('-', '_2d').replace('.', '_2e')
        for call in subject._read_property.call_args_list:
            self.assertEqual(call.args[0], expected_path)
            self.assertIn(call.args[1], ['org.freedesktop.systemd1.Unit', 'org.freedesktop.systemd1.Service'])
        signatures = {call.args[2]:call.args[3] for call in subject._read_property.call_args_list}
        self.assertEqual(signatures['MainPID'], 'u')
        self.assertEqual(signatures['Delegate'], 'b')
        self.assertEqual(signatures['DelegateControllers'], 'as')
        self.assertEqual(signatures['DropInPaths'], 'as')




    def test_selected_batch_reads_live_values_and_brackets_the_whole_result(self):
        subject=self.subject()
        properties=[('fixed','First','s'),('fixed','Second','s')]
        self.assertEqual(subject._get_many('/fixed',properties),{'First':'255.4','Second':'255.4'})
        self.assertEqual(subject._get_many('/fixed',properties),{'First':'255.4','Second':'255.4'})
        self.assertEqual(subject.library.sd_bus_get_property.call_count,4)
        self.assertEqual(subject.files.read.call_count,4)
        self.assertEqual(subject.library.sd_bus_message_unref.call_count,4)

    def test_selected_batch_changed_library_discards_all_values_and_cannot_resume(self):
        subject=self.subject()
        subject.files.read.side_effect=[(subject.original,b'library'),({'inode':18},b'library')]
        with self.assertRaises(BusRefused):subject._get_many('/fixed',[('fixed','First','s'),('fixed','Second','s')])
        self.assertEqual(subject.library.sd_bus_get_property.call_count,2)
        self.assert_lost(subject)

    def test_selected_batch_refuses_replacement_before_any_call_and_duplicate_names(self):
        subject=self.subject()
        subject.files.read.return_value=({'inode':18},b'library')
        with self.assertRaises(BusRefused):subject._get_many('/fixed',[('fixed','First','s')])
        subject.library.sd_bus_get_property.assert_not_called();self.assert_lost(subject)
        subject=self.subject()
        with self.assertRaises(BusRefused):subject._get_many('/fixed',[('fixed','First','s'),('other','First','s')])
        subject.library.sd_bus_get_property.assert_not_called();self.assert_lost(subject)

    def test_selected_batch_stops_at_first_bad_reply_without_returning_partial_result(self):
        subject=self.subject()
        original=subject.library.sd_bus_get_property.side_effect
        calls=[]
        def reply(*args):
            calls.append(args[4]);return original(*args) if len(calls)==1 else -22
        subject.library.sd_bus_get_property.side_effect=reply
        with self.assertRaises(BusRefused):subject._get_many('/fixed',[('fixed','First','s'),('fixed','Second','s'),('fixed','Third','s')])
        self.assertEqual(calls,[b'First',b'Second']);self.assert_lost(subject)

    def dictionary_subject(self, names, values=(), endings=()):
        subject = self.subject()
        def reply(*arguments):
            ctypes.cast(arguments[6], ctypes.POINTER(ctypes.c_void_p))[0] = 2
            return 1
        subject.library.sd_bus_call_method.side_effect = reply
        subject.library.sd_bus_message_enter_container.return_value = 1
        subject.library.sd_bus_message_exit_container.return_value = 1
        subject.library.sd_bus_message_at_end.side_effect = list(endings)
        subject._string = Mock(side_effect=list(names))
        fields = iter(values)
        def basic(message, kind, destination):
            field = ctypes.c_uint32 if kind == b'u' else ctypes.c_int
            ctypes.cast(destination, ctypes.POINTER(field))[0] = next(fields)
            return 1
        subject.library.sd_bus_message_read_basic.side_effect = basic
        return subject

    def test_getall_rejects_duplicate_keys_even_for_unknown_properties(self):
        subject = self.dictionary_subject(['Unknown', 'Unknown'], endings=[0, 1, 0])
        subject.library.sd_bus_message_skip.return_value = 1
        with self.assertRaises(BusRefused): subject._get_all('/fixed', 'fixed', {'MainPID': 'u'})
        self.assert_lost(subject)
        subject.library.sd_bus_message_unref.assert_called_once()

    def test_getall_missing_property_and_trailing_body_permanently_refuse(self):
        for names, values, endings in [([], [], [1, 1]),
                                      (['MainPID'], [1234], [0, 1, 1, 1, 0])]:
            subject = self.dictionary_subject(names, values, endings)
            with self.assertRaises(BusRefused): subject._get_all('/fixed', 'fixed', {'MainPID': 'u'})
            self.assert_lost(subject)

    def test_getall_invalid_boolean_and_variant_type_refuse(self):
        subject = self.dictionary_subject(['Delegate'], [2], [0])
        with self.assertRaises(BusRefused): subject._get_all('/fixed', 'fixed', {'Delegate': 'b'})
        self.assert_lost(subject)
        subject = self.dictionary_subject(['MainPID'], endings=[0])
        subject.library.sd_bus_message_enter_container.side_effect = [1, 1, -22]
        with self.assertRaises(BusRefused): subject._get_all('/fixed', 'fixed', {'MainPID': 'u'})
        self.assert_lost(subject)

    def test_getall_changed_library_discards_complete_reply(self):
        subject = self.dictionary_subject(['MainPID'], [1234], [0, 1, 1, 1, 1])
        subject.files.read.side_effect = [(subject.original, b'library'), ({'inode': 18}, b'library')]
        with self.assertRaises(BusRefused): subject._get_all('/fixed', 'fixed', {'MainPID': 'u'})
        self.assert_lost(subject)

    def test_getall_entry_limit_bounds_unknown_property_processing(self):
        subject = self.dictionary_subject(['Unknown' + str(index) for index in range(512)],
                                         endings=[item for _ in range(512) for item in [0, 1]] + [0])
        subject.library.sd_bus_message_skip.return_value = 1
        with self.assertRaises(BusRefused): subject._get_all('/fixed', 'fixed', {'MainPID': 'u'})
        self.assertEqual(subject.library.sd_bus_message_skip.call_count, 512)
        self.assert_lost(subject)


@unittest.skipUnless(sys.platform=='linux' and getattr(os,'getuid',lambda:1)()==0,
    'actual Root system bus and Ubuntu systemd fixture')
class ActualSystemdInterfaceTest(unittest.TestCase):
    path='/org/freedesktop/systemd1/unit/dbus_2eservice'
    fields=(
        ('org.freedesktop.systemd1.Unit',{'Id':'s','LoadState':'s','ActiveState':'s','SubState':'s','FragmentPath':'s','DropInPaths':'as'}),
        ('org.freedesktop.systemd1.Service',{'User':'s','Group':'s','MainPID':'u','ControlGroup':'s','Delegate':'b','DelegateSubgroup':'s','DelegateControllers':'as','KillMode':'s','Restart':'s'}),
    )

    def test_actual_fresh_interface_pairs_match_selected_typed_properties(self):
        subject=ReadOnlySystemdProperties();self.addCleanup(subject.close)
        selected=[(interface,name,signature) for interface,fields in self.fields for name,signature in fields.items()]
        expected=subject._get_many(self.path,selected)
        started=time.monotonic()
        for _ in range(20):
            observed={name:value for interface,fields in self.fields
                for name,value in subject._get_all(self.path,interface,fields).items()}
            self.assertEqual(observed,expected)
        print('actual_systemd_interface_pairs=20 elapsed_ms='+str(int((time.monotonic()-started)*1000)))
        self.assertEqual(subject._get_many(self.path,selected),expected)

    def test_actual_missing_and_wrong_variant_refuse_without_reconnection(self):
        for fields in ({'GitgoodMissingFixtureProperty':'s'},{'MainPID':'s'}):
            subject=ReadOnlySystemdProperties();self.addCleanup(subject.close)
            with self.subTest(fields=fields),self.assertRaises(BusRefused):
                subject._get_all(self.path,'org.freedesktop.systemd1.Service',fields)
            self.assertFalse(subject.usable);self.assertFalse(subject.files.usable)
            with self.assertRaises(BusRefused):subject.manager_version()


if __name__ == '__main__':
    unittest.main()
