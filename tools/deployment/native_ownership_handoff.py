"""Bounded authenticated local ownership handoff to the actual live controller."""
import json
import os
from pathlib import Path
import re
import socket
import stat
import sys
import time

from native_command_wire import _peer, receive_frame
from native_controller_scope import private_directory
from native_durable_database import unique
from native_generation_monitor import open_guard
from native_ownership_records import require, validate_record
from native_service_scope import process_identity, root_file
from resource_generations import canonical, identifier

RESPONSE_SECONDS=60.0


def decode_request(raw, installation):
    require(type(raw) is bytes and 0<len(raw)<=32768 and raw.endswith(b'\n') and raw.count(b'\n')==1)
    value=json.loads(raw[:-1],object_pairs_hook=unique)
    require(type(value) is dict and raw==canonical(value)+b'\n')
    require(type(value.get('protocol')) is int and value['protocol']==4 and value.get('kind')=='native_ownership_handoff')
    if value.get('action')=='admit':
        require(set(value)=={'protocol','kind','action','installation','operation','candidate','mode','owner_pid'})
        identifier(value['installation']);identifier(value['operation'])
        require(type(value['candidate']) is str and re.fullmatch('[0-9a-f]{40}',value['candidate']))
        require(value['installation']==installation and value['mode'] in {'runtime','migrate','backup','restore'})
        require(type(value['owner_pid']) is int and 1<value['owner_pid']<2**31)
    else:
        require(set(value)=={'protocol','kind','action','record'} and value['action']=='publish')
        validate_record(value['record']);require(value['record']['protocol']==4 and value['record']['installation']==installation)
    return value


def serve_once(controller, timeout=0.25):
    """Serve only ownership handoffs; no lifecycle command or arbitrary dispatch."""
    from native_ownership_controller import NativeOwnershipController
    require(type(controller) is NativeOwnershipController)
    try:controller._controller()
    except Exception:controller.close();raise
    endpoint=controller.endpoint;endpoint.check()
    connection=endpoint.endpoint.accept(timeout)
    if connection is None:
        try:controller._controller()
        except Exception:controller.close();raise
        return None
    try:
        endpoint.check();raw,peer=receive_frame(connection,uid=controller.scope['uid'],maximum=32768)
        request=decode_request(raw,controller.installation);endpoint.check()
        if request['action']=='admit':result=controller.admit(request,peer)
        else:result=controller.publish(request['record'],peer)
        require(_peer(connection,controller.scope['uid'])==peer);endpoint.check()
        payload=canonical(result)+b'\n';require(len(payload)<=4096)
        connection.settimeout(2);connection.sendall(payload);endpoint.check();return result
    except Exception:
        if controller.state=='assigning':controller.close()
        try:
            connection.settimeout(0.25);connection.sendall(b'{"protocol":4,"status":"refused"}\n')
        except OSError:pass
        raise
    finally:connection.close()


def _socket_identity(path, uid, gid):
    info=path.lstat()
    require(stat.S_ISSOCK(info.st_mode) and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1)
    require(info.st_uid==uid and info.st_gid==gid)
    return tuple(getattr(info,key) for key in ['st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_ctime_ns'])


def exchange(request, guard, captured):
    """The client authenticates the server's actual MainPID and birth, too."""
    admission=captured['admission'];scope=admission['worker_observation']['service_scope']
    installation=scope['installation'];uid,gid=scope['uid'],scope['gid']
    path=Path('/etc/gitgood/installations')/installation/'controller-endpoint-v2.json'
    seal_file,sealed=root_file(path,4096);seal=json.loads(sealed,object_pairs_hook=unique)
    require(sealed==canonical(seal) and set(seal)=={'protocol','kind','installation','uid','gid','unit_sha256','directory_identity','limits'})
    require(type(seal['protocol']) is int and seal['protocol']==2 and seal['kind']=='native_controller_endpoint_seal')
    require((seal['installation'],seal['uid'],seal['gid'])==(installation,uid,gid))
    require(seal['unit_sha256']==scope['unit_definition']['sha256'])
    require(type(seal['limits']) is dict and set(seal['limits'])=={'cpu_quota_us','memory_bytes'})
    require(scope['limits']=={**seal['limits'],'cpu_period_us':100000,'swap_bytes':0})
    directory=Path('/run/gitgood/installations')/installation;node=directory/'controller.sock'
    original=private_directory(directory,uid,gid);require(original[0]==seal['directory_identity'])
    socket_original=_socket_identity(node,uid,gid)
    deadline=time.monotonic()+RESPONSE_SECONDS
    def current(connection=None):
        require(time.monotonic()<deadline and guard.check()['current'] is True)
        require(root_file(path,4096)==(seal_file,sealed))
        require(private_directory(directory,uid,gid)==original and _socket_identity(node,uid,gid)==socket_original)
        require(process_identity(scope['manager']['pid'],uid,gid,scope['groups']['driver']['path'].removeprefix('/sys/fs/cgroup'))==scope['manager'])
        if connection is not None:
            require(_peer(connection,uid)=={'pid':scope['manager']['pid'],'uid':uid,'gid':gid})
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        current();connection.settimeout(min(2,deadline-time.monotonic()));connection.connect(str(node));current(connection)
        wire=canonical(request)+b'\n';require(len(wire)<=32768)
        connection.settimeout(min(2,deadline-time.monotonic()));connection.sendall(wire);connection.shutdown(socket.SHUT_WR)
        raw=bytearray()
        while b'\n' not in raw:
            remaining=deadline-time.monotonic();require(remaining>0)
            connection.settimeout(remaining);chunk=connection.recv(4097-len(raw));require(chunk)
            raw.extend(chunk);require(len(raw)<=4096)
        require(raw.count(b'\n')==1 and raw.endswith(b'\n'))
        value=json.loads(raw[:-1],object_pairs_hook=unique);require(bytes(raw)==canonical(value)+b'\n')
        current(connection);return value


def handoff(raw):
    guard=None
    try:
        require(type(raw) is bytes and 0<len(raw)<=32768)
        request=json.loads(raw,object_pairs_hook=unique);require(raw==canonical(request))
        require(type(request) is dict and type(request.get('protocol')) is int and request['protocol']==4)
        action=request.get('action')
        if action=='admit':
            require(set(request)=={'protocol','action','installation','mode','owner_pid'})
            installation,mode,owner=request['installation'],request['mode'],request['owner_pid']
        else:
            require(action=='publish' and set(request)=={'protocol','action','record'})
            record=request['record'];validate_record(record);require(record['protocol']==4)
            installation,mode,owner=record['installation'],record['mode'],record['owner']['pid']
        worker='native' if mode=='runtime' else 'maintenance'
        guard,_,_,_,_=open_guard(canonical({'protocol':2,'installation':installation,'worker':worker,'owner_pid':owner}))
        captured=guard.capture();admitted=captured['admission'];observed=admitted['worker_observation']
        authority_path=Path('/etc/gitgood/installations')/installation/'ownership-admission-v3.json'
        authority_file,authority_raw=root_file(authority_path,16384)
        authority=json.loads(authority_raw,object_pairs_hook=unique)
        require(authority_raw==canonical(authority) and set(authority)=={'protocol','kind','installation','operation','candidate','binding_sha256'})
        require(authority['protocol']==3 and authority['kind']=='native_application_ownership_seal')
        require(authority['installation']==installation and authority['binding_sha256']==admitted['binding_sha256'])
        if action=='admit':
            wire={'protocol':4,'kind':'native_ownership_handoff','action':'admit','installation':installation,
                  'operation':authority['operation'],'candidate':authority['candidate'],'mode':mode,'owner_pid':owner}
        else:
            require(record['owner']==observed['owner'] and record['scope']==observed['service_scope'] and record['pointer']==admitted['pointer'])
            require(record['guard']=={name:captured[name] for name in record['guard']})
            require(all(record[name]==authority[name] for name in ['installation','operation','candidate','binding_sha256']))
            wire={'protocol':4,'kind':'native_ownership_handoff','action':'publish','record':record}
        result=exchange(wire,guard,captured)
        require(root_file(authority_path,16384)==(authority_file,authority_raw))
        require(guard.check()['current'] is True)
        if action=='admit':
            require(set(result)=={'protocol','status','installation','operation','candidate','claim','mode','pointer',
                                 'predecessor_sha256','reservation_sha256','owner','controller'})
            require(result['protocol']==4 and result['status']=='admitted')
            require(all(result[name]==wire[name] for name in ['installation','operation','candidate','mode']))
            require(result['owner']==observed['owner'] and result['controller']==observed['service_scope']['manager'])
            require(result['pointer']==admitted['pointer'])
            identifier(result['claim'])
        return result
    finally:
        if guard is not None:guard.close()


def main():
    try:
        require(len(sys.argv)==1)
        raw=sys.stdin.buffer.readline(32770);require(raw.endswith(b'\n') and len(raw)<=32769)
        result=handoff(raw[:-1]);payload=canonical(result)+b'\n';require(len(payload)<=4096)
        sys.stdout.buffer.write(payload);sys.stdout.buffer.flush();return 0
    except Exception:
        sys.stdout.buffer.write(b'{"protocol":4,"status":"refused"}\n');sys.stdout.buffer.flush();return 1
