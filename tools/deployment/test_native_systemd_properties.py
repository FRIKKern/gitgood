import ctypes
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import Mock, patch

import native_systemd_properties as properties_module

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
        # Serial transport stand-in for the fixed unit/path/schema contract.
        subject._get_many = subject._get_many_serial
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
        self.assertEqual(subject._get_many_serial('/fixed',properties),{'First':'255.4','Second':'255.4'})
        self.assertEqual(subject._get_many_serial('/fixed',properties),{'First':'255.4','Second':'255.4'})
        self.assertEqual(subject.library.sd_bus_get_property.call_count,4)
        self.assertEqual(subject.files.read.call_count,4)
        self.assertEqual(subject.library.sd_bus_message_unref.call_count,4)

    def test_selected_batch_changed_library_discards_all_values_and_cannot_resume(self):
        subject=self.subject()
        subject.files.read.side_effect=[(subject.original,b'library'),({'inode':18},b'library')]
        with self.assertRaises(BusRefused):subject._get_many_serial('/fixed',[('fixed','First','s'),('fixed','Second','s')])
        self.assertEqual(subject.library.sd_bus_get_property.call_count,2)
        self.assert_lost(subject)

    def test_selected_batch_refuses_replacement_before_any_call_and_duplicate_names(self):
        subject=self.subject()
        subject.files.read.return_value=({'inode':18},b'library')
        with self.assertRaises(BusRefused):subject._get_many_serial('/fixed',[('fixed','First','s')])
        subject.library.sd_bus_get_property.assert_not_called();self.assert_lost(subject)
        subject=self.subject()
        with self.assertRaises(BusRefused):subject._get_many_serial('/fixed',[('fixed','First','s'),('other','First','s')])
        subject.library.sd_bus_get_property.assert_not_called();self.assert_lost(subject)

    def test_selected_batch_stops_at_first_bad_reply_without_returning_partial_result(self):
        subject=self.subject()
        original=subject.library.sd_bus_get_property.side_effect
        calls=[]
        def reply(*args):
            calls.append(args[4]);return original(*args) if len(calls)==1 else -22
        subject.library.sd_bus_get_property.side_effect=reply
        with self.assertRaises(BusRefused):subject._get_many_serial('/fixed',[('fixed','First','s'),('fixed','Second','s'),('fixed','Third','s')])
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


class QueuedSystemdBatchTest(unittest.TestCase):
    """Native callback/slot lifetimes with an explicit libsystemd ABI stand-in."""
    fields=[('fixed','First','s'),('fixed','Second','s')]

    def subject(self):
        value=SystemdPropertiesTest().subject();library=value.library
        pending=[];current=[None];created=[];slots=[]
        def new_message(bus,target,destination,path,interface,method):
            self.assertEqual(destination,b'org.freedesktop.systemd1')
            self.assertEqual(interface,b'org.freedesktop.DBus.Properties');self.assertEqual(method,b'Get')
            number=100+len(created);created.append(number)
            ctypes.cast(target,ctypes.POINTER(ctypes.c_void_p))[0]=number;return 0
        def call(bus,target,message,callback,userdata,timeout):
            self.assertEqual(timeout,5_000_000)
            number=200+len(slots);slots.append(number)
            ctypes.cast(target,ctypes.POINTER(ctypes.c_void_p))[0]=number
            pending.append((number,callback,userdata.value));return 0
        def process(bus,target):
            if not pending:return 0
            slot,callback,userdata=pending.pop();current[0]=slot
            self.assertEqual(callback(500+slot,userdata,None),1)
            return 1
        library.sd_bus_message_new_method_call.side_effect=new_message
        library.sd_bus_message_append_basic.return_value=0
        library.sd_bus_call_async.side_effect=call
        library.sd_bus_process.side_effect=process;library.sd_bus_wait.return_value=1
        library.sd_bus_get_current_slot.side_effect=lambda bus:current[0]
        library.sd_bus_message_is_method_error.return_value=0
        library.sd_bus_message_has_signature.return_value=1
        library.sd_bus_message_enter_container.return_value=1
        library.sd_bus_message_exit_container.return_value=1
        value.fixture_pending=pending;value.fixture_slots=slots
        return value

    def assert_lost(self,value):
        SystemdPropertiesTest().assert_lost(value)
        self.assertFalse(value._selected_active)
        self.assertEqual(value.library.sd_bus_slot_unref.call_count,len(value.fixture_slots))

    def test_out_of_order_replies_complete_only_fresh_selected_batches_on_the_same_bus(self):
        value=self.subject();original_bus=value.bus
        value._string=Mock(side_effect=lambda message:'value-'+str(message))
        process=value.library.sd_bus_process.side_effect
        for offset in [0,2]:
            selected=list(self.fields)
            value.library.sd_bus_process.side_effect=lambda *args:(selected.clear(),process(*args))[1]
            self.assertEqual(value._get_many('/fixed',selected),
                {'First':'value-'+str(700+offset),'Second':'value-'+str(701+offset)})
            self.assertEqual(selected,[])
        self.assertIs(value.bus,original_bus);self.assertEqual(value.files.read.call_count,4)
        self.assertEqual(value.library.sd_bus_call_async.call_count,4)
        self.assertEqual(value.library.sd_bus_slot_unref.call_count,4)
        self.assertCountEqual([call.args[0].value for call in value.library.sd_bus_slot_unref.call_args_list],value.fixture_slots)
        self.assertEqual(value.library.sd_bus_message_unref.call_count,4) # Requests only, never borrowed replies.
        value.library.sd_bus_get_property.assert_not_called()
        value.library.sd_bus_flush_close_unref.assert_not_called()

    def test_invalid_or_duplicate_selection_refuses_before_any_native_request(self):
        for fields in [[],self.fields*17,[('fixed','First','s'),('other','First','s')],
                [('fixed','First','o')],[('fixed\0foreign','First','s')]]:
            value=self.subject()
            with self.subTest(fields=fields),self.assertRaises(BusRefused):value._get_many('/fixed',fields)
            value.library.sd_bus_call_async.assert_not_called()
            self.assertFalse(value.usable)

    def test_library_loss_before_or_after_batch_never_returns_partial_values(self):
        for after in [False,True]:
            value=self.subject()
            value.files.read.side_effect=([(value.original,b'library')] if after else [])+[({'inode':18},b'library')]
            with self.subTest(after=after),self.assertRaises(BusRefused):value._get_many('/fixed',self.fields)
            if after:self.assert_lost(value)
            else:
                value.library.sd_bus_call_async.assert_not_called();self.assertFalse(value.usable)

    def test_partial_queue_failure_cancels_every_allocated_slot_and_request(self):
        value=self.subject();original=value.library.sd_bus_call_async.side_effect
        def call(*args):
            result=original(*args)
            return result if len(value.fixture_slots)==1 else -5
        value.library.sd_bus_call_async.side_effect=call
        with self.assertRaises(BusRefused):value._get_many('/fixed',self.fields)
        self.assertEqual(value.library.sd_bus_message_unref.call_count,2)
        value.library.sd_bus_process.assert_not_called();self.assert_lost(value)
        for function in ['sd_bus_message_new_method_call','sd_bus_message_append_basic']:
            value=self.subject();original=getattr(value.library,function).side_effect
            def failed(*args):
                if original:original(*args)
                return -5
            getattr(value.library,function).side_effect=failed
            with self.subTest(function=function),self.assertRaises(BusRefused):value._get_many('/fixed',self.fields)
            value.library.sd_bus_call_async.assert_not_called()
            self.assertEqual(value.library.sd_bus_message_unref.call_count,1);self.assert_lost(value)

    def test_duplicate_reply_foreign_userdata_or_wrong_slot_poison_the_complete_batch(self):
        for mode in ['duplicate','userdata','slot']:
            value=self.subject()
            def process(bus,target):
                slot,callback,userdata=value.fixture_pending.pop()
                value.library.sd_bus_get_current_slot.side_effect=None
                value.library.sd_bus_get_current_slot.return_value=slot if mode!='slot' else slot+1
                callback(700,999 if mode=='userdata' else userdata,None)
                if mode=='duplicate':callback(700,userdata,None)
                return 1
            value.library.sd_bus_process.side_effect=process
            with self.subTest(mode=mode),self.assertRaises(BusRefused):value._get_many('/fixed',self.fields)
            self.assert_lost(value)

    def test_method_error_wrong_variant_and_trailing_reply_data_permanently_refuse(self):
        for function,result in [('sd_bus_message_is_method_error',1),('sd_bus_message_has_signature',0),
                ('sd_bus_message_enter_container',-22),('sd_bus_message_at_end',0)]:
            value=self.subject();getattr(value.library,function).return_value=result
            with self.subTest(function=function),self.assertRaises(BusRefused):value._get_many('/fixed',self.fields)
            self.assert_lost(value)

    def test_process_or_wait_failure_cancels_all_pending_replies(self):
        for waiting in [False,True]:
            value=self.subject();value.library.sd_bus_process.side_effect=None
            value.library.sd_bus_process.return_value=0 if waiting else -5
            value.library.sd_bus_wait.return_value=-5
            with self.subTest(waiting=waiting),self.assertRaises(BusRefused):value._get_many('/fixed',self.fields)
            self.assert_lost(value)

    def test_missing_reply_is_bounded_by_one_batch_deadline(self):
        value=self.subject();value.library.sd_bus_process.side_effect=None;value.library.sd_bus_process.return_value=0
        with patch.object(properties_module.time,'monotonic',side_effect=[0,0,0,0,1,6]):
            with self.assertRaises(BusRefused):value._get_many('/fixed',self.fields)
        self.assert_lost(value)
        value=self.subject();value.library.sd_bus_process.side_effect=None;value.library.sd_bus_process.return_value=1
        with patch.object(properties_module.time,'monotonic',return_value=0):
            with self.assertRaises(BusRefused):value._get_many('/fixed',self.fields)
        self.assertEqual(value.library.sd_bus_process.call_count,4096);self.assert_lost(value)

    def test_interruption_cancels_slots_before_original_connection_is_closed(self):
        value=self.subject();value.library.sd_bus_process.side_effect=KeyboardInterrupt('Fixture interruption')
        with self.assertRaises(KeyboardInterrupt):value._get_many('/fixed',self.fields)
        self.assert_lost(value)
        names=[call[0] for call in value.library.method_calls]
        self.assertLess(max(index for index,name in enumerate(names) if name=='sd_bus_slot_unref'),
            names.index('sd_bus_flush_close_unref'))

    def test_callback_exception_is_contained_and_cannot_escape_through_native_abi(self):
        value=self.subject();value._read_value=Mock(side_effect=KeyboardInterrupt('Fixture callback interruption'))
        with self.assertRaises(BusRefused):value._get_many('/fixed',self.fields)
        self.assert_lost(value)


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

    def test_twenty_actual_queued_selected_batches_match_fresh_serial_typed_reads(self):
        subject=ReadOnlySystemdProperties();self.addCleanup(subject.close)
        selected=[(interface,name,signature) for interface,fields in self.fields for name,signature in fields.items()]
        started=time.monotonic()
        for _ in range(20):self.assertEqual(subject._get_many(self.path,selected),subject._get_many_serial(self.path,selected))
        print('actual_systemd_selected_pairs=20 elapsed_ms='+str(int((time.monotonic()-started)*1000)),flush=True)

    def test_actual_queued_missing_property_and_wrong_variant_permanently_refuse(self):
        for name,signature in [('GitgoodMissingFixtureProperty','s'),('MainPID','s')]:
            subject=ReadOnlySystemdProperties();self.addCleanup(subject.close)
            with self.subTest(name=name),self.assertRaises(BusRefused):
                subject._get_many(self.path,[('org.freedesktop.systemd1.Service',name,signature)])
            self.assertFalse(subject.usable);self.assertFalse(subject.files.usable)
            with self.assertRaises(BusRefused):subject.manager_version()


if __name__ == '__main__':
    unittest.main()
