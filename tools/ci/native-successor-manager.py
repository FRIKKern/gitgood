#!/usr/bin/env python3
"""Actual ordinary systemd MainPID serving production protocol-4 handoffs.

The three fixture owners use migrate/migrate/runtime modes. No business
migration/bootstrap, product lifecycle policy/history, or product startup is
fabricated. Production endpoint, custody, reservation and handoff are unchanged.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, '/opt/gitgood/native/v2')
from generation_custody import GenerationRecordCustody
from generation_publication import GenerationPublication
from native_command_endpoint import NativeCommandEndpoint
from native_durable_binding import observe_durable_binding
from native_ownership_controller import NativeOwnershipController
from native_ownership_handoff import serve_once
from native_ownership_records import OwnershipRecordRefused
from native_lifecycle_responsibility import NativeLifecycleResponsibility, sha
from native_service_scope import group_identity
from native_public_runtime import NativePublicRuntime, PublicRuntimeRefused

spec = importlib.util.spec_from_file_location('owned_fixture', Path(__file__).with_name('native-owned-manager.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
STAGES = (('migration-owner', 'migrate'), ('bootstrap-owner', 'migrate'), ('runtime-owner', 'runtime'))


def serve(controller, run):
    assignment = json.loads(json.dumps(controller.assignment))
    try:
        return serve_once(controller)
    except OwnershipRecordRefused:
        # A repeated admission after completed publication must reach the real
        # endpoint and refuse without changing the captured assignment/history.
        if controller.state != 'complete' or controller.assignment != assignment:
            raise
        controller.store.check()
        path = run / 'repeat-admission-refused.json'
        if path.exists():
            raise RuntimeError('Unexpected additional refused request')
        fixture.write(path, {'actual_endpoint_refused': True, 'controller_state': 'complete',
                             'assignment_preserved': True, 'claim': controller.claim})


def main(seed_path):
    seed = json.loads(Path(seed_path).read_bytes())
    run, root, seal = (Path(seed[name]) for name in ('run', 'root', 'seal_directory'))
    deadline = time.monotonic() + 300
    phase = 'delegation'
    controller = endpoint = custody = journal = None
    os.umask(0o077)
    try:
        assert os.getuid() == os.geteuid() == seed['uid'] > 0
        assert os.getgid() == os.getegid() == seed['gid'] > 0
        assert not (run / 'observed.json').exists()
        assert not (root / 'history/lifecycle-responsibility-v2').exists()
        assert not (seal / 'lifecycle-worker-admission-v2.json').exists()
        parent = Path('/sys/fs/cgroup/system.slice') / seed['unit']
        assert os.getxattr(parent, 'user.delegate') == b'1'
        assert not (parent / 'cgroup.procs').read_text().strip()
        (parent / 'cgroup.subtree_control').write_text('+cpu +memory')
        for name in ('native', 'web', 'edge', 'maintenance'):
            (parent / name).mkdir()
        phase = 'observe-real-binding'
        observed = observe_durable_binding(seed['root'], seed['installation'], seed['unit_sha256'],
                                           seed['executables'], **seed['limits'])
        fixture.write(run / 'observed.json', observed)
        expected = fixture.wait(seal / 'generation-admission-v2.json', deadline)
        assert expected['binding_sha256'] == observed['binding_sha256']
        phase = 'publish-generation'
        import datetime
        published = GenerationPublication(seed['root'], seed['installation'], expected['binding_sha256'],
            expected['history_identity'], expected['lock_identity'], seed['unit_sha256'],
            seed['executables'], **seed['limits']).publish(operation=seed['generation_operation'],
            generation=seed['generation'], created_at=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ'))
        fixture.write(run / 'published.json', published)
        fixture.wait(seal / 'fixture-start.json', deadline)
        phase = 'open-actual-controller'
        custody = GenerationRecordCustody(root / 'history', seed['installation'],
                                          expected['history_identity'], expected['lock_identity'])
        custody.__enter__()
        endpoint = NativeCommandEndpoint(seed['installation'])
        controller = NativeOwnershipController(seed['installation'], custody, endpoint)
        if seed.get('lifecycle_fixture'):
            # These stages exercise the actual sealed journal/input transport.
            # Their receipts deliberately describe fixture metadata, not
            # application inspection, staging or business effects.
            directory = Path('/var/lib/gitgood/operation-inputs') / seed['installation'] / seed['ownership_operation']
            request = json.loads((directory / 'request.json').read_bytes())
            policy = json.loads((seal / 'lifecycle-worker-admission-v2.json').read_bytes())
            journal = NativeLifecycleResponsibility(custody, request, policy['inputs_seal_sha256'],
                published['pointer']['generation_sha256'])
            journal.claim()
            fixture_observation = {'fixture_only': True, 'business_stage_effects_verified': False}
            for stage in ('inspect', 'stage'):
                journal.begin(stage);journal.succeed(stage, sha(fixture_observation))
        fixture.write(run / 'controller-open.json', {'actual_main_pid': os.getpid(),
                       'controller_identity': controller.scope['manager']})
        configuration = json.loads((root / 'configuration/installation.json').read_bytes())
        for label, mode in STAGES:
            stage = run / label
            stage.mkdir(mode=0o700)
            phase = label + '-reserve'
            if journal is not None:
                journal.begin({'migration-owner': 'migrate', 'bootstrap-owner': 'bootstrap', 'runtime-owner': 'verify'}[label])
            reservation = controller.reserve(mode)
            fixture.write(stage / 'reserved.json', reservation)
            # Root observes the actual held SQL/kernel exclusion before this
            # new owner exists. This is fixture scheduling, not admission.
            fixture.wait(seal / ('fixture-launch-' + label + '.json'), deadline)
            leaf = parent / ('native' if mode == 'runtime' else 'maintenance')
            leaf_identity = group_identity(leaf, seed['uid'])
            environment = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
                'HOME': str(stage), 'ERL_CRASH_DUMP': '/dev/null', 'ERL_CRASH_DUMP_SECONDS': '0',
                'RELEASE_TMP': str(stage), 'RELEASE_DISTRIBUTION': 'none',
                'ERL_FLAGS': '+S 2:2 +SDio 1 +SDcpu 1', **configuration['forge'],
                'GITGOOD_SUPERVISION_PROFILE': 'systemd-v2', 'PHX_SERVER': 'true' if mode == 'runtime' else 'false',
                'GITGOOD_GIT': seed['executables']['git'], 'GITGOOD_PYTHON': seed['executables']['python'],
                'GITGOOD_OWNED_PROOF_DIRECTORY': str(stage), 'GITGOOD_OWNED_PROOF_CONTROLLER_MODE': mode}
            if journal is not None:
                environment['GITGOOD_OWNED_PROOF_LIFECYCLE_ACTION'] = {
                    'migration-owner': 'migrate', 'bootstrap-owner': 'bootstrap', 'runtime-owner': 'runtime'}[label]
            if seed.get('business_inputs_fixture'):
                environment['GITGOOD_OWNED_PROOF_PRIVATE_INPUTS'] = 'true'
            if seed.get('business_effects_fixture'):
                environment['GITGOOD_OWNED_PROOF_MAINTENANCE_EFFECTS'] = 'true'
            if seed.get('runtime_effects_fixture'):
                environment['GITGOOD_OWNED_PROOF_RUNTIME_EFFECTS'] = 'true'
            if journal is not None and label == 'migration-owner':
                phase = 'wrong-bootstrap-action-in-migration-window'
                trial = stage / 'refused-trial';trial.mkdir(mode=0o700)
                trial_env = {**environment, 'GITGOOD_OWNED_PROOF_DIRECTORY': str(trial),
                             'GITGOOD_OWNED_PROOF_LIFECYCLE_ACTION': 'bootstrap'}
                with (trial / 'worker.private.log').open('xb') as trial_output:
                    rejected = fixture.launch([seed['release'] + '/bin/gitgood', 'eval',
                        'Code.eval_file("' + seed['worker'] + '")'], leaf, environment=trial_env, output=trial_output)
                    until = time.monotonic() + 30
                    while rejected.poll() is None:
                        assert time.monotonic() < until
                        serve(controller, trial)
                    assert rejected.returncode != 0 and not (trial / 'attached.json').exists()
                assert controller.state == 'reserved' and controller.assignment is None
                controller.exclusion.check()
                assert group_identity(leaf, seed['uid']) == leaf_identity
                (leaf / 'cgroup.kill').write_text('1')
                until = time.monotonic() + 5
                while 'populated 0' not in (leaf / 'cgroup.events').read_text():
                    assert time.monotonic() < until;time.sleep(.05)
                fixture.write(stage / 'wrong-action-refused.json', {'requested_action': 'bootstrap',
                    'recorded_stage': 'migrate', 'before_handoff_and_lease': True, 'fixture_probe_started': False})
                fixture.wait(seal / 'fixture-correct-action.json', deadline)
            phase = label + '-actual-admission-and-publication'
            with (stage / 'worker.private.log').open('xb') as output:
                default_stage = seed.get('default_release_fixture') and label == 'runtime-owner'
                arguments = [seed['release'] + '/bin/gitgood', 'start'] if default_stage else [
                    seed['release'] + '/bin/gitgood', 'eval', 'Code.eval_file("' + seed['worker'] + '")']
                if default_stage:
                    environment = {key: value for key, value in environment.items() if not key.startswith('GITGOOD_OWNED_PROOF_')}
                beam = fixture.launch(arguments, leaf, environment=environment, output=output)
                fixture.write(stage / 'launched.json', {'launcher_pid': beam.pid})
                sentinel = None
                public = None
                public_stage = seed.get('public_runtime_fixture') and label == 'runtime-owner'
                while beam.poll() is None:
                    assert time.monotonic() < deadline
                    serve(controller, stage)
                    if default_stage and controller.state == 'complete' and not (stage / 'default-owner.json').exists():
                        fixture.write(stage / 'default-owner.json', {'record': controller.record,
                            'release_command': 'start', 'fixture_runtime_application_substitution': False})
                    if public_stage and (seal / 'fixture-start-public-runtime.json').exists() and public is None:
                        public = NativePublicRuntime(controller)
                        public.start()
                        fixture.write(stage / 'public-services.json', {'web': public.births['web'], 'edge': public.births['edge'],
                            'fixed_production_launcher_used': True, 'public_activation_verified': False})
                    observe_native_abort_first = default_stage and (seal / 'fixture-observe-native-abort-first.json').exists()
                    if observe_native_abort_first and not (stage / 'native-abort-observation-ready.json').exists():
                        assert public is not None and public.state == 'running' and public.closed_receipt is None
                        fixture.write(stage / 'native-abort-observation-ready.json',
                            {'original_release_running': True, 'public_stop_deferred_until_native_exit': True})
                    if public is not None and public.state == 'running' and not observe_native_abort_first:
                        try:
                            public.check()
                        except PublicRuntimeRefused:
                            fixture.write(stage / 'public-quiescent.json', public.stop())
                    if not public_stage and (seal / ('fixture-sentinel-' + label + '.json')).exists() and sentinel is None:
                        sentinel = fixture.launch(['/usr/bin/sleep', '300'], parent / 'web',
                            environment={'PATH': '/usr/bin:/bin'}, output=subprocess.DEVNULL)
                        fixture.write(stage / 'sentinel.json', {'sentinel_pid': sentinel.pid})
                if default_stage:
                    assert public is not None and public.state == 'running' and public.closed_receipt is None
                    assert (seal / 'fixture-observe-native-abort-first.json').exists()
                fixture.write(stage / 'owner-exited.json', {'exit_code': beam.returncode,
                    'fixture_signalled_beam': False,
                    'public_stop_deferred_until_native_release_exit': bool(default_stage)})
                if public_stage:
                    assert public is not None
                    if not (stage / 'public-quiescent.json').exists():
                        fixture.write(stage / 'public-quiescent.json', public.stop())
                else:
                    assert sentinel is not None and sentinel.poll() is None
                phase = label + '-await-original-absence'
                fixture.wait(seal / ('fixture-cleanup-' + label + '.json'), deadline)
                assert group_identity(leaf, seed['uid']) == leaf_identity
                if not public_stage:
                    (leaf / 'cgroup.kill').write_text('1')
                until = time.monotonic() + 10
                while 'populated 0' not in (leaf / 'cgroup.events').read_text():
                    assert time.monotonic() < until
                    time.sleep(.1)
                assert group_identity(leaf, seed['uid']) == leaf_identity
                if public_stage:
                    fixture.write(stage / 'quiescent.json', {'selected_leaf_empty': True,
                        'cleanup_actor': 'native-public-runtime', 'fixed_public_runtime_cleanup_verified': True})
                else:
                    assert sentinel.poll() is None
                    fixture.write(stage / 'quiescent.json', {'selected_leaf_empty': True, 'sibling_preserved': True,
                        'cleanup_actor': 'fixture-manager', 'product_controller_cleanup_verified': False})
                fixture.wait(seal / ('fixture-reap-sentinel-' + label + '.json'), deadline)
                # This exact owned Popen child is reaped before another reserve;
                # no unrelated service/process is touched or assumed absent.
                if not public_stage:
                    sentinel.terminate()
                    sentinel.wait(timeout=5)
                    fixture.write(stage / 'sibling-reaped.json', {'original_sibling_reaped': True})
                else:
                    fixture.write(stage / 'sibling-reaped.json', {'original_public_services_reaped': True})
                phase = label + '-await-root-next'
                fixture.wait(seal / ('fixture-next-' + label + '.json'), deadline)
                if seed.get('schema_refusal_fixture') or seed.get('inventory_refusal_fixture') or (
                        seed.get('runtime_schema_refusal_fixture') and label == 'runtime-owner'):
                    assert label == ('runtime-owner' if seed.get('runtime_schema_refusal_fixture') else 'migration-owner')
                    fixture.write(run / 'controller-maintenance-refusal-complete.json',
                        {'claims': 3 if label == 'runtime-owner' else 1, 'fixture_did_not_advance_lifecycle': True})
                    phase = 'await-root-stop-after-schema-refusal'
                    while time.monotonic() < deadline:
                        controller._controller()
                        time.sleep(.25)
                    raise TimeoutError('Fixture observer did not stop refused unit')
                if journal is not None:
                    journal.succeed(journal.snapshot['stage'], sha({'fixture_only': True,
                        'business_stage_effects_verified': False, 'ownership_boundary_observed': label}))
        fixture.write(run / 'controller-chain-complete.json', {'actual_controller_handoff_completed': True,
            'claims': 3, 'same_controller': True, 'same_boot_and_generation': True,
            'business_lifecycle_stages_executed': False})
        phase = 'await-root-stop'
        while time.monotonic() < deadline:
            controller._controller()
            time.sleep(.25)
        raise TimeoutError('Fixture observer did not stop its unit')
    except Exception as error:
        if controller is not None and controller.state in {'preparing', 'reserved', 'assigning', 'assigned', 'publishing', 'complete'}:
            # Closed state vocabulary locates the failed boundary without
            # exception messages, SQL, credentials, arguments or stack traces.
            phase = 'handoff-' + controller.state
        fixture.write(run / 'manager-failed.json', {'phase': phase, 'error_type': type(error).__name__})
        while time.monotonic() < deadline:
            time.sleep(.25)
        return 0
    finally:
        if journal is not None:journal.close()
        if controller is not None:
            controller.close()
        if endpoint is not None:
            endpoint.close()
        if custody is not None:
            custody.__exit__(None, None, None)


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1]))
