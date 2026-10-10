import io
import unittest
from unittest.mock import patch

import native_generation_admission as admission
from resource_generations import canonical


class GenerationAdmissionRequestTest(unittest.TestCase):
    def setUp(self):
        self.installation='00000000-0000-4000-8000-000000000001'
        self.request={'protocol':2,'installation':self.installation,'worker':'native','owner_pid':42}
        self.database={'cluster':'7694259926196269080','database':'ordinary','database_oid':31,'owner_oid':32,'role':'ordinary','session_role':'ordinary','role_oid':32,'encoding':'UTF8','version':'18.4','address':'127.0.0.1','port':55432,'can_login':True,'superuser':False,'create_database':False,'create_role':False,'replication':False,'bypass_rls':False,'memberships':0}
        self.seal={'protocol':2,'kind':'native_generation_admission_seal','installation':self.installation,'binding_sha256':'b'*64,'history_identity':{'device':1,'inode':2,'uid':1000},'lock_identity':{'device':1,'inode':3,'uid':1000},'unit_sha256':'a'*64,'executables':{name:'/fixed/'+name for name in ['python','node','git','psql','caddy']},'limits':{'cpu_quota_us':200000,'memory_bytes':268435456},'database':self.database}
        self.file={'path':'/etc/gitgood/installations/'+self.installation+'/generation-admission-v2.json','device':1,'inode':4,'bytes':123,'sha256':'c'*64}
        self.result={'published_generation_admitted':True,'writer_exclusion_established':False,'installation_readiness_established':False,'lifecycle_responsibility_admitted':False,'binding_sha256':'b'*64,'pointer':{'fixture':True},'worker_observation':{'fixture':True}}

    def call(self, request=None):
        return admission.admit_request(canonical(self.request if request is None else request))

    def test_closed_request_cannot_supply_authority_or_choose_seal_path(self):
        for changes in [{'protocol':True},{'protocol':1},{'worker':'driver'},{'worker':'web'},{'owner_pid':True},{'owner_pid':1},{'owner_pid':2**31},{'installation':'../foreign'},{'seal':'/tmp/authority'}]:
            with self.subTest(changes=changes),patch.object(admission,'root_file') as root, self.assertRaises(Exception):self.call({**self.request,**changes})
            root.assert_not_called()

    def test_oversized_duplicate_and_malformed_wire_refuse_before_seal_read(self):
        for raw in [b'',b'x'*4097,b'{}\0',b'{"protocol":2,"protocol":2}',b'[]',b'not-json']:
            with self.subTest(raw=raw[:20]),patch.object(admission,'root_file') as root,self.assertRaises(Exception):admission.admit_request(raw)
            root.assert_not_called()

    def test_only_fixed_root_seal_inputs_reach_reader_and_are_reobserved(self):
        with patch.object(admission,'root_file',return_value=(self.file,canonical(self.seal))) as root,patch.object(admission,'NativeGenerationReader') as factory:
            factory.return_value.admit.return_value=self.result
            value=self.call()
        self.assertEqual(root.call_count,2)
        self.assertTrue(all(str(call.args[0])==self.file['path'] and call.args[1]==16384 for call in root.call_args_list))
        self.assertEqual(factory.call_args.args,('/var/lib/gitgood/installations/'+self.installation,self.installation,'b'*64,self.seal['history_identity'],self.seal['lock_identity'],'a'*64,self.seal['executables']))
        self.assertEqual(factory.call_args.kwargs,self.seal['limits'])
        factory.return_value.admit.assert_called_once_with(worker='native',owner_pid=42)
        self.assertEqual(value['database'],self.database)
        for name in ['writer_exclusion_established','installation_readiness_established','lifecycle_responsibility_admitted']:self.assertFalse(value[name])

    def test_foreign_noncanonical_or_extended_seal_refuses_before_reader(self):
        for changes in [{'protocol':True},{'installation':'00000000-0000-4000-8000-000000000002'},{'kind':'legacy'},{'extra':True},{'limits':{'cpu_quota_us':200000,'memory_bytes':268435456,'command':'shell'}}]:
            with patch.object(admission,'root_file',return_value=(self.file,canonical({**self.seal,**changes}))),patch.object(admission,'NativeGenerationReader') as factory,self.assertRaises(Exception):self.call()
            factory.assert_not_called()
        with patch.object(admission,'root_file',return_value=(self.file,canonical(self.seal)+b'\n')),self.assertRaises(Exception):self.call()

    def test_privileged_or_changed_expected_database_refuses_before_reader(self):
        for changes in [{'superuser':True},{'memberships':1},{'owner_oid':33},{'session_role':'foreign'},{'version':'other'},{'address':'remote'},{'role_oid':True}]:
            seal={**self.seal,'database':{**self.database,**changes}}
            with patch.object(admission,'root_file',return_value=(self.file,canonical(seal))),patch.object(admission,'NativeGenerationReader') as factory,self.assertRaises(Exception):self.call()
            factory.assert_not_called()

    def test_replaced_root_seal_after_admission_refuses_the_response(self):
        with patch.object(admission,'root_file',side_effect=[(self.file,canonical(self.seal)),({**self.file,'inode':5},canonical(self.seal))]),patch.object(admission,'NativeGenerationReader') as factory,self.assertRaises(Exception):
            factory.return_value.admit.return_value=self.result;self.call()

    def test_reader_unavailable_or_wrong_authority_is_not_returned(self):
        for changes in [{'published_generation_admitted':False},{'writer_exclusion_established':True},{'installation_readiness_established':True},{'lifecycle_responsibility_admitted':True},{'binding_sha256':'d'*64}]:
            with patch.object(admission,'root_file',return_value=(self.file,canonical(self.seal))),patch.object(admission,'NativeGenerationReader') as factory,self.assertRaises(Exception):
                factory.return_value.admit.return_value={**self.result,**changes};self.call()

    def test_entry_refusal_does_not_echo_input_or_traceback(self):
        class Stream:
            def __init__(self,raw):self.buffer=io.BytesIO(raw)
        output=Stream(b'')
        with patch.object(admission.sys,'argv',['entry']),patch.object(admission.sys,'stdin',Stream(b'private-invalid-request\n')),patch.object(admission.sys,'stdout',output):
            status=admission.main()
        self.assertEqual(status,1);self.assertEqual(output.buffer.getvalue(),b'{"protocol":2,"status":"refused"}\n')


if __name__=='__main__':unittest.main()
