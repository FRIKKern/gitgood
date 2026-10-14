import copy
import hashlib
import os
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

import native_artifact_controller as controller
from native_generation_reader import NativeGenerationReader
from native_lifecycle_generation_reader import STAGE_WORKERS
from resource_generations import canonical
import test_inspect_native_artifact as artifact_fixture


class ArtifactControllerReaderTest(unittest.TestCase):
    def fixture(self):
        value=controller._ArtifactControllerReader.__new__(controller._ArtifactControllerReader)
        value.expected='b'*64
        request={'operation':'fixed-op','durable_binding_sha256':value.expected}
        inputs={'request':request,'candidate':'a'*40,'inputs_seal_sha256':'c'*64,'request_sha256':'d'*64}
        value.inputs=Mock();value.inputs.check.return_value=inputs;value.inputs.seal={'uid':1000,'gid':1000}
        value.scope={'uid':1000,'gid':1000}
        record={'origin':{'request':copy.deepcopy(request),'inputs_seal_sha256':'c'*64,'request_sha256':'d'*64},
            'generation_sha256':'e'*64,'status':'running','stage':'inspect','completed':[]}
        view=Mock();view.snapshot.return_value=record;view.heads={'fixed-op':'original'}
        value._view=Mock(return_value=view);value._fingerprint=Mock(return_value={'original':'files'});value._check=Mock()
        base={'pointer':{'generation_sha256':'e'*64},'files':{'original':'files'}}
        return value,record,base

    def test_only_original_controller_inspect_pending_and_running_stage_windows_are_admitted(self):
        for status,stage,completed in (('running','inspect',[]),('pending','inspect',['inspect']),('running','stage',['inspect'])):
            value,record,base=self.fixture();record.update(status=status,stage=stage,completed=completed)
            with patch.object(NativeGenerationReader,'_snapshot',return_value=base):
                result=value._snapshot(value.scope)
            self.assertEqual(result['lifecycle'],record);self.assertIsNot(result['lifecycle'],record)

    def test_uncertain_complete_worker_or_wrong_completed_window_refuses(self):
        for status,stage,completed in (('uncertain','inspect',[]),('complete','stage',['inspect']),
                                     ('running','migrate',['inspect','stage']),('running','stage',[])):
            value,record,base=self.fixture();record.update(status=status,stage=stage,completed=completed)
            with patch.object(NativeGenerationReader,'_snapshot',return_value=base),self.assertRaises(controller.ArtifactControllerRefused):
                value._snapshot(value.scope)

    def test_changed_original_request_digest_generation_or_file_fingerprint_refuses(self):
        for changed in ('request','inputs','generation','files'):
            value,record,base=self.fixture()
            if changed=='request':record['origin']['request_sha256']='f'*64
            elif changed=='inputs':record['origin']['inputs_seal_sha256']='f'*64
            elif changed=='generation':record['generation_sha256']='f'*64
            else:value._fingerprint.return_value={'changed':'files'}
            with patch.object(NativeGenerationReader,'_snapshot',return_value=base),self.assertRaises(controller.ArtifactControllerRefused):
                value._snapshot(value.scope)

    def test_controller_reader_supplies_no_worker_admission_or_widened_worker_stages(self):
        value,_,_=self.fixture()
        with self.assertRaises(controller.ArtifactControllerRefused):value.admit(worker='maintenance',owner_pid=123)
        for purpose,workers in STAGE_WORKERS.items():
            for allowed in workers.values():self.assertFalse({'inspect','stage'} & set(allowed),purpose)


class ControllerAdmissionTest(unittest.TestCase):
    def test_root_refuses_before_borrowing_history_endpoint_or_journal(self):
        installation='00000000-0000-4000-8000-000000000001'
        with patch.object(controller.os,'getuid',return_value=0,create=True),patch.object(controller.os,'open') as opened:
            with self.assertRaises(controller.ArtifactControllerRefused):controller.NativeArtifactInspectionController(installation,None,None,None)
            opened.assert_not_called()

    def test_caller_maps_refuse_before_opening_generation_or_archive(self):
        installation='00000000-0000-4000-8000-000000000001'
        with ExitStack() as stack:
            for name in ('getuid','geteuid','getgid','getegid'):stack.enter_context(patch.object(controller.os,name,return_value=1000,create=True))
            opened=stack.enter_context(patch.object(controller.os,'open'))
            with self.assertRaises(controller.ArtifactControllerRefused):controller.NativeArtifactInspectionController(installation,{}, {}, {})
            opened.assert_not_called()


class OwnedJournalRefreshTest(unittest.TestCase):
    def fixture(self):
        operation='fixed-op';before={'events':[{'kind':'claimed'}],'predecessor_sha256':None}
        after={'events':[{'kind':'claimed'},{'kind':'succeeded'}],
            'predecessor_sha256':hashlib.sha256(canonical(before)).hexdigest()}
        sha=hashlib.sha256(canonical(after)).hexdigest()
        base={name:{'original':name} for name in ('binding','pointer','record','records','transitions','receipts')}
        old={**base,'lifecycle':before,'files':{'generation':'original','@lifecycle_inputs':'original',
            '@lifecycle':{'directories':{'records':(1,2,1000,1000,448,1,1)},
                'files':{'heads/'+operation+'.json':('original-head',),'records/original.json':('original-record',)}}}}
        new=copy.deepcopy(old);new['lifecycle']=after
        new['files']['@lifecycle']['directories']['records']=(1,2,1000,1000,448,2,2)
        new['files']['@lifecycle']['files']['heads/'+operation+'.json']=('owned-new-head',)
        new['files']['@lifecycle']['files']['records/'+sha+'.json']=('owned-new-record',)
        journal=Mock();journal.snapshot=copy.deepcopy(after);journal.operation=operation;journal.head={'snapshot_sha256':sha}
        return old,new,journal

    def test_only_owned_append_and_head_publication_refresh_original_snapshot(self):
        old,new,journal=self.fixture();self.assertIsNone(controller._owned_journal_refresh(old,new,journal))

    def test_changed_generation_input_old_record_or_directory_inode_cannot_be_adopted(self):
        for changed in ('generation','input','old-record','directory'):
            old,new,journal=self.fixture()
            if changed=='generation':new['pointer']={'foreign':'generation'}
            elif changed=='input':new['files']['@lifecycle_inputs']='changed'
            elif changed=='old-record':new['files']['@lifecycle']['files']['records/original.json']=('changed-inode',)
            else:new['files']['@lifecycle']['directories']['records']=(1,3,1000,1000,448,2,2)
            with self.assertRaises(controller.ArtifactControllerRefused):controller._owned_journal_refresh(old,new,journal)

class InspectionTransitionTest(unittest.TestCase):
    def fixture(self):
        artifact=artifact_fixture.ArtifactInspectionTest();artifact.setUp();self.addCleanup(artifact.doCleanups)
        sha=artifact.archive()
        value=controller.NativeArtifactInspectionController.__new__(controller.NativeArtifactInspectionController)
        value.usable=True;value.installation='00000000-0000-4000-8000-000000000001'
        value.operation='00000000-0000-4000-8000-000000000002';value.state='inspect';value.source=artifact.path
        value.archive=os.open(artifact.path,os.O_RDONLY);self.addCleanup(value.close)
        value.reader=Mock();value.exclusion=Mock();value.journal=Mock();value.custody=Mock();value.custody.lock=12
        value.inputs={'candidate':artifact.candidate};value.declaration={'sha256':sha,'bytes':artifact.path.stat().st_size}
        value.check=Mock(return_value={'original':'checked'});value._open_reader=Mock()
        return value

    def test_actual_archive_inspection_is_recorded_before_explicit_stage_request(self):
        value=self.fixture();receipt=value.inspect()
        self.assertEqual(receipt['inspection']['status'],'inspected');self.assertEqual(value.state,'inspected')
        value.journal.succeed.assert_called_once_with('inspect',hashlib.sha256(canonical(receipt)).hexdigest())
        self.assertEqual(value._open_reader.call_count,1)
        frame=value.begin_stage()
        value.journal.begin.assert_called_once_with('stage');self.assertEqual(value.state,'stage')
        self.assertEqual(frame,canonical({'protocol':2,'kind':'native_root_controller_request',
            'installation':value.installation,'operation':value.operation,'history_lock_fd':12})+b'\n')

    def test_bad_archive_digest_cannot_advance_durable_inspection(self):
        value=self.fixture();value.declaration['sha256']='f'*64
        with self.assertRaises(controller.ArtifactControllerRefused):value.inspect()
        value.journal.succeed.assert_not_called();self.assertFalse(value.usable)
        value.exclusion.close.assert_called()

    def test_stage_request_before_inspection_refuses_without_advancing_journal(self):
        value=self.fixture()
        with self.assertRaises(controller.ArtifactControllerRefused):value.begin_stage()
        value.journal.begin.assert_not_called();self.assertFalse(value.usable)

    def test_lost_original_guard_refuses_before_inspection_or_durable_transition(self):
        value=self.fixture();value.check.side_effect=controller.ArtifactControllerRefused()
        with patch.object(controller,'inspect_native_artifact') as inspect,self.assertRaises(controller.ArtifactControllerRefused):value.inspect()
        inspect.assert_not_called();value.journal.succeed.assert_not_called()


if __name__=='__main__':unittest.main()
