import copy
import os
import threading
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

import native_root_database_reader as root
from native_inventory import database_environment
from native_root_controller import RootControllerRefused, _RootObservationPass
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
        value.prepared_statements=set()
        value.kernel='2048';value.socket={'original':'socket'}
        value._base=Mock(return_value=copy.deepcopy(value.client));value.lifecycle=Mock()
        return value

    def exchange(self,value,reply,kind='identity'):
        selector=Mock();selector.select.return_value=[('ready',1)]
        manager=Mock();manager.__enter__=Mock(return_value=selector);manager.__exit__=Mock(return_value=False)
        with patch.object(root.uuid,'uuid4',return_value='12345678-1234-4234-8234-123456789abc'), \
                patch.object(root.selectors,'DefaultSelector',return_value=manager), \
                patch.object(root.os,'read',side_effect=reply if type(reply) is list else [reply]):
            return value._exchange(kind)

    def reply(self,**changes):
        return canonical({'nonce':'12345678-1234-4234-8234-123456789abc','reader':copy.deepcopy(READER),'value':copy.deepcopy(GOOD),**changes})+b'\n'

    def test_fresh_fixed_identity_statement_reuses_original_child_and_brackets_it(self):
        value=self.view();child=value.child
        self.assertEqual(self.exchange(value,self.reply()),GOOD)
        self.assertEqual(self.exchange(value,self.reply()),GOOD)
        self.assertIs(value.child,child);self.assertEqual(value._base.call_count,4)
        commands=[call.args[0] for call in child.stdin.write.call_args_list]
        self.assertIn(root.SQL.encode(),commands[0]);self.assertIn(root.READER_SQL.encode(),commands[0])
        self.assertIn(b'PREPARE gitgood_root_identity_v2(text)',commands[0])
        self.assertEqual(commands[1],b"EXECUTE gitgood_root_identity_v2('12345678-1234-4234-8234-123456789abc');\n")
        self.assertTrue(all(b'pg_try_advisory_lock' not in command for command in commands))
        child.terminate.assert_not_called()

    def test_only_fixed_statement_plans_persist_and_every_execution_has_fresh_nonce(self):
        value=self.view()
        first=value._statement('identity','12345678-1234-4234-8234-123456789abc',root.SQL)
        second=value._statement('identity','12345678-1234-4234-8234-123456789abd',root.SQL)
        exclusion=value._statement('exclusion','12345678-1234-4234-8234-123456789abe',root.ROOT_EXCLUSION_SQL)
        self.assertIn(root.SQL.encode(),first);self.assertIn(root.READER_SQL.encode(),first)
        self.assertNotIn(b'PREPARE',second);self.assertIn(b'123456789abd',second)
        self.assertNotIn(b'123456789abc',second)
        self.assertIn(root.ROOT_EXCLUSION_SQL.encode(),exclusion)
        self.assertEqual(value.prepared_statements,{'identity','exclusion'})
        value.child.stdin.write.assert_not_called()

    def test_supplied_sql_nonce_kind_and_corrupt_plan_state_refuse_before_io(self):
        value=self.view();nonce='12345678-1234-4234-8234-123456789abc'
        for kind,actual_nonce,statement in [('foreign',nonce,root.SQL),('identity',"x');SELECT 1;--",root.SQL),
                ('identity',nonce,'SELECT 1')]:
            with self.assertRaises((ValueError,root.RootDatabaseReaderRefused)):
                value._statement(kind,actual_nonce,statement)
        for state in [None,{},set(['foreign'])]:
            value.prepared_statements=state
            with self.assertRaises(root.RootDatabaseReaderRefused):value._statement('identity',nonce,root.SQL)
        value.child.stdin.write.assert_not_called()

    def test_failed_preparation_permanently_poisoned_without_reconnect(self):
        value=self.view();child=value.child;child.stdin.write.return_value=0
        child.stdin.write.side_effect=None
        with patch.object(root.subprocess,'Popen') as create:
            with self.assertRaises(root.RootDatabaseReaderRefused):self.exchange(value,self.reply())
            self.assertFalse(value.usable);self.assertIsNone(value.child)
            with self.assertRaises(root.RootDatabaseReaderRefused):self.exchange(value,self.reply())
            create.assert_not_called()

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


class ReaderStageObservationTest(unittest.TestCase):
    """Fixed shared SELECT; process/kernel/base and wire replies are stand-ins."""
    view = ReaderExchangeTest.view

    def root_context(self, stack):
        for name in ('getuid','geteuid','getgid','getegid'):
            stack.enter_context(patch.object(root.os,name,return_value=0,create=True))

    def stage_reply(self, value, replies):
        selector=Mock();selector.select.return_value=[('ready',1)]
        manager=Mock();manager.__enter__=Mock(return_value=selector);manager.__exit__=Mock(return_value=False)
        stack=ExitStack();self.addCleanup(stack.close);self.root_context(stack)
        nonces=['12345678-1234-4234-8234-'+format(i,'012x') for i in range(len(replies))]
        stack.enter_context(patch.object(root.uuid,'uuid4',side_effect=nonces))
        stack.enter_context(patch.object(root.selectors,'DefaultSelector',return_value=manager))
        stack.enter_context(patch.object(root.os,'read',side_effect=[canonical({
            'nonce':nonces[i],'reader':copy.deepcopy(READER),'value':reply})+b'\n'
            for i,reply in enumerate(replies)]))

    def observed(self):
        return {'database':copy.deepcopy(GOOD),'holders':[{'original':'writer'}],'clients':2}

    def test_one_original_exclusion_reply_supplies_identity_and_lease_within_each_pass(self):
        value=self.view();child=value.child;observed=self.observed()
        self.stage_reply(value,[observed,observed])
        for _ in range(2):
            with _RootObservationPass():
                self.assertEqual(value.identity(),GOOD)
                self.assertEqual(value.exclusion(),canonical(observed))
        self.assertEqual(child.stdin.write.call_count,2);self.assertEqual(value._base.call_count,4)
        commands=[call.args[0] for call in child.stdin.write.call_args_list]
        self.assertNotEqual(commands[0],commands[1])
        self.assertIn(root.ROOT_EXCLUSION_SQL.encode(),commands[0])
        self.assertEqual(commands[1],b"EXECUTE gitgood_root_exclusion_v2('12345678-1234-4234-8234-000000000001');\n")
        self.assertTrue(all(b'pg_try_advisory_lock' not in command for command in commands))
        self.assertIs(value.child,child);child.terminate.assert_not_called()

    def test_standalone_consumers_still_issue_separate_fresh_queries(self):
        value=self.view();self.stage_reply(value,[self.observed(),self.observed()])
        self.assertEqual(value.identity(),GOOD);self.assertEqual(value.exclusion(),canonical(self.observed()))
        self.assertEqual(value.child.stdin.write.call_count,2);self.assertEqual(value._base.call_count,4)

    def test_returned_identity_mutation_cannot_change_shared_reply_or_expected_binding(self):
        value=self.view();self.stage_reply(value,[self.observed()])
        with _RootObservationPass():
            identity=value.identity();identity['database_oid']=999
            self.assertEqual(value.identity(),GOOD)
            self.assertEqual(value.exclusion(),canonical(self.observed()))
        self.assertEqual(value.expected,GOOD);self.assertEqual(value.child.stdin.write.call_count,1)

    def test_changed_writer_observation_is_fresh_in_the_separate_final_pass(self):
        value=self.view();first=self.observed();second={**first,'holders':[]}
        self.stage_reply(value,[first,second])
        with _RootObservationPass():self.assertEqual(value.exclusion(),canonical(first))
        with _RootObservationPass():self.assertEqual(value.exclusion(),canonical(second))
        self.assertEqual(value.child.stdin.write.call_count,2)

    def test_unknown_missing_or_changed_database_reply_permanently_poison_before_identity(self):
        for observed in [None,[],{}, {**self.observed(),'authority':True},
                {**self.observed(),'database':{**GOOD,'database_oid':11}}]:
            with self.subTest(observed=observed):
                value=self.view();child=value.child
                with patch.object(value,'_exchange',return_value=observed):
                    with self.assertRaises(root.RootDatabaseReaderRefused):value.identity()
                self.assertFalse(value.usable);child.terminate.assert_called_once()

    def test_original_loss_cannot_return_shared_success_or_revive_the_failed_pass(self):
        value=self.view();self.stage_reply(value,[self.observed()])
        with self.assertRaises(RootControllerRefused):
            with _RootObservationPass():
                value.identity();value.close()
                with self.assertRaises(root.RootDatabaseReaderRefused):value.exclusion()
                value.usable=True
                value.identity()
        self.assertEqual(value._base.call_count,3)

    def test_original_base_loss_after_query_refuses_both_consumers_and_closes_owned_child(self):
        for consumer in ('identity','exclusion'):
            with self.subTest(consumer=consumer):
                value=self.view();child=value.child
                self.stage_reply(value,[self.observed()])
                value._base.side_effect=[value.client,ValueError('lost original')]
                with self.assertRaises(root.RootDatabaseReaderRefused):
                    with _RootObservationPass():getattr(value,consumer)()
                self.assertFalse(value.usable);child.terminate.assert_called_once()

    def test_different_original_reader_cannot_reuse_another_readers_reply(self):
        first=self.view();second=self.view();self.stage_reply(first,[self.observed(),self.observed()])
        with _RootObservationPass():
            first.identity();second.exclusion()
        self.assertEqual(first.child.stdin.write.call_count,1)
        self.assertEqual(second.child.stdin.write.call_count,1)


if __name__=='__main__':unittest.main()
