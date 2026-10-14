import copy
import hashlib
import os
import socket
import threading
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

import native_root_artifact_dispatch as dispatch
from resource_generations import canonical


class DispatchBoundaryTest(unittest.TestCase):
    def root(self,stack):
        for name in ('getuid','geteuid','getgid','getegid'):
            stack.enter_context(patch.object(dispatch.os,name,return_value=0,create=True))

    def fixture(self):
        value=dispatch.NativeRootArtifactStageDispatch.__new__(dispatch.NativeRootArtifactStageDispatch)
        value.usable=True;value.state='ready';value.owner=(os.getpid(),threading.get_ident())
        value.request=Mock();value.allocation=Mock();value.stage_view=Mock()
        value.original={'original':'exclusion-and-allocation-lock'}
        value.allocation.check.return_value=copy.deepcopy(value.original)
        value.allocated={'installation':'original-inst','operation':'original-op','candidate':'a'*40}
        value.stage_view.check.side_effect=lambda:{'artifact_staged':value.stage_view.state=='staged'}
        value.stage_view.state='ready'
        receipt={**value.allocated,'root_controlled_code':True,'status':'staged','complete_journey_acceptance':False}
        def stage():value.stage_view.state='staged';return copy.deepcopy(receipt)
        value.stage_view.stage.side_effect=stage
        return value,receipt

    def test_ordinary_account_refuses_before_observing_request(self):
        request=Mock()
        with patch.object(dispatch.os,'getuid',return_value=1000,create=True),self.assertRaises(dispatch.RootArtifactDispatchRefused):
            dispatch.NativeRootArtifactStageDispatch(request)
        request.check.assert_not_called();request.close.assert_not_called()

    def test_caller_authority_map_refuses_before_database_observation(self):
        with ExitStack() as stack:
            self.root(stack);database=stack.enter_context(patch.object(dispatch,'NativeRootDatabaseExclusionObservation'))
            with self.assertRaises(dispatch.RootArtifactDispatchRefused):dispatch.NativeRootArtifactStageDispatch({'authorized':True})
            database.assert_not_called()

    def test_original_guard_loss_refuses_before_extraction_and_closes_only_owned_views(self):
        value,_=self.fixture();value.allocation.check.side_effect=ValueError('lost original')
        with ExitStack() as stack:
            self.root(stack)
            with self.assertRaises(dispatch.RootArtifactDispatchRefused):value.stage()
        value.stage_view.stage.assert_not_called();value.stage_view.close.assert_called();value.allocation.close.assert_called()
        self.assertFalse(value.usable)

    def test_success_brackets_actual_stage_then_repeated_stage_refuses(self):
        value,receipt=self.fixture()
        with ExitStack() as stack:
            self.root(stack);self.assertEqual(value.stage(),receipt);self.assertTrue(value.check()['artifact_staged'])
            with self.assertRaises(dispatch.RootArtifactDispatchRefused):value.stage()
        self.assertEqual(value.stage_view.stage.call_count,1);self.assertFalse(value.usable)

    def test_foreign_receipt_or_acceptance_claim_cannot_be_returned_as_success(self):
        for field in ('operation','candidate','root_controlled_code','complete_journey_acceptance'):
            value,receipt=self.fixture();receipt[field]='foreign' if field in {'operation','candidate'} else field=='complete_journey_acceptance'
            value.stage_view.stage.side_effect=None;value.stage_view.stage.return_value=receipt
            with ExitStack() as stack:
                self.root(stack)
                with self.assertRaises(dispatch.RootArtifactDispatchRefused):value.stage()
            self.assertFalse(value.usable);value.allocation.close.assert_called()

    def test_private_effect_checks_refuse_loss_before_or_after_existing_stage_check(self):
        for loss in ('before','after'):
            value=dispatch._ObservedArtifactStage.__new__(dispatch._ObservedArtifactStage)
            value.allocation=Mock();value.allocation_original={'original':True};value.close=Mock()
            value.allocation.check.side_effect=[ValueError('lost')] if loss=='before' else [{'original':True},ValueError('lost')]
            with patch.object(dispatch.NativeProtectedArtifactStage,'check',return_value={'artifact_staged':False}) as checked:
                with self.assertRaises(dispatch.RootArtifactDispatchRefused):value.check()
                self.assertEqual(checked.call_count,0 if loss=='before' else 1)
            value.close.assert_called_once();value.allocation.close.assert_called_once()


class ConnectedResponseTest(unittest.TestCase):
    def test_real_socket_response_is_bounded_and_only_sent_after_root_observers_close(self):
        server,client=socket.socketpair();self.addCleanup(server.close);self.addCleanup(client.close);client.settimeout(2)
        request=Mock();request.close.side_effect=server.close
        stage=Mock();receipt={'installation':'i','operation':'o','candidate':'a'*40,'status':'staged'}
        stage.stage.return_value=receipt
        def close():request.close()
        stage.close.side_effect=close
        with patch.object(dispatch,'NativeRootControllerRequest',return_value=request),patch.object(dispatch,'NativeRootArtifactStageDispatch',return_value=stage):
            result=dispatch.serve_artifact_stage('i','o',server)
        self.assertEqual(server.fileno(),-1);stage.close.assert_called_once()
        raw=client.recv(513);self.assertEqual(raw,canonical(result)+b'\n');self.assertLessEqual(len(raw),512)
        self.assertEqual(result['receipt_sha256'],hashlib.sha256(canonical(receipt)).hexdigest())

    def test_root_failure_returns_no_exception_details_or_caller_authority(self):
        server,client=socket.socketpair();self.addCleanup(server.close);self.addCleanup(client.close);client.settimeout(2)
        with patch.object(dispatch,'NativeRootControllerRequest',side_effect=ValueError('private-secret')):
            result=dispatch.serve_artifact_stage('i','o',server)
        raw=client.recv(513)
        self.assertEqual(result,{'protocol':2,'kind':'native_root_artifact_result','status':'refused'})
        self.assertEqual(raw,canonical(result)+b'\n');self.assertNotIn(b'private-secret',raw)


if __name__=='__main__':unittest.main()
