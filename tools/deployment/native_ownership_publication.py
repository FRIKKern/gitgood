"""Fixed ownership publication admission; no shell, cleanup, signal or lease acquisition.

Prior ownership responsibility still requires controller reconciliation. This
entry admits an initial claim or its identical live retry, never a replacement.
"""
import json
import os
from pathlib import Path
import sys

from native_durable_binding import configuration
from native_durable_database import unique
from native_generation_monitor import open_guard
from native_backend_scope import NativeBackendScope
from native_kernel_backend import observe_held_backend_kernel_identity
from native_ownership_markers import NativeOwnershipMarkers
from native_ownership_records import OwnershipRecordRefused, validate_record
from native_service_scope import root_file
from resource_generations import canonical


def require(value):
    if not value:
        raise OwnershipRecordRefused('Native ownership publication unavailable')


def parse_request(raw):
    require(type(raw) is bytes and 0<len(raw)<=32768 and b'\0' not in raw)
    request = json.loads(raw,object_pairs_hook=unique)
    require(type(request) is dict and set(request)=={'protocol','record'})
    require(type(request['protocol']) is int and request['protocol']==3)
    require(raw==canonical(request))
    validate_record(request['record'])
    return request['record']


def publish_request(raw):
    guard = None
    try:
        record = parse_request(raw)
        installation = record['installation']
        worker = 'native' if record['mode']=='runtime' else 'maintenance'
        seal_path = Path('/etc/gitgood/installations')/installation/'ownership-admission-v3.json'
        seal_file,sealed = root_file(seal_path,16384)
        authority = json.loads(sealed,object_pairs_hook=unique)
        require(sealed==canonical(authority))
        require(type(authority) is dict and set(authority)=={'protocol','kind','installation','operation','candidate','binding_sha256'})
        require(type(authority['protocol']) is int and authority['protocol']==3)
        require(authority['kind']=='native_application_ownership_seal')
        require(all(authority[key]==record[key] for key in ['installation','operation','candidate','binding_sha256']))
        backend_scope=NativeBackendScope(installation,record['scope']['boot_id'])
        require(backend_scope.check()==record['backend_kernel']['server_scope'])
        guard_request = canonical({'protocol':2,'installation':installation,'worker':worker,'owner_pid':record['owner']['pid']})
        guard,request,seal,admission_identity,admission_bytes = open_guard(guard_request)
        captured = guard.capture()
        admitted = captured['admission']
        require(admitted['binding_sha256']==record['binding_sha256'] and admitted['pointer']==record['pointer'])
        require(admitted['worker_observation']['service_scope']==record['scope'])
        require(admitted['worker_observation']['owner']==record['owner'])
        require({key:captured[key] for key in record['guard']}==record['guard'])
        binding = guard.snapshot['binding']
        require(binding['database']==seal['database']==record['database_session']['database'])
        root = Path('/var/lib/gitgood/installations')/installation
        storage = binding['resources']['storage']
        require(storage['path']==str(root/'storage'))
        custody = NativeOwnershipMarkers(storage['path'],installation,{key:storage[key] for key in ['device','inode','uid']})
        retained = custody.inspect()
        # Unknown, partial or prior responsibility is retained and refused.
        # A later controller reconciliation must prove owner, backend and
        # descendants absent before replacing this initial-only admission.
        require(all(value==record for value in retained['records']))
        if not retained['records']:
            for name in ['.gitgood-runtime-v2.json','.gitgood-maintenance-v2.json']:
                try:
                    (root/'storage'/name).lstat()
                except FileNotFoundError:
                    continue
                raise OwnershipRecordRefused('Existing marker requires reconciliation')
        owner = {key:record['owner'][key] for key in ['pid','birth','uid']}
        def session():
            files,url = configuration(root,installation,record['scope']['uid'])
            require(files==binding['configuration'])
            result = observe_held_backend_kernel_identity(seal['executables']['psql'],url,record['backend_kernel'],seal['database'],backend_scope.check(),owner=owner)
            require(result['owner_connection_observed'] and result['lease_acquired'] is False)
            require(result['original_backend_kernel_observed'] is True)
            require(configuration(root,installation,record['scope']['uid'])==(files,url))
            return result
        def current():
            require(guard.check()['current'] is True)
            require(root_file(seal_path,16384)==(seal_file,sealed))
            require(root_file(Path(admission_identity['path']),16384)==(admission_identity,admission_bytes))
            require(backend_scope.check()==record['backend_kernel']['server_scope'])
        current();session();current()
        custody.retain(record)
        current();session();current()
        result = custody.publish(record)
        current();session();current()
        require(custody.inspect()['records']==[record])
        return {'protocol':3,'status':'retained',**result,'writer_exclusion_established':False,
                'lifecycle_responsibility_admitted':False}
    finally:
        if guard is not None:
            guard.close()


def main():
    try:
        require(len(sys.argv)==1)
        raw = sys.stdin.buffer.readline(32770)
        require(raw.endswith(b'\n') and len(raw)<=32769)
        value = canonical(publish_request(raw[:-1]))
        require(len(value)<=4096)
        sys.stdout.buffer.write(value+b'\n');sys.stdout.buffer.flush()
        return 0
    except Exception:
        sys.stdout.buffer.write(b'{"protocol":3,"status":"refused"}\n');sys.stdout.buffer.flush()
        return 1


if __name__=='__main__':
    raise SystemExit(main())
