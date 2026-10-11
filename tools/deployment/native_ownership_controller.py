"""Live same-generation ownership handoff; stored receipts never grant authority."""
import json
import os
from pathlib import Path
import threading
import time
import uuid

from generation_custody import GenerationRecordCustody
from generation_publication import stopped
from native_backend_scope import NativeBackendScope
from native_command_endpoint import NativeCommandEndpoint
from native_durable_binding import configuration, persistent_identity
from native_durable_database import unique
from native_generation_lease_guard import persistent_fingerprint
from native_kernel_backend import (capture_backend_kernel_identity,
    observe_held_backend_kernel_identity,observe_prior_backend_identity_absence,_validate_record as validate_kernel)
from native_lifecycle_generation_reader import open_reader
from native_ownership_records import require, validate_record
from native_ownership_transition import OwnershipTransitionStore, sha
from native_service_scope import process_identity, read_bytes, root_file, members, group_identity, _CapturedRootFiles
from native_worker_scope import _ancestry
from native_writer_exclusion import NativeWriterExclusion
from resource_generations import canonical, identifier, validate_scope

RESERVATION_SECONDS=120.0


def original_owner_absent(record):
    """An original zombie is present; unreadable procfs is not absence."""
    owner=record['owner'];path=Path('/proc')/str(owner['pid'])/'stat'
    try:raw=read_bytes(path).decode('ascii')
    except FileNotFoundError:return
    require(raw.startswith(str(owner['pid'])+' (') and ') ' in raw)
    fields=raw[raw.rfind(')')+2:].split()
    require(len(fields)>=20 and fields[19].isdecimal())
    require(fields[19]!=owner['birth'])


class NativeOwnershipController:
    """Borrow actual controller endpoint and original held installation custody.

    reserve runs before the new worker starts. admit assigns its first exact
    BEAM birth once, then releases the retained exclusion. publish checks that
    BEAM's new held lease and publishes under this still-live reservation.
    """
    def __init__(self, installation, custody, endpoint):
        identifier(installation)
        require(type(custody) is GenerationRecordCustody and type(endpoint) is NativeCommandEndpoint)
        custody.check();endpoint.check()
        require(custody.installation==endpoint.scope.installation==installation)
        self.installation=installation;self.custody=custody;self.endpoint=endpoint
        self.owner=(os.getpid(),threading.get_ident());self.scope=endpoint.scope.check()
        require(self.scope['manager']['pid']==os.getpid())
        self.root=Path('/var/lib/gitgood/installations')/installation
        self.reader=None;self.reader_original=None;self.store=None;self.exclusion=None
        self.usable=True;self.state='idle';self.root_files={};self.deadline=None

    def _root(self, name, maximum=16384):
        path=Path('/etc/gitgood/installations')/self.installation/name
        fingerprint=_CapturedRootFiles._fingerprint(path,maximum,False)
        identity,raw=root_file(path,maximum)
        require(_CapturedRootFiles._fingerprint(path,maximum,False)==fingerprint)
        value=json.loads(raw,object_pairs_hook=unique);require(raw==canonical(value))
        self.root_files[str(path)]=(maximum,fingerprint,identity,raw)
        return value

    def _controller(self):
        require(self.usable and self.owner==(os.getpid(),threading.get_ident()))
        if self.deadline is not None:require(time.monotonic()<self.deadline)
        self.custody.check();self.endpoint.check();require(self.endpoint.scope.check()==self.scope)
        for name,(maximum,fingerprint,identity,raw) in self.root_files.items():
            path=Path(name)
            require(_CapturedRootFiles._fingerprint(path,maximum,False)==fingerprint)
            require(root_file(path,maximum)==(identity,raw))
            require(_CapturedRootFiles._fingerprint(path,maximum,False)==fingerprint)

    def _base(self):
        self._controller()
        require(self.reader._snapshot(self.scope)==self.snapshot)
        require(persistent_fingerprint(self.binding)==self.files)
        require(configuration(self.root,self.installation,self.scope['uid'])==(self.configuration,self.url))
        require(self.backend_scope.check()==self.server_scope)
        self.store.check();self._controller()

    def _absent(self):
        results={}
        for key,record in self.priors.items():
            self._controller();original_owner_absent(record)
            observed=observe_prior_backend_identity_absence(self.seal['executables']['psql'],self.url,
                record['backend_kernel'],self.binding['database'],self.backend_scope.check())
            require(observed['original_backend_absent'] is True and observed['kernel_backend_absence_observed'] is True)
            original_owner_absent(record);results[key]=observed
        return results

    def _reservation_check(self):
        self._base();stopped(self.scope);self._absent();self.exclusion.check();self._base()

    def _dispose_views(self):
        if self.reader is not None:
            self.reader.close();self.reader=None
        if self.store is not None:self.store.close();self.store=None

    def _retained_transition(self, record, values):
        claim=record['claim'];files=self.store.known['receipts']
        required={claim+'.'+kind+'.json' for kind in ['reservation','assignment','intent','complete']}
        require(required<=set(files))
        reservation=files[claim+'.reservation.json'][0];assignment=files[claim+'.assignment.json'][0]
        intent=files[claim+'.intent.json'][0];complete=files[claim+'.complete.json'][0]
        require(type(reservation) is dict and set(reservation)=={'protocol','kind','installation','operation','candidate','claim','mode',
            'binding_sha256','pointer','scope','predecessor_sha256','predecessor_marker','history_sha256',
            'persistent_files_sha256','absence','exclusion_kernel'})
        require(type(reservation['protocol']) is int and reservation['protocol']==4 and reservation['kind']=='native_ownership_reservation')
        require(all(reservation[name]==record[name] for name in ['installation','operation','candidate','claim','mode','binding_sha256',
            'pointer','scope','predecessor_sha256']))
        require(reservation['history_sha256']==record['guard']['history_sha256'] and
                reservation['persistent_files_sha256']==record['guard']['persistent_files_sha256'])
        require(sha(reservation)==record['reservation_sha256'])
        kernel=reservation['exclusion_kernel']
        validate_kernel(kernel,kernel['database_session'],record['database_session']['database'],record['backend_kernel']['server_scope'])
        require(type(assignment) is dict and set(assignment)=={'protocol','kind','installation','operation','claim','reservation_sha256','owner','peer'})
        require(type(assignment['protocol']) is int and assignment['protocol']==4 and assignment['kind']=='native_ownership_assignment')
        require(all(assignment[name]==record[name] for name in ['installation','operation','claim','reservation_sha256','owner']))
        validate_scope({**record['scope'],'manager':assignment['peer']})
        require(assignment['peer']['pid']!=record['scope']['manager']['pid'])
        predecessor=record['predecessor_sha256'];previous=values[predecessor] if predecessor else None
        old_name,old_marker=self.store.marker(previous) if previous else (None,None)
        original=reservation['predecessor_marker']
        if previous is None:require(original is None)
        else:
            require(type(original) is list and len(original)==8 and all(type(value) is int and value>=0 for value in original))
            archive=files[claim+'.old-marker.json'];require(archive[0]==old_marker)
            require(self.store._moved_identity(tuple(original),archive[1]))
        new_name,new_marker=self.store.marker(record)
        require(intent=={'protocol':4,'kind':'native_ownership_marker_transition','installation':record['installation'],
            'claim':claim,'reservation_sha256':record['reservation_sha256'],'predecessor_sha256':predecessor,'record_sha256':sha(record),
            'old_name':old_name,'old_marker':old_marker,'old_identity':original,'new_name':new_name,'new_marker':new_marker})
        require(type(intent['protocol']) is int)
        require(complete=={'protocol':4,'kind':'native_ownership_publication_receipt','installation':record['installation'],
            'claim':claim,'operation':record['operation'],'record_sha256':sha(record),'intent_sha256':sha(intent),'marker_sha256':sha(new_marker)})
        require(type(complete['protocol']) is int)
        ancestors=set();key=predecessor
        while key is not None:
            require(key in values and key not in ancestors);ancestors.add(key)
            parent=values[key];key=parent['predecessor_sha256'] if parent['protocol']==4 else None
        require(type(reservation['absence']) is dict and set(reservation['absence'])==ancestors)
        for observed in reservation['absence'].values():
            require(type(observed) is dict and set(observed)=={'original_backend_absent','backend_activity_absence_observed',
                'kernel_backend_absence_observed','pid_reused','expected_database_observed','lease_acquired','writer_exclusion_established',
                'owner_process_absence_observed','descendant_absence_observed','kernel_pid_reused','replacement_admitted'})
            require(all(type(value) is bool for value in observed.values()))
            require(all(observed[name] for name in ['original_backend_absent','backend_activity_absence_observed',
                                                  'kernel_backend_absence_observed','expected_database_observed']))
            require(not any(observed[name] for name in ['lease_acquired','writer_exclusion_established','owner_process_absence_observed',
                                                       'descendant_absence_observed','replacement_admitted']))

    def _prior(self):
        values=self.store.records()
        require(all(value['protocol']>=3 for value in values.values()))
        for record in values.values():
            require(all(record[name]==self.authority[name] for name in ['installation','operation','candidate','binding_sha256']))
            require(record['scope']==self.scope and record['pointer']==self.snapshot['pointer'])
            require(record['backend_kernel']['server_scope']==self.server_scope)
        parents={};initial=[]
        for key,record in values.items():
            predecessor=record['predecessor_sha256'] if record['protocol']==4 else None
            if predecessor is None:initial.append(key)
            else:
                require(predecessor in values and predecessor not in parents)
                parents[predecessor]=key
            if record['protocol']==4:
                self._retained_transition(record,values)
        if not values:
            self.store.no_marker();require(not self.store.known['receipts']);return None,None
        require(len(initial)==1)
        visited=set();tip=initial[0]
        while tip in parents:
            require(tip not in visited);visited.add(tip);tip=parents[tip]
        require(len(visited)+1==len(values))
        expected=set()
        for record in values.values():
            if record['protocol']==4:
                kinds=['reservation','assignment','intent','complete']
                if record['predecessor_sha256'] is not None:kinds.append('old-marker')
                expected.update(record['claim']+'.'+kind+'.json' for kind in kinds)
        require(set(self.store.known['receipts'])==expected)
        return values[tip],self.store.current_marker(values[tip])

    def reserve(self, mode):
        require(self.state in {'idle','complete'} and mode in {'runtime','migrate','backup','restore'})
        self._dispose_views();self.root_files={};self.deadline=time.monotonic()+RESERVATION_SECONDS
        self.state='preparing';self.mode=mode;self.assignment=None;self.record=None
        try:
            self._controller()
            self.seal=self._root('generation-admission-v2.json')
            require(set(self.seal)=={'protocol','kind','installation','binding_sha256','history_identity','lock_identity',
                'unit_sha256','executables','limits','database'})
            require(type(self.seal['protocol']) is int and self.seal['protocol']==2 and self.seal['kind']=='native_generation_admission_seal')
            require(type(self.seal['limits']) is dict and set(self.seal['limits'])=={'cpu_quota_us','memory_bytes'})
            require(self.scope['limits']=={**self.seal['limits'],'cpu_period_us':100000,'swap_bytes':0})
            require(self.seal['installation']==self.installation and self.custody.identity==self.seal['history_identity']
                    and self.custody.expected_lock_identity==self.seal['lock_identity'])
            self.authority=self._root('ownership-admission-v3.json')
            require(set(self.authority)=={'protocol','kind','installation','operation','candidate','binding_sha256'})
            require(type(self.authority['protocol']) is int and self.authority['protocol']==3 and self.authority['kind']=='native_application_ownership_seal')
            require(self.authority['installation']==self.installation and self.authority['binding_sha256']==self.seal['binding_sha256'])
            worker='native' if mode=='runtime' else 'maintenance';self.worker=worker
            self.reader=open_reader(str(self.root),self.installation,self.seal['binding_sha256'],self.seal['history_identity'],
                self.seal['lock_identity'],self.seal['unit_sha256'],self.seal['executables'],worker=worker,**self.seal['limits'])
            self.reader.borrow_custody(self.custody)
            self.snapshot=self.reader._snapshot(self.scope);self.binding=self.snapshot['binding']
            require(self.binding['database']==self.seal['database'])
            self.files=persistent_fingerprint(self.binding)
            require(persistent_identity(self.root,self.scope,self.seal['executables'])==self.binding)
            require(persistent_identity(self.root,self.scope,self.seal['executables'])==self.binding)
            require(persistent_fingerprint(self.binding)==self.files)
            if 'lifecycle' in self.snapshot:
                require(self.snapshot['lifecycle']['operation']==self.authority['operation'])
                require(self.snapshot['lifecycle']['candidate']==self.authority['candidate'])
            storage=self.binding['resources']['storage']
            self.store=OwnershipTransitionStore(storage['path'],self.installation,{name:storage[name] for name in ['device','inode','uid']})
            self.backend_scope=NativeBackendScope(self.installation,self.scope['boot_id']);self.server_scope=self.backend_scope.check()
            self.priors=self.store.records();require(len(self.priors)<128)
            self.previous,self.captured_marker=self._prior()
            self.configuration,self.url=configuration(self.root,self.installation,self.scope['uid'])
            require(self.configuration==self.binding['configuration'])
            self._base();stopped(self.scope);absence=self._absent()
            self.exclusion=NativeWriterExclusion(self.seal['executables']['psql'],self.url,self.binding['database'])
            self.exclusion.__enter__();excluded=self.exclusion.check()
            session={name:excluded[name] for name in ['database','backend_pid','backend_birth']}
            self.exclusion_kernel=capture_backend_kernel_identity(self.seal['executables']['psql'],self.url,session,
                self.binding['database'],self.server_scope)
            self._reservation_check()
            self.claim=str(uuid.uuid4())
            self.reservation={'protocol':4,'kind':'native_ownership_reservation','installation':self.installation,
                'operation':self.authority['operation'],'candidate':self.authority['candidate'],'claim':self.claim,'mode':mode,
                'binding_sha256':self.authority['binding_sha256'],'pointer':self.snapshot['pointer'],'scope':self.scope,
                'predecessor_sha256':sha(self.previous) if self.previous else None,
                'predecessor_marker':list(self.captured_marker[1][1]) if self.captured_marker else None,
                'history_sha256':sha(self.snapshot),'persistent_files_sha256':sha(self.files),
                'absence':absence,'exclusion_kernel':self.exclusion_kernel}
            self.store.put('receipts',self.claim+'.reservation.json',self.reservation)
            self._reservation_check();self.state='reserved'
            return {'claim':self.claim,'reservation_sha256':sha(self.reservation)}
        except Exception:
            self.close();raise

    def _peer_owner(self, peer, owner_pid):
        require(type(peer) is dict and set(peer)=={'pid','uid','gid'})
        require(peer['uid']==self.scope['uid'] and peer['gid']==self.scope['gid'])
        first=_ancestry(owner_pid,self.scope,self.worker,_peer_pid=peer['pid'])
        require(first and first[0]['pid']==peer['pid'] and first[-1]['pid']==owner_pid)
        owner=first[-1];require(owner['pid']!=self.scope['manager']['pid'])
        # The old captured leaves were empty before reservation. Every process
        # now admitted in the selected leaf must belong to this exact new BEAM.
        for name,item in self.scope['groups'].items():
            if name=='driver':continue
            require(group_identity(item['path'],self.scope['uid'])==item)
            if name==self.worker:
                for pid in members(item['path']):
                    chain=_ancestry(owner_pid,self.scope,self.worker,_peer_pid=pid);require(chain[-1]==owner)
                # Nested cgroups are not part of the initial bounded handoff.
                require(not any(path.is_dir() for path in Path(item['path']).iterdir()))
            else:
                events=dict(line.split() for line in read_bytes(Path(item['path'])/'cgroup.events',1024).decode('ascii').splitlines())
                require(events.get('populated')=='0')
        require(_ancestry(owner_pid,self.scope,self.worker,_peer_pid=peer['pid'])==first)
        return owner

    def admit(self, request, peer):
        require(self.state=='reserved' and self.assignment is None)
        self._base()
        require(set(request)=={'protocol','kind','action','installation','operation','candidate','mode','owner_pid'})
        require(request['protocol']==4 and request['kind']=='native_ownership_handoff' and request['action']=='admit')
        require(all(request[name]==self.authority[name] for name in ['installation','operation','candidate']))
        require(request['mode']==self.mode)
        owner=self._peer_owner(peer,request['owner_pid']);self._absent();self.exclusion.check();self._base()
        self.assignment={'protocol':4,'kind':'native_ownership_assignment','installation':self.installation,
            'operation':self.authority['operation'],'claim':self.claim,'reservation_sha256':sha(self.reservation),
            'owner':owner,'peer':process_identity(peer['pid'],self.scope['uid'],self.scope['gid'],
                self.scope['groups'][self.worker]['path'].removeprefix('/sys/fs/cgroup'))}
        self.state='assigning'
        self.store.put('receipts',self.claim+'.assignment.json',self.assignment)
        require(self._peer_owner(peer,request['owner_pid'])==owner)
        self._absent();self.exclusion.check();self._base()
        exclusion,self.exclusion=self.exclusion,None;exclusion.close()
        gone=observe_prior_backend_identity_absence(self.seal['executables']['psql'],self.url,self.exclusion_kernel,
            self.binding['database'],self.backend_scope.check())
        require(gone['original_backend_absent'] and gone['kernel_backend_absence_observed'])
        self._base();require(self._peer_owner(peer,request['owner_pid'])==owner)
        self.state='assigned'
        return {'protocol':4,'status':'admitted','installation':self.installation,
            'operation':self.authority['operation'],'candidate':self.authority['candidate'],'claim':self.claim,'mode':self.mode,
            'pointer':self.snapshot['pointer'],'predecessor_sha256':self.reservation['predecessor_sha256'],
            'reservation_sha256':sha(self.reservation),'owner':owner,'controller':self.scope['manager']}

    def _publication_check(self):
        self._base();self._absent()
        require(self._peer_owner(self.peer,self.record['owner']['pid'])==self.assignment['owner'])
        result=observe_held_backend_kernel_identity(self.seal['executables']['psql'],self.url,self.record['backend_kernel'],
            self.binding['database'],self.backend_scope.check(),
            owner={name:self.record['owner'][name] for name in ['pid','birth','uid']})
        require(result['owner_connection_observed'] is True and result['original_backend_kernel_observed'] is True)
        self._base()

    def publish(self, record, peer):
        require(self.state in {'assigned','publishing','complete'})
        validate_record(record);require(record['protocol']==4)
        require(all(record[name]==self.authority[name] for name in ['installation','operation','candidate','binding_sha256']))
        require(record['claim']==self.claim and record['mode']==self.mode and record['scope']==self.scope)
        require(record['pointer']==self.snapshot['pointer'] and record['owner']==self.assignment['owner'])
        require(record['reservation_sha256']==sha(self.reservation) and record['predecessor_sha256']==self.reservation['predecessor_sha256'])
        require(record['guard']=={'scope_sha256':sha({'scope':self.scope,'owner':record['owner'],'worker':self.worker}),
                'history_sha256':sha(self.snapshot),'persistent_files_sha256':sha(self.files)})
        require(record['database_session']['database']==self.binding['database'])
        if self.record is not None:require(record==self.record)
        self.record=json.loads(canonical(record));self.peer=dict(peer)
        self._publication_check()
        if self.state!='complete':self.state='publishing'
        result=self.store.publish(record,self.previous,self.captured_marker,self._publication_check)
        self._publication_check();self.state='complete';self.deadline=None;return result

    def close(self):
        self.usable=False
        if self.exclusion is not None:
            exclusion,self.exclusion=self.exclusion,None;exclusion.close()
        self._dispose_views()
        # Borrowed endpoint/custody and every retained record remain untouched.
