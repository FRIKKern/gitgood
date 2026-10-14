import copy
import hashlib
import os
from pathlib import Path
import stat
import sys
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch

import native_root_artifact_policy as root
from native_protected_artifact import parse_policy
from resource_generations import canonical
from test_native_protected_artifact import INSTALLATION, OPERATION, policy
import test_inspect_native_artifact as artifact_fixture
from upgrade_journal import fcntl


class ArtifactDeclarationTest(unittest.TestCase):
    observed={'installation':INSTALLATION,'operation':OPERATION,'candidate':'a'*40}

    def declaration(self):
        return {'protocol':2,'kind':'native_artifact_declaration',**self.observed,'sha256':'b'*64,'bytes':1024}

    def test_closed_original_declaration_is_copied_without_paths_or_programs(self):
        value=self.declaration();result=root._declaration(value,self.observed)
        self.assertEqual(result,value);self.assertIsNot(result,value)

    def test_caller_paths_authority_boolean_protocol_and_unbounded_bytes_refuse(self):
        for name,item in (('path','/caller'),('authority',True),('protocol',True),('bytes',True),('bytes',0),('bytes',root.MAX_ARCHIVE+1)):
            with self.assertRaises(root.RootArtifactPolicyRefused):root._declaration(dict(self.declaration(),**{name:item}),self.observed)

    def test_foreign_operation_candidate_or_invalid_digest_refuses(self):
        for name,item in (('operation',INSTALLATION),('candidate','c'*40),('sha256','bad')):
            with self.assertRaises(Exception):root._declaration(dict(self.declaration(),**{name:item}),self.observed)

    def test_inspection_receipt_records_actual_result_without_granting_authority(self):
        value={'status':'inspected','candidate':'a'*40,'artifact_sha256':'b'*64}
        receipt=root._inspection_receipt(INSTALLATION,OPERATION,value)
        self.assertEqual(receipt['kind'],'native_artifact_inspection')
        value['candidate']='c'*40;self.assertEqual(receipt['inspection']['candidate'],'a'*40)
        with self.assertRaises(root.RootArtifactPolicyRefused):root._inspection_receipt(INSTALLATION,OPERATION,{'status':'planned'})


class PolicyAllocationAdmissionTest(unittest.TestCase):
    def test_non_root_or_caller_map_refuses_before_any_file_open(self):
        with patch.object(root.os,'getuid',return_value=1000,create=True),patch.object(root.os,'open') as opened:
            with self.assertRaises(root.RootArtifactPolicyRefused):root.NativeRootArtifactPolicyAllocation({'authority':True})
            opened.assert_not_called()

    def test_wrong_running_stage_refuses_and_closes_owned_exclusion_before_files(self):
        class Guard:
            def __init__(self):self.closed=False
            def check(self):return {'stage':'migrate','recorded_status':'running'}
            def close(self):self.closed=True
        value=Guard()
        with ExitStack() as stack:
            for name in ('getuid','geteuid','getgid','getegid'):stack.enter_context(patch.object(root.os,name,return_value=0,create=True))
            stack.enter_context(patch.object(root,'fcntl',Mock()))
            stack.enter_context(patch.object(root,'NativeRootDatabaseExclusionObservation',Guard))
            opened=stack.enter_context(patch.object(root.os,'open'))
            with self.assertRaises(root.RootArtifactPolicyRefused):root.NativeRootArtifactPolicyAllocation(value)
            self.assertTrue(value.closed);opened.assert_not_called()


@unittest.skipUnless(sys.platform=='linux' and os.getuid()==0 and fcntl is not None,'Actual isolated Root policy filesystem')
class RootPolicyFilesystemTest(unittest.TestCase):
    def setUp(self):
        self.fixture=artifact_fixture.ArtifactInspectionTest();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.digest=self.fixture.archive();self.base=Path(self.fixture.scratch.name)/'namespace'
        self.base.mkdir(mode=0o755)
        self.policy_dir=self.base/'etc/gitgood/installations'/INSTALLATION/'artifacts'
        self.source_dir=self.base/'var/lib/gitgood/artifact-inputs'/INSTALLATION/OPERATION
        self.destination=self.base/'opt/gitgood/artifacts'/INSTALLATION
        for directory in (self.policy_dir,self.source_dir,self.destination):directory.mkdir(parents=True,mode=0o755)
        self.archive=self.source_dir/'archive.tar.gz';self.archive.write_bytes(self.fixture.path.read_bytes());self.archive.chmod(0o444)
        self.lock=self.policy_dir/'allocation-lock-v1';self.lock.touch(mode=0o600)
        declared={'protocol':2,'kind':'native_artifact_declaration','installation':INSTALLATION,'operation':OPERATION,
            'candidate':self.fixture.candidate,'sha256':self.digest,'bytes':self.archive.stat().st_size}
        inspected=root.inspect_native_artifact(self.archive,self.digest,self.fixture.candidate)
        evidence=root._inspection_receipt(INSTALLATION,OPERATION,inspected)
        self.record={'completed':['inspect'],'events':[{'stage':'inspect','kind':'succeeded',
            'evidence':{'receipt_sha256':hashlib.sha256(canonical(evidence)).hexdigest()}}]}
        template=policy()
        custody=SimpleNamespace(directory=self.base/'history',_identity=lambda _:{'device':1,'inode':2,'uid':1000})
        lifecycle=SimpleNamespace(original={'lifecycle':self.record},worker={'purpose':'native_initial_enrollment'},
            inputs=Mock(),history=SimpleNamespace(custody=custody),request=template['request'])
        lifecycle.inputs.check.return_value={'inputs.json':canonical({'protocol':2,'artifact':declared})}
        live=SimpleNamespace(lifecycle=lifecycle,binding={'resources':{'root':{'device':1,'inode':3,'uid':1000}}})
        self.observed={'installation':INSTALLATION,'operation':OPERATION,'candidate':self.fixture.candidate,
            'stage':'stage','recorded_status':'running','database_writer_exclusion_verified':True,
            'request_sha256':hashlib.sha256(canonical(template['request'])).hexdigest(),'snapshot_sha256':'e'*64}
        class Guard:
            def __init__(inner):inner.closed=False;inner.live=live;inner.scope={'uid':1000,'gid':1000}
            def check(inner):
                if inner.closed:raise RuntimeError('Closed stand-in')
                return copy.deepcopy(self.observed)
            def close(inner):inner.closed=True
        self.Guard=Guard
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        original_path=Path
        def mapped(path):
            value=original_path(path)
            for prefix in ('/etc','/var','/opt'):
                if value==original_path(prefix) or value.is_relative_to(prefix):return self.base/value.relative_to('/')
            return value
        original_directory=root._root_directory
        def directory(path):
            # Explicit scratch-ancestor exemption; actual Root-owned files,
            # directory descriptors, flock and rename syscalls remain real.
            value=original_path(path)
            if value in self.base.parents:
                info=value.stat();return (info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode)
            return original_directory(path)
        self.stack.enter_context(patch.object(root,'Path',side_effect=mapped))
        self.stack.enter_context(patch.object(root,'_root_directory',side_effect=directory))
        self.stack.enter_context(patch.object(root,'NativeRootDatabaseExclusionObservation',Guard))
        self.stack.enter_context(patch.object(root.os,'fstatvfs',return_value=SimpleNamespace(f_bavail=64*1024**3,f_frsize=1)))

    def view(self):
        guard=self.Guard();value=root.NativeRootArtifactPolicyAllocation(guard);self.addCleanup(value.close)
        return value

    def test_actual_root_policy_publication_is_read_only_and_matches_original_inspection(self):
        value=self.view();receipt=value.allocate();target=self.policy_dir/(OPERATION+'.json')
        self.assertTrue(receipt['policy_allocated']);self.assertFalse(receipt['stage_effect_authorized'])
        self.assertEqual(stat.S_IMODE(target.stat().st_mode),0o400);self.assertEqual(target.stat().st_uid,0)
        declared=parse_policy(target.read_bytes(),INSTALLATION,OPERATION)
        self.assertEqual(declared['archive']['sha256'],self.digest);self.assertTrue(value.check()['policy_allocated'])

    def test_actual_competing_root_allocation_is_refused_without_replacing_lock(self):
        value=self.view();inode=self.lock.stat().st_ino
        with self.assertRaises(root.RootArtifactPolicyRefused):root.NativeRootArtifactPolicyAllocation(self.Guard())
        self.assertEqual(self.lock.stat().st_ino,inode);self.assertTrue(value.check()['original_exclusion_and_root_allocation_lock_observed'])

    def test_actual_unlock_permanently_refuses_and_retains_input_and_lock(self):
        value=self.view();fcntl.flock(value.lock,fcntl.LOCK_UN)
        with self.assertRaises(root.RootArtifactPolicyRefused):value.check()
        self.assertFalse(value.usable);self.assertTrue(self.archive.exists());self.assertTrue(self.lock.exists())

    def test_foreign_existing_target_refuses_without_creating_policy_partial(self):
        value=self.view();target=self.policy_dir/(OPERATION+'.json');target.write_bytes(b'foreign');target.chmod(0o400)
        with self.assertRaises(root.RootArtifactPolicyRefused):value.allocate()
        self.assertEqual(target.read_bytes(),b'foreign');self.assertFalse(list(self.policy_dir.glob('*.partial')))

    def test_wrong_recorded_inspection_receipt_refuses_before_policy_write(self):
        self.record['events'][0]['evidence']['receipt_sha256']='f'*64
        value=self.view()
        with self.assertRaises(root.RootArtifactPolicyRefused):value.allocate()
        self.assertFalse((self.policy_dir/(OPERATION+'.json')).exists());self.assertTrue(self.archive.exists())


if __name__=='__main__':unittest.main()
