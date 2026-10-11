"""Fixed read-only kernel observation for a Root-scoped worker's SQL lease.

The Root-sealed server scope is separate from the untrusted request. This
observation retains no ownership, acquires no lease and authorizes no effects.
"""
import hashlib
import json
from pathlib import Path
import sys

from native_durable_binding import configuration, executable
from native_durable_database import unique
from native_generation_monitor import open_guard
from native_kernel_backend import capture_backend_kernel_identity, _validate_record, _validate_scope
from native_ownership_database import validate_session
from native_service_scope import root_file
from native_worker_scope import observe_worker
from resource_generations import canonical, identifier

MAXIMUM = 8192


class BackendObservationRefused(Exception):
    pass


def require(value):
    if not value:
        raise BackendObservationRefused('Native backend observation unavailable')


def parse_request(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAXIMUM and b'\0' not in raw)
    value = json.loads(raw, object_pairs_hook=unique)
    require(type(value) is dict and set(value) == {'protocol','kind','installation','worker','owner_pid','database_session'})
    require(type(value['protocol']) is int and value['protocol'] == 2)
    require(value['kind'] == 'native_backend_observation')
    identifier(value['installation'])
    require(type(value['worker']) is str and value['worker'] in {'native','maintenance'})
    require(type(value['owner_pid']) is int and 1 < value['owner_pid'] < 2**31)
    require(type(value['database_session']) is dict)
    require(raw == canonical(value))
    return value


def observe_request(raw):
    guard = None
    try:
        request = parse_request(raw)
        simple = {key:request[key] for key in ['protocol','installation','worker','owner_pid']}
        guard, _, admission, admission_file, admission_bytes = open_guard(canonical(simple))
        database = admission['database']; snapshot = request['database_session']
        validate_session(snapshot, database)
        options = {**admission['limits'], 'worker':request['worker'], 'owner_pid':request['owner_pid'],
                   '_root_files':guard.root_files}
        observed = observe_worker(request['installation'], admission['unit_sha256'], **options)
        scope_path = (Path('/etc/gitgood/installations') / request['installation'] /
                      ('backend-kernel-' + observed['service_scope']['boot_id'] + '.json'))
        scope_file, scope_bytes = root_file(scope_path, 4096)
        scope_seal = json.loads(scope_bytes, object_pairs_hook=unique)
        require(scope_bytes == canonical(scope_seal))
        require(type(scope_seal) is dict and set(scope_seal) == {'protocol','kind','installation','server_scope'})
        require(type(scope_seal['protocol']) is int and scope_seal['protocol'] == 2)
        require(scope_seal['kind'] == 'native_backend_kernel_scope_seal')
        require(scope_seal['installation'] == request['installation'])
        server_scope = scope_seal['server_scope']; _validate_scope(server_scope)
        require(server_scope['boot_id'] == observed['service_scope']['boot_id'])
        root = Path('/var/lib/gitgood/installations') / request['installation']
        before, url = configuration(root, request['installation'], observed['service_scope']['uid'])
        psql = executable(admission['executables']['psql'])
        owner = {key:observed['owner'][key] for key in ['pid','birth','uid']}
        record = capture_backend_kernel_identity(psql['path'], url, snapshot, database, server_scope, owner=owner)
        _validate_record(record, snapshot, database, server_scope)
        require(configuration(root, request['installation'], observed['service_scope']['uid']) == (before,url))
        require(executable(admission['executables']['psql']) == psql)
        require(root_file(scope_path,4096) == (scope_file,scope_bytes))
        require(root_file(Path(admission_file['path']),16384) == (admission_file,admission_bytes))
        require(observe_worker(request['installation'],admission['unit_sha256'],**options) == observed)
        guard.root_files.freeze()
        result = {'protocol':2,'status':'observed','installation':request['installation'],
                  'worker':request['worker'],'owner_pid':request['owner_pid'],'owner':observed['owner'],'kernel_record':record,
                  'service_scope_sha256':hashlib.sha256(canonical(observed['service_scope'])).hexdigest(),
                  'ownership_retained':False,'writer_exclusion_established':False,
                  'installation_readiness_established':False,'replacement_admitted':False}
        require(len(canonical(result)) <= 4096)
        return result
    finally:
        if guard is not None:
            guard.close()


def main():
    try:
        require(len(sys.argv) == 1)
        raw = sys.stdin.buffer.readline(MAXIMUM + 2)
        require(raw.endswith(b'\n') and len(raw) <= MAXIMUM + 1)
        result = observe_request(raw[:-1])
        sys.stdout.buffer.write(canonical(result) + b'\n'); sys.stdout.buffer.flush()
        return 0
    except Exception:
        sys.stdout.buffer.write(b'{"protocol":2,"status":"refused"}\n'); sys.stdout.buffer.flush()
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
