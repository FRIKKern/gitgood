"""Fixed bounded observation stream; no database lease or lifecycle effects."""
import json
import os
import selectors
from pathlib import Path
import sys
import time

from native_durable_database import DatabaseRefused, unique, validate_database
from native_lifecycle_generation_reader import open_reader
from native_generation_lease_guard import NativeGenerationLeaseGuard
from native_monitor_ownership_attachment import MonitorOwnershipAttachment
from native_monitor_business_inputs import MonitorBusinessInputs
from native_service_scope import root_file
from resource_generations import GenerationRefused, canonical, identifier


def require(value):
    if not value:
        raise ValueError('Native generation monitor unavailable')


def parse_request(raw):
    require(type(raw) is bytes and 0 < len(raw) <= 4096 and b'\0' not in raw)
    try:
        request = json.loads(raw, object_pairs_hook=unique)
    except DatabaseRefused:
        raise ValueError('Native generation monitor unavailable') from None
    require(type(request) is dict and set(request) == {'protocol','installation','worker','owner_pid'})
    require(type(request['protocol']) is int and request['protocol'] == 2)
    try:
        identifier(request['installation'])
    except GenerationRefused:
        raise ValueError('Native generation monitor unavailable') from None
    require(type(request['worker']) is str and request['worker'] in {'native','maintenance'})
    require(type(request['owner_pid']) is int and 1 < request['owner_pid'] < 2**31)
    return request


def open_guard(raw):
    request = parse_request(raw); installation = request['installation']
    path = Path('/etc/gitgood/installations') / installation / 'generation-admission-v2.json'
    identity, sealed = root_file(path, 16_384)
    seal = json.loads(sealed, object_pairs_hook=unique)
    require(sealed == canonical(seal))
    require(type(seal) is dict and set(seal) == {'protocol','kind','installation','binding_sha256',
            'history_identity','lock_identity','unit_sha256','executables','limits','database'})
    require(type(seal['protocol']) is int and seal['protocol'] == 2)
    require(seal['kind'] == 'native_generation_admission_seal' and seal['installation'] == installation)
    require(type(seal['limits']) is dict and set(seal['limits']) == {'cpu_quota_us','memory_bytes'})
    database = seal['database']; require(type(database) is dict)
    validate_database(database, {'PGDATABASE':database.get('database'),'PGUSER':database.get('role'),
                                 'PGPORT':str(database.get('port'))})
    reader = open_reader('/var/lib/gitgood/installations/' + installation, installation,
                                    seal['binding_sha256'], seal['history_identity'], seal['lock_identity'],
                                    seal['unit_sha256'], seal['executables'], worker=request['worker'], **seal['limits'])
    try:guard = NativeGenerationLeaseGuard(reader, worker=request['worker'], owner_pid=request['owner_pid'])
    except Exception:
        reader.close();raise
    return guard, request, seal, identity, sealed


def send(value, *, maximum=16_384):
    raw = canonical(value); require(len(raw) <= maximum)
    sys.stdout.buffer.write(raw + b'\n'); sys.stdout.buffer.flush()


def main():
    guard = None
    attachment = None
    business = None
    selector = None
    try:
        require(len(sys.argv) == 1)
        raw = sys.stdin.buffer.readline(4097)
        require(raw.endswith(b'\n') and len(raw) <= 4096)
        guard, request, seal, identity, sealed = open_guard(raw)
        captured = guard.capture(); admitted = captured['admission']
        require(admitted['published_generation_admitted'] and admitted['binding_sha256'] == seal['binding_sha256'])
        require(not admitted['writer_exclusion_established'] and not admitted['installation_readiness_established']
                and not admitted['lifecycle_responsibility_admitted'])
        require(root_file(Path(identity['path']), 16_384) == (identity, sealed))
        value = {'protocol':2,'installation':request['installation'],'worker':request['worker'],
                 'pointer':admitted['pointer'],'binding_sha256':admitted['binding_sha256'],
                 'worker_observation':admitted['worker_observation'],'database':seal['database'],
                 'seal_file':identity,'published_generation_admitted':True,
                 'writer_exclusion_established':False,'installation_readiness_established':False,
                 'lifecycle_responsibility_admitted':False}
        if 'lifecycle_observation' in admitted:
            value['lifecycle_observation'] = admitted['lifecycle_observation']
        token = {name:captured[name] for name in ['scope_sha256','history_sha256','persistent_files_sha256']}
        send({'protocol':2,'status':'admitted','admission':value,'guard':token})
        attachment = MonitorOwnershipAttachment(guard,captured,seal)
        selector = selectors.DefaultSelector()
        os.set_blocking(sys.stdin.fileno(),False)
        selector.register(sys.stdin.fileno(),selectors.EVENT_READ)
        next_check = time.monotonic()
        while True:
            events = selector.select(max(0,next_check-time.monotonic()))
            if events:
                require(root_file(Path(identity['path']),16_384)==(identity,sealed))
                if business is not None:
                    response = business.feed(os.read(sys.stdin.fileno(), business.maximum+1))
                    if response is not None:
                        require(root_file(Path(identity['path']),16_384)==(identity,sealed))
                        send(response, maximum=32_768)
                    continue
                attached = attachment.feed(os.read(sys.stdin.fileno(),attachment.maximum+1))
                if attached is not None:
                    require(attached['current']['current'] is True)
                    require({name:attached['current'][name] for name in token}==token)
                    require(root_file(Path(identity['path']),16_384)==(identity,sealed))
                    business = MonitorBusinessInputs(attachment, token, attached['ownership'])
                    send({'protocol':2,'status':'ownership_attached','guard':token,'ownership':attached['ownership']})
                continue
            next_check = time.monotonic() + 1
            require(root_file(Path(identity['path']), 16_384) == (identity, sealed))
            observed = attachment.check()
            current = observed['current']
            require(current['current'] is True and {name:current[name] for name in token} == token)
            require(root_file(Path(identity['path']), 16_384) == (identity, sealed))
            frame = {'protocol':2,'status':'current','guard':token}
            if 'ownership' in observed:frame['ownership']=observed['ownership']
            send(frame)
    except Exception:
        try:
            send({'protocol':2,'status':'refused'})
        except Exception:
            pass
        return 1
    finally:
        if selector is not None:
            selector.close()
        if attachment is not None:
            attachment.close()
        if guard is not None:
            try:
                guard.close()
            except Exception:
                pass


if __name__ == '__main__':
    raise SystemExit(main())
