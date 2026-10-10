import copy
import unittest
from unittest.mock import patch

import native_ownership_database as database
from native_durable_database import DatabaseRefused
from test_native_durable_database import GOOD


class OwnershipDatabaseBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.expected = copy.deepcopy(GOOD)
        self.snapshot = {'database':self.expected,'backend_pid':1234,'backend_birth':'1770000000000000'}

    def test_closed_original_session_shape(self):
        self.assertIsNone(database.validate_session(self.snapshot,self.expected))
        for key,value in [('backend_pid',True),('backend_pid',2**31),('backend_birth','1;SELECT'),
                          ('backend_birth',str(2**64)),('backend_birth',0),('extra','private')]:
            snapshot = copy.deepcopy(self.snapshot);snapshot[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(DatabaseRefused):
                database.validate_session(snapshot,self.expected)

    def test_invalid_identity_refuses_before_starting_database_process(self):
        for field in ['superuser','create_database','create_role','replication','bypass_rls']:
            expected = copy.deepcopy(self.expected);expected[field]=True
            snapshot = copy.deepcopy(self.snapshot);snapshot['database']=expected
            with self.subTest(field=field),patch.object(database.subprocess,'Popen') as opened:
                with self.assertRaises(DatabaseRefused):
                    database.observe_held_session('/trusted/psql','postgresql://'+expected['role']+'@127.0.0.1:'+str(expected['port'])+'/'+expected['database'],snapshot,expected)
                opened.assert_not_called()

    def test_changed_snapshot_database_refuses(self):
        changed = copy.deepcopy(self.snapshot);changed['database']['database_oid']+=1
        with self.assertRaises(DatabaseRefused): database.validate_session(changed,self.expected)
