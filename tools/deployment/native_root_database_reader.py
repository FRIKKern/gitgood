"""One original Root read-only SQL observer selected from protected lifecycle.

Only fixed identity/exclusion SELECTs exist. This owns no writer lease and
never reconnects, replaces an original backend or authorizes an effect.
"""
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import threading
import time
import uuid

from native_backend_scope import NativeBackendScope
from native_durable_binding import configuration, executable
from native_durable_database import SQL, unique, validate_database
from native_inventory import database_environment
from native_kernel_backend import _capture_process, _check_scope, _stat
from native_ownership_database import OBSERVATION_OPTIONS, ROOT_EXCLUSION_SQL, _socket_for_process
from native_root_lifecycle import NativeRootLifecycleObservation
from native_root_controller import _within_root_observation_pass
from native_service_scope import read_bytes
from resource_generations import canonical


class RootDatabaseReaderRefused(Exception):
    pass


def require(value):
    if not value:raise RootDatabaseReaderRefused('Original read-only Root database observer lost')


def _reader(value):
    require(type(value) is dict and set(value) == {'backend_pid','backend_birth','client_address',
        'client_port','read_only','isolation','held'})
    require(type(value['backend_pid']) is int and 0 < value['backend_pid'] < 2**31)
    require(type(value['backend_birth']) is str and re.fullmatch(r'[1-9][0-9]{0,19}',value['backend_birth'])
        and int(value['backend_birth']) < 2**64)
    require(value['client_address'] == '127.0.0.1' and type(value['client_port']) is int
        and 0 < value['client_port'] < 65536)
    require(value['read_only'] == 'on' and value['isolation'] == 'read committed' and value['held'] is False)
    return json.loads(canonical(value))


READER_SQL = """SELECT json_build_object('backend_pid',pg_backend_pid(),
 'backend_birth',(SELECT floor(extract(epoch FROM backend_start)*1000000)::bigint::text
 FROM pg_stat_activity WHERE pid=pg_backend_pid()),
 'client_address',host(inet_client_addr()),'client_port',inet_client_port(),
 'read_only',current_setting('transaction_read_only'),'isolation',current_setting('transaction_isolation'),
 'held',EXISTS(SELECT 1 FROM pg_locks WHERE pid=pg_backend_pid() AND locktype='advisory'))"""


class NativeRootDatabaseReader:
    def __init__(self, lifecycle):
        self.usable = False;self.child = None;self.owner = None
        self.reader = self.client = self.kernel = self.socket = None
        self.prepared_statements = set()
        try:
            require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0)
            require(type(lifecycle) is NativeRootLifecycleObservation)
            self.owner = (os.getpid(),threading.get_ident());self.lifecycle = lifecycle
            self.observed = lifecycle.check();self.scope = lifecycle.scope
            require(self.observed['stage'] == 'stage' and self.observed['recorded_status'] == 'running')
            self.installation = self.observed['installation']
            self.binding = lifecycle.original['generation']['binding']
            self.expected = json.loads(canonical(self.binding['database']))
            self.root = Path('/var/lib/gitgood/installations')/self.installation
            self.files,self.url = configuration(self.root,self.installation,self.scope['uid'])
            require(self.files == self.binding['configuration'])
            self.psql = lifecycle.generation_seal['executables']['psql']
            require(executable(self.psql) == self.binding['executables']['psql'])
            info = Path(self.psql).stat();self.binary = self._binary(info)
            self.server = NativeBackendScope(self.installation,self.scope['boot_id'])
            self.server_scope = self.server.check();_check_scope(self.server_scope)
            self.network = os.readlink('/proc/self/ns/net')
            self.namespaces = {name:os.readlink('/proc/self/ns/'+name) for name in ('mnt','cgroup','pid','time','net')}
            self.group = read_bytes('/proc/self/cgroup',16384)
            require(os.readlink('/proc/'+str(self.scope['manager']['pid'])+'/ns/net') == self.network)
            self.environment = database_environment(self.url)
            self.environment.update(PGPASSFILE='/dev/null',PGOPTIONS=OBSERVATION_OPTIONS,
                PGAPPNAME='gitgood native root read-only observer v2')
            self.environment_raw = canonical(self.environment)
            self.child = subprocess.Popen([self.psql,'--quiet','--no-psqlrc','--no-password',
                '--tuples-only','--no-align','--set=ON_ERROR_STOP=1'],env=self.environment,
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=0)
            self.pipes = tuple(self._file(os.fstat(pipe.fileno())) for pipe in (self.child.stdin,self.child.stdout))
            self.usable = True;self._exchange('identity');self._exchange('identity')
        except BaseException:
            self.close();raise RootDatabaseReaderRefused('Original read-only Root database observer unavailable') from None

    @staticmethod
    def _file(info):
        return (info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode)

    @staticmethod
    def _binary(info):
        return tuple(getattr(info,name) for name in ('st_dev','st_ino','st_uid','st_gid',
            'st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns'))

    @_within_root_observation_pass
    def _configuration(self):
        """Original private configuration, fresh in every no-effect pass."""
        try:
            require(self.usable and self.owner == (os.getpid(),threading.get_ident()))
            require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0)
            require(self.root == Path('/var/lib/gitgood/installations')/self.installation
                and self.scope['installation'] == self.installation)
            value = configuration(self.root,self.installation,self.scope['uid'])
            require(value == (self.files,self.url))
            return value
        except BaseException:
            self.close();raise RootDatabaseReaderRefused('Original private Root observer configuration lost') from None

    def _client(self):
        process = Path('/proc')/str(self.child.pid)
        birth,state = _stat(self.child.pid);require(state not in {'Z','X'})
        raw = read_bytes(process/'stat',16384);fields = raw[raw.rfind(b')')+2:].split()
        require(len(fields) >= 20 and fields[1] == str(self.owner[0]).encode())
        status = read_bytes(process/'status',16384)
        for name in ('Uid','Gid'):
            lines = [line.partition(b':')[2].split() for line in status.splitlines() if line.startswith(name.encode()+b':')]
            require(lines == [[b'0']*4])
        require(process.stat().st_uid == 0 and os.readlink(process/'exe') == self.psql
            and self._binary((process/'exe').stat()) == self.binary)
        require(read_bytes(process/'cgroup',16384) == self.group)
        require({name:os.readlink(process/'ns'/name) for name in self.namespaces} == self.namespaces)
        after,after_state = _stat(self.child.pid)
        require(after == birth and after_state not in {'Z','X'})
        return {'pid':self.child.pid,'birth':birth}

    def _base(self):
        require(self.usable and self.owner == (os.getpid(),threading.get_ident()))
        require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0)
        require(self.child is not None and self.child.poll() is None)
        require(canonical(self.environment) == self.environment_raw)
        require(self.lifecycle.check() == self.observed and self.server.check() == self.server_scope)
        _check_scope(self.server_scope)
        require({name:os.readlink('/proc/self/ns/'+name) for name in self.namespaces} == self.namespaces
            and read_bytes('/proc/self/cgroup',16384) == self.group)
        require(self._configuration() == (self.files,self.url))
        require(self._binary(Path(self.psql).stat()) == self.binary)
        require(tuple(self._file(os.fstat(pipe.fileno())) for pipe in (self.child.stdin,self.child.stdout)) == self.pipes)
        current = self._client()
        if self.client is not None:require(current == self.client)
        if self.reader is not None:
            require(_capture_process(self.reader['backend_pid'],self.server_scope) == self.kernel)
            require(_socket_for_process(Path('/proc')/str(self.child.pid),self.network,0,
                self.reader['client_port'],self.expected['port']) == self.socket)
        return current

    def _statement(self, kind, nonce, statement):
        """Only fixed SELECT plans persist in this original session, never data."""
        names = {'identity': 'gitgood_root_identity_v2', 'exclusion': 'gitgood_root_exclusion_v2'}
        require(type(kind) is str and kind in names)
        require(type(nonce) is str and str(uuid.UUID(nonce)) == nonce)
        require(statement == (SQL if kind == 'identity' else ROOT_EXCLUSION_SQL))
        require(type(self.prepared_statements) is set and self.prepared_statements <= names.keys())
        prefix = '';name = names[kind]
        if kind not in self.prepared_statements:
            prefix = ("PREPARE " + name + "(text) AS SELECT json_build_object('nonce',$1,'reader',(" +
                READER_SQL + "),'value',(" + statement + "));\n")
            self.prepared_statements.add(kind)
        return (prefix + "EXECUTE " + name + "('" + nonce + "');\n").encode()

    def _exchange(self, kind):
        try:
            require(type(kind) is str and kind in {'identity','exclusion'})
            client = self._base();nonce = str(uuid.uuid4())
            statement = SQL if kind == 'identity' else ROOT_EXCLUSION_SQL
            raw = self._statement(kind, nonce, statement)
            require(len(raw) <= 8192 and self.child.stdin.write(raw) == len(raw));self.child.stdin.flush()
            output = bytearray();deadline = time.monotonic()+4
            with selectors.DefaultSelector() as selector:
                selector.register(self.child.stdout,selectors.EVENT_READ)
                while b'\n' not in output:
                    remaining = deadline-time.monotonic();require(remaining > 0 and selector.select(remaining))
                    block = os.read(self.child.stdout.fileno(),min(4096,16385-len(output)))
                    require(block);output.extend(block);require(len(output) <= 16384)
            require(output.endswith(b'\n') and output.count(b'\n') == 1)
            value = json.loads(output,object_pairs_hook=unique)
            require(type(value) is dict and set(value) == {'nonce','reader','value'} and value['nonce'] == nonce)
            reader = _reader(value['reader'])
            if self.reader is None:
                require(kind == 'identity');validate_database(value['value'],self.environment)
                require(value['value'] == self.expected)
                self.reader = reader;self.client = client
                self.kernel = _capture_process(reader['backend_pid'],self.server_scope)
                self.socket = _socket_for_process(Path('/proc')/str(self.child.pid),self.network,0,
                    reader['client_port'],self.expected['port'])
            else:require(reader == self.reader)
            require(self._base() == client)
            if kind == 'identity':
                validate_database(value['value'],self.environment);require(value['value'] == self.expected)
            return json.loads(canonical(value['value']))
        except BaseException:
            self.close();raise RootDatabaseReaderRefused('Original read-only Root database observer lost') from None

    @_within_root_observation_pass
    def _stage_observation(self):
        """One fixed reply per no-effect pass, never across effect boundaries."""
        try:
            value = self._exchange('exclusion')
            require(type(value) is dict and set(value) == {'database','holders','clients'})
            validate_database(value['database'],self.environment)
            require(value['database'] == self.expected)
            return value
        except BaseException:
            self.close();raise RootDatabaseReaderRefused('Original read-only Root database observer lost') from None

    def identity(self):
        return self._stage_observation()['database']

    def exclusion(self):
        return canonical(self._stage_observation())

    def close(self):
        self.usable = False
        # Only this retained Popen child is owned. Forks may not close its parent.
        if self.owner != (os.getpid(),threading.get_ident()):return
        if self.child is not None:
            if self.child.poll() is None:
                self.child.terminate()
                try:self.child.wait(timeout=2)
                except subprocess.TimeoutExpired:self.child.kill();self.child.wait()
            for pipe in (self.child.stdin,self.child.stdout):
                if pipe is not None:pipe.close()
            self.child = None
