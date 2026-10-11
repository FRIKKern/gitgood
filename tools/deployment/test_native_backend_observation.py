"""Bridge ordering tests use explicit service/SQL stand-ins, not host acceptance."""
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import native_backend_observation as observation
from resource_generations import canonical
from test_native_ownership_records import fixture


class BackendObservationRequestTest(unittest.TestCase):
    def request(self):
        record = fixture()
        return {'protocol':2,'kind':'native_backend_observation','installation':record['installation'],
                'worker':'native','owner_pid':record['owner']['pid'],'database_session':record['database_session']}

    def test_closed_canonical_request(self):
        value = self.request()
        self.assertEqual(observation.parse_request(canonical(value)), value)

    def test_payload_cannot_supply_scope_commands_or_type_aliases(self):
        value = self.request()
        for raw in [b'',b'\0',b'x'*8193,canonical(value)+b'\n',json.dumps(value).encode(),
                    b'{"protocol":2,"protocol":2}',canonical({**value,'server_scope':{}}),
                    canonical({**value,'command':'private fixture'}),canonical({**value,'protocol':True}),
                    canonical({**value,'owner_pid':True}),canonical({**value,'worker':'driver'})]:
            with self.subTest(size=len(raw)), self.assertRaises(Exception):
                observation.parse_request(raw)


class BackendObservationOrderingTest(unittest.TestCase):
    def setUp(self):
        self.record = fixture()
        self.request = {'protocol':2,'kind':'native_backend_observation','installation':self.record['installation'],
                        'worker':'native','owner_pid':self.record['owner']['pid'],
                        'database_session':self.record['database_session']}
        self.raw = canonical(self.request)
        self.observed = {'service_scope':self.record['scope'],'owner':self.record['owner'],'worker':'native'}
        self.scope = {'boot_id':self.record['scope']['boot_id'],'pid_namespace':'pid:[12345]',
                      'time_namespace':'time:[4441]','postgres_uid':1001}
        self.scope_seal = {'protocol':2,'kind':'native_backend_kernel_scope_seal',
                           'installation':self.record['installation'],'server_scope':self.scope}
        self.kernel = {'protocol':2,'kind':'native_backend_kernel_identity','server_scope':self.scope,
                       'database_session':self.record['database_session'],'kernel_birth':'450'}
        self.seal = {'database':self.record['database_session']['database'],'unit_sha256':'a'*64,
                     'limits':{'cpu_quota_us':2000000,'memory_bytes':268435456},
                     'executables':{'psql':'/trusted/psql'}}
        self.calls=[];self.closed=False
        self.root_files=SimpleNamespace(freeze=lambda:self.calls.append('freeze'))
        self.guard=SimpleNamespace(root_files=self.root_files,close=lambda:setattr(self,'closed',True))
        self.identity={'path':'/fixed/admission'};self.sealed=b'fixed admission bytes'
        self.scope_path = Path('/etc/gitgood/installations')/self.record['installation']/('backend-kernel-'+self.scope['boot_id']+'.json')
        def root_file(path,maximum):
            self.calls.append('scope' if Path(path)==self.scope_path else 'admission')
            if Path(path)==self.scope_path:return {'path':str(path)},canonical(self.scope_seal)
            self.assertEqual(Path(path),Path(self.identity['path']))
            return self.identity,self.sealed
        self.root_file=root_file
        def capture(psql,url,snapshot,database,scope,*,owner):
            self.calls.append('capture')
            self.assertEqual(psql,'/trusted/psql')
            self.assertEqual(snapshot,self.record['database_session'])
            self.assertEqual(scope,self.scope)
            self.assertEqual(owner,{k:self.record['owner'][k] for k in ['pid','birth','uid']})
            return copy.deepcopy(self.kernel)
        mocks=[patch.object(observation,'open_guard',return_value=(self.guard,{},self.seal,self.identity,self.sealed)),
               patch.object(observation,'observe_worker',side_effect=lambda *a,**kw:(self.calls.append('worker') or copy.deepcopy(self.observed))),
               patch.object(observation,'root_file',side_effect=root_file),
               patch.object(observation,'configuration',return_value=({'fixture':'unchanged'},'postgresql://private-fixture')),
               patch.object(observation,'executable',return_value={'path':'/trusted/psql','sha256':'b'*64}),
               patch.object(observation,'capture_backend_kernel_identity',side_effect=capture)]
        for mock in mocks:mock.start();self.addCleanup(mock.stop)

    def test_actual_observer_owner_and_root_scope_bracket_capture_without_authority(self):
        result=observation.observe_request(self.raw)
        self.assertEqual(self.calls,['worker','scope','capture','scope','admission','worker','freeze'])
        self.assertTrue(self.closed)
        self.assertEqual(result['owner'],self.record['owner'])
        self.assertEqual(result['kernel_record'],self.kernel)
        self.assertEqual(result['service_scope_sha256'],hashlib.sha256(canonical(self.record['scope'])).hexdigest())
        for key in ['ownership_retained','writer_exclusion_established','installation_readiness_established','replacement_admitted']:
            self.assertIs(result[key],False)

    def test_root_scope_boot_kind_alias_or_extra_field_refuses_before_capture(self):
        for field,value in [('protocol',True),('kind','unknown'),('installation','unknown'),('extra',True)]:
            original=copy.deepcopy(self.scope_seal);self.scope_seal[field]=value
            with self.subTest(field=field),self.assertRaises(Exception):observation.observe_request(self.raw)
            self.assertNotIn('capture',self.calls);self.assertTrue(self.closed)
            self.scope_seal=original;self.calls=[]
        self.scope_seal['server_scope']['boot_id']='11111111-1111-4111-8111-111111111111'
        with self.assertRaises(Exception):observation.observe_request(self.raw)
        self.assertNotIn('capture',self.calls)

    def test_changed_scope_seal_or_admission_after_capture_refuses(self):
        for changed in ['scope','admission']:
            count=0
            def root_file(path,maximum):
                nonlocal count
                result=self.root_file(path,maximum)
                if Path(path)==self.scope_path:count+=1
                if (changed=='scope' and count==2) or (changed=='admission' and Path(path)==Path(self.identity['path'])):
                    return result[0],result[1]+b' '
                return result
            with self.subTest(changed=changed),patch.object(observation,'root_file',side_effect=root_file):
                with self.assertRaises(Exception):observation.observe_request(self.raw)
            self.assertTrue(self.closed);self.assertNotIn('freeze',self.calls);self.calls=[]

    def test_changed_configuration_executable_or_original_owner_refuses(self):
        for name,values in [('configuration',[({'fixture':'unchanged'},'postgresql://private-fixture'),({},'changed')]),
                            ('executable',[{'path':'/trusted/psql','sha256':'b'*64},{'path':'/trusted/psql','sha256':'c'*64}]),
                            ('observe_worker',[self.observed,{**self.observed,'owner':{**self.record['owner'],'birth':'30002'}}])]:
            with self.subTest(name=name),patch.object(observation,name,side_effect=values):
                with self.assertRaises(Exception):observation.observe_request(self.raw)
            self.assertTrue(self.closed);self.assertNotIn('freeze',self.calls);self.calls=[]

    def test_kernel_reply_cannot_change_original_session_or_root_scope(self):
        for field,value in [('kernel_birth','0'),('database_session',{**self.record['database_session'],'backend_pid':2223}),
                            ('server_scope',{**self.scope,'postgres_uid':1002}),('protocol',True)]:
            with self.subTest(field=field),patch.object(observation,'capture_backend_kernel_identity',return_value={**self.kernel,field:value}):
                with self.assertRaises(Exception):observation.observe_request(self.raw)
            self.assertTrue(self.closed);self.assertNotIn('freeze',self.calls);self.calls=[]

    def test_failed_capture_closes_guard_without_retention_or_retry(self):
        with patch.object(observation,'capture_backend_kernel_identity',side_effect=ValueError('private fixture loss')):
            with self.assertRaises(Exception):observation.observe_request(self.raw)
        self.assertTrue(self.closed);self.assertNotIn('freeze',self.calls)


if __name__=='__main__':unittest.main()
