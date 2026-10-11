"""Service/session stand-ins; real filesystem and database/socket tests are separate."""
import copy
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import native_ownership_observation as observations
from resource_generations import canonical
from test_native_ownership_records import fixture


class OwnershipObservationOrderingTest(unittest.TestCase):
    def setUp(self):
        self.record=fixture(os.getuid() if os.getuid()!=0 else 1000)
        self.calls=[];self.closed=False
        root=Path('/var/lib/gitgood/installations')/self.record['installation']
        self.files={'installation.json':{'sha256':'f'*64}}
        self.binding={'database':self.record['database_session']['database'],'configuration':self.files,
            'resources':{'storage':{'path':str(root/'storage'),'device':1,'inode':2,'uid':self.record['scope']['uid']}}}
        self.seal={'database':self.record['database_session']['database'],'executables':{'psql':'/trusted/psql'}}
        self.captured={'admission':{'pointer':self.record['pointer'],'binding_sha256':self.record['binding_sha256'],
            'worker_observation':{'worker':'native','owner':self.record['owner'],'service_scope':self.record['scope']}},**self.record['guard']}
        def generation():
            self.calls.append('generation');return {'current':True,**self.record['guard']}
        self.guard=SimpleNamespace(snapshot={'binding':self.binding},check=generation)
        self.authority={'protocol':3,'kind':'native_application_ownership_seal',
            **{name:self.record[name] for name in ['installation','operation','candidate','binding_sha256']}}
        def root_file(path,maximum):return {'path':str(path)},canonical(self.authority)
        def session(*args,**kwargs):
            self.calls.append('session')
            self.assertEqual(kwargs['owner'],{name:self.record['owner'][name] for name in ['pid','birth','uid']})
            self.assertEqual(args[2],self.record['backend_kernel'])
            self.assertEqual(args[4],self.record['backend_kernel']['server_scope'])
            return {'owner_connection_observed':True,'lease_acquired':False,'original_backend_kernel_observed':True}
        def custody_check():
            self.calls.append('custody');return {'record_sha256':'a'*64,'marker_sha256':'b'*64}
        def close():self.closed=True
        self.custody=SimpleNamespace(check=custody_check,close=close)
        mocks=[patch.object(observations,'root_file',side_effect=root_file),
            patch.object(observations,'configuration',return_value=(self.files,'postgresql://private-fixture')),
            patch.object(observations,'observe_held_backend_kernel_identity',side_effect=session),
            patch.object(observations,'NativeBackendScope',return_value=SimpleNamespace(check=lambda:copy.deepcopy(self.record['backend_kernel']['server_scope']))),
            patch.object(observations,'NativeOwnershipMarkerGuard',return_value=self.custody)]
        for mocked in mocks:mocked.start();self.addCleanup(mocked.stop)

    def attach(self):return observations.NativeOwnershipObservation(self.guard,self.captured,self.record,self.seal)

    def test_original_context_and_session_bracket_marker_capture_and_checks(self):
        subject=self.attach();self.addCleanup(subject.close)
        self.assertEqual(self.calls,['generation','session','custody','generation','custody'])
        self.calls.clear();value=subject.check()
        self.assertEqual(self.calls,['generation','session','custody','generation','custody'])
        self.assertTrue(value['ownership']['original_database_session_observed'])
        self.assertTrue(value['ownership']['owner_socket_observed'])
        self.assertTrue(value['ownership']['original_backend_kernel_observed'])
        self.assertEqual(value['ownership']['kernel_record_sha256'],hashlib.sha256(canonical(self.record['backend_kernel'])).hexdigest())
        for name in ['lease_acquired','replacement_admitted','installation_readiness_established','lifecycle_responsibility_admitted']:
            self.assertFalse(value['ownership'][name])

    def test_changed_original_capture_or_worker_refuses_before_session_or_custody(self):
        for path,value in [('owner','foreign'),('worker','maintenance')]:
            captured=copy.deepcopy(self.captured);captured['admission']['worker_observation'][path]=value
            with self.assertRaises(ValueError):observations.NativeOwnershipObservation(self.guard,captured,self.record,self.seal)
            self.assertEqual(self.calls,[])

    def test_changed_root_candidate_or_operation_refuses_before_session_or_custody(self):
        for name in ['candidate','operation','extra']:
            authority={**self.authority,name:'changed'}
            with patch.object(observations,'root_file',return_value=({'path':'/fixture'},canonical(authority))):
                with self.assertRaises(ValueError):self.attach()
            self.assertEqual(self.calls,[])

    def test_original_root_seal_replacement_is_terminal_and_cannot_be_recaptured(self):
        subject=self.attach();self.calls.clear()
        with patch.object(observations,'root_file',return_value=({'path':'/changed'},canonical(self.authority))):
            with self.assertRaises(ValueError):subject.check()
        self.assertTrue(self.closed);self.assertTrue(subject.poisoned)
        with self.assertRaises(ValueError):subject.check()
        self.assertEqual(self.calls,[])

    def test_original_kernel_birth_loss_is_terminal_without_recapture(self):
        subject=self.attach();self.calls.clear()
        with patch.object(observations,'observe_held_backend_kernel_identity',side_effect=ValueError('kernel birth loss')):
            with self.assertRaises(ValueError):subject.check()
        self.assertTrue(subject.poisoned);self.assertTrue(self.closed)
        self.assertEqual(self.calls,['generation'])
        with self.assertRaises(ValueError):subject.check()

    def test_changed_protected_server_scope_refuses_before_fresh_sql_or_custody(self):
        subject=self.attach();self.calls.clear()
        with patch.object(subject.backend_scope,'check',return_value={**self.record['backend_kernel']['server_scope'],'postgres_uid':1002}):
            with self.assertRaises(ValueError):subject.check()
        self.assertTrue(subject.poisoned);self.assertEqual(self.calls,[])

    def test_original_backend_loss_or_borrowed_socket_stops_before_custody(self):
        for changed in [{'owner_connection_observed':False,'lease_acquired':False},{'owner_connection_observed':True,'lease_acquired':True}]:
            subject=self.attach();self.calls.clear()
            with patch.object(observations,'observe_held_backend_kernel_identity',return_value=changed):
                with self.assertRaises(ValueError):subject.check()
            self.assertTrue(subject.poisoned);self.assertEqual(self.calls,['generation'])

    def test_configuration_change_refuses_before_original_backend_observation(self):
        subject=self.attach();self.calls.clear()
        with patch.object(observations,'configuration',return_value=({},'postgresql://other')):
            with self.assertRaises(ValueError):subject.check()
        self.assertEqual(self.calls,['generation']);self.assertTrue(self.closed)

    def test_marker_loss_is_terminal_without_repair_or_new_capture(self):
        subject=self.attach();self.calls.clear()
        with patch.object(self.custody,'check',side_effect=ValueError('changed custody')):
            with self.assertRaises(ValueError):subject.check()
        self.assertTrue(subject.poisoned);self.assertTrue(self.closed)
        self.assertEqual(self.calls,['generation','session'])

    def test_initial_result_is_consumed_once_and_does_not_replace_fresh_checks(self):
        subject=self.attach();self.addCleanup(subject.close)
        self.calls.clear()
        initial=subject.take_initial()
        self.assertEqual(self.calls,[])
        initial['ownership']['owner_socket_observed']=False
        self.assertTrue(subject.check()['ownership']['owner_socket_observed'])
        self.assertEqual(self.calls,['generation','session','custody','generation','custody'])
        self.calls.clear()
        with self.assertRaises(ValueError):subject.take_initial()
        self.assertTrue(subject.poisoned);self.assertTrue(self.closed)
        with self.assertRaises(ValueError):subject.check()
        self.assertEqual(self.calls,[])

    def test_failed_original_session_prevents_initial_marker_open(self):
        with patch.object(observations,'NativeOwnershipMarkerGuard') as factory:
            with patch.object(observations,'observe_held_backend_kernel_identity',return_value={'owner_connection_observed':False,'lease_acquired':False}):
                with self.assertRaises(ValueError):self.attach()
            factory.assert_not_called()
        self.assertEqual(self.calls,['generation'])

    def test_fresh_check_invalidates_unconsumed_initial_result(self):
        subject=self.attach();self.addCleanup(subject.close)
        subject.check();self.calls.clear()
        with self.assertRaises(ValueError):subject.take_initial()
        self.assertEqual(self.calls,[])
        self.assertTrue(subject.poisoned);self.assertTrue(self.closed)

    def test_generation_loss_after_initial_marker_capture_refuses_and_closes(self):
        values=[{'current':True,**self.record['guard']},{'current':False,**self.record['guard']}]
        def generation():
            self.calls.append('generation');return values.pop(0)
        with patch.object(self.guard,'check',side_effect=generation):
            with self.assertRaises(ValueError):self.attach()
        self.assertTrue(self.closed)
        self.assertEqual(self.calls,['generation','session','custody','generation'])

    def test_marker_change_across_initial_final_generation_refuses_without_token(self):
        values=[{'record_sha256':'a'*64,'marker_sha256':'b'*64},{'record_sha256':'a'*64,'marker_sha256':'c'*64}]
        def custody():
            self.calls.append('custody');return values.pop(0)
        with patch.object(self.custody,'check',side_effect=custody):
            with self.assertRaises(ValueError):self.attach()
        self.assertTrue(self.closed)
        self.assertEqual(self.calls,['generation','session','custody','generation','custody'])


if __name__=='__main__':unittest.main()
