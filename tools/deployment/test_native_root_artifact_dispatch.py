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
from native_root_controller import _within_root_observation_pass,RootControllerRefused


class _DependencyObservation:
    """Explicit dependency stand-in; no controller or stage authority."""
    def __init__(self):
        self.usable=True;self.owner=(os.getpid(),threading.get_ident());self.calls=0

    @_within_root_observation_pass
    def check(self):
        self.calls+=1
        if not self.usable:raise RootControllerRefused('Fixture dependency lost')
        return {'observed':True,'stage_effect_authorized':False}


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
            with ExitStack() as stack:
                self.root(stack)
                checked=stack.enter_context(patch.object(dispatch.NativeProtectedArtifactStage,'check',return_value={'artifact_staged':False}))
                with self.assertRaises(dispatch.RootArtifactDispatchRefused):value.check()
                self.assertEqual(checked.call_count,0 if loss=='before' else 1)
            value.close.assert_called_once();value.allocation.close.assert_called_once()

    def test_each_effect_boundary_uses_new_initial_and_final_dependency_observations(self):
        value=dispatch._ObservedArtifactStage.__new__(dispatch._ObservedArtifactStage)
        dependency=_DependencyObservation();value.allocation=Mock();value.allocation_original={'original':True}
        value.allocation.check.side_effect=lambda:(dependency.check(),dict(value.allocation_original))[1]
        with ExitStack() as stack:
            self.root(stack)
            checked=stack.enter_context(patch.object(dispatch.NativeProtectedArtifactStage,'check',
                side_effect=lambda:(dependency.check(),{'artifact_staged':False})[1]))
            self.assertEqual(value.check(),{'artifact_staged':False});self.assertEqual(dependency.calls,2)
            self.assertEqual(value.check(),{'artifact_staged':False});self.assertEqual(dependency.calls,4)
        self.assertEqual(checked.call_count,2)

    def test_dependency_loss_during_read_only_stage_check_refuses_before_returning_a_write_guard(self):
        value=dispatch._ObservedArtifactStage.__new__(dispatch._ObservedArtifactStage)
        dependency=_DependencyObservation();value.allocation=Mock();value.allocation_original={'original':True};value.close=Mock()
        value.allocation.check.side_effect=lambda:(dependency.check(),dict(value.allocation_original))[1]
        def lost_after_observation():
            dependency.check();dependency.usable=False
            return {'artifact_staged':False}
        with ExitStack() as stack:
            self.root(stack)
            stack.enter_context(patch.object(dispatch.NativeProtectedArtifactStage,'check',side_effect=lost_after_observation))
            with self.assertRaises(dispatch.RootArtifactDispatchRefused):value.check()
        self.assertEqual(dependency.calls,2);value.close.assert_called_once();value.allocation.close.assert_called_once()


class ConnectedResponseTest(unittest.TestCase):
    def test_reply_loss_preserves_original_refusal_cause_and_closes_descriptors(self):
        server,client=socket.socketpair();self.addCleanup(server.close);self.addCleanup(client.close)
        original=TimeoutError('private SQL and credentials')
        request=Mock();request.close.side_effect=server.close
        stage=Mock();stage.stage.side_effect=original;stage.close.side_effect=request.close
        with patch.object(dispatch,'NativeRootControllerRequest',return_value=request),patch.object(dispatch,'NativeRootArtifactStageDispatch',return_value=stage), \
                patch.object(socket.socket,'sendall',side_effect=BrokenPipeError('transport closed')):
            with self.assertRaises(dispatch.RootArtifactDispatchRefused) as raised:
                dispatch.serve_artifact_stage('i','o',server)
        self.assertIs(raised.exception.__cause__,original)
        self.assertNotIn('private',str(raised.exception));self.assertEqual(server.fileno(),-1)
        stage.close.assert_called_once()

    def test_failure_observation_is_closed_bounded_and_excludes_private_frames(self):
        namespace={'private':'private credentials and SQL'}
        exec(compile('def stage():\n    raise TimeoutError(private)\n',dispatch.__file__,'exec'),namespace)
        try:namespace['stage']()
        except TimeoutError as error:
            wrapped=dispatch.RootArtifactDispatchRefused('private wrapper');wrapped.__context__=error
            error.__context__=wrapped
            observed=dispatch.failure_observation(wrapped)
        self.assertEqual(len(observed),2)
        self.assertEqual(observed[1],{'error_type':'TimeoutError','check_site':{
            'file':'native_root_artifact_dispatch.py','function':'stage','line':2}})
        self.assertNotIn(b'private',canonical(observed));self.assertNotIn(os.fsencode(dispatch.__file__),canonical(observed))
        chain=ValueError('private')
        for _ in range(30):
            outer=ValueError('private');outer.__context__=chain;chain=outer
        self.assertEqual(len(dispatch.failure_observation(chain)),16)

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

    def test_root_failure_wire_is_minimal_and_local_location_excludes_secrets(self):
        server,client=socket.socketpair();self.addCleanup(server.close);self.addCleanup(client.close);client.settimeout(2)
        with patch.object(dispatch,'NativeRootControllerRequest',side_effect=ValueError('private-secret')):
            result=dispatch.serve_artifact_stage('i','o',server)
        raw=client.recv(513)
        expected={'protocol':2,'kind':'native_root_artifact_result','status':'refused'}
        self.assertEqual({key:value for key,value in result.items() if key!='root_refusal'},expected)
        self.assertEqual(set(result),set(expected)|{'root_refusal'})
        self.assertEqual(result['root_refusal'][0]['error_type'],'ValueError')
        self.assertEqual(set(result['root_refusal'][0]),{'error_type','check_site'})
        self.assertNotIn(b'private-secret',canonical(result))
        self.assertEqual(raw,canonical(expected)+b'\n');self.assertNotIn(b'root_refusal',raw)
        self.assertNotIn(b'private-secret',raw);self.assertLessEqual(len(raw),512)


if __name__=='__main__':unittest.main()
