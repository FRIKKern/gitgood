"""Attach read-only ownership custody to an already captured generation guard."""
import json
from pathlib import Path

from native_ownership_database import observe_held_session
from native_ownership_marker_guard import NativeOwnershipMarkerGuard
from native_ownership_records import require, validate_record
from native_service_scope import root_file
from native_durable_database import unique
from native_durable_binding import configuration
from resource_generations import canonical


class NativeOwnershipObservation:
    def __init__(self, generation_guard, captured, record, generation_seal):
        self.custody = None
        self.poisoned = False
        self._initial = None
        try:
            validate_record(record)
            self.record = json.loads(canonical(record))
            self.guard = generation_guard
            self.seal = json.loads(canonical(generation_seal))
            admitted = captured['admission']
            expected_worker = 'native' if record['mode']=='runtime' else 'maintenance'
            require(admitted['worker_observation']['worker']==expected_worker)
            require(admitted['worker_observation']['service_scope']['installation']==record['installation'])
            require(admitted['pointer']==record['pointer'] and admitted['binding_sha256']==record['binding_sha256'])
            require(admitted['worker_observation']['owner']==record['owner'])
            require(admitted['worker_observation']['service_scope']==record['scope'])
            self.token = {name:captured[name] for name in record['guard']}
            require(self.token==record['guard'])
            binding = self.guard.snapshot['binding']
            require(binding['database']==self.seal['database']==record['database_session']['database'])
            self.root = Path('/var/lib/gitgood/installations')/record['installation']
            self.authority_path = Path('/etc/gitgood/installations')/record['installation']/'ownership-admission-v2.json'
            self.authority_identity,self.authority_bytes = root_file(self.authority_path,16384)
            authority = json.loads(self.authority_bytes,object_pairs_hook=unique)
            require(self.authority_bytes==canonical(authority))
            require(type(authority) is dict and set(authority)=={'protocol','kind','installation','operation','candidate','binding_sha256'})
            require(type(authority['protocol']) is int and authority['protocol']==2)
            require(authority['kind']=='native_application_ownership_seal')
            require(all(authority[name]==record[name] for name in ['installation','operation','candidate','binding_sha256']))
            storage = binding['resources']['storage']
            require(storage['path']==str(self.root/'storage'))
            self.storage = json.loads(canonical(storage))
            self._initial = self._observe(initial=True)
        except Exception:
            self.close()
            raise ValueError('Native ownership observation unavailable') from None

    def _generation(self):
        require(not self.poisoned)
        require(root_file(self.authority_path,16384)==(self.authority_identity,self.authority_bytes))
        current = self.guard.check()
        require(current['current'] is True and {name:current[name] for name in self.token}==self.token)
        require(root_file(self.authority_path,16384)==(self.authority_identity,self.authority_bytes))
        return current

    def _session(self):
        binding = self.guard.snapshot['binding']
        files,url = configuration(self.root,self.record['installation'],self.record['scope']['uid'])
        require(files==binding['configuration'])
        owner = {name:self.record['owner'][name] for name in ['pid','birth','uid']}
        observed = observe_held_session(self.seal['executables']['psql'],url,self.record['database_session'],self.seal['database'],owner=owner)
        require(observed['owner_connection_observed'] and observed['lease_acquired'] is False)
        require(configuration(self.root,self.record['installation'],self.record['scope']['uid'])==(files,url))

    def _observe(self, *, initial=False):
        try:
            require(not self.poisoned)
            require(self.custody is None if initial else self.custody is not None)
            self._generation();self._session()
            if initial:
                self.custody = NativeOwnershipMarkerGuard(self.storage['path'],self.record['installation'],
                    {name:self.storage[name] for name in ['device','inode','uid']},self.record)
            custody = self.custody.check()
            current = self._generation()
            require(self.custody.check()==custody)
            return {'current':current,'ownership':{'operation':self.record['operation'],
                'record_sha256':custody['record_sha256'],'marker_sha256':custody['marker_sha256'],
                'ownership_marker_observed':True,'original_database_session_observed':True,
                'owner_socket_observed':True,'lease_acquired':False,'replacement_admitted':False,
                'installation_readiness_established':False,'lifecycle_responsibility_admitted':False}}
        except Exception:
            self.close()
            raise ValueError('Native ownership observation lost') from None

    def take_initial(self):
        """Consume the just-completed bracket once; subsequent heartbeats reobserve."""
        try:
            require(not self.poisoned and self._initial is not None)
            value = self._initial
            self._initial = None
            return json.loads(canonical(value))
        except Exception:
            self.close()
            raise ValueError('Native initial ownership observation unavailable') from None

    def check(self):
        self._initial = None
        return self._observe()

    def close(self):
        self.poisoned = True
        self._initial = None
        if self.custody is not None:
            custody,self.custody = self.custody,None
            custody.close()
