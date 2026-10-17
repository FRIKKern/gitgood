import copy
import json
import os
import threading
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

import native_ownership_database as ordinary
import native_root_database_exclusion as root
from native_durable_database import DatabaseRefused
from resource_generations import canonical
from test_native_durable_database import GOOD


class RootLeaseGrammarTest(unittest.TestCase):
    def setUp(self):
        self.database = copy.deepcopy(GOOD)
        self.environment = {'PGDATABASE':self.database['database'],'PGUSER':self.database['role'],
            'PGPORT':str(self.database['port'])}
        self.value = {'database':copy.deepcopy(self.database),'clients':2,'holders':[
            {'backend_pid':1234,'backend_birth':'1770000000000000','client_address':'127.0.0.1','client_port':23456}]}

    def parse(self, value):return root._lease(canonical(value),self.database,self.environment)

    def test_only_one_original_holder_and_observer_client_are_accepted(self):
        session,port=self.parse(self.value)
        self.assertEqual(session,{'database':self.database,'backend_pid':1234,'backend_birth':'1770000000000000'})
        self.assertEqual(port,23456)

    def test_missing_multiple_or_foreign_writers_cannot_be_called_excluded(self):
        for holder in ([],self.value['holders']*2,None):
            with self.assertRaises(root.RootDatabaseExclusionRefused):self.parse(dict(self.value,holders=holder))
        for clients in (0,1,3,True,'2'):
            with self.assertRaises(root.RootDatabaseExclusionRefused):self.parse(dict(self.value,clients=clients))

    def test_foreign_address_port_pid_birth_or_identity_refuses(self):
        for name,item in (('client_address','127.0.0.2'),('client_port',True),('client_port',65536),
                          ('backend_pid',True),('backend_birth','1; SELECT'),('backend_birth',str(2**64))):
            value=copy.deepcopy(self.value);value['holders'][0][name]=item
            with self.assertRaises((root.RootDatabaseExclusionRefused,DatabaseRefused)):self.parse(value)
        value=copy.deepcopy(self.value);value['database']['database_oid']+=1
        with self.assertRaises(root.RootDatabaseExclusionRefused):self.parse(value)

    def test_unknown_duplicate_boolean_and_unbounded_reply_refuses(self):
        for raw in (canonical(dict(self.value,authority=True)),b'{"clients":2,"clients":2}',b'x'*16385):
            with self.assertRaises((root.RootDatabaseExclusionRefused,DatabaseRefused)):
                root._lease(raw,self.database,self.environment)
        value=copy.deepcopy(self.value);value['database']['superuser']=True
        with self.assertRaises(DatabaseRefused):self.parse(value)


class OriginalClientParentTest(unittest.TestCase):
    def raw(self, state=b'S', parent=b'359', birth=b'1024'):
        fields=[state,parent,*([b'0']*17),birth]
        return b'777 (client (name)) '+b' '.join(fields)+b'\n'

    def test_kernel_parent_and_birth_are_distinct_from_server_sql_birth(self):
        self.assertEqual(root._parent(self.raw(),777),(359,'1024'))

    def test_zombie_foreign_pid_or_invalid_parent_birth_refuses(self):
        for raw in (self.raw(b'Z'),self.raw(b'X'),self.raw(b'unknown'),self.raw(parent=b'2147483648'),
                    self.raw(birth=str(2**64).encode()),self.raw().replace(b'777 (',b'778 ('),b'x'*16385):
            with self.assertRaises(root.RootDatabaseExclusionRefused):root._parent(raw,777)


class OrdinarySocketAdmissionTest(unittest.TestCase):
    def test_root_cannot_enter_ordinary_socket_owner_route_before_shared_primitive(self):
        owner={'pid':777,'birth':'1024','uid':1000}
        with patch.object(ordinary.os,'getuid',return_value=0,create=True), \
                patch.object(ordinary.os,'geteuid',return_value=0,create=True), \
                patch.object(ordinary,'_socket_for_process') as primitive:
            with self.assertRaises(DatabaseRefused):ordinary._owner_socket(owner,23456,54321)
            primitive.assert_not_called()

    def test_ordinary_socket_primitive_is_bracketed_by_unchanged_original_owner(self):
        owner={'pid':777,'birth':'1024','uid':1000}
        with patch.object(ordinary,'_owner',return_value=('original-process','net:[1]')) as observe, \
                patch.object(ordinary,'_socket_for_process',return_value={'original':'socket'}) as primitive:
            self.assertEqual(ordinary._owner_socket(owner,23456,54321),{'original':'socket'})
            self.assertEqual(observe.call_count,2)
            primitive.assert_called_once_with('original-process','net:[1]',1000,23456,54321)


class RootOriginalExclusionTest(unittest.TestCase):
    def view(self):
        value=root.NativeRootDatabaseExclusionObservation.__new__(root.NativeRootDatabaseExclusionObservation)
        value.usable=True;value.owner=(os.getpid(),threading.get_ident());value.request=Mock()
        value.observed={'installation':'fixed','operation':'fixed-op','stage':'stage'}
        value.session={'backend_pid':1234,'backend_birth':'original-sql'};value.client_port=23456
        value.server_scope={'original':'server'};value.kernel={'kernel_birth':'1024'};value.kernel_raw=canonical(value.kernel)
        value.socket={'original':'socket'}
        value._base=Mock();value._query=Mock(return_value=(copy.deepcopy(value.session),value.client_port))
        value._socket=Mock(return_value=copy.deepcopy(value.socket))
        return value

    def test_non_root_or_caller_map_refuses_before_request_or_database_reads(self):
        with patch.object(root.os,'getuid',return_value=1000,create=True), \
                patch.object(root.NativeRootDatabaseExclusionObservation,'_query') as query:
            with self.assertRaises(root.RootDatabaseExclusionRefused):root.NativeRootDatabaseExclusionObservation({'authority':True})
            query.assert_not_called()

    def test_original_sql_socket_and_kernel_are_bracketed_without_lease_acquisition_or_effects(self):
        value=self.view()
        with patch.object(root,'_capture_process',return_value='1024') as kernel:
            result=value.check()
            self.assertEqual(kernel.call_count,2);self.assertEqual(value._base.call_count,2)
            value._query.assert_called_once_with();value._socket.assert_called_once_with()
        for name in ('original_database_writer_lease_observed','original_database_client_socket_observed',
                     'original_database_backend_kernel_observed','database_writer_exclusion_verified'):
            self.assertIs(result[name],True)
        for name in ('lease_acquired','lifecycle_exclusion_established','stage_effect_authorized','complete_journey_acceptance'):
            self.assertIs(result[name],False)
        self.assertFalse({'database','backend_pid','backend_birth','client_port','socket','kernel','configuration'} & set(result))

    def test_observed_kernel_loss_permanently_poisons_without_query_or_replacement(self):
        value=self.view()
        with patch.object(root,'_capture_process',return_value='changed') as kernel:
            with self.assertRaises(root.RootDatabaseExclusionRefused):value.check()
            value._query.assert_not_called();value.request.close.assert_called_once_with()
            kernel.return_value='1024'
            with self.assertRaises(root.RootDatabaseExclusionRefused):value.check()
            self.assertEqual(kernel.call_count,1)

    def test_changed_sql_session_client_port_or_socket_cannot_be_adopted(self):
        for changed in ('session','port','socket'):
            value=self.view()
            if changed=='session':value._query.return_value=({'backend_pid':1235,'backend_birth':'replacement'},value.client_port)
            elif changed=='port':value._query.return_value=(value.session,value.client_port+1)
            else:value._socket.return_value={'replacement':'socket'}
            with patch.object(root,'_capture_process',return_value='1024'),self.assertRaises(root.RootDatabaseExclusionRefused):value.check()
            self.assertFalse(value.usable)

    def test_changed_parent_request_refuses_before_sql_socket_or_kernel(self):
        value=self.view();value._base.side_effect=root.RootDatabaseExclusionRefused()
        with patch.object(root,'_capture_process') as kernel,self.assertRaises(root.RootDatabaseExclusionRefused):value.check()
        kernel.assert_not_called();value._query.assert_not_called();value._socket.assert_not_called()


class OriginalClientSelectionTest(unittest.TestCase):
    def view(self):
        value=root.NativeRootDatabaseExclusionObservation.__new__(root.NativeRootDatabaseExclusionObservation)
        value.scope={'manager':{'pid':359}};value.psql='/fixed/root/psql';value._client=Mock(return_value={'pid':777,'birth':'1024'})
        return value

    def test_only_one_actual_direct_child_of_the_pinned_client_image_is_selected(self):
        value=self.view()
        with patch.object(root,'read_bytes',return_value=b'776 777'), \
                patch.object(root.os,'readlink',side_effect=['/fixed/other',value.psql]):
            self.assertEqual(value._discover_client(),{'pid':777,'birth':'1024'})
        value._client.assert_called_once_with(777)

    def test_missing_ambiguous_duplicate_or_oversized_child_set_refuses(self):
        for children in (b'',b'777 778',b'777 777',b' '.join(str(pid).encode() for pid in range(1000,1129))):
            value=self.view()
            with patch.object(root,'read_bytes',return_value=children),patch.object(root.os,'readlink',return_value=value.psql), \
                    self.assertRaises(root.RootDatabaseExclusionRefused):value._discover_client()

    def test_selected_child_loss_is_not_skipped_or_replaced(self):
        value=self.view();value._client.side_effect=FileNotFoundError()
        with patch.object(root,'read_bytes',return_value=b'777 778'),patch.object(root.os,'readlink',return_value=value.psql), \
                self.assertRaises(FileNotFoundError):value._discover_client()
        value._client.assert_called_once_with(777)


if __name__=='__main__':unittest.main()
