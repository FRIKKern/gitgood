"""Controller order/retention tests with explicit service/database stand-ins."""
import copy
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

import native_ownership_controller as controller
import native_ownership_handoff as handoff_transport
from generation_custody import GenerationRecordCustody, CustodyRefused
from native_command_endpoint import NativeCommandEndpoint
from native_generation_reader import NativeGenerationReader, _ReadOnlyCustody
from native_lifecycle_generation_reader import NativeLifecycleGenerationReader
from native_ownership_records import OwnershipRecordRefused
from native_ownership_transition import OwnershipTransitionStore, sha
from resource_generations import canonical
from test_native_ownership_records import fixture
from test_native_ownership_transition import next_record


def absent_result():
    return {'original_backend_absent':True,'backend_activity_absence_observed':True,
        'kernel_backend_absence_observed':True,'pid_reused':False,'expected_database_observed':True,
        'lease_acquired':False,'writer_exclusion_established':False,'owner_process_absence_observed':False,
        'descendant_absence_observed':False,'kernel_pid_reused':False,'replacement_admitted':False}


class OriginalOwnerAbsenceTest(unittest.TestCase):
    def test_only_missing_original_pid_or_distinct_birth_is_absence(self):
        record=fixture();owner=record['owner']
        with patch.object(controller,'read_bytes',side_effect=FileNotFoundError):controller.original_owner_absent(record)
        raw=(str(owner['pid'])+' (original) S '+'0 '*18+str(int(owner['birth'])+1)+'\n').encode()
        with patch.object(controller,'read_bytes',return_value=raw):controller.original_owner_absent(record)
        for state in ['S','Z','X']:
            raw=(str(owner['pid'])+' (original) '+state+' '+'0 '*18+owner['birth']+'\n').encode()
            with self.subTest(state=state),patch.object(controller,'read_bytes',return_value=raw):
                with self.assertRaises(OwnershipRecordRefused):controller.original_owner_absent(record)
        for error in [PermissionError,OSError]:
            with patch.object(controller,'read_bytes',side_effect=error):
                with self.assertRaises(error):controller.original_owner_absent(record)

    def test_supplied_authority_objects_cannot_construct_a_controller(self):
        with self.assertRaises(OwnershipRecordRefused):
            controller.NativeOwnershipController(str(uuid.uuid4()),SimpleNamespace(check=lambda:None),SimpleNamespace())

    def test_absolute_reservation_deadline_refuses_before_any_new_observation(self):
        value=object.__new__(controller.NativeOwnershipController)
        value.usable=True;value.owner=(os.getpid(),controller.threading.get_ident());value.deadline=10.0
        with patch.object(controller.time,'monotonic',return_value=10.0):
            with self.assertRaises(OwnershipRecordRefused):value._controller()


@unittest.skipUnless(sys.platform=='linux' and os.getuid()!=0,'ordinary Linux controller custody')
class ControllerCustodyTest(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        root=Path(temporary.name);self.storage=root/'storage';self.storage.mkdir(mode=0o700)
        history=root/'history';history.mkdir(mode=0o700)
        lock=history/'.upgrade-history-lock-v1';lock.touch(mode=0o600)
        def identity(path):
            info=path.stat();return {'device':info.st_dev,'inode':info.st_ino,'uid':info.st_uid}
        self.identity=identity(self.storage)
        self.base=fixture(os.getuid());self.scope=copy.deepcopy(self.base['scope'])
        self.scope['manager']['pid']=os.getpid();self.base['scope']=self.scope
        self.base['guard']['scope_sha256']=sha({'scope':self.scope,'owner':self.base['owner'],'worker':'native'})
        self.custody=GenerationRecordCustody(history,self.base['installation'],identity(history),identity(lock))
        self.custody.__enter__();self.addCleanup(self.custody.__exit__,None,None,None)
        self.endpoint=object.__new__(NativeCommandEndpoint)
        self.endpoint.scope=SimpleNamespace(installation=self.base['installation'],check=lambda:copy.deepcopy(self.scope))
        self.endpoint.check=lambda:None
        self.events=[];self.stage='migrate';self.backend=self.base['backend_kernel']['server_scope']
        self.authority={'protocol':3,'kind':'native_application_ownership_seal',
            **{key:self.base[key] for key in ['installation','operation','candidate','binding_sha256']}}
        self.seal={'protocol':2,'kind':'native_generation_admission_seal','installation':self.base['installation'],
            'binding_sha256':self.base['binding_sha256'],'history_identity':self.custody.identity,
            'lock_identity':self.custody.expected_lock_identity,'unit_sha256':self.scope['unit_definition']['sha256'],
            'executables':{'psql':'/trusted/psql'},'limits':{name:self.scope['limits'][name] for name in ['cpu_quota_us','memory_bytes']},
            'database':self.base['database_session']['database']}
        self.binding={'database':self.seal['database'],'configuration':{'private':'synthetic'},
                      'resources':{'storage':{'path':str(self.storage),**self.identity}}}
        def reader(*args,**kwargs):
            stage=self.stage
            snapshot={'binding':self.binding,'pointer':self.base['pointer'],'files':{},
                      'lifecycle':{'operation':self.base['operation'],'candidate':self.base['candidate'],'stage':stage}}
            return SimpleNamespace(borrow_custody=lambda custody:self.assertIs(custody,self.custody),
                                   _snapshot=lambda scope:copy.deepcopy(snapshot),close=lambda:None)
        test=self
        class Exclusion:
            def __init__(self,*args):self.closed=False
            def __enter__(self):test.events.append('exclude');return self
            def check(self):
                test.assertFalse(self.closed);test.events.append('check-exclusion')
                return {'held':True,**copy.deepcopy(test.base['database_session'])}
            def close(self):
                if test.subject.state in {'assigning','assigned','publishing','complete'}:
                    test.assertIn(test.subject.claim+'.assignment.json',test.subject.store.known['receipts'])
                test.events.append('release-exclusion');self.closed=True
        def kernel(psql,url,session,database,scope):
            return {'protocol':2,'kind':'native_backend_kernel_identity','database_session':session,
                    'server_scope':scope,'kernel_birth':'500'}
        patches=[patch.object(controller,'open_reader',side_effect=reader),
            patch.object(controller,'persistent_identity',return_value=self.binding),
            patch.object(controller,'persistent_fingerprint',return_value={}),
            patch.object(controller,'configuration',return_value=(self.binding['configuration'],'postgresql://private-fixture')),
            patch.object(controller,'NativeBackendScope',return_value=SimpleNamespace(check=lambda:copy.deepcopy(self.backend))),
            patch.object(controller,'stopped',side_effect=lambda scope:self.events.append('stopped')),
            patch.object(controller,'NativeWriterExclusion',Exclusion),
            patch.object(controller,'capture_backend_kernel_identity',side_effect=kernel),
            patch.object(controller,'original_owner_absent',side_effect=lambda record:self.events.append('owner-absent')),
            patch.object(controller,'observe_prior_backend_identity_absence',side_effect=lambda *args:self.events.append('backend-absent') or absent_result()),
            patch.object(controller,'observe_held_backend_kernel_identity',side_effect=lambda *args,**kwargs:
                self.events.append('new-held-session') or {'owner_connection_observed':True,'original_backend_kernel_observed':True})]
        for value in patches:value.start();self.addCleanup(value.stop)
        self.subject=controller.NativeOwnershipController(self.base['installation'],self.custody,self.endpoint)
        self.addCleanup(self.subject.close)
        self.subject._root=lambda name:copy.deepcopy(self.seal if name=='generation-admission-v2.json' else self.authority)
        self.subject._peer_owner=lambda peer,pid:copy.deepcopy(self.new_owner)
        self.peer={'pid':2100,'uid':os.getuid(),'gid':os.getgid()}
        self.new_owner=copy.deepcopy(self.base['owner'])
        self.security=patch.object(controller,'process_identity',side_effect=lambda pid,*args:{**copy.deepcopy(self.new_owner),'pid':pid})
        self.security.start();self.addCleanup(self.security.stop)

    def claim(self, mode):
        self.subject.reserve(mode)
        request={'protocol':4,'kind':'native_ownership_handoff','action':'admit',
                 **{name:self.authority[name] for name in ['installation','operation','candidate']},
                 'mode':mode,'owner_pid':self.new_owner['pid']}
        handoff=self.subject.admit(request,self.peer)
        record=next_record(self.subject.previous,mode=mode,uid=os.getuid()) if self.subject.previous else next_record(mode=mode,uid=os.getuid())
        record.update({name:self.authority[name] for name in ['installation','operation','candidate','binding_sha256']})
        record.update(claim=handoff['claim'],reservation_sha256=handoff['reservation_sha256'],
            predecessor_sha256=handoff['predecessor_sha256'],scope=copy.deepcopy(self.scope),owner=copy.deepcopy(self.new_owner),
            pointer=copy.deepcopy(self.base['pointer']))
        record['backend_kernel']['server_scope']=copy.deepcopy(self.backend)
        record['guard']={'scope_sha256':sha({'scope':self.scope,'owner':record['owner'],'worker':self.subject.worker}),
                         'history_sha256':sha(self.subject.snapshot),'persistent_files_sha256':sha(self.subject.files)}
        result=self.subject.publish(record,self.peer)
        return record,result,request

    def test_migrate_bootstrap_runtime_keeps_one_operation_and_distinct_original_claims(self):
        records=[]
        for stage,mode in [('migrate','migrate'),('bootstrap','migrate'),('complete','runtime')]:
            self.stage=stage;self.new_owner['pid']+=10;self.new_owner['birth']=str(int(self.new_owner['birth'])+10)
            record,receipt,_=self.claim(mode);records.append(record)
            self.assertEqual(receipt['record_sha256'],sha(record))
        self.assertEqual({record['operation'] for record in records},{self.base['operation']})
        self.assertEqual(len({record['claim'] for record in records}),3)
        self.assertEqual(len(self.subject.store.records()),3)
        self.assertEqual(records[1]['predecessor_sha256'],sha(records[0]))
        self.assertEqual(records[2]['predecessor_sha256'],sha(records[1]))
        self.assertIn('owner-absent',self.events);self.assertIn('backend-absent',self.events)

    def test_live_reservation_assigns_only_one_exact_owner(self):
        _,_,request=self.claim('migrate')
        with self.assertRaises(OwnershipRecordRefused):self.subject.admit(request,self.peer)
        self.assertEqual(self.events.count('release-exclusion'),1)

    def test_completed_handoff_keeps_controller_live_and_next_reservation_gets_a_fresh_deadline(self):
        before=controller.time.monotonic();record,result,_=self.claim('migrate')
        self.assertIsNone(self.subject.deadline)
        self.endpoint.endpoint=SimpleNamespace(accept=lambda timeout:None)
        with patch.object(controller.time,'monotonic',return_value=before+3600):
            self.subject._controller();self.assertIsNone(handoff_transport.serve_once(self.subject))
            self.assertEqual(self.subject.publish(record,self.peer),result)
            self.assertEqual(self.subject.state,'complete');self.assertIsNone(self.subject.deadline)
            self.stage='bootstrap';self.new_owner['pid']+=10
            self.subject.reserve('migrate')
            self.assertEqual(self.subject.deadline,before+3600+controller.RESERVATION_SECONDS)
            self.assertEqual(self.subject.state,'reserved')

    def request(self):
        return {'protocol':4,'kind':'native_ownership_handoff','action':'admit',
                **{name:self.authority[name] for name in ['installation','operation','candidate']},
                'mode':'migrate','owner_pid':self.new_owner['pid']}

    def retained_files(self):
        return {str(path.relative_to(self.storage)):(path.stat().st_ino,path.read_bytes())
                for path in self.storage.rglob('*') if path.is_file()}

    def test_refused_request_before_assignment_retries_only_under_original_live_exclusion(self):
        self.subject.reserve('migrate');exclusion=self.subject.exclusion
        before=self.retained_files()
        with self.assertRaises(OwnershipRecordRefused):
            self.subject.admit({**self.request(),'candidate':'0'*40},self.peer)
        self.assertEqual(self.subject.state,'reserved');self.assertIsNone(self.subject.assignment)
        self.assertIs(self.subject.exclusion,exclusion);self.assertFalse(exclusion.closed)
        self.assertEqual(self.retained_files(),before)
        result=self.subject.admit(self.request(),self.peer)
        self.assertEqual(result['claim'],self.subject.claim);self.assertTrue(exclusion.closed)
        self.assertEqual(self.events.count('release-exclusion'),1)

    def test_reopening_an_unassigned_reservation_does_not_turn_its_receipt_into_authority(self):
        self.subject.reserve('migrate');before=self.retained_files()
        self.subject.close();self.custody.check()
        reopened=controller.NativeOwnershipController(self.base['installation'],self.custody,self.endpoint)
        self.addCleanup(reopened.close)
        reopened.store=OwnershipTransitionStore(self.storage,self.base['installation'],self.identity)
        with self.assertRaises(OwnershipRecordRefused):reopened._prior()
        self.assertEqual(self.retained_files(),before)

    def test_failure_after_reservation_receipt_retains_bytes_and_refuses_automatic_reassignment(self):
        original=OwnershipTransitionStore.put
        def interrupted(store,role,name,value):
            original(store,role,name,value)
            if name.endswith('.reservation.json'):raise OSError('lost reservation acknowledgement')
        with patch.object(OwnershipTransitionStore,'put',new=interrupted):
            with self.assertRaises(OSError):self.subject.reserve('migrate')
        before=self.retained_files();self.assertEqual(len(before),1)
        self.assertTrue(next(iter(before)).endswith('.reservation.json'))
        self.assertFalse(self.subject.usable);self.assertIsNone(self.subject.exclusion)
        self.custody.check()
        with self.assertRaises(OwnershipRecordRefused):self.subject.reserve('migrate')
        self.assertEqual(self.retained_files(),before)

    def test_expired_unassigned_reservation_releases_only_its_exclusion_and_preserves_receipt(self):
        self.subject.reserve('migrate');before=self.retained_files();exclusion=self.subject.exclusion
        with patch.object(controller.time,'monotonic',return_value=self.subject.deadline):
            with self.assertRaises(OwnershipRecordRefused):handoff_transport.serve_once(self.subject)
        self.assertFalse(self.subject.usable);self.assertTrue(exclusion.closed)
        self.custody.check();self.assertEqual(self.retained_files(),before)

    def test_lost_admission_reply_retains_assignment_and_cannot_invent_missing_backend_identity(self):
        self.subject.reserve('migrate')
        class LostReply:
            def settimeout(self,value):pass
            def sendall(self,value):raise BrokenPipeError('admission response lost')
            def close(self):pass
        connection=LostReply();self.endpoint.endpoint=SimpleNamespace(accept=lambda timeout:connection)
        with patch.object(handoff_transport,'receive_frame',return_value=(canonical(self.request())+b'\n',self.peer)),\
             patch.object(handoff_transport,'_peer',return_value=self.peer):
            with self.assertRaises(BrokenPipeError):handoff_transport.serve_once(self.subject)
        self.assertEqual(self.subject.state,'assigned');self.assertIsNone(self.subject.exclusion)
        self.assertIsNone(self.subject.record)
        before=self.retained_files()
        self.assertEqual(len(before),2)
        self.new_owner['pid']+=10;self.new_owner['birth']=str(int(self.new_owner['birth'])+10)
        with patch.object(controller,'observe_prior_backend_identity_absence') as absence:
            with self.assertRaises(OwnershipRecordRefused):self.subject.admit(self.request(),self.peer)
            with self.assertRaises(OwnershipRecordRefused):self.subject.reserve('migrate')
            absence.assert_not_called()
        self.assertEqual(self.retained_files(),before)
        self.subject.close();self.custody.check()
        reopened=controller.NativeOwnershipController(self.base['installation'],self.custody,self.endpoint)
        self.addCleanup(reopened.close)
        reopened.store=OwnershipTransitionStore(self.storage,self.base['installation'],self.identity)
        with self.assertRaises(OwnershipRecordRefused):reopened._prior()
        self.assertEqual(self.retained_files(),before)

    def test_delayed_exclusion_backend_exit_rechecks_the_original_birth_without_reassignment(self):
        self.subject.reserve('migrate');deadline=self.subject.deadline
        kernel=copy.deepcopy(self.subject.exclusion_kernel)
        clock=[controller.time.monotonic()]
        def wait(seconds):clock[0]+=seconds
        with patch.object(controller.time,'monotonic',side_effect=lambda:clock[0]),\
             patch.object(controller.time,'sleep',side_effect=wait) as sleep,\
             patch.object(controller,'observe_prior_backend_identity_absence',
                side_effect=[controller.DatabaseRefused('still present'),controller.DatabaseRefused('still present'),absent_result()]) as absence:
            result=self.subject.admit(self.request(),self.peer)
        self.assertEqual(result['owner'],self.new_owner);self.assertEqual(self.subject.state,'assigned')
        self.assertEqual(sleep.call_count,2);self.assertEqual(absence.call_count,3)
        self.assertTrue(all(call.args[2]==kernel for call in absence.call_args_list))
        self.assertEqual(self.subject.deadline,deadline)
        self.assertEqual(self.events.count('release-exclusion'),1)
        self.assertEqual(len(self.retained_files()),2)

    def test_unknown_exclusion_backend_times_out_and_retains_first_assignment(self):
        self.subject.reserve('migrate');deadline=self.subject.deadline
        clock=[controller.time.monotonic()];started=clock[0]
        with patch.object(controller.time,'monotonic',side_effect=lambda:clock[0]),\
             patch.object(controller.time,'sleep',side_effect=lambda seconds:clock.__setitem__(0,clock[0]+seconds)),\
             patch.object(controller,'observe_prior_backend_identity_absence',side_effect=controller.DatabaseRefused('unknown')):
            with self.assertRaises(OwnershipRecordRefused):self.subject.admit(self.request(),self.peer)
        self.assertLessEqual(clock[0]-started,controller.EXCLUSION_EXIT_SECONDS+0.001)
        self.assertEqual(self.subject.state,'assigning');self.assertEqual(self.subject.deadline,deadline)
        self.assertIsNone(self.subject.exclusion);before=self.retained_files()
        self.assertEqual(len(before),2);self.assertEqual(self.subject.assignment['owner'],self.new_owner)
        with self.assertRaises(OwnershipRecordRefused):self.subject.admit(self.request(),self.peer)
        with self.assertRaises(OwnershipRecordRefused):self.subject.reserve('migrate')
        self.assertEqual(self.retained_files(),before);self.custody.check()
        self.assertEqual(self.events.count('release-exclusion'),1)

    def test_exclusion_exit_wait_cannot_extend_the_original_reservation_deadline(self):
        self.subject.reserve('migrate');clock=[controller.time.monotonic()]
        self.subject.deadline=clock[0]+0.08;deadline=self.subject.deadline
        with patch.object(controller.time,'monotonic',side_effect=lambda:clock[0]),\
             patch.object(controller.time,'sleep',side_effect=lambda seconds:clock.__setitem__(0,clock[0]+seconds)),\
             patch.object(controller,'observe_prior_backend_identity_absence',side_effect=controller.DatabaseRefused('still present')):
            with self.assertRaises(OwnershipRecordRefused):self.subject.admit(self.request(),self.peer)
        self.assertEqual(clock[0],deadline);self.assertEqual(self.subject.deadline,deadline)
        self.assertEqual(self.subject.state,'assigning');self.assertEqual(len(self.retained_files()),2)

    def test_exclusion_exit_wait_refuses_changed_assigned_owner_before_retry(self):
        self.subject.reserve('migrate');original=copy.deepcopy(self.new_owner)
        def wait(seconds):self.new_owner['birth']=str(int(self.new_owner['birth'])+1)
        with patch.object(controller.time,'sleep',side_effect=wait),\
             patch.object(controller,'observe_prior_backend_identity_absence',side_effect=controller.DatabaseRefused('still present')) as absence:
            with self.assertRaises(OwnershipRecordRefused):self.subject.admit(self.request(),self.peer)
        self.assertEqual(absence.call_count,1);self.assertEqual(self.subject.assignment['owner'],original)
        self.assertEqual(self.subject.state,'assigning');self.assertEqual(len(self.retained_files()),2)

    def test_exclusion_exit_wait_refuses_changed_generation_before_retry(self):
        self.subject.reserve('migrate');original=self.subject.reader._snapshot
        def wait(seconds):self.subject.reader._snapshot=lambda scope:{**original(scope),'pointer':{}}
        with patch.object(controller.time,'sleep',side_effect=wait),\
             patch.object(controller,'observe_prior_backend_identity_absence',side_effect=controller.DatabaseRefused('still present')) as absence:
            with self.assertRaises(OwnershipRecordRefused):self.subject.admit(self.request(),self.peer)
        self.assertEqual(absence.call_count,1);self.assertEqual(self.subject.state,'assigning')
        self.assertEqual(len(self.retained_files()),2)

    def assert_exclusion_absence_refuses(self, missing):
        self.subject.reserve('migrate')
        with patch.object(controller,'observe_prior_backend_identity_absence',return_value={**absent_result(),missing:False}),\
             patch.object(controller.time,'sleep') as sleep:
            with self.assertRaises(OwnershipRecordRefused):self.subject.admit(self.request(),self.peer)
        self.assertEqual(self.subject.state,'assigning');sleep.assert_not_called()

    def test_exclusion_exit_wait_needs_positive_sql_absence(self):
        self.assert_exclusion_absence_refuses('original_backend_absent')

    def test_exclusion_exit_wait_needs_positive_kernel_absence(self):
        self.assert_exclusion_absence_refuses('kernel_backend_absence_observed')

    def test_exclusion_absence_result_after_wait_deadline_refuses(self):
        self.subject.reserve('migrate');clock=[controller.time.monotonic()]
        def late(*args):clock[0]+=controller.EXCLUSION_EXIT_SECONDS;return absent_result()
        with patch.object(controller.time,'monotonic',side_effect=lambda:clock[0]),\
             patch.object(controller,'observe_prior_backend_identity_absence',side_effect=late):
            with self.assertRaises(OwnershipRecordRefused):self.subject.admit(self.request(),self.peer)
        self.assertEqual(self.subject.state,'assigning');self.assertEqual(len(self.retained_files()),2)

    def test_exclusion_exit_wait_does_not_retry_unclassified_errors(self):
        self.subject.reserve('migrate')
        with patch.object(controller,'observe_prior_backend_identity_absence',side_effect=ValueError('invalid observer')) as absence,\
             patch.object(controller.time,'sleep') as sleep:
            with self.assertRaises(ValueError):self.subject.admit(self.request(),self.peer)
        self.assertEqual(absence.call_count,1);sleep.assert_not_called()
        self.assertEqual(self.subject.state,'assigning');self.assertEqual(len(self.retained_files()),2)

    def test_full_record_inventory_refuses_before_new_reservation_or_exclusion(self):
        store=OwnershipTransitionStore(self.storage,self.base['installation'],self.identity)
        store.close()
        for _ in range(128):
            record=next_record(self.base,uid=os.getuid())
            path=self.storage/'.gitgood-ownership-v2'/(record['claim']+'.json')
            path.write_bytes(canonical(record));path.chmod(0o600)
        before=self.retained_files()
        with self.assertRaises(OwnershipRecordRefused):self.subject.reserve('migrate')
        self.assertNotIn('exclude',self.events)
        self.assertEqual(self.retained_files(),before)

    def test_original_backend_absence_is_rechecked_after_exclusion_release(self):
        self.claim('migrate');self.new_owner['pid']+=10
        self.stage='bootstrap';self.subject.reserve('migrate')
        request={'protocol':4,'kind':'native_ownership_handoff','action':'admit',
                 **{name:self.authority[name] for name in ['installation','operation','candidate']},
                 'mode':'migrate','owner_pid':self.new_owner['pid']}
        self.subject.admit(request,self.peer)
        self.assertEqual(self.subject.state,'assigned')
        before={str(path):path.read_bytes() for path in self.storage.rglob('*') if path.is_file()}
        with patch.object(controller,'observe_prior_backend_identity_absence',side_effect=ValueError('old backend unknown')):
            with self.assertRaises(ValueError):self.subject._absent()
        self.assertEqual({str(path):path.read_bytes() for path in self.storage.rglob('*') if path.is_file()},before)

    def test_reopened_retained_history_refuses_replaced_same_byte_old_marker(self):
        self.claim('migrate');self.new_owner['pid']+=10;self.stage='bootstrap'
        record,_,_=self.claim('migrate')
        self.subject._dispose_views()
        archive=self.storage/'.gitgood-successors-v4'/(record['claim']+'.old-marker.json')
        replacement=self.storage/'replacement';replacement.write_bytes(archive.read_bytes());replacement.chmod(0o600);replacement.replace(archive)
        self.subject.store=OwnershipTransitionStore(self.storage,self.base['installation'],self.identity)
        with self.assertRaises(OwnershipRecordRefused):self.subject._prior()
        self.assertEqual(archive.read_bytes(),canonical(self.subject.store._marker(self.subject.previous)))

    def test_lifecycle_reader_refusal_never_releases_borrowed_original_flock(self):
        reader=object.__new__(NativeLifecycleGenerationReader)
        reader.installation=self.custody.installation;reader.directory=self.custody.directory
        reader.custody=_ReadOnlyCustody(self.custody.directory,self.custody.installation,self.custody.identity,self.custody.expected_lock_identity)
        reader._owns_custody=True;reader.lifecycle_view=None
        reader.inputs=SimpleNamespace(check=lambda:(_ for _ in ()).throw(ValueError('changed inputs')),close=lambda:None)
        reader.borrow_custody(self.custody)
        with self.assertRaises(Exception):reader._layout()
        self.custody.check()
        contender=GenerationRecordCustody(self.custody.directory,self.custody.installation,self.custody.identity,self.custody.expected_lock_identity)
        with self.assertRaises(CustodyRefused):contender.__enter__()
        self.custody.check()
