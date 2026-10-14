import copy
import os
import threading
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

import native_root_database_reader as root
from native_inventory import database_environment
from resource_generations import canonical
from test_native_durable_database import GOOD, URL


READER = {'backend_pid':1234,'backend_birth':'1770000000000000','client_address':'127.0.0.1',
    'client_port':23456,'read_only':'on','isolation':'read committed','held':False}


class ReaderGrammarTest(unittest.TestCase):
    def test_closed_read_only_original_metadata_is_copied(self):
        actual=root._reader(READER);self.assertEqual(actual,READER);self.assertIsNot(actual,READER)

    def test_writable_nonfresh_isolation_or_lease_holder_refuses(self):
        for field,value in [('read_only','off'),('isolation','repeatable read'),('held',True),('held',0)]:
            with self.subTest(field=field,value=value),self.assertRaises(root.RootDatabaseReaderRefused):
                root._reader({**READER,field:value})

    def test_foreign_boolean_unbounded_or_unknown_session_fields_refuse(self):
        for field,value in [('backend_pid',True),('backend_pid',0),('backend_birth','0'),
            ('backend_birth',str(2**64)),('client_address','127.0.0.2'),('client_port',True),('client_port',65536)]:
            with self.subTest(field=field),self.assertRaises(root.RootDatabaseReaderRefused):root._reader({**READER,field:value})
        for value in [None,[],{**READER,'authority':True}]:
            with self.assertRaises(root.RootDatabaseReaderRefused):root._reader(value)


class ReaderAdmissionTest(unittest.TestCase):
    def test_ordinary_caller_refuses_before_lifecycle_or_process(self):
        with patch.object(root.os,'getuid',return_value=1000,create=True),patch.object(root.subprocess,'Popen') as child:
            with self.assertRaises(root.RootDatabaseReaderRefused):root.NativeRootDatabaseReader(Mock())
            child.assert_not_called()

    def test_root_caller_map_refuses_before_process_or_private_configuration(self):
        with ExitStack() as stack:
            for name in ('getuid','geteuid','getgid','getegid'):stack.enter_context(patch.object(root.os,name,return_value=0,create=True))
            child=stack.enter_context(patch.object(root.subprocess,'Popen'))
            config=stack.enter_context(patch.object(root,'configuration'))
            with self.assertRaises(root.RootDatabaseReaderRefused):root.NativeRootDatabaseReader({'authority':True})
            child.assert_not_called();config.assert_not_called()


class ReaderExchangeTest(unittest.TestCase):
    """Framing and poison boundaries with explicit process/kernel/base stand-ins."""
    def view(self):
        value=root.NativeRootDatabaseReader.__new__(root.NativeRootDatabaseReader)
        value.usable=True;value.owner=(os.getpid(),threading.get_ident());value.child=Mock()
        value.child.poll.return_value=None;value.child.stdin.write.side_effect=lambda raw:len(raw)
        value.child.stdout.fileno.return_value=19
        value.expected=copy.deepcopy(GOOD);value.environment=database_environment(URL)
        value.reader=copy.deepcopy(READER);value.client={'pid':777,'birth':'1024'}
        value.kernel='2048';value.socket={'original':'socket'}
        value._base=Mock(return_value=copy.deepcopy(value.client));value.lifecycle=Mock()
        return value

    def exchange(self,value,reply,kind='identity'):
        selector=Mock();selector.select.return_value=[('ready',1)]
        manager=Mock();manager.__enter__=Mock(return_value=selector);manager.__exit__=Mock(return_value=False)
        with patch.object(root.uuid,'uuid4',return_value='fixed-nonce'), \
                patch.object(root.selectors,'DefaultSelector',return_value=manager), \
                patch.object(root.os,'read',side_effect=reply if type(reply) is list else [reply]):
            return value._exchange(kind)

    def reply(self,**changes):
        return canonical({'nonce':'fixed-nonce','reader':copy.deepcopy(READER),'value':copy.deepcopy(GOOD),**changes})+b'\n'

    def test_fresh_fixed_identity_statement_reuses_original_child_and_brackets_it(self):
        value=self.view();child=value.child
        self.assertEqual(self.exchange(value,self.reply()),GOOD)
        self.assertEqual(self.exchange(value,self.reply()),GOOD)
        self.assertIs(value.child,child);self.assertEqual(value._base.call_count,4)
        for call in child.stdin.write.call_args_list:
            self.assertIn(root.SQL.encode(),call.args[0]);self.assertNotIn(b'pg_try_advisory_lock',call.args[0])
        child.terminate.assert_not_called()

    def test_exclusion_statement_retains_exact_two_client_scope_without_acquiring_lease(self):
        value=self.view();observed={'database':GOOD,'holders':[],'clients':2}
        self.assertEqual(self.exchange(value,self.reply(value=observed),'exclusion'),observed)
        command=value.child.stdin.write.call_args.args[0]
        self.assertIn(root.ROOT_EXCLUSION_SQL.encode(),command);self.assertNotIn(b'pg_try_advisory_lock',command)

    def test_caller_sql_or_acquisition_mode_refuses_before_write_and_permanently_closes_owned_child(self):
        for kind in [None,'SELECT private','acquire',True]:
            value=self.view();child=value.child
            with self.assertRaises(root.RootDatabaseReaderRefused):value._exchange(kind)
            value._base.assert_not_called();child.stdin.write.assert_not_called();child.terminate.assert_called_once()
            value.lifecycle.close.assert_not_called();self.assertFalse(value.usable)

    def test_wrong_nonce_or_original_backend_birth_cannot_be_adopted(self):
        for raw in [self.reply(nonce='foreign'),self.reply(reader={**READER,'backend_birth':'1770000000000001'})]:
            value=self.view()
            with self.assertRaises(root.RootDatabaseReaderRefused):self.exchange(value,raw)
            self.assertIsNone(value.child);self.assertFalse(value.usable)
            with self.assertRaises(root.RootDatabaseReaderRefused):self.exchange(value,self.reply())

    def test_duplicate_excess_truncated_and_oversized_frames_poison_without_reconnection(self):
        for raw in [b'{"nonce":"fixed-nonce","nonce":"fixed-nonce"}\n',self.reply()+b'{}\n',
            [b'{}',b''],[b'x'*4096]*5]:
            value=self.view()
            with patch.object(root.subprocess,'Popen') as create,self.assertRaises(root.RootDatabaseReaderRefused):
                self.exchange(value,raw)
            create.assert_not_called();self.assertFalse(value.usable)

    def test_writable_server_reply_or_changed_database_never_returns_identity(self):
        for raw in [self.reply(reader={**READER,'read_only':'off'}),self.reply(value={**GOOD,'database_oid':11})]:
            value=self.view()
            with self.assertRaises(root.RootDatabaseReaderRefused):self.exchange(value,raw)
            self.assertFalse(value.usable)

    def test_original_base_loss_before_or_after_select_never_returns_success(self):
        for loss in ['before','after']:
            value=self.view();child=value.child
            value._base.side_effect=[ValueError('lost private original')] if loss=='before' else [value.client,ValueError('lost')]
            with self.assertRaises(root.RootDatabaseReaderRefused):self.exchange(value,self.reply())
            self.assertEqual(child.stdin.write.call_count,0 if loss=='before' else 1)
            child.terminate.assert_called_once();value.lifecycle.close.assert_not_called()

    def test_foreign_process_or_thread_cannot_close_parent_owned_child(self):
        value=self.view();child=value.child;value.owner=(os.getpid()+1,threading.get_ident())
        value.close();child.terminate.assert_not_called();child.stdin.close.assert_not_called()
        self.assertFalse(value.usable)


if __name__=='__main__':unittest.main()
