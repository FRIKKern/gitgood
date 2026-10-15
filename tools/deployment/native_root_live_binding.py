"""Fixed Root original live binding observation; no exclusion or stage effects."""
import os
from pathlib import Path
import threading

from native_durable_binding import _CapturedExecutableDigests, _root_persistent_identity
from native_generation_lease_guard import _PersistentFingerprintPlan
from native_root_lifecycle import NativeRootLifecycleObservation
from native_root_database_reader import NativeRootDatabaseReader
from native_root_controller import _within_root_observation_pass
from resource_generations import canonical, identifier


class RootLiveBindingRefused(Exception):
    pass


def require(value):
    if not value:
        raise RootLiveBindingRefused('Original live native binding unavailable or changed')


class NativeRootLiveBindingObservation:
    """UUID-only view; compare live files/database with the original Root seal."""
    def __init__(self, installation, operation):
        self.usable = False;self.lifecycle = None;self.executables = None;self.database_reader = None
        try:
            identifier(installation);identifier(operation);require(installation != operation)
            require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0)
            self.owner = (os.getpid(),threading.get_ident())
            self.installation,self.operation = installation,operation
            self.lifecycle = NativeRootLifecycleObservation(installation,operation)
            self.observed_lifecycle = self.lifecycle.check()
            self.scope = self.lifecycle.scope
            self.binding = self.lifecycle.original['generation']['binding']
            self.binding_raw = canonical(self.binding)
            self.root = Path('/var/lib/gitgood/installations')/installation
            self.fingerprint_plan = _PersistentFingerprintPlan(self.binding)
            self.files = self.fingerprint_plan.read()
            self.executables = _CapturedExecutableDigests(self.lifecycle.generation_seal['executables'])
            # Staging keeps the ordinary owner idle until Root acknowledgement.
            # Handoff windows must retain short-lived observers: a persistent
            # second client would correctly trip the ordinary writer's guard.
            if self.observed_lifecycle['stage'] == 'stage' and self.observed_lifecycle['recorded_status'] == 'running':
                self.database_reader = NativeRootDatabaseReader(self.lifecycle)
            self.usable = True
            self._observe();self.executables.freeze();self.check()
        except BaseException:
            self.close();raise RootLiveBindingRefused('Original live native binding unavailable or changed') from None

    def _current(self):
        require(self.usable and self.owner == (os.getpid(),threading.get_ident()))
        require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0)
        require(self.lifecycle.check() == self.observed_lifecycle)
        require(canonical(self.binding) == self.binding_raw)
        require(self.fingerprint_plan.read() == self.files)

    def _observe(self):
        self._current()
        options = {'_executable_files':self.executables}
        if self.database_reader is not None:options['_database_reader'] = self.database_reader
        value = _root_persistent_identity(self.root,self.scope,self.lifecycle.generation_seal['executables'],**options)
        require(value == self.binding and canonical(value) == self.binding_raw)
        self._current()

    @_within_root_observation_pass
    def check(self):
        try:
            require(self.usable and self.owner == (os.getpid(),threading.get_ident()))
            self._observe()
            return {**self.observed_lifecycle,'live_durable_resource_identity_verified':True,
                'original_live_files_and_database_observed':True,'lifecycle_exclusion_established':False,
                'stage_effect_authorized':False,'complete_journey_acceptance':False}
        except BaseException:
            self.close();raise RootLiveBindingRefused('Original live native binding unavailable or changed') from None

    def close(self):
        self.usable = False
        if self.database_reader is not None:self.database_reader.close()
        if self.executables is not None:self.executables.close()
        if self.lifecycle is not None:self.lifecycle.close()
        # Every original policy, file, directory, database and history remains.
