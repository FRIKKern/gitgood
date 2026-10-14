#!/usr/bin/env python3
"""Pure/local fixture regressions; no root service, database, or VM effects."""
import contextlib
import ast
import importlib.util
import io
import json
import os
import re
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("native_owned_proof", HERE / "native-owned-proof.py")
proof = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proof)


class BoundedProofTests(unittest.TestCase):
    @contextlib.contextmanager
    def fixture_file_host(self):
        with contextlib.ExitStack() as stack:
            if os.name == 'nt':
                for name in ('fchmod','fchown'):
                    stack.enter_context(patch.object(proof.os,name,create=True))
                stack.enter_context(patch.object(proof.os,'O_NOFOLLOW',0,create=True))
            yield getattr(os,'getuid',lambda:0)(),getattr(os,'getgid',lambda:0)()

    def test_fixture_signal_is_invisible_until_complete_publication(self):
        actual_fdopen = os.fdopen
        with tempfile.TemporaryDirectory() as scratch,self.fixture_file_host() as (uid,gid):
            path = Path(scratch)/'signal.json';observations = []
            class Barrier:
                def __init__(self,fd,mode):self.file = actual_fdopen(fd,mode)
                def __enter__(self):return self
                def __exit__(self,*args):return self.file.__exit__(*args)
                def __getattr__(self,name):return getattr(self.file,name)
                def write(self,data):
                    observations.append(path.exists())
                    return self.file.write(data)
            with patch.object(proof.os,'fdopen',side_effect=Barrier):
                proof.write_new(path,{'exclusion_observed':True},uid=uid,gid=gid)
            self.assertEqual(observations,[False])
            self.assertEqual(json.loads(path.read_bytes()),{'exclusion_observed':True})
            self.assertEqual([item.name for item in Path(scratch).iterdir()],['signal.json'])

    def test_foreign_signal_created_before_publication_is_retained_with_original_partial(self):
        actual_sync = os.fsync
        with tempfile.TemporaryDirectory() as scratch,self.fixture_file_host() as (uid,gid):
            path = Path(scratch)/'signal.json';calls = []
            def race(fd):
                calls.append(fd)
                if len(calls) == 1:path.write_bytes(b'foreign original signal')
                return actual_sync(fd)
            with patch.object(proof.os,'fsync',side_effect=race),self.assertRaises(OSError):
                proof.write_new(path,{'exclusion_observed':True},uid=uid,gid=gid)
            self.assertEqual(path.read_bytes(),b'foreign original signal')
            partials = list(Path(scratch).glob('.fixture-*.partial'))
            self.assertEqual(len(partials),1)
            self.assertEqual(json.loads(partials[0].read_bytes()),{'exclusion_observed':True})

    def test_manager_source_location_omits_message_payload_paths_and_traceback(self):
        path = HERE/'native-owned-manager.py'
        tree = ast.parse(path.read_text())
        function = next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name == 'failure_site')
        namespace = {'__file__':str(path),'Path':Path,'re':re}
        exec(compile(ast.Module(body=[function],type_ignores=[]),str(path),'exec'),namespace)
        private = 'private password, SQL and configuration'
        caller = compile('def fixture_failure():\n    raise ValueError(private)\n',str(path),'exec')
        namespace['private'] = private;exec(caller,namespace)
        try:namespace['fixture_failure']()
        except ValueError as error:observed = namespace['failure_site'](error)
        self.assertEqual(observed,{'file':'native-owned-manager.py','function':'fixture_failure','line':2})
        self.assertNotIn(private,json.dumps(observed));self.assertNotIn(str(HERE),json.dumps(observed))
        try:raise ValueError(private)
        except ValueError as error:self.assertEqual(namespace['failure_site'](error),{'status':'unavailable'})

    def test_manager_diagnostic_requires_closed_fixed_source_site_and_types(self):
        original = {'phase':'handoff-reserved','error_type':'JSONDecodeError',
            'check_site':{'file':'native-owned-manager.py','function':'wait','line':42}}
        self.assertEqual(proof.manager_failure(original),original)
        for site in ({'file':'/private/source.py','function':'wait','line':42},
            {'file':[],'function':'wait','line':42},
            {'file':'native-owned-manager.py','function':'wait','line':True},
            {**original['check_site'],'message':'private'}, {'status':'unknown'}):
            with self.subTest(site=site):self.assertIsNone(proof.manager_failure({**original,'check_site':site}))
        self.assertIsNone(proof.manager_failure({**original,'message':'private'}))

    def test_artifact_failure_accepts_only_bounded_closed_chain_and_elapsed_time(self):
        original={'chain':[{'error_type':'TimeoutError','check_site':{
            'file':'native_artifact_controller.py','function':'stage','line':344}}],'elapsed_ms':240001}
        self.assertEqual(proof.artifact_failure(original),original)
        bad=[{**original,'elapsed_ms':True},{**original,'elapsed_ms':1200001},
            {**original,'message':'private'},{**original,'chain':original['chain']*17},
            {**original,'chain':[{'error_type':'private-secret','check_site':{'status':'unavailable'}}]},
            {**original,'chain':[{'error_type':'TimeoutError','check_site':{
                'file':'/private/secret.py','function':'stage','line':344}}]},
            {**original,'chain':[{'error_type':'TimeoutError','check_site':{
                'file':'native_artifact_controller.py','function':'private-secret','line':344}}]}]
        for item in bad:
            with self.subTest(item=item):self.assertIsNone(proof.artifact_failure(item))
        manager={'phase':'actual-controller-root-artifact-stage','error_type':'ArtifactControllerRefused',
            'check_site':{'file':'native-successor-manager.py','function':'main','line':112},
            'artifact_failure':original}
        self.assertEqual(proof.manager_failure(manager),manager)
        self.assertIsNone(proof.manager_failure({**manager,'phase':'handoff-reserved'}))

    def test_stage_profile_excludes_private_paths_callers_values_and_unknown_functions(self):
        private={'private-password':('SQL and environment',)}
        stats={
            ('/opt/gitgood/native/v2/native_root_lifecycle.py',300,'check'):(2,4,.01,.5,private),
            ('/private/credentials.py',10,'check'):(1,1,.01,.5,private),
            ('/opt/gitgood/native/v2/native_root_lifecycle.py',10,'private_password'):(1,1,.01,.5,private),
            ('/opt/gitgood/native/v2/native_root_lifecycle.py',301,'_current'):(1,True,.01,.5,private),
            ('/opt/gitgood/native/v2/native_root_lifecycle.py',302,'_snapshot'):(1,1,float('nan'),.5,private)}
        with patch.object(proof.pstats,'Stats',return_value=SimpleNamespace(stats=stats)):
            observed=proof.root_stage_profile(Mock())
        self.assertEqual(observed,[{'file':'native_root_lifecycle.py','function':'check','line':300,
            'calls':4,'self_ms':10,'cumulative_ms':500}])
        self.assertNotIn('private',json.dumps(observed));self.assertNotIn('/opt',json.dumps(observed))

    def test_normal_root_refusal_accepts_only_closed_local_metadata_without_wire_authority(self):
        chain=[{'error_type':'ProtectedArtifactRefused','check_site':{
            'file':'native_protected_artifact.py','function':'_preflight_archive','line':289}}]
        result={'protocol':2,'kind':'native_root_artifact_result','status':'refused','root_refusal':chain}
        self.assertEqual(proof.root_stage_refusal(result,97000),{'chain':chain,'elapsed_ms':97000})
        for changed in ({**result,'protocol':True},{**result,'status':'staged'},
                {**result,'private':'secret'},{**result,'root_refusal':chain*17},
                {**result,'root_refusal':[{'error_type':'ValueError','check_site':{'file':'/private/secret.py','function':'check','line':1}}]},
                {key:value for key,value in result.items() if key!='root_refusal'}):
            with self.subTest(changed=changed):self.assertIsNone(proof.root_stage_refusal(changed,97000))
        self.assertIsNone(proof.root_stage_refusal(result,True))

    def test_backend_discovery_waits_for_two_stable_sql_samples_and_keeps_kernel_births(self):
        seed = {'installation': 'fixture', 'account': 'gg_fixture'}
        database = Mock(query=Mock(side_effect=['12:100', '12:100\n13:101', '12:100\n13:101',
            '12:100\n13:101\n14:102', '12:100\n13:101\n14:102', '12:100\n13:101\n14:102']))
        kernel = lambda pid: {'pid': pid, 'birth': str(pid+100), 'uid': 1000, 'cgroup': 'original'}
        with patch.object(proof, 'process', side_effect=kernel), patch.object(proof.time, 'sleep') as wait:
            captured = proof.capture_application_backends(database, seed, {'postgres_uid': 1000})
        self.assertEqual([item['session'] for item in captured], [
            {'backend_pid': 12, 'backend_birth': '100'}, {'backend_pid': 13, 'backend_birth': '101'},
            {'backend_pid': 14, 'backend_birth': '102'}])
        self.assertEqual([item['kernel']['birth'] for item in captured], ['112', '113', '114'])
        self.assertTrue(all(call.args[0].startswith('SELECT ') for call in database.query.call_args_list))
        self.assertTrue(all(0 < call.kwargs['timeout'] <= 5 for call in database.query.call_args_list))
        wait.assert_called()

    def test_backend_discovery_remains_bounded_and_never_skips_selected_kernel_loss_or_wrong_uid(self):
        seed = {'installation': 'fixture', 'account': 'gg_fixture'}
        database = Mock(query=Mock(return_value='12:100'))
        with patch.object(proof.time, 'monotonic', side_effect=[0, 0, 6]), patch.object(proof.time, 'sleep'), \
                patch.object(proof, 'process') as kernel:
            with self.assertRaises(ValueError):proof.capture_application_backends(database, seed, {'postgres_uid': 1000})
            kernel.assert_not_called()
        for observed in (ProcessLookupError(), {'pid': 12, 'birth': '112', 'uid': 1001, 'cgroup': 'wrong'}):
            database.query.return_value = '12:100\n13:101'
            with patch.object(proof.time, 'sleep'), patch.object(proof, 'process', side_effect=[observed]):
                with self.assertRaises((ProcessLookupError, ValueError)):
                    proof.capture_application_backends(database, seed, {'postgres_uid': 1000})

    def test_default_helper_discovery_skips_only_unselected_disappearance_and_still_requires_one(self):
        seed = {'unit': 'gitgood-installation-fixture.service', 'executables': {'python': '/usr/bin/python3.12'}}
        arguments = b'/usr/bin/python3.12\0-I\0-S\0/opt/gitgood/native/v2/native_generation_monitor_entry.py\0'

        def read(path, *_):
            pid = path.parent.name
            if pid == '11':raise FileNotFoundError()
            if pid == '12':raise ProcessLookupError()
            return io.BytesIO(arguments)

        service = SimpleNamespace(members=Mock(return_value=[11, 12, 13]))
        with patch.dict(sys.modules, {'native_service_scope': service}), patch.object(Path, 'open', autospec=True, side_effect=read):
            self.assertEqual(proof.discover_default_helper(seed), 13)
            service.members.return_value = [11, 12]
            with self.assertRaises(ValueError):proof.discover_default_helper(seed)
            service.members.return_value = [13, 14]
            with self.assertRaises(ValueError):proof.discover_default_helper(seed)
            service.members.return_value = [13]
            with patch.object(Path, 'open', side_effect=PermissionError()), self.assertRaises(PermissionError):
                proof.discover_default_helper(seed)
            with patch.object(Path, 'open', side_effect=OSError('unexpected fixture I/O failure')), self.assertRaises(OSError):
                proof.discover_default_helper(seed)

        seed.update(installation='fixture', ownership_operation='operation', candidate='a'*40)
        record = {'protocol': 4, 'mode': 'runtime', 'installation': 'fixture',
            'operation': 'operation', 'candidate': 'a'*40, 'owner': {'pid': 10}}
        launched = {'record': record, 'release_command': 'start', 'fixture_runtime_application_substitution': False}
        records = SimpleNamespace(validate_record=Mock())
        with patch.dict(sys.modules, {'native_ownership_records': records}), \
                patch.object(proof, 'discover_default_helper', return_value=13), \
                patch.object(proof, 'process', side_effect=[{}, ProcessLookupError()]):
            with self.assertRaises(ProcessLookupError):
                proof.capture_default_attachment(seed, launched, {}, None, {})

    def test_check_location_never_forwards_exception_messages_paths_values_or_source_text(self):
        private = 'private-credential-and-sql-fixture'
        with patch.object(proof.sys, 'platform', 'unsupported'):
            try:
                proof.preflight(SimpleNamespace(private=private))
            except ValueError as error:
                error.args = (private, '/private/configuration/credentials.json')
                result = proof.failure_check_site(error)
        self.assertEqual(set(result), {'file', 'function', 'line'})
        self.assertEqual(result['file'], 'native-owned-proof.py')
        self.assertEqual(result['function'], 'preflight')
        self.assertIs(type(result['line']), int)
        self.assertNotIn(private, json.dumps(result))
        self.assertNotIn('/private/', json.dumps(result))
        try:
            raise ValueError(private)
        except ValueError as error:
            self.assertEqual(proof.failure_check_site(error), {'status': 'unavailable'})

    def test_root_fixture_observes_original_lease_socket_without_ordinary_user_bypass(self):
        seed = {'uid': 1002, 'installation': '12345678-1234-4234-8234-123456789abc', 'account': 'gg_fixture'}
        record = {'owner': {'pid': 4242, 'birth': '111', 'uid': 1002},
                  'database_session': {'backend_pid': 4243, 'backend_birth': '222', 'database': {'port': 5440}},
                  'backend_kernel': {'kernel_birth': '222'}}
        database = SimpleNamespace(environment={'PGPORT': '5440'}, predicate=Mock(return_value='pid=4243'),
                                   query=Mock(side_effect=['127.0.0.1:12345', '1']))
        def process(pid):
            return {'pid': pid, 'uid': 1002 if pid == 4242 else 1001, 'birth': '111' if pid == 4242 else '222', 'state': 'S'}
        tcp = b'header\n0: 0100007F:3039 0100007F:1540 01 0:0 0:0 0 1002 0 7777\n'
        def link(path):
            return 'net:[10]' if str(path).replace('\\','/').endswith('ns/net') else 'socket:[7777]'
        entries = [SimpleNamespace(name='7', path='/proc/4242/fd/7')]
        with patch.object(proof, 'process', side_effect=process), patch.object(Path, 'open', return_value=io.BytesIO(tcp)), \
                patch.object(proof.os, 'readlink', side_effect=link), \
                patch.object(proof.os, 'scandir', return_value=contextlib.nullcontext(iter(entries))):
            result = proof.observe_default_lease(seed, record, database, {'postgres_uid': 1001})
        self.assertEqual(result, {'client_port': 12345, 'socket_inode': '7777', 'descriptor': '7'})
        self.assertTrue(all(call.args[0].startswith('SELECT ') for call in database.query.call_args_list))
        database.query = Mock(side_effect=['127.0.0.1:12345', '0'])
        with patch.object(proof, 'process', side_effect=process), patch.object(Path, 'open') as reads:
            with self.assertRaises(ValueError):proof.observe_default_lease(seed, record, database, {'postgres_uid': 1001})
            reads.assert_not_called()
        database.query = Mock(side_effect=['127.0.0.1:12345', '1'])
        with patch.object(proof, 'process', side_effect=process), patch.object(Path, 'open', return_value=io.BytesIO(tcp)), \
                patch.object(proof.os, 'readlink', return_value='net:[10]'), \
                patch.object(proof.os, 'scandir', return_value=contextlib.nullcontext(iter(entries))):
            with self.assertRaises(ValueError):proof.observe_default_lease(seed, record, database, {'postgres_uid': 1001})

    def test_default_native_fault_requires_actual_observation_acknowledgment(self):
        seed = {'seal_directory': str(self.directory), 'run': str(self.directory)}
        ready = {'original_release_running': True, 'public_stop_deferred_until_native_exit': True}
        for returned in [None, {}, {**ready, 'public_stop_deferred_until_native_exit': False}]:
            with self.subTest(returned=returned), patch.object(proof, 'write_new'), \
                    patch.object(proof, 'wait_for', return_value=returned), patch.object(proof, 'inject_loss') as inject:
                with self.assertRaises(ValueError):
                    proof.inject_default_release_loss(seed, self.directory, {}, {}, None)
                inject.assert_not_called()
        with patch.object(proof, 'write_new'), patch.object(proof, 'wait_for', side_effect=TimeoutError), \
                patch.object(proof, 'inject_loss') as inject:
            with self.assertRaises(TimeoutError):proof.inject_default_release_loss(seed, self.directory, {}, {}, None)
            inject.assert_not_called()
        events = []
        with patch.object(proof, 'write_new', side_effect=lambda *args: events.append('request')), \
                patch.object(proof, 'wait_for', side_effect=lambda *args: events.append('ack') or ready), \
                patch.object(proof, 'inject_loss', side_effect=lambda *args: events.append('loss')):
            proof.inject_default_release_loss(seed, self.directory, {}, {}, None)
        self.assertEqual(events, ['request', 'ack', 'loss'])

    def tls_context(self, failure=None):
        return SimpleNamespace(verify_mode=proof.ssl.CERT_REQUIRED, check_hostname=True,
                               wrap_socket=Mock(side_effect=failure))

    def test_wrong_tls_name_can_be_refused_before_certificate_delivery(self):
        for reason in ['TLSV1_ALERT_UNRECOGNIZED_NAME', 'TLSV1_ALERT_INTERNAL_ERROR', 'SSLV3_ALERT_HANDSHAKE_FAILURE']:
            failure = proof.ssl.SSLError(1, 'synthetic server-name alert');failure.reason = reason
            context = self.tls_context(failure)
            with self.subTest(reason=reason), patch.object(proof.socket, 'create_connection', return_value=contextlib.nullcontext(Mock())):
                self.assertEqual(proof.require_tls_refusal(context, 'localhost', server_name=True), 'server-name-handshake-alert')
                with self.assertRaises(ValueError):proof.require_tls_refusal(context, '127.0.0.1')

    def test_untrusted_tls_issuer_requires_client_certificate_refusal(self):
        context = self.tls_context(proof.ssl.SSLCertVerificationError(1, 'synthetic certificate refusal'))
        with patch.object(proof.socket, 'create_connection', return_value=contextlib.nullcontext(Mock())):
            self.assertEqual(proof.require_tls_refusal(context, '127.0.0.1'), 'certificate-verification')
            self.assertEqual(proof.require_tls_refusal(context, 'localhost', server_name=True), 'certificate-verification')

    def test_tls_negative_cannot_accept_success_network_errors_or_disabled_validation(self):
        failure = proof.ssl.SSLError(1, 'synthetic unrelated error');failure.reason = 'DECRYPTION_FAILED_OR_BAD_RECORD_MAC'
        for failure in [None, failure]:
            with patch.object(proof.socket, 'create_connection', return_value=contextlib.nullcontext(Mock())):
                with self.assertRaises(ValueError):proof.require_tls_refusal(self.tls_context(failure), 'localhost', server_name=True)
        with patch.object(proof.socket, 'create_connection', side_effect=ConnectionRefusedError):
            with self.assertRaises(ConnectionRefusedError):proof.require_tls_refusal(self.tls_context(), 'localhost', server_name=True)
        for field, value in [('check_hostname', False), ('verify_mode', proof.ssl.CERT_NONE)]:
            context = self.tls_context();setattr(context, field, value)
            with patch.object(proof.socket, 'create_connection') as connect:
                with self.assertRaises(ValueError):proof.require_tls_refusal(context, 'localhost', server_name=True)
                connect.assert_not_called()

    def fixture_elixir(self):
        expected = next(line.split()[1].split('-otp-')[0]
                        for line in (HERE.parents[1] / '.tool-versions').read_text().splitlines()
                        if line.startswith('elixir '))
        executable = shutil.which('elixir')
        if not executable:
            self.skipTest('The pinned Elixir runtime is required for this executable fixture check')
        version = subprocess.run([executable, '--version'], capture_output=True, text=True, timeout=10)
        match = re.search(r'Elixir (\d+\.\d+\.\d+)\b', version.stdout)
        supported = version.returncode == 0 and match is not None and match.group(1) == expected
        if os.environ.get('GITHUB_ACTIONS') == 'true':
            self.assertTrue(supported, 'Hosted fixture checks require the pinned Elixir ' + expected + ' runtime')
        elif not supported:
            self.skipTest('Local Elixir is outside the pinned ' + expected + ' fixture baseline; hosted execution remains required')
        return executable

    def setUp(self):
        # Local Windows checks must not spill into a full system temp drive.
        self.scratch = HERE.parents[1] / ".gitgood/native-owned-static"
        self.scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="check-", dir=self.scratch)
        self.directory = Path(self.temporary.name).resolve()
        self.assertTrue(self.directory.is_relative_to(self.scratch.resolve()))

    def tearDown(self):
        self.assertTrue(self.directory.is_relative_to(self.scratch.resolve()))
        self.temporary.cleanup()

    def test_cleanup_failure_cannot_be_green_or_hide_other_owned_units(self):
        receipt = {"status": "passed", "scope": "publication-only-component", "cases": []}
        units = ["gitgood-installation-first.service", "gitgood-installation-second.service"]
        with patch.object(proof, "command", side_effect=[TimeoutError(), b""]) as command, \
                patch.object(proof, "write_new") as write, contextlib.redirect_stdout(io.StringIO()):
            result = proof.finalize(receipt, units, self.directory, "complete")
        self.assertEqual(result, 1)
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["cleanup_errors"], units[:1])
        self.assertEqual(command.call_count, 2)
        self.assertEqual(write.call_args.args[0], self.directory / "receipt.json")

    def test_existing_failure_is_not_erased_by_successful_cleanup(self):
        receipt = {"status": "failed", "scope": "publication-only-component", "cases": []}
        with patch.object(proof, "command", return_value=b""), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(proof.finalize(receipt, [], None, "preflight"), 1)

    @unittest.skipUnless(sys.platform == 'linux' and os.getuid() > 0, 'Actual ordinary Linux lifecycle journal custody')
    def test_lifecycle_fixture_history_requires_original_inputs_and_exact_pending_tip(self):
        deployment = str(HERE.parent / 'deployment')
        with patch.object(sys, 'path', [deployment, *sys.path]):
            from native_lifecycle_responsibility import sha
            from native_operation_inputs import file_identity, file_record
            from test_native_lifecycle_responsibility import LifecycleResponsibilityTest
            fixture = LifecycleResponsibilityTest()
            fixture.setUp();self.addCleanup(fixture.doCleanups)
            fixture.history = self.directory / 'history';fixture.history.mkdir(mode=0o700)
            lock = fixture.history / '.upgrade-history-lock-v1'
            lock.write_bytes(b'');lock.chmod(0o600)
            journal = fixture.journal(fixture.open());journal.claim()
            for stage, label in zip(('inspect', 'stage', 'migrate', 'bootstrap', 'verify'),
                                    (None, None, 'migration-owner', 'bootstrap-owner', 'runtime-owner')):
                observation = {'fixture_only': True, 'business_stage_effects_verified': False}
                if label:observation['ownership_boundary_observed'] = label
                journal.begin(stage);journal.succeed(stage, sha(observation))
            inputs = self.directory / 'inputs';inputs.mkdir(mode=0o700)
            path = inputs / 'request.json';path.write_bytes(proof.canonical(fixture.request));path.chmod(0o600)
            preserved = {'files': {path: proof.fingerprint(path)},
                'input_directory': inputs, 'input_identity': proof.identity(inputs),
                'request': fixture.request, 'inputs_seal_sha256': 'c'*64,
                'sealed_files': {'request.json': file_record(file_identity(path.stat(), os.getuid(), os.getgid(), 16384), path.read_bytes())}}
            seed = {'root': str(self.directory), 'uid': os.getuid(), 'gid': os.getgid(),
                    'installation': fixture.installation, 'ownership_operation': fixture.request['operation']}
            pointer = {'generation_sha256': fixture.generation}
            observed = proof.observe_fixture_lifecycle_history(seed, pointer, preserved)
            self.assertTrue(observed['sealed_lifecycle_inputs_retained'])
            self.assertTrue(observed['fixture_lifecycle_history_verified'])
            self.assertEqual(observed['remaining_lifecycle_stages'], ['activate', 'enroll'])
            # Identical bytes/inode still invalidate the original input seal
            # after metadata changes; a digest alone cannot establish custody.
            before = path.stat()
            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000))
            with self.assertRaises(ValueError):proof.observe_fixture_lifecycle_history(seed, pointer, preserved)
            preserved['sealed_files']['request.json'] = file_record(file_identity(path.stat(), os.getuid(), os.getgid(), 16384), path.read_bytes())
            # An extra business-stage receipt exceeds this fixture's scope,
            # even when the production journal accepts that valid transition.
            journal.begin('activate');journal.succeed('activate', 'd'*64)
            with self.assertRaises(ValueError):proof.observe_fixture_lifecycle_history(seed, pointer, preserved)

    def hosted_opt_fixture(self, *, uid=0, mode=0o40777):
        before = SimpleNamespace(st_dev=10, st_ino=20, st_uid=uid, st_gid=0, st_mode=mode)
        after = SimpleNamespace(st_dev=10, st_ino=20, st_uid=uid, st_gid=0, st_mode=0o40755)
        path = Mock()
        path.resolve.return_value = path
        path.lstat.side_effect = [before, after]
        operating = SimpleNamespace(geteuid=lambda: 0,
            environ={"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted"},
            O_RDONLY=0, O_DIRECTORY=1, O_NOFOLLOW=2, O_CLOEXEC=4,
            open=Mock(return_value=31), close=Mock(), fstat=Mock(side_effect=[before, after]), fchmod=Mock())
        return path, operating

    def test_hosted_opt_hardening_changes_only_original_directory_descriptor(self):
        path, operating = self.hosted_opt_fixture()
        with patch.object(proof, "os", operating), patch.object(proof, "Path", return_value=path) as constructor, \
                patch.object(proof.sys, "platform", "linux"):
            result = proof.harden_hosted_opt()
        constructor.assert_called_once_with("/opt")
        operating.open.assert_called_once_with(path, 7)
        operating.fchmod.assert_called_once_with(31, 0o755)
        operating.close.assert_called_once_with(31)
        self.assertEqual((result["before_mode"], result["after_mode"]), (0o777, 0o755))
        self.assertFalse(result["recursive_changes"])
        self.assertFalse(result["production_guards_modified"])

    def test_hosted_opt_hardening_refuses_untrusted_owner_or_non_directory(self):
        for options in [{"uid": 1001}, {"mode": 0o120777}]:
            with self.subTest(options=options):
                path, operating = self.hosted_opt_fixture(**options)
                with patch.object(proof, "os", operating), patch.object(proof, "Path", return_value=path), \
                        patch.object(proof.sys, "platform", "linux"), self.assertRaises(ValueError):
                    proof.harden_hosted_opt()
                operating.fchmod.assert_not_called()
                operating.close.assert_called_once_with(31)

    def test_runtime_inventory_refuses_escape_before_copy(self):
        source = self.directory / "source"
        source.mkdir()
        outside = self.directory / "private"
        outside.write_text("must not be copied", encoding="utf-8")
        try:
            (source / "escape").symlink_to(outside)
        except OSError:
            self.skipTest("host cannot create test symlink")
        destination = self.directory / "destination"
        with self.assertRaises(ValueError):
            proof.copy_runtime(source, destination)
        self.assertFalse(destination.exists())

    def test_runtime_inventory_enforces_combined_byte_bound(self):
        source = self.directory / "source"
        source.mkdir()
        (source / "first").write_bytes(b"1234")
        (source / "second").write_bytes(b"5678")
        with patch.object(proof, "COPY_LIMIT", 7), self.assertRaises(ValueError):
            proof.copy_inventory(source)

    def test_production_import_closure_preserves_required_components(self):
        modules = proof.module_closure(HERE.parents[1] / "tools/deployment")
        self.assertLessEqual(len(modules), 128)
        self.assertTrue({"native_generation_monitor_entry.py", "native_writer_exclusion.py",
                         "native_ownership_publication_entry.py", "native_lifecycle_worker_inputs.py",
                         "native_lifecycle_business_inputs.py"} <= set(modules))
        self.assertFalse(any(name.startswith("test_") for name in modules))

    def test_original_zombie_is_not_backend_absence(self):
        original = {"pid": 12, "birth": "123"}
        with patch.object(proof, "process", return_value={**original, "state": "Z"}):
            self.assertFalse(proof.absent(original))
        with patch.object(proof, "process", return_value={"pid": 12, "birth": "124", "state": "S"}):
            self.assertTrue(proof.absent(original))

    def test_backend_fault_targets_original_sql_birth(self):
        database = proof.Database.__new__(proof.Database)
        self.assertEqual(database.predicate({"backend_pid": 27, "backend_birth": "123456"}),
                         "pid=27 AND floor(extract(epoch FROM backend_start)*1000000)::bigint=123456")
        with self.assertRaises(ValueError):
            database.predicate({"backend_pid": 27, "backend_birth": "123456 OR true"})

    def test_case_diagnostics_find_actual_fixed_owner_directory_without_phase_path_injection(self):
        stage = self.directory / 'bootstrap-owner';stage.mkdir()
        (stage / 'startup-events.txt').write_text('bootstrap:observed\nmonitor:accepted\n', encoding='ascii')
        result = proof.case_startup_diagnostics({'run': str(self.directory),
            'proof_phase': 'bootstrap-owner:protected-handoff-and-heartbeats'})
        self.assertEqual(result, {'status': 'observed', 'events': ['bootstrap:observed', 'monitor:accepted']})
        for phase in ('../bootstrap-owner:private', '/bootstrap-owner:private', 'unknown:private'):
            self.assertEqual(proof.case_startup_diagnostics({'run': str(self.directory), 'proof_phase': phase}),
                {'status': 'unavailable'})

    def test_startup_diagnostics_accept_only_closed_events_and_numeric_exit(self):
        (self.directory / "startup-events.txt").write_text("bootstrap:observed\nmonitor:entered\nmonitor:refused\n", encoding="ascii")
        (self.directory / "owner-exited.json").write_text(json.dumps({"exit_code": 1, "fixture_signalled_beam": False}))
        self.assertEqual(proof.startup_diagnostics(self.directory), {
            "status": "observed", "events": ["bootstrap:observed", "monitor:entered", "monitor:refused"],
            "original_exit_code": 1})

    def test_startup_diagnostics_never_forward_unknown_or_excess_output(self):
        path = self.directory / "startup-events.txt"
        for raw in [b"configuration:secret-value\n", b"bootstrap:observed\n" * 65, b"x" * 4097, b"\xff"]:
            with self.subTest(raw_size=len(raw)):
                path.write_bytes(raw)
                self.assertEqual(proof.startup_diagnostics(self.directory), {"status": "invalid"})
        path.write_bytes(b"bootstrap:observed\n")
        (self.directory / "owner-exited.json").write_text(json.dumps({
            "exit_code": 1, "fixture_signalled_beam": False, "private": "secret-value"}))
        self.assertEqual(proof.startup_diagnostics(self.directory), {"status": "invalid"})

    def test_vm_trace_reduces_actual_messages_to_fixed_tags(self):
        # Exercise the real fixture tracer with explicitly fake startup modules;
        # this checks trace grammar/redaction, never production startup admission.
        executable = self.fixture_elixir()
        source = (HERE / "native-owned-worker.exs").read_text(encoding="utf-8")
        diagnostics = source.split("defmodule GitgoodOwnedProof.Witness", 1)[0]
        script = '''
calls = [
  {Gitgood.InstallationProfile, :resolve, 3},
  {Gitgood.InstallationGenerationMonitor, :start_link, 1},
  {Gitgood.InstallationGenerationMonitor, :admission, 1},
  {Gitgood.NativeOwnershipInputs, :read_application, 2},
  {Gitgood.NativeOwnershipStartup, :validate_artifact, 2},
  {Gitgood.NativeApplicationConfiguration, :check, 3},
  {Gitgood.NativeDatabaseLease, :start_link, 1},
  {Gitgood.NativeOwnershipFence, :start_link, 2},
  {Gitgood.NativeOwnershipClaim, :claim, 4},
  {Gitgood.InstallationGenerationMonitor, :attach_ownership, 3}
]
for {module, entries} <- Enum.group_by(calls, &elem(&1, 0)) do
  definitions = for {_, function, arity} <- entries do
    arguments = for i <- 1..arity, do: Macro.var(String.to_atom("_input#{i}"), nil)
    body = case function do
      :check -> quote do: {:error, "synthetic-private-return"}
      :read_application -> quote do: raise("synthetic-private-exception")
      _ -> quote do: {:ok, "synthetic-private-return"}
    end
    quote do
      def unquote(function)(unquote_splicing(arguments)), do: unquote(body)
    end
  end
  Module.create(module, {:__block__, [], definitions}, Macro.Env.location(__ENV__))
end
'''
        script += diagnostics + '''
GitgoodOwnedProof.Diagnostics.start()
GitgoodOwnedProof.Diagnostics.mark("bootstrap")
for {module, function, arity} <- calls do
  try do
    apply(module, function, List.duplicate("synthetic-private-argument", arity))
  rescue
    _ -> :ok
  end
end
path = Path.join(System.fetch_env!("GITGOOD_OWNED_PROOF_DIRECTORY"), "startup-events.txt")
until = System.monotonic_time(:millisecond) + 2_000
wait = fn recurse ->
  if length(String.split(File.read!(path), "\\n", trim: true)) < 21 do
    true = System.monotonic_time(:millisecond) < until
    Process.sleep(10)
    recurse.(recurse)
  end
end
wait.(wait)
'''
        environment = {**os.environ, "GITGOOD_OWNED_PROOF_DIRECTORY": str(self.directory),
                       "ERL_FLAGS": "+S 2:2 +SDio 1 +SDcpu 1"}
        result = subprocess.run([executable, "-e", "Code.eval_string(IO.read(:stdio, :all))"],
                                input=script, text=True, capture_output=True, timeout=20, env=environment)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        detail = proof.startup_diagnostics(self.directory)
        self.assertEqual(detail["status"], "observed")
        self.assertEqual(len(detail["events"]), 21)
        self.assertIn("configuration:refused", detail["events"])
        self.assertIn("inputs:exception", detail["events"])
        self.assertNotIn("synthetic-private", (self.directory / "startup-events.txt").read_text())

    def test_diagnostic_read_has_a_real_byte_bound_and_refuses_changed_identity(self):
        path = self.directory / "startup-events.txt"
        path.write_bytes(b"bootstrap:observed\n")
        actual_read = os.read
        with patch.object(proof.os, "read", wraps=actual_read) as read:
            self.assertEqual(proof.bounded_diagnostic_read(path), b"bootstrap:observed\n")
            self.assertEqual(read.call_args.args[1], 4097)
        def changed_read(descriptor, maximum):
            raw = actual_read(descriptor, maximum)
            path.write_bytes(b"bootstrap:observed\n" * 2)
            return raw
        with patch.object(proof.os, "read", side_effect=changed_read), self.assertRaises(ValueError):
            proof.bounded_diagnostic_read(path)

    def test_actual_fixture_application_spec_uses_supported_otp_loader(self):
        executable = self.fixture_elixir()
        script = '''
{:__block__, _, expressions} =
  System.fetch_env!("GITGOOD_OWNED_WORKER_SOURCE") |> File.read!() |> Code.string_to_quoted!()
[loader] = Enum.filter(expressions, fn expression ->
  Macro.prewalk(expression, false, fn
    {{:., _, [_, :load]}, _, [{:{}, _, [:application, :gitgood_owned_proof, _]}]} = node, _ -> {node, true}
    node, found -> {node, found}
  end) |> elem(1)
end)
{:ok, _} = Code.eval_quoted(loader)
{:ok, properties} = :application.get_all_key(:gitgood_owned_proof)
{GitgoodOwnedProof.Application, []} = Keyword.fetch!(properties, :mod)
[:kernel, :stdlib, :elixir, :logger, :postgrex, :jason] = Keyword.fetch!(properties, :applications)
IO.puts("fixture-application-spec-loaded")
'''
        environment = {**os.environ, "GITGOOD_OWNED_WORKER_SOURCE": str(HERE / "native-owned-worker.exs"),
                       "ERL_FLAGS": "+S 2:2 +SDio 1 +SDcpu 1"}
        result = subprocess.run([executable, "-e", "Code.eval_string(IO.read(:stdio, :all))"],
                                input=script, text=True, capture_output=True, timeout=20, env=environment)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), "fixture-application-spec-loaded", result.stderr)

    def test_actual_maintenance_application_loads_fixed_spec_before_original_startup(self):
        executable = self.fixture_elixir()
        script = '''
defmodule Gitgood.NativeOwnershipStartup do
  def validate_lifecycle_options(root: "/fixture", action: action)
      when action in [:migrate, :bootstrap], do: :ok
end
defmodule Gitgood.NativeMaintenanceWorker do
  def execute, do: {:error, :fixture_worker_must_not_run}
end
defmodule Gitgood.NativeOwnershipSupervisor do
  def start_lifecycle_link("/fixture", action,
        [{Gitgood.Repo, parameters: [search_path: "pg_catalog, public"]},
         {Gitgood.NativeMaintenanceWorker, action}]) do
    {Gitgood.NativeMaintenanceApplication, ^action} =
      Application.spec(:gitgood_native_maintenance, :mod)
    [:kernel, :stdlib, :elixir, :logger] =
      Application.spec(:gitgood_native_maintenance, :applications)
    IO.puts("actual-maintenance-spec-loaded-before-original-refusal")
    {:error, :fixture_original_startup_refused}
  end
end
:ok = :logger.set_primary_config(:level, :none)
dependencies = [:kernel, :stdlib, :elixir, :logger]
:ok = :application.load({:application, :gitgood,
  [vsn: ~c"fixture", applications: dependencies]})
Application.put_env(:gitgood, :supervision_profile, "systemd-v2")
Application.put_env(:gitgood, :storage_root, "/fixture")
Code.compile_file(System.fetch_env!("GITGOOD_MAINTENANCE_SOURCE"))
Gitgood.NativeMaintenance.start(:migrate)
# The actual permanent start failure must end this original BEAM without a
# fixture halt/signal. If it merely returns, the bounded subprocess times out.
Process.sleep(:infinity)
'''
        environment = {**os.environ,
            "GITGOOD_MAINTENANCE_SOURCE": str(HERE.parents[1] / 'apps/forge/lib/gitgood/native_maintenance.ex'),
            "ERL_FLAGS": "+S 2:2 +SDio 1 +SDcpu 1"}
        source = self.directory / 'maintenance-loader.exs'
        source.write_text(script, encoding='utf-8')
        result = subprocess.run([executable, str(source)], text=True, capture_output=True,
                                timeout=20, env=environment)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(),
            'actual-maintenance-spec-loaded-before-original-refusal', result.stderr)
        self.assertNotIn('warning:', result.stderr)

    def test_actual_runtime_application_loads_fixed_spec_before_original_startup(self):
        executable = self.fixture_elixir()
        script = '''
defmodule Gitgood.NativeOwnershipStartup do
  def validate_lifecycle_options(root: "/fixture", action: :runtime), do: :ok
end
defmodule Gitgood.NativeRuntimeWorker do
  def activate, do: {:error, :fixture_worker_must_not_run}
end
defmodule Gitgood.NativeOwnershipSupervisor do
  def start_lifecycle_link("/fixture", :runtime,
        [{Gitgood.Repo, parameters: [search_path: "pg_catalog, public"]}, Gitgood.NativeRuntimeWorker]) do
    {Gitgood.NativeRuntimeApplication, []} = Application.spec(:gitgood_native_runtime, :mod)
    [:kernel, :stdlib, :elixir, :logger] = Application.spec(:gitgood_native_runtime, :applications)
    IO.puts("actual-runtime-spec-loaded-before-original-refusal")
    {:error, :fixture_original_startup_refused}
  end
end
:ok = :logger.set_primary_config(:level, :none)
:ok = :application.load({:application, :gitgood,
  [vsn: ~c"fixture", applications: [:kernel, :stdlib, :elixir, :logger]]})
Application.put_env(:gitgood, :supervision_profile, "systemd-v2")
Application.put_env(:gitgood, :storage_root, "/fixture")
Code.compile_file(System.fetch_env!("GITGOOD_RUNTIME_SOURCE"))
Gitgood.NativeRuntime.start()
Process.sleep(:infinity)
'''
        environment = {**os.environ,
            'GITGOOD_RUNTIME_SOURCE': str(HERE.parents[1] / 'apps/forge/lib/gitgood/native_runtime.ex'),
            'ERL_FLAGS': '+S 2:2 +SDio 1 +SDcpu 1'}
        source = self.directory / 'runtime-loader.exs';source.write_text(script, encoding='utf-8')
        result = subprocess.run([executable, str(source)], text=True, capture_output=True, timeout=20, env=environment)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), 'actual-runtime-spec-loaded-before-original-refusal', result.stderr)
        self.assertNotIn('warning:', result.stderr)

    def test_actual_runtime_schema_refusal_cannot_start_product_children(self):
        executable = self.fixture_elixir()
        script = '''
defmodule Gitgood.NativeOwnershipStartup do
  use GenServer
  def start_link(_), do: GenServer.start_link(__MODULE__, [])
  def init([]), do: {:ok, nil}
  def current(pid), do: GenServer.call(pid, :current)
  def handle_call(:current, _, state), do: {:reply, :ok, state}
end
defmodule Gitgood.Build do
  def identity, do: %{"candidate" => String.duplicate("b", 40)}
end
defmodule Gitgood.NativeMigrationInventory do
  def read, do: [1, 2]
  def match_build(_, [1, 2]), do: {:ok, [1, 2]}
end
defmodule Gitgood.NativeMaintenanceWorker do
  def validate_database(:bootstrap, %{"target_versions" => [1, 2]}) do
    send(:runtime_schema_observer, :schema_refused)
    :error
  end
end
defmodule Gitgood.RuntimeWorkers do
  def children do
    send(:runtime_schema_observer, :product_children_requested)
    []
  end
end
defmodule Gitgood.Readiness do
  def check, do: %{ready: true}
end
Process.flag(:trap_exit, true)
Process.register(self(), :runtime_schema_observer)
:ok = :logger.set_primary_config(:level, :none)
Code.compile_file(System.fetch_env!("GITGOOD_RUNTIME_WORKER_SOURCE"))
{:ok, root} = Supervisor.start_link([Gitgood.NativeOwnershipStartup, Gitgood.NativeRuntimeWorker],
  strategy: :one_for_all, max_restarts: 0, name: Gitgood.Supervisor)
try do
  Gitgood.NativeRuntimeWorker.activate()
  raise "schema refusal returned a successful activation"
catch
  :exit, _ -> :ok
end
receive do :schema_refused -> :ok after 1_000 -> raise "actual schema prerequisite was not checked" end
receive do {:EXIT, ^root, _} -> :ok after 1_000 -> raise "failed native root remained alive" end
receive do :product_children_requested -> raise "product children started after schema refusal" after 0 -> :ok end
IO.puts("actual-runtime-schema-refused-before-product-children")
'''
        environment = {**os.environ,
            'GITGOOD_RUNTIME_WORKER_SOURCE': str(HERE.parents[1] / 'apps/forge/lib/gitgood/native_runtime_worker.ex'),
            'ERL_FLAGS': '+S 2:2 +SDio 1 +SDcpu 1'}
        source = self.directory / 'runtime-schema.exs';source.write_text(script, encoding='utf-8')
        result = subprocess.run([executable, str(source)], text=True, capture_output=True, timeout=20, env=environment)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), 'actual-runtime-schema-refused-before-product-children', result.stderr)
        self.assertNotIn('warning:', result.stderr)

    def test_actual_default_application_callback_activates_fixed_root_without_nested_application(self):
        executable = self.fixture_elixir()
        script = '''
defmodule Gitgood.InstallationProfile do
  def resolve("systemd-v2", "/fixture", :runtime), do: {:ok, %{profile: :systemd_v2}}
end
defmodule Gitgood.NativeOwnershipStartup do
  def validate_lifecycle_options(root: "/fixture", action: :runtime), do: :ok
end
defmodule Gitgood.NativeOwnershipSupervisor do
  def start_lifecycle_link("/fixture", :runtime,
      [{Gitgood.Repo, parameters: [search_path: "pg_catalog, public"]}, Gitgood.NativeRuntimeWorker]) do
    false = Enum.any?(Application.started_applications(), fn {app, _, _} -> app == :gitgood_native_runtime end)
    Supervisor.start_link([], strategy: :one_for_all, max_restarts: 0, name: Gitgood.Supervisor)
  end
end
defmodule Gitgood.NativeRuntimeWorker do
  def activate do
    root = Process.whereis(Gitgood.Supervisor)
    true = is_pid(root) and Process.alive?(root)
    false = Enum.any?(Application.started_applications(), fn {app, _, _} -> app == :gitgood_native_runtime end)
    case Application.get_env(:gitgood, :fixture_activation, :success) do
      :success -> {:ok, %{product_workers_started: true, internal_readiness_observed: true}}
      :refuse -> {:error, :synthetic_refusal}
      :wrong_outcome -> {:ok, %{product_workers_started: false, internal_readiness_observed: false}}
      :exit -> exit(:synthetic_refusal)
      :must_not_run -> raise("existing root was adopted")
    end
  end
end
defmodule Gitgood.InstallationLease do
  def enabled?, do: raise("development branch called for native startup")
end
defmodule Gitgood.RuntimeWorkers do
  def children, do: raise("development branch called for native startup")
end
defmodule GitgoodWeb.Endpoint do
  def config_change(_, _), do: :ok
end
Code.compile_file(System.fetch_env!("GITGOOD_RUNTIME_SOURCE"))
Code.compile_file(System.fetch_env!("GITGOOD_APPLICATION_SOURCE"))
:ok = :application.load({:application, :gitgood,
  [vsn: ~c"fixture", mod: {Gitgood.Application, []}, applications: [:kernel, :stdlib, :elixir, :logger]]})
Application.put_env(:gitgood, :supervision_profile, "systemd-v2")
Application.put_env(:gitgood, :storage_root, "/fixture")
:ok = Application.start(:gitgood, :permanent)
true = Process.alive?(Process.whereis(Gitgood.Supervisor))
IO.puts("actual-default-callback-fixed-root-activated-without-nested-application")
:ok = Application.stop(:gitgood)
nil = Process.whereis(Gitgood.Supervisor)
Process.flag(:trap_exit, true)
for mode <- [:refuse, :wrong_outcome, :exit] do
  Application.put_env(:gitgood, :fixture_activation, mode)
  {:error, :native_runtime_unavailable} = Gitgood.NativeRuntime.start_application()
  nil = Process.whereis(Gitgood.Supervisor)
end
{:ok, existing} = Supervisor.start_link([], strategy: :one_for_all, max_restarts: 0, name: Gitgood.Supervisor)
Application.put_env(:gitgood, :fixture_activation, :must_not_run)
{:error, :native_runtime_unavailable} = Gitgood.NativeRuntime.start_application()
{:error, :native_runtime_unavailable} = Gitgood.Application.start({:takeover, :other}, [])
{:error, :native_runtime_unavailable} = Gitgood.Application.start(:normal, [:caller_argument])
true = Process.alive?(existing)
:ok = Supervisor.stop(existing)
IO.puts("actual-default-callback-refusal-stops-only-created-root")
'''
        environment = {**os.environ,
            'GITGOOD_RUNTIME_SOURCE': str(HERE.parents[1] / 'apps/forge/lib/gitgood/native_runtime.ex'),
            'GITGOOD_APPLICATION_SOURCE': str(HERE.parents[1] / 'apps/forge/lib/gitgood/application.ex'),
            'ERL_FLAGS': '+S 2:2 +SDio 1 +SDcpu 1'}
        source = self.directory / 'default-runtime-callback.exs';source.write_text(script, encoding='utf-8')
        result = subprocess.run([executable, str(source)], text=True, capture_output=True, timeout=20, env=environment)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('actual-default-callback-fixed-root-activated-without-nested-application', result.stdout)
        self.assertIn('actual-default-callback-refusal-stops-only-created-root', result.stdout)
        self.assertNotIn('warning:', result.stderr)

    @unittest.skipUnless(sys.platform == "linux", "real Linux JIT file-limit check runs on the hosted runner")
    def test_real_beam_jit_boots_with_the_finite_fixture_file_limit(self):
        import resource
        executable = shutil.which("erl")
        self.assertIsNotNone(executable, "the pinned hosted OTP runtime is required")
        seed = {"account": "fixture", "seal_directory": str(self.directory), "run": str(self.directory)}
        unit = proof.unit_text(seed, self.directory / "manager.py").decode()
        file_limit = int(next(line.split("=", 1)[1] for line in unit.splitlines() if line.startswith("LimitFSIZE=")))
        self.assertIn("LimitCORE=0\n", unit)
        self.assertLessEqual(file_limit, 64 * 1024**2)
        environment = {"PATH": os.environ["PATH"], "LANG": "C.UTF-8", "HOME": str(self.directory),
                       "TMPDIR": str(self.directory), "ERL_CRASH_DUMP": "/dev/null", "ERL_CRASH_DUMP_SECONDS": "0",
                       "ERL_FLAGS": "+S 2:2 +SDio 1 +SDcpu 1"}
        for limit, expected in [(16 * 1024**2, -signal.SIGXFSZ), (file_limit, 0)]:
            with self.subTest(limit=limit):
                def constrain():
                    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
                    resource.setrlimit(resource.RLIMIT_FSIZE, (limit, limit))
                result = subprocess.run([executable, "-noshell", "-eval",
                    'jit = erlang:system_info(emu_flavor), io:format("native-beam-limit-ok~n"), halt().'],
                    env=environment, capture_output=True, timeout=15, preexec_fn=constrain)
                self.assertEqual(result.returncode, expected)
                if expected == 0:
                    self.assertEqual(result.stdout, b"native-beam-limit-ok\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
