"""Root observation of the original controller's held database writer lease.

Discover from actual fixed SQL and protected runtime, never caller lease maps.
No lease is acquired, no process is signalled and no artifact effect is granted.
"""
import json
import os
from pathlib import Path
import re
import threading

from native_backend_scope import NativeBackendScope
from native_durable_binding import configuration
from native_durable_database import SQL, unique, validate_database
from native_inventory import database_environment
from native_kernel_backend import _capture_process, _check_scope, capture_backend_kernel_identity
from native_ownership_database import OBSERVATION_OPTIONS, _query_database, _socket_for_process, validate_session
from native_root_controller_request import NativeRootControllerRequest
from native_service_scope import process_identity, read_bytes
from resource_generations import canonical

LEASE_SQL = """SELECT json_build_object('database',("""+SQL+"""),
 'holders',(SELECT coalesce(json_agg(json_build_object(
  'backend_pid',a.pid,'backend_birth',floor(extract(epoch FROM a.backend_start)*1000000)::bigint::text,
  'client_address',host(a.client_addr),'client_port',a.client_port) ORDER BY a.pid),'[]'::json)
  FROM pg_locks l JOIN pg_stat_activity a ON a.pid=l.pid
  WHERE l.locktype='advisory' AND l.classid::bigint=1197034575 AND l.objid::bigint=1
   AND l.objsubid=2 AND l.mode='ExclusiveLock' AND l.granted
   AND l.database=(SELECT oid FROM pg_database WHERE datname=current_database())
   AND a.backend_type='client backend' AND a.usename=current_user AND a.datname=current_database()),
 'clients',(SELECT count(*) FROM pg_stat_activity WHERE datname=current_database()
  AND backend_type='client backend'))"""


class RootDatabaseExclusionRefused(Exception):
    pass


def require(value):
    if not value:
        raise RootDatabaseExclusionRefused('Original native controller database exclusion unavailable or changed')


def _lease(raw, expected, environment):
    require(type(raw) is bytes and 0 < len(raw) <= 16384)
    value = json.loads(raw,object_pairs_hook=unique)
    require(type(value) is dict and set(value) == {'database','holders','clients'})
    validate_database(value['database'],environment)
    require(value['database'] == expected and canonical(value['database']) == canonical(expected))
    # One retained writer client and this short-lived read-only observer.
    # Unexpected other client backends refuse, rather than claiming exclusion.
    require(type(value['clients']) is int and value['clients'] == 2)
    require(type(value['holders']) is list and len(value['holders']) == 1)
    holder = value['holders'][0]
    require(type(holder) is dict and set(holder) == {'backend_pid','backend_birth','client_address','client_port'})
    require(holder['client_address'] == '127.0.0.1' and type(holder['client_port']) is int and 0 < holder['client_port'] < 65536)
    snapshot = {'database':value['database'],'backend_pid':holder['backend_pid'],'backend_birth':holder['backend_birth']}
    validate_session(snapshot,expected)
    return snapshot,holder['client_port']


def _parent(raw, pid):
    require(type(raw) is bytes and 0 < len(raw) <= 16384)
    end = raw.rfind(b')')
    require(raw.startswith((str(pid)+' (').encode('ascii')) and end > 0 and raw[end:end+2] == b') ')
    fields = raw[end+2:].split()
    require(len(fields) >= 20 and fields[0] in {b'R',b'S',b'D',b'T',b't',b'I',b'P'})
    require(re.fullmatch(b'[1-9][0-9]{0,9}',fields[1]) and re.fullmatch(b'[1-9][0-9]{0,19}',fields[19]))
    require(int(fields[1]) < 2**31 and int(fields[19]) < 2**64)
    return int(fields[1]),fields[19].decode('ascii')


class NativeRootDatabaseExclusionObservation:
    """Take custody of an original request; capture once and permanently poison."""
    def __init__(self, request):
        self.usable = False;self.request = None
        try:
            require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0)
            require(type(request) is NativeRootControllerRequest);self.request = request
            self.owner = (os.getpid(),threading.get_ident())
            self.observed = request.check();self.scope = request.scope
            require(self.observed['original_controller_peer_authenticated'] is True
                and self.observed['original_controller_history_lock_observed'] is True)
            self.live = request.live;self.binding = self.live.binding
            self.database = json.loads(canonical(self.binding['database']))
            self.psql = self.live.lifecycle.generation_seal['executables']['psql']
            self.server = NativeBackendScope(self.observed['installation'],self.scope['boot_id'])
            self.server_scope = self.server.check()
            files,self.url = configuration(self.live.root,self.observed['installation'],self.scope['uid'])
            require(files == self.binding['configuration'])
            self.environment = database_environment(self.url)
            self.environment.update(PGPASSFILE='/dev/null',PGOPTIONS=OBSERVATION_OPTIONS,
                PGAPPNAME='gitgood native root exclusion observation v2')
            self.network = os.readlink('/proc/'+str(self.scope['manager']['pid'])+'/ns/net')
            require(self.network == os.readlink('/proc/self/ns/net'))
            self.client = self._discover_client()
            self.session,self.client_port = self._query()
            self._base()
            self.socket = self._socket()
            self.kernel = capture_backend_kernel_identity(self.psql,self.url,self.session,self.database,self.server_scope)
            self.kernel_raw = canonical(self.kernel)
            self._base();self.usable = True;self.check()
        except BaseException:
            self.close();raise RootDatabaseExclusionRefused('Original native controller database exclusion unavailable or changed') from None

    def _client(self, pid):
        process = Path('/proc')/str(pid)
        first = _parent(read_bytes(process/'stat'),pid)
        require(first[0] == self.scope['manager']['pid'])
        driver = self.scope['groups']['driver']['path'].removeprefix('/sys/fs/cgroup')
        value = process_identity(pid,self.scope['uid'],self.scope['gid'],driver)
        require(value['birth'] == first[1])
        require(all(value[name] == self.scope['manager'][name] for name in ('mount_namespace','cgroup_namespace')))
        require(os.readlink(process/'ns/net') == self.network == os.readlink('/proc/self/ns/net'))
        require(os.readlink(process/'ns/pid') == self.server_scope['pid_namespace'])
        require(os.readlink(process/'ns/time') == self.server_scope['time_namespace'])
        require(os.readlink(process/'exe') == self.psql)
        binary = (process/'exe').stat();expected = self.binding['executables']['psql']
        require(binary.st_uid == 0 and (binary.st_dev,binary.st_ino,binary.st_size) ==
            (expected['device'],expected['inode'],expected['bytes']))
        require(_parent(read_bytes(process/'stat'),pid) == first)
        return value

    def _discover_client(self):
        manager = self.scope['manager']['pid']
        children = read_bytes(Path('/proc')/str(manager)/'task'/str(manager)/'children').split()
        require(len(children) <= 128 and len(set(children)) == len(children))
        require(all(re.fullmatch(b'[1-9][0-9]{0,9}',pid) and int(pid) < 2**31 for pid in children))
        found = []
        for child in children:
            pid = int(child);process = Path('/proc')/str(pid)
            try:executable = os.readlink(process/'exe')
            except FileNotFoundError:continue # Only before an original client is selected.
            if executable == self.psql:found.append(self._client(pid))
        require(len(found) == 1)
        return found[0]

    def _query(self):
        return _lease(_query_database(self.psql,self.environment,LEASE_SQL),self.database,self.environment)

    def _socket(self):
        require(self._client(self.client['pid']) == self.client)
        value = _socket_for_process(Path('/proc')/str(self.client['pid']),self.network,self.scope['uid'],
            self.client_port,self.database['port'])
        require(self._client(self.client['pid']) == self.client)
        return value

    def _base(self):
        require(self.owner == (os.getpid(),threading.get_ident()))
        require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0)
        require(self.request.check() == self.observed and self.server.check() == self.server_scope)
        require(self._client(self.client['pid']) == self.client)
        require(configuration(self.live.root,self.observed['installation'],self.scope['uid']) ==
            (self.binding['configuration'],self.url))
        require(canonical(self.binding['database']) == canonical(self.database))
        _check_scope(self.server_scope)

    def check(self):
        try:
            require(self.usable)
            self._base();require(canonical(self.kernel) == self.kernel_raw)
            require(_capture_process(self.session['backend_pid'],self.server_scope) == self.kernel['kernel_birth'])
            require(self._query() == (self.session,self.client_port))
            require(self._socket() == self.socket)
            require(_capture_process(self.session['backend_pid'],self.server_scope) == self.kernel['kernel_birth'])
            self._base()
            return {**self.observed,'original_database_writer_lease_observed':True,
                'original_database_client_socket_observed':True,'original_database_backend_kernel_observed':True,
                'database_writer_exclusion_verified':True,'lease_acquired':False,
                'lifecycle_exclusion_established':False,'stage_effect_authorized':False,'complete_journey_acceptance':False}
        except BaseException:
            self.close();raise RootDatabaseExclusionRefused('Original native controller database exclusion unavailable or changed') from None

    def close(self):
        self.usable = False
        if self.request is not None:self.request.close()
        # Never terminate or replace the original controller/client/backend.
