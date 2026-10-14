"""Read-only observation of one original native lease backend; never reacquire."""
import json
import os
from pathlib import Path
import re
import selectors
import socket
import struct
import subprocess
import time

from native_durable_database import SQL, DatabaseRefused, unique, validate_database
from native_inventory import database_environment


def require(value):
    if not value:
        raise DatabaseRefused('Native ownership database session unavailable')


OBSERVATION_OPTIONS = '-c statement_timeout=3000 -c default_transaction_read_only=on -c search_path=pg_catalog'

ROOT_EXCLUSION_SQL = """SELECT json_build_object('database',("""+SQL+"""),
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
    result = _socket_for_process(process,network,owner['uid'],client_port,server_port)
    require(_owner(owner) == (process,network))
    return result


def _tcp_socket_reply(raw, sequence, port_id, uid, client_port, server_port):
    """Decode one bounded kernel reply; never accept a dump or partial identity."""
    require(type(raw) is bytes and 88 <= len(raw) <= 4096)
    length,kind,flags,observed_sequence,observed_port = struct.unpack_from('=IHHII',raw)
    require(kind == 20 and flags == 0 and observed_sequence == sequence and observed_port == port_id)
    require(88 <= length <= len(raw) and ((length+3)&~3) == len(raw))
    require(not any(raw[length:]))
    body = raw[16:length]
    require(body[0] == socket.AF_INET and body[1] == 1)
    require(struct.unpack_from('!HH',body,4) == (client_port,server_port))
    loopback = socket.inet_pton(socket.AF_INET,'127.0.0.1')+bytes(12)
    require(body[8:24] == loopback and body[24:40] == loopback)
    require(struct.unpack_from('=I',body,40)[0] == 0)
    observed_uid,inode = struct.unpack_from('=II',body,64)
    require(observed_uid == uid and inode > 0)
    # Kernels add bounded attributes even when no extensions are requested.
    # They are not identity/authority inputs, but their complete framing must
    # be valid. Never read a partial or concatenated netlink message as success.
    offset = 72;seen = set()
    while offset < len(body):
        require(len(seen) < 64 and len(body)-offset >= 4)
        size,attribute = struct.unpack_from('=HH',body,offset)
        require(size >= 4 and attribute > 0 and attribute not in seen and size <= len(body)-offset)
        seen.add(attribute);aligned = (size+3)&~3
        require(aligned <= len(body)-offset and not any(body[offset+size:offset+aligned]))
        offset += aligned
    require(offset == len(body))
    return str(inode)


def _tcp_socket_inode(uid, client_port, server_port):
    """Fresh read-only SOCK_DIAG_BY_FAMILY query for a fixed IPv4 TCP tuple."""
    require(type(uid) is int and 0 <= uid < 2**32)
    require(type(client_port) is int and 0<client_port<65536)
    require(type(server_port) is int and 0<server_port<65536)
    loopback = socket.inet_pton(socket.AF_INET,'127.0.0.1')+bytes(12)
    identity = struct.pack('!HH',client_port,server_port)+loopback+loopback+struct.pack('=III',0,2**32-1,2**32-1)
    request = struct.pack('=BBBBI',socket.AF_INET,socket.IPPROTO_TCP,0,0,2)+identity
    require(len(request) == 56)
    sequence = int.from_bytes(os.urandom(4),'little') or 1
    # Type20 is observation; no dump, ACK, multicast or destroy flag exists.
    with socket.socket(socket.AF_NETLINK,socket.SOCK_RAW,4) as observer:
        observer.settimeout(2);observer.bind((0,0))
        port_id,groups = observer.getsockname()
        require(type(port_id) is int and 0 < port_id < 2**32 and groups == 0)
        message = struct.pack('=IHHII',72,20,1,sequence,port_id)+request
        require(observer.sendto(message,(0,0)) == len(message))
        raw,ancillary,flags,address = observer.recvmsg(4096)
        require(not ancillary and flags == 0 and address == (0,0))
        return _tcp_socket_reply(raw,sequence,port_id,uid,client_port,server_port)


def _socket_for_process(process, network, uid, client_port, server_port):
    """Private socket primitive; independent caller admission remains required."""
    require(os.readlink(process/'ns/net') == network == os.readlink('/proc/self/ns/net'))
    inode = _tcp_socket_inode(uid,client_port,server_port)
    with os.scandir(process/'fd') as iterator:
        entries = []
        for index,entry in enumerate(iterator):
            require(index<4096)
            entries.append(entry.name)
    found = []
    for entry in entries:
        try:
            if os.readlink(process/'fd'/entry)=='socket:['+inode+']':
                found.append(entry)
        except FileNotFoundError:
            continue
    require(len(found)==1)
    require(os.readlink(process/'fd'/found[0])=='socket:['+inode+']')
    require(os.readlink(process/'ns/net') == network == os.readlink('/proc/self/ns/net'))
    return {'network_namespace':network,'socket_inode':inode,'descriptor':found[0],
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
