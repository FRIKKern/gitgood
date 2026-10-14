"""Fixed Root staging through an original authenticated controller request.

The dispatcher owns its Root observation views and allocation lock. It never
owns or replaces the ordinary controller's history/database exclusion.
"""
import hashlib
import os
from pathlib import Path
import socket
import threading

from native_protected_artifact import NativeProtectedArtifactStage
from native_root_artifact_policy import NativeRootArtifactPolicyAllocation
from native_root_controller_request import NativeRootControllerRequest
from native_root_database_exclusion import NativeRootDatabaseExclusionObservation
from native_root_controller import _RootObservationPass
from resource_generations import canonical


class RootArtifactDispatchRefused(Exception):
    pass


def failure_observation(error):
    """Bounded fixed-code locations only; never exception messages or values."""
    files = {'native_artifact_controller.py','native_root_artifact_dispatch.py',
        'native_root_artifact_policy.py','native_protected_artifact.py',
        'native_root_controller_request.py','native_root_database_exclusion.py',
        'native_root_live_binding.py','native_root_lifecycle.py',
        'native_root_controller.py','native_ownership_database.py','native_root_database_reader.py'}
    allowed = {str(Path(__file__).with_name(name)):name for name in files}
    functions = {'__init__','check','stage','begin_stage','allocate',
        '_preflight_archive','_check_archive_input','_inspect','_base','_current','_observe','_query',
        '_query_database','_lease','_socket','_client','_lock','_validate_stage',
        '_staged_output','serve_artifact_stage','_exchange','identity','exclusion',
        '_socket_for_process','_tcp_socket_inode','_tcp_socket_reply'}
    types = {'RootArtifactDispatchRefused','ArtifactControllerRefused',
        'RootArtifactPolicyRefused','ProtectedArtifactRefused','RootControllerRequestRefused',
        'RootDatabaseExclusionRefused','RootLiveBindingRefused','RootLifecycleRefused',
        'RootControllerRefused','OwnershipDatabaseRefused','RootDatabaseReaderRefused','TimeoutError',
        'BrokenPipeError','ConnectionResetError','OSError','ValueError','AssertionError'}
    result = [];seen = set()
    for _ in range(16):
        if error is None or id(error) in seen:break
        seen.add(id(error));site = {'status':'unavailable'};cursor = error.__traceback__
        for _ in range(128):
            if cursor is None:break
            code = cursor.tb_frame.f_code
            if (code.co_filename in allowed and code.co_name in functions
                    and type(cursor.tb_lineno) is int and 0 < cursor.tb_lineno < 10000):
                site = {'file':allowed[code.co_filename],'function':code.co_name,'line':cursor.tb_lineno}
            cursor = cursor.tb_next
        name = type(error).__name__
        result.append({'error_type':name if name in types else 'other','check_site':site})
        error = error.__cause__ if error.__cause__ is not None else error.__context__
    return result


def require(value):
    if not value:
        raise RootArtifactDispatchRefused('Original serialized artifact stage unavailable; retain effects')


class _ObservedArtifactStage(NativeProtectedArtifactStage):
    """Private stage path brackets every existing effect check with custody."""
    def __init__(self, allocation):
        require(type(allocation) is NativeRootArtifactPolicyAllocation)
        self.allocation = allocation
        observed = allocation.check()
        require(observed['policy_allocated'] is True)
        self.allocation_original = observed
        try:
            super().__init__(allocation.installation,allocation.operation)
            require(self.scope == allocation.exclusion.scope)
        except BaseException:
            self.close();raise

    def check(self):
        try:
            with _RootObservationPass():
                require(self.allocation.check() == self.allocation_original)
                result = super().check()
            # A separate fresh pass catches loss during the read-only guard.
            # No pass spans archive writes, entry creation or publication.
            with _RootObservationPass():
                require(self.allocation.check() == self.allocation_original)
            return result
        except BaseException:
            self.close();self.allocation.close()
            raise RootArtifactDispatchRefused('Original serialized artifact stage unavailable; retain effects') from None


class NativeRootArtifactStageDispatch:
    """Take one exact original request, allocate once and extract once."""
    def __init__(self, request):
        self.usable = False;self.request = None;self.allocation = None;self.stage_view = None
        try:
            require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0)
            require(type(request) is NativeRootControllerRequest)
            self.request = request;self.owner = (os.getpid(),threading.get_ident())
            observed = request.check()
            require(observed['stage'] == 'stage' and observed['recorded_status'] == 'running')
            exclusion = NativeRootDatabaseExclusionObservation(request)
            try:self.allocation = NativeRootArtifactPolicyAllocation(exclusion)
            except BaseException:exclusion.close();raise
            self.allocated = self.allocation.allocate()
            require(self.allocated['policy_allocated'] is True and self.allocated['artifact_staged'] is False)
            self.stage_view = _ObservedArtifactStage(self.allocation)
            self.original = self.allocation.check()
            self.state = 'ready';self.usable = True;self.check()
        except BaseException:
            self.close();raise RootArtifactDispatchRefused('Original serialized artifact stage unavailable; retain effects') from None

    def check(self):
        try:
            require(self.usable and self.owner == (os.getpid(),threading.get_ident()))
            require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0)
            require(self.allocation.check() == self.original)
            current = self.stage_view.check()
            require(current['artifact_staged'] is (self.state == 'staged'))
            require(self.allocation.check() == self.original)
            return {'installation':self.allocated['installation'],'operation':self.allocated['operation'],
                'candidate':self.allocated['candidate'],'original_exclusion_and_allocation_lock_observed':True,
                'artifact_staged':self.state == 'staged','complete_journey_acceptance':False}
        except BaseException:
            self.close();raise RootArtifactDispatchRefused('Original serialized artifact stage unavailable; retain effects') from None

    def stage(self):
        try:
            self.check();require(self.state == 'ready')
            receipt = self.stage_view.stage()
            require(receipt['installation'] == self.allocated['installation']
                and receipt['operation'] == self.allocated['operation']
                and receipt['candidate'] == self.allocated['candidate'])
            require(receipt['root_controlled_code'] is True and receipt['status'] == 'staged'
                and receipt['complete_journey_acceptance'] is False)
            self.state = 'staged';self.check()
            return receipt
        except BaseException:
            self.close();raise RootArtifactDispatchRefused('Original serialized artifact stage unavailable; retain effects') from None

    def close(self):
        self.usable = False
        if self.stage_view is not None:self.stage_view.close()
        if self.allocation is not None:self.allocation.close()
        elif self.request is not None:self.request.close()
        # Original controller custody/session and partial/final effects remain.


def serve_artifact_stage(installation, operation, connection):
    """Serve an already accepted local socket; Root provisioning is separate.

    Drop Root SQL observers before acknowledging success. The ordinary owner
    must then recheck its same exclusion and independently validate the fixed
    Root output before recording durable stage completion.
    """
    dispatch = request = reply = failure = None
    response = {'protocol':2,'kind':'native_root_artifact_result','status':'refused'}
    try:
        require(type(connection) is socket.socket)
        reply = connection.dup();reply.settimeout(2)
        request = NativeRootControllerRequest(installation,operation,connection)
        dispatch = NativeRootArtifactStageDispatch(request)
        receipt = dispatch.stage()
        response = {'protocol':2,'kind':'native_root_artifact_result','status':'staged',
            'installation':receipt['installation'],'operation':receipt['operation'],'candidate':receipt['candidate'],
            'receipt_sha256':hashlib.sha256(canonical(receipt)).hexdigest()}
    except BaseException as error:
        failure = error
        response = {'protocol':2,'kind':'native_root_artifact_result','status':'refused'}
    finally:
        if dispatch is not None:dispatch.close()
        elif request is not None:request.close()
        elif type(connection) is socket.socket:connection.close()
    try:
        raw = canonical(response)+b'\n';require(len(raw) <= 512)
        if reply is not None:
            try:reply.sendall(raw)
            except OSError:
                if failure is not None:
                    raise RootArtifactDispatchRefused('Original stage refused before reply transport loss; retain effects') from failure
                raise
        else:require(False)
        # The ordinary peer receives only the fixed bounded wire response.
        # Keep a separately sanitized refusal for the local Root caller, even
        # when that refusal was successfully delivered and no transport failed.
        return {**response,'root_refusal':failure_observation(failure)} if failure is not None else response
    finally:
        if reply is not None:reply.close()
