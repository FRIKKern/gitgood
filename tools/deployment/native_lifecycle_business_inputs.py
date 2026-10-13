"""Private business projections from an original held lifecycle guard; no effects."""
import copy
import hashlib
import json
import re


class LifecycleBusinessInputsRefused(Exception):
    pass


def require(value):
    if not value:
        raise LifecycleBusinessInputsRefused('Native lifecycle business inputs unavailable')


def closed(value, fields):
    return type(value) is dict and set(value) == set(fields)


def versions(value):
    require(type(value) is list and len(value) <= 1024)
    require(all(type(version) is int and 0 < version < 2**63 for version in value))
    require(value == sorted(set(value)))
    return list(value)


def bootstrap_projection(value, installation, operation):
    fields = ('installation', 'request', 'username', 'team', 'password')
    require(closed(value, fields) and all(type(value[name]) is str for name in fields))
    require(value['installation'] == installation and value['request'] == operation)
    require(all(re.fullmatch(r'[a-z][a-z0-9-]{1,39}', value[name]) for name in ('username', 'team')))
    require('\0' not in value['password'] and 12 <= len(value['password'].encode('utf-8')) <= 256)
    payload = ['gitgood-installation-owner-v1', *[value[name] for name in fields]]
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()
    return copy.deepcopy(value), digest


def _project(payloads, observed, action, installation):
    """Internal parser; observed must come from the guard's captured snapshot."""
    try:
        require(type(action) is str and action in {'migrate', 'bootstrap'})
        require(type(observed) is dict and observed['worker'] == 'maintenance')
        require(observed['recorded_status'] == 'running' and observed['stage'] == action)
        operation, candidate, purpose = (observed[name] for name in ('operation', 'candidate', 'purpose'))
        require(re.fullmatch(r'[0-9a-f]{40}', candidate))
        if purpose == 'native_initial_enrollment':
            document = payloads['inputs.json']
            fields = {'kind', 'installation', 'operation', 'candidate', 'migrations', 'bootstrap'}
            expected_kind = 'native_initial_business_inputs'
        else:
            require(purpose == 'native_upgrade_execution' and action == 'migrate')
            document = payloads['plan.json']
            fields = {'kind', 'installation', 'operation', 'candidate', 'migrations'}
            expected_kind = 'native_upgrade_business_inputs'
        require(type(document) is dict and type(document['protocol']) is int and document['protocol'] == 2)
        business = document['business']
        require(closed(business, fields) and business['kind'] == expected_kind)
        require((business['installation'], business['operation'], business['candidate']) ==
                (installation, operation, candidate))
        migration = business['migrations']
        require(closed(migration, {'before_versions', 'target_versions'}))
        before, target = versions(migration['before_versions']), versions(migration['target_versions'])
        require(target and set(before) <= set(target))
        if purpose == 'native_initial_enrollment':
            require(not before)
            bootstrap, bootstrap_sha = bootstrap_projection(business['bootstrap'], installation, operation)
        result = {'protocol': 2, 'kind': 'native_private_business_inputs', 'installation': installation,
                  'operation': operation, 'candidate': candidate, 'action': action,
                  'migrations': {'before_versions': before, 'target_versions': target}}
        if action == 'bootstrap':
            result.update(bootstrap=bootstrap, bootstrap_request_sha256=bootstrap_sha)
        return result
    except Exception:
        raise LifecycleBusinessInputsRefused('Native lifecycle business inputs unavailable') from None
