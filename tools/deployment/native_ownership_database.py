"""Read-only observation of one original native lease backend; never reacquire."""
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import time

from native_durable_database import SQL, DatabaseRefused, unique, validate_database
from native_inventory import database_environment


def require(value):
    if not value:
        raise DatabaseRefused('Native ownership database session unavailable')


OBSERVATION_OPTIONS = '-c statement_timeout=3000 -c default_transaction_read_only=on -c search_path=pg_catalog'


def _query_database(psql, environment, statement):
    """Bound a trusted internal statement; no external entry accepts SQL."""
    require(type(psql) is str and psql.startswith('/') and '\0' not in psql and len(psql)<=4096)
    require(environment.get('PGOPTIONS')==OBSERVATION_OPTIONS and environment.get('PGPASSFILE')=='/dev/null')
    require(type(statement) is str and 0<len(statement)<=8192 and '\0' not in statement)
    arguments=[psql,'--no-psqlrc','--no-password','--tuples-only','--no-align','--set=ON_ERROR_STOP=1','--command',statement]
    with subprocess.Popen(arguments,env=environment,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL) as child:
        output=bytearray()
        try:
            deadline=time.monotonic()+4
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout,selectors.EVENT_READ)
                while True:
                    remaining=deadline-time.monotonic()
                    require(remaining>0 and selector.select(remaining))
                    block=os.read(child.stdout.fileno(),min(4096,16385-len(output)))
                    if not block:break
                    output.extend(block);require(len(output)<=16384)
            require(child.wait(timeout=max(.01,deadline-time.monotonic()))==0 and 0<len(output)<=16384)
            return bytes(output)
        finally:
            if child.poll() is None:
                child.kill();child.wait()


def validate_session(snapshot, expected_database):
    require(type(snapshot) is dict and set(snapshot)=={'database','backend_pid','backend_birth'})
    require(type(snapshot['database']) is dict and type(expected_database) is dict)
    require(snapshot['database']==expected_database)
    require(all(type(snapshot['database'][key]) is type(value) for key,value in expected_database.items()))
    require(type(snapshot['backend_pid']) is int and 0<snapshot['backend_pid']<2**31)
    birth = snapshot['backend_birth']
    require(type(birth) is str and re.fullmatch(r'[1-9][0-9]{0,19}',birth) and int(birth)<2**64)


def _owner(owner):
    require(type(owner) is dict and set(owner)=={'pid','birth','uid'})
    require(type(owner['pid']) is int and 1<owner['pid']<2**31)
    require(type(owner['uid']) is int and owner['uid']==os.getuid()==os.geteuid()!=0)
    require(type(owner['birth']) is str and re.fullmatch(r'[1-9][0-9]{0,19}',owner['birth']))
    require(int(owner['birth'])<2**64)
    process = Path('/proc')/str(owner['pid'])
    require(process.stat().st_uid==owner['uid'])
    with (process/'stat').open('rb') as source:
        raw = source.read(16385)
    require(0<len(raw)<=16384)
    fields = raw.decode('ascii')[raw.rfind(b')')+2:].split()
    require(len(fields)>=20 and fields[0]!='Z' and fields[19]==owner['birth'])
    network = os.readlink(process/'ns/net')
    require(network==os.readlink('/proc/self/ns/net'))
    return process,network


def _owner_socket(owner, client_port, server_port):
    process,network = _owner(owner)
    require(type(client_port) is int and 0<client_port<65536)
    with (process/'net/tcp').open('rb') as source:
        raw = source.read(1048577)
    require(0<len(raw)<=1048576)
    rows = raw.decode('ascii').splitlines()
    require(len(rows)<=8193)
    expected_local = '0100007F:'+format(client_port,'04X')
    expected_remote = '0100007F:'+format(server_port,'04X')
    matching = []
    for line in rows[1:]:
        columns = line.split()
        require(len(columns)>=10)
        if columns[1]==expected_local and columns[2]==expected_remote and columns[3]=='01':
            require(columns[7]==str(owner['uid']) and re.fullmatch(r'[1-9][0-9]{0,19}',columns[9]))
            matching.append(columns[9])
    require(len(matching)==1)
    with os.scandir(process/'fd') as iterator:
        entries = []
        for index,entry in enumerate(iterator):
            require(index<4096)
            entries.append(entry.name)
    found = []
    for entry in entries:
        try:
            if os.readlink(process/'fd'/entry)=='socket:['+matching[0]+']':
                found.append(entry)
        except FileNotFoundError:
            continue
    require(len(found)==1 and _owner(owner)[1]==network)
    require(os.readlink(process/'fd'/found[0])=='socket:['+matching[0]+']')
    return {'network_namespace':network,'socket_inode':matching[0],'descriptor':found[0],
            'client_port':client_port,'server_port':server_port}


def observe_held_session(psql, database_url, snapshot, expected_database, *, owner=None):
    """Observe the original PID/birth, ordinary identity and existing lease.

    The caller independently admits the executable, private configuration and
    expected database. Neither an input snapshot nor this query grants a lease.
    """
    try:
        require(type(psql) is str and psql.startswith('/') and '\0' not in psql and len(psql)<=4096)
        environment = database_environment(database_url)
        environment.update(PGPASSFILE='/dev/null',PGOPTIONS=OBSERVATION_OPTIONS)
        validate_database(expected_database,environment)
        validate_session(snapshot,expected_database)
        if owner is not None:
            _owner(owner)
        # Only a validated integer is inserted; the SQL and advisory key are
        # fixed here, never supplied through a command or request field.
        statement = "SELECT json_build_object('database',("+SQL.strip().rstrip(';')+"), " \
            "'backend_pid',a.pid,'backend_birth',floor(extract(epoch FROM a.backend_start)*1000000)::bigint::text," \
            "'client_address',host(a.client_addr),'client_port',a.client_port," \
            "'held',EXISTS(SELECT 1 FROM pg_locks WHERE locktype='advisory' AND pid=a.pid " \
            "AND classid::bigint=1197034575 AND objid::bigint=1 AND objsubid=2 AND mode='ExclusiveLock' AND granted)) " \
            "FROM pg_stat_activity a WHERE a.pid="+str(snapshot['backend_pid'])+" AND a.backend_type='client backend' " \
            "AND a.usename=current_user AND a.datname=current_database()"
        observed = json.loads(_query_database(psql,environment,statement),object_pairs_hook=unique)
        require(type(observed) is dict and set(observed)=={'database','backend_pid','backend_birth','held','client_address','client_port'})
        require(observed['held'] is True)
        require(observed['client_address']=='127.0.0.1' and type(observed['client_port']) is int and 0<observed['client_port']<65536)
        current = {key:observed[key] for key in snapshot}
        validate_session(current,expected_database)
        require(current==snapshot)
        result = {'original_backend_present':True,'existing_lease_observed':True,'session':current,'lease_acquired':False,
                  'owner_connection_observed':False}
        if owner is not None:
            connection = _owner_socket(owner,observed['client_port'],expected_database['port'])
            require(_owner_socket(owner,observed['client_port'],expected_database['port'])==connection)
            result.update(owner_connection_observed=True,owner_connection=connection)
        return result
    except (DatabaseRefused,OSError,ValueError,TypeError,KeyError,UnicodeError,RecursionError,subprocess.SubprocessError):
        raise DatabaseRefused('Native ownership database session unavailable') from None
