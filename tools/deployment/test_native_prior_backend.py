import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import native_prior_backend as prior
from native_durable_database import DatabaseRefused
from test_native_durable_database import GOOD, URL
from native_inventory import database_environment
from native_ownership_database import OBSERVATION_OPTIONS, _query_database


class PriorBackendObservationTest(unittest.TestCase):
    def setUp(self):
        self.expected=copy.deepcopy(GOOD)
        self.snapshot={'database':self.expected,'backend_pid':1234,'backend_birth':'1770000000000000'}

    def observe(self,backend,database=None):
        raw=json.dumps({'database':self.expected if database is None else database,'backend':backend}).encode()
        with patch.object(prior,'_query_database',return_value=raw) as query:
            result=prior.observe_prior_backend_absence('/trusted/psql',URL,self.snapshot,self.expected)
            return result,query.call_args

    def test_absent_original_backend_confers_no_process_or_writer_authority(self):
        result,call=self.observe(None)
        self.assertTrue(result['original_backend_absent'])
        self.assertTrue(result['backend_activity_absence_observed'])
        self.assertFalse(result['kernel_backend_absence_observed'])
        self.assertFalse(result['pid_reused'])
        for key in ['lease_acquired','writer_exclusion_established','owner_process_absence_observed','descendant_absence_observed']:
            self.assertIs(result[key],False)
        environment=call.args[1]
        self.assertIn('search_path=pg_catalog',environment['PGOPTIONS'])
        self.assertIn('default_transaction_read_only=on',environment['PGOPTIONS'])
        self.assertEqual(environment['PGPASSFILE'],'/dev/null')
        self.assertNotIn('pg_try_advisory_lock',call.args[2])

    def test_original_birth_refuses_without_assuming_lease_release_is_backend_absence(self):
        with self.assertRaises(DatabaseRefused):
            self.observe({'pid':1234,'birth':self.snapshot['backend_birth']})

    def test_known_reused_pid_is_not_adopted_or_exposed_as_a_signal_target(self):
        result,_=self.observe({'pid':1234,'birth':'1770000000000001'})
        self.assertTrue(result['original_backend_absent'] and result['pid_reused'])
        self.assertNotIn('backend_pid',result)
        self.assertNotIn('backend_birth',result)
        self.assertFalse(result['writer_exclusion_established'])

    def test_hidden_birth_and_invalid_rows_cannot_prove_absence(self):
        for value in [{},[],False,{'pid':1234,'birth':None},{'pid':1234,'birth':'01'},
                      {'pid':True,'birth':'2'},{'pid':1235,'birth':'2'},
                      {'pid':1234,'birth':'2','extra':True}]:
            with self.subTest(value=value),self.assertRaises(DatabaseRefused):self.observe(value)

    def test_changed_database_refuses_even_with_no_matching_backend(self):
        for key in ['cluster','database_oid','role_oid','superuser','memberships']:
            changed=copy.deepcopy(self.expected)
            changed[key]=True if key=='superuser' else str(changed[key])+'changed' if isinstance(changed[key],str) else changed[key]+1
            with self.subTest(key=key),self.assertRaises(DatabaseRefused):self.observe(None,changed)

    def test_duplicate_or_unknown_output_cannot_establish_absence(self):
        for raw in [b'null',b'[]',b'{"backend":null,"backend":null}',
                    json.dumps({'database':self.expected,'backend':None,'extra':True}).encode()]:
            with patch.object(prior,'_query_database',return_value=raw),self.assertRaises(DatabaseRefused):
                prior.observe_prior_backend_absence('/trusted/psql',URL,self.snapshot,self.expected)

    def test_malformed_or_type_aliased_snapshot_refuses_before_query(self):
        for key,value in [('backend_pid',True),('backend_birth','1;SELECT'),('extra',True),
                          ('database',{**self.expected,'memberships':False}),
                          ('database',{**self.expected,'superuser':0})]:
            snapshot=copy.deepcopy(self.snapshot);snapshot[key]=value
            with self.subTest(key=key,value=value),patch.object(prior,'_query_database') as query:
                with self.assertRaises(DatabaseRefused):
                    prior.observe_prior_backend_absence('/trusted/psql',URL,snapshot,self.expected)
                query.assert_not_called()


@unittest.skipUnless(sys.platform=='linux','Actual bounded query child requires Linux selectors')
class PriorBackendQueryProcessTest(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='gitgood-prior-backend-query-')
        self.addCleanup(self.temporary.cleanup)
        self.executable=Path(self.temporary.name)/'owned-query'
        self.environment=database_environment(URL)
        self.environment.update(PGPASSFILE='/dev/null',PGOPTIONS=OBSERVATION_OPTIONS)

    def executable_code(self,code):
        self.executable.write_text('#!'+sys.executable+'\n'+code+'\n')
        self.executable.chmod(0o700)

    def test_actual_child_receives_fixed_catalog_read_only_options_and_no_argv_password(self):
        self.executable_code("import json,os,sys\nprint(json.dumps({'args':sys.argv[1:],'options':os.environ['PGOPTIONS'],'passfile':os.environ['PGPASSFILE']}))")
        value=json.loads(_query_database(str(self.executable),self.environment,'SELECT 1'))
        self.assertEqual(value['options'],OBSERVATION_OPTIONS)
        self.assertEqual(value['passfile'],'/dev/null')
        self.assertNotIn('private-fixture',str(value['args']))
        self.assertEqual(value['args'][-2:],['--command','SELECT 1'])

    def test_untrusted_query_environment_refuses_before_process(self):
        for key,value in [('PGOPTIONS','-c search_path=public'),('PGPASSFILE','/other/passwords')]:
            with self.subTest(key=key),patch('native_ownership_database.subprocess.Popen') as process:
                with self.assertRaises(DatabaseRefused):
                    _query_database(str(self.executable),{**self.environment,key:value},'SELECT 1')
                process.assert_not_called()

    def test_actual_oversized_or_failed_query_child_cannot_return_observation(self):
        for code in ["print('x'*20000)","import sys\nprint('partial');sys.exit(2)"]:
            self.executable_code(code)
            original=subprocess.Popen;children=[]
            def track(*args,**kwargs):
                child=original(*args,**kwargs);children.append(child);return child
            with patch('native_ownership_database.subprocess.Popen',side_effect=track),self.assertRaises(DatabaseRefused):
                _query_database(str(self.executable),self.environment,'SELECT 1')
            self.assertEqual(len(children),1)
            self.assertIsNotNone(children[0].returncode)
