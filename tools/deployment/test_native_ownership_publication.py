import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import native_ownership_publication as publication
from native_ownership_records import OwnershipRecordRefused
from resource_generations import canonical
from test_native_ownership_records import fixture


class OwnershipPublicationRequestTest(unittest.TestCase):
    def test_closed_canonical_request_preserves_record(self):
        record = fixture()
        raw = canonical({'protocol':3,'record':record})
        self.assertEqual(publication.parse_request(raw),record)

    def test_malformed_duplicate_noncanonical_oversized_or_command_request_refuses(self):
        record = fixture()
        valid = canonical({'protocol':3,'record':record})
        cases = [b'',b'\0',b'x'*32769,b'{"protocol":2,"protocol":2,"record":{}}',
                 json.dumps({'protocol':3,'record':record}).encode(),
                 canonical({'protocol':3,'record':record,'command':'private command'}),
                 valid+b'\n',canonical({'protocol':True,'record':record})]
        for raw in cases:
            with self.subTest(size=len(raw)),self.assertRaises(Exception): publication.parse_request(raw)


class OwnershipPublicationOrderingTest(unittest.TestCase):
    """Explicit service/database stand-ins; filesystem and kernel proof is separate."""
    def setUp(self):
        self.record = fixture(os.getuid() if os.getuid()!=0 else 1000)
        self.raw = canonical({'protocol':3,'record':self.record})
        self.calls = []
        self.retained = []
        self.marker_retained = False
        self.closed = False
        self.authority = {'protocol':3,'kind':'native_application_ownership_seal',
                          **{key:self.record[key] for key in ['installation','operation','candidate','binding_sha256']}}
        root = Path('/var/lib/gitgood/installations')/self.record['installation']
        self.root = root
        self.files = {'installation.json':{'sha256':'f'*64}}
        self.seal = {'database':self.record['database_session']['database'],'executables':{'psql':'/trusted/psql'}}
        self.guard = type('Guard',(),{})()
        self.guard.snapshot = {'binding':{'database':self.seal['database'],'configuration':self.files,
            'resources':{'storage':{'path':str(root/'storage'),'device':1,'inode':2,'uid':self.record['scope']['uid']}}}}
        self.guard.capture = lambda: {'admission':{'binding_sha256':self.record['binding_sha256'],
            'pointer':self.record['pointer'],'worker_observation':{'service_scope':self.record['scope'],'owner':self.record['owner']}},**self.record['guard']}
        self.guard.check = lambda: {'current':True}
        self.guard.close = lambda: setattr(self,'closed',True)
        self.custody = type('Custody',(),{})()
        self.custody.inspect = lambda: {'records':copy.deepcopy(self.retained)}
        def retain(record):
            self.calls.append('retain');self.retained=[copy.deepcopy(record)]
        self.custody.retain = retain
        def publish(record):
            self.calls.append('publish');self.marker_retained=True
            return {'ownership_marker_retained':True,'operation':record['operation'],'replacement_admitted':False,
                    'installation_readiness_established':False}
        self.custody.publish = publish
        def root_file(path,maximum):
            if Path(path).name=='ownership-admission-v3.json': return {'path':str(path)},canonical(self.authority)
            return {'path':str(path)},b'fixed admission bytes'
        self.root_file = root_file
        def session(*args,**kwargs):
            self.calls.append('session')
            self.assertEqual(kwargs['owner'],{key:self.record['owner'][key] for key in ['pid','birth','uid']})
            self.assertEqual(args[2],self.record['backend_kernel'])
            self.assertEqual(args[4],self.record['backend_kernel']['server_scope'])
            return {'owner_connection_observed':True,'lease_acquired':False,'original_backend_kernel_observed':True}
        self.session = session
        mocks = [patch.object(publication,'root_file',side_effect=root_file),
                 patch.object(publication,'open_guard',return_value=(self.guard,{},self.seal,
                     {'path':'/fixed/admission'},b'fixed admission bytes')),
                 patch.object(publication,'NativeOwnershipMarkers',return_value=self.custody),
                 patch.object(publication,'configuration',return_value=(self.files,'postgresql://private-fixture')),
                 patch.object(publication,'observe_held_backend_kernel_identity',side_effect=session),
                 patch.object(publication,'NativeBackendScope',return_value=SimpleNamespace(check=lambda:copy.deepcopy(self.record['backend_kernel']['server_scope']))),
                 patch.object(Path,'lstat',side_effect=FileNotFoundError)]
        for mocked in mocks:
            mocked.start();self.addCleanup(mocked.stop)

    def test_independent_session_checks_bracket_both_writes_and_return_no_replacement_authority(self):
        result = publication.publish_request(self.raw)
        self.assertEqual(self.calls,['session','retain','session','publish','session'])
        self.assertTrue(self.closed)
        self.assertTrue(result['ownership_marker_retained'])
        self.assertFalse(result['replacement_admitted'])
        self.assertFalse(result['writer_exclusion_established'])
        self.assertFalse(result['lifecycle_responsibility_admitted'])

    def test_candidate_or_operation_seal_mismatch_refuses_before_observation_or_mutation(self):
        for name,value in [('candidate','b'*40),('operation','unknown'),('extra','private')]:
            authority=copy.deepcopy(self.authority);authority[name]=value
            with self.subTest(name=name),patch.object(publication,'root_file',return_value=({'path':'/fixed'},canonical(authority))):
                with self.assertRaises(OwnershipRecordRefused): publication.publish_request(self.raw)
            self.assertEqual(self.calls,[])
            self.assertFalse(self.marker_retained)

    def test_caller_scope_cannot_replace_independently_sealed_scope(self):
        changed={**self.record['backend_kernel']['server_scope'],'postgres_uid':1002}
        with patch.object(publication,'NativeBackendScope',return_value=SimpleNamespace(check=lambda:changed)):
            with self.assertRaises(OwnershipRecordRefused):publication.publish_request(self.raw)
        self.assertEqual(self.calls,[]);self.assertFalse(self.marker_retained)

    def test_original_kernel_loss_after_retention_keeps_uncertain_record_and_prevents_marker(self):
        checks=[{'owner_connection_observed':True,'lease_acquired':False,'original_backend_kernel_observed':True},ValueError('original kernel loss')]
        with patch.object(publication,'observe_held_backend_kernel_identity',side_effect=checks):
            with self.assertRaises(ValueError):publication.publish_request(self.raw)
        self.assertEqual(self.retained,[self.record]);self.assertFalse(self.marker_retained);self.assertTrue(self.closed)

    def test_legacy_prior_record_refuses_new_claim_without_rewriting_it(self):
        legacy=copy.deepcopy(self.record);legacy.pop('backend_kernel');legacy['protocol']=2
        self.retained=[legacy]
        with self.assertRaises(OwnershipRecordRefused):publication.publish_request(self.raw)
        self.assertEqual(self.retained,[legacy]);self.assertEqual(self.calls,[]);self.assertTrue(self.closed)

    def test_changed_captured_owner_refuses_before_any_mutation(self):
        original = self.guard.capture
        value = original();value['admission']['worker_observation']['owner']=copy.deepcopy(self.record['owner'])
        value['admission']['worker_observation']['owner']['birth']='30002'
        self.guard.capture = lambda: value
        with self.assertRaises(OwnershipRecordRefused): publication.publish_request(self.raw)
        self.assertEqual(self.calls,[]);self.assertTrue(self.closed)

    def test_unreconciled_prior_record_refuses_without_cleanup(self):
        prior=copy.deepcopy(self.record);prior['candidate']='b'*40
        self.retained=[prior]
        with self.assertRaises(OwnershipRecordRefused): publication.publish_request(self.raw)
        self.assertEqual(self.retained,[prior]);self.assertEqual(self.calls,[])
        self.assertTrue(self.closed)

    def test_another_process_held_session_cannot_publish(self):
        with patch.object(publication,'observe_held_backend_kernel_identity',return_value={'owner_connection_observed':False,'lease_acquired':False}):
            with self.assertRaises(OwnershipRecordRefused): publication.publish_request(self.raw)
        self.assertEqual(self.calls,[]);self.assertFalse(self.marker_retained);self.assertTrue(self.closed)

    def test_loss_after_retention_keeps_record_and_prevents_marker(self):
        def session(*args,**kwargs):
            self.calls.append('session')
            if self.retained: raise OwnershipRecordRefused('Private session loss')
            return {'owner_connection_observed':True,'lease_acquired':False,'original_backend_kernel_observed':True}
        with patch.object(publication,'observe_held_backend_kernel_identity',side_effect=session):
            with self.assertRaises(OwnershipRecordRefused): publication.publish_request(self.raw)
        self.assertEqual(self.retained,[self.record]);self.assertFalse(self.marker_retained)
        self.assertTrue(self.closed)

    def test_loss_after_marker_keeps_both_uncertain_effects(self):
        def session(*args,**kwargs):
            self.calls.append('session')
            if self.marker_retained: raise OwnershipRecordRefused('Private session loss')
            return {'owner_connection_observed':True,'lease_acquired':False,'original_backend_kernel_observed':True}
        with patch.object(publication,'observe_held_backend_kernel_identity',side_effect=session):
            with self.assertRaises(OwnershipRecordRefused): publication.publish_request(self.raw)
        self.assertEqual(self.retained,[self.record]);self.assertTrue(self.marker_retained)
        self.assertTrue(self.closed)
