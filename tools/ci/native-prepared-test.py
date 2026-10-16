#!/usr/bin/env python3
"""Fixed statement/framing tests and isolated hosted PostgreSQL equivalence."""
import contextlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from types import MethodType, ModuleType, SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch
import uuid

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'deployment'))
if sys.platform == 'win32':
    # Import compatibility only; no modeled Root admission or filesystem claim.
    if 'pwd' not in sys.modules:
        module = ModuleType('pwd')
        def unavailable(*_):raise RuntimeError('No Windows POSIX account database')
        module.getpwnam = unavailable;sys.modules['pwd'] = module
    for name in ('getuid', 'geteuid', 'getgid', 'getegid'):
        if not hasattr(os, name):setattr(os, name, lambda: 1000)
import native_prepared_probe as probe
import native_root_database_reader as root
import test_native_root_database_reader as original_tests

NONCE = '12345678-1234-4234-8234-123456789abc'


class PreparedFramingTest(original_tests.ReaderExchangeTest):
    """Repeat the original framing/poison cases with explicit kernel stand-ins."""
    def exchange(self, value, reply, kind='identity'):
        if not hasattr(value, '_diagnostic_probe'):
            value._diagnostic_probe = probe.PreparedExchange(root, value)
        selector = Mock();selector.select.return_value = [('ready', 1)]
        manager = MagicMock();manager.__enter__.return_value = selector
        with patch.object(root.uuid, 'uuid4', return_value=NONCE), \
                patch.object(root.selectors, 'DefaultSelector', return_value=manager), \
                patch.object(root.os, 'read', side_effect=reply if type(reply) is list else [reply]):
            return MethodType(value._diagnostic_probe.function, value)(kind)

    def reply(self, **changes):
        changes.setdefault('nonce', NONCE)
        return super().reply(**changes)

    def test_fresh_fixed_identity_statement_reuses_original_child_and_brackets_it(self):
        value = self.view();child = value.child
        for _ in range(2):self.assertEqual(self.exchange(value, self.reply()), original_tests.GOOD)
        self.assertIs(value.child, child);self.assertEqual(value._base.call_count, 4)
        commands = [call.args[0] for call in child.stdin.write.call_args_list]
        self.assertIn(root.SQL.encode(), commands[0]);self.assertIn(b'PREPARE gitgood_probe_identity(text)', commands[0])
        self.assertEqual(commands[1], ("EXECUTE gitgood_probe_identity('" + NONCE + "');\n").encode())
        self.assertTrue(all(b'pg_try_advisory_lock' not in command for command in commands))
        child.terminate.assert_not_called()

    def test_builder_refuses_foreign_reader_nonce_statement_and_unreviewed_exchange(self):
        value = self.view();prepared = probe.PreparedExchange(root, value)
        for reader, kind, nonce, statement in [(self.view(), 'identity', NONCE, root.SQL),
                (value, 'identity', 'foreign', root.SQL), (value, 'identity', NONCE, 'SELECT 1'),
                (value, 'acquire', NONCE, root.SQL)]:
            with self.assertRaises(ValueError):prepared.query(reader, kind, nonce, statement)
        value.child.stdin.write.assert_not_called()
        with patch.object(root.NativeRootDatabaseReader, '_exchange', new=lambda *_: None):
            with self.assertRaises(ValueError):probe.PreparedExchange(root, value)

    def test_preparation_state_is_bound_to_one_original_child_and_never_caches_replies(self):
        value = self.view();prepared = probe.PreparedExchange(root, value)
        first = prepared.query(value, 'exclusion', NONCE, root.ROOT_EXCLUSION_SQL)
        second = prepared.query(value, 'exclusion', NONCE, root.ROOT_EXCLUSION_SQL)
        self.assertIn(root.READER_SQL.encode(), first);self.assertIn(root.ROOT_EXCLUSION_SQL.encode(), first)
        self.assertNotIn(b'PREPARE', second);self.assertEqual(prepared.calls, 2)
        value.child = Mock()
        with self.assertRaises(ValueError):prepared.query(value, 'exclusion', NONCE, root.ROOT_EXCLUSION_SQL)


class ComparisonRestorationTest(unittest.TestCase):
    def fixture(self):
        class Stage:
            usable = True;state = 'ready'
            def __init__(self):self.allocation = SimpleNamespace(close=Mock())
            def check(self):return 'original'
            def close(self):self.usable = False
        return Stage, Stage(), MagicMock()

    def test_original_check_is_restored_before_timers_and_effects(self):
        owner, stage, timers = self.fixture();original = vars(owner)['check']
        with patch.object(probe, 'compare_guard', return_value={'diagnostic_only': True}) as compare:
            with probe.BeforeStageComparison(root, owner, timers) as experiment:
                self.assertEqual(stage.check(), 'original')
                compare.assert_called_once_with(root, original, stage)
                timers.__enter__.assert_called_once()
                self.assertIs(vars(owner)['check'], original)
                self.assertEqual(experiment.result, {'diagnostic_only': True})
        timers.__exit__.assert_called_once();self.assertIs(vars(owner)['check'], original)

    def test_interruption_mismatch_and_partial_setup_poison_without_revival(self):
        for failure in [KeyboardInterrupt(), ValueError('mismatch'), RuntimeError('setup')]:
            owner, stage, timers = self.fixture();original = vars(owner)['check']
            setup_failure = isinstance(failure, RuntimeError)
            if setup_failure:timers.__enter__.side_effect = failure
            with patch.object(probe, 'compare_guard', side_effect=None if setup_failure else failure), \
                    self.assertRaises(type(failure)):
                with probe.BeforeStageComparison(root, owner, timers):stage.check()
            self.assertFalse(stage.usable);stage.allocation.close.assert_called_once()
            self.assertIs(vars(owner)['check'], original)


class WholeGuardStandInTest(unittest.TestCase):
    """Control flow only; actual Root actors remain a separate hosted gate."""
    def setUp(self):
        self.reader = original_tests.ReaderExchangeTest().view()
        self.stage = SimpleNamespace(usable=True, state='ready', allocation=SimpleNamespace(
            exclusion=SimpleNamespace(live=SimpleNamespace(database_reader=self.reader))))
        self.context = contextlib.ExitStack();self.addCleanup(self.context.close)
        selector = Mock();selector.select.return_value = [('ready', 1)]
        manager = MagicMock();manager.__enter__.return_value = selector
        self.context.enter_context(patch.object(root.selectors, 'DefaultSelector', return_value=manager))
        self.context.enter_context(patch.object(root.uuid, 'uuid4', return_value=NONCE))
        def read(*_):
            command = self.reader.child.stdin.write.call_args.args[0]
            exclusion = b'gitgood_probe_exclusion' in command or b"'holders'" in command
            value = {'database': original_tests.GOOD, 'holders': [], 'clients': 2} if exclusion else original_tests.GOOD
            return root.canonical({'nonce': NONCE, 'reader': original_tests.READER, 'value': value}) + b'\n'
        self.context.enter_context(patch.object(root.os, 'read', side_effect=read))

    def test_fixed_pairs_restore_instance_and_class_and_remove_only_own_session_plans(self):
        order = [];original = vars(root.NativeRootDatabaseReader)['_exchange']
        def guard(stage):
            order.append('_exchange' in vars(self.reader))
            return self.reader._exchange('exclusion')
        result = probe.compare_guard(root, guard, self.stage)
        self.assertEqual(order, [value for pair in range(20) for value in
            ((False, True) if pair % 2 == 0 else (True, False))])
        self.assertEqual(result['prepared_exchange_calls'], 20)
        self.assertEqual(result['extra_read_only_checks'], 40)
        self.assertEqual(len(result['pairs']), 20)
        self.assertNotIn('_exchange', vars(self.reader))
        self.assertIs(vars(root.NativeRootDatabaseReader)['_exchange'], original)
        commands = [call.args[0] for call in self.reader.child.stdin.write.call_args_list]
        self.assertEqual(commands[-2], b'DEALLOCATE gitgood_probe_exclusion;\n')
        self.assertIn(root.SQL.encode(), commands[-1])
        self.assertNotIn(root.ROOT_EXCLUSION_SQL.encode(), commands[-1])

    def test_guard_interruptions_and_mismatch_restore_original_instance_method(self):
        for failure in [KeyboardInterrupt(), ValueError('mismatch')]:
            def guard(stage):
                if '_exchange' in vars(self.reader):raise failure
                return self.reader._exchange('exclusion')
            with self.assertRaises(type(failure)):probe.compare_guard(root, guard, self.stage)
            self.assertNotIn('_exchange', vars(self.reader))

    def test_an_existing_profiler_refuses_before_query_or_instance_mutation(self):
        with patch.object(probe.sys, 'getprofile', return_value=object()),self.assertRaises(ValueError):
            probe.compare_guard(root, lambda stage: None, self.stage)
        self.reader.child.stdin.write.assert_not_called();self.assertNotIn('_exchange', vars(self.reader))


@unittest.skipUnless(sys.platform == 'linux' and os.environ.get('GITHUB_ACTIONS') == 'true'
    and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted', 'Disposable hosted PostgreSQL required')
class ActualPostgresPreparationTest(unittest.TestCase):
    """Actual SQL/session/framing; explicit process/base stand-ins.

    The later complete Root guard comparison must verify actual kernel custody.
    This namespace creates no product records and is removed before that proof.
    """
    @classmethod
    def command(cls, statement, environment, database=None):
        arguments = [cls.psql, '--no-psqlrc', '--no-password', '-At', '--set=ON_ERROR_STOP=1']
        if database:arguments += ['--dbname', database]
        result = subprocess.run(arguments + ['--command', statement], env=environment,
            capture_output=True, timeout=10)
        if result.returncode or len(result.stdout) > 16384 or len(result.stderr) > 16384:
            raise RuntimeError('Owned PostgreSQL diagnostic command failed')
        return result.stdout

    @classmethod
    def setUpClass(cls):
        cls.psql = str(HERE.parents[1] / '.gitgood/postgres-18.4/bin/psql')
        cls.admin = dict(os.environ);cls.name = 'gg_prepare_' + uuid.uuid4().hex
        cls.addClassCleanup(cls.cleanup_namespace)
        cls.command("CREATE ROLE " + cls.name + " LOGIN PASSWORD 'synthetic-probe-password' NOSUPERUSER "
            "NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS", cls.admin, 'postgres')
        cls.command('CREATE DATABASE ' + cls.name + ' OWNER ' + cls.name, cls.admin, 'postgres')
        cls.command('GRANT EXECUTE ON FUNCTION pg_catalog.pg_control_system() TO ' + cls.name, cls.admin, cls.name)
        cls.environment = {**cls.admin, 'PGDATABASE': cls.name, 'PGUSER': cls.name,
            'PGPASSWORD': 'synthetic-probe-password', 'PGPASSFILE': '/dev/null',
            'PGOPTIONS': root.OBSERVATION_OPTIONS}

    @classmethod
    def cleanup_namespace(cls):
        cls.command('DROP DATABASE IF EXISTS ' + cls.name, cls.admin, 'postgres')
        cls.command('DROP ROLE IF EXISTS ' + cls.name, cls.admin, 'postgres')

    def setUp(self):
        self.subject = root.NativeRootDatabaseReader.__new__(root.NativeRootDatabaseReader)
        value = self.subject;value.usable = True;value.owner = (os.getpid(), threading.get_ident())
        value.environment = self.environment;value.expected = json.loads(self.command(root.SQL, self.environment))
        value.reader = value.client = value.kernel = value.socket = None
        value.server_scope = {};value.network = 'explicit-stand-in';value.lifecycle = Mock()
        value.child = subprocess.Popen([self.psql, '--quiet', '--no-psqlrc', '--no-password', '-At',
            '--set=ON_ERROR_STOP=1'], env=self.environment, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        child = value.child;self.child = child
        pipes = tuple(root.NativeRootDatabaseReader._file(os.fstat(pipe.fileno())) for pipe in (child.stdin, child.stdout))
        def base():
            if child is not value.child or child.poll() is not None or not value.usable:
                raise root.RootDatabaseReaderRefused('Owned diagnostic child lost')
            self.assertEqual(tuple(root.NativeRootDatabaseReader._file(os.fstat(pipe.fileno()))
                for pipe in (child.stdin, child.stdout)), pipes)
            return {'pid': child.pid, 'birth': 'explicit-stand-in'}
        value._base = base
        self.patches = contextlib.ExitStack();self.addCleanup(self.patches.close)
        self.patches.enter_context(patch.object(root, '_capture_process', return_value='kernel-stand-in'))
        self.patches.enter_context(patch.object(root, '_socket_for_process', return_value={'socket': 'stand-in'}))
        self.addCleanup(value.close)
        self.prepared = probe.PreparedExchange(root, value)
        self.prototype = MethodType(self.prepared.function, value)
        self.prepared.original(value, 'identity')

    def test_actual_identity_and_exclusion_pairs_keep_same_reader_and_fresh_nonce(self):
        original = self.prepared.original;subject = self.subject
        for kind in ('identity', 'exclusion'):
            for _ in range(10):
                baseline = original(subject, kind);reader = dict(subject.reader)
                self.assertEqual(self.prototype(kind), baseline)
                self.assertEqual(subject.reader, reader);self.assertIs(subject.child, self.child)
                self.assertEqual(subject.reader['read_only'], 'on');self.assertFalse(subject.reader['held'])
        self.assertEqual(self.prepared.calls, 20)
        self.prepared.cleanup();self.assertFalse(self.prepared.prepared)
        self.assertEqual(original(subject, 'identity'), subject.expected)

    def test_fresh_client_count_changes_after_preparation_without_returned_data_reuse(self):
        baseline = self.prototype('exclusion');self.assertEqual(baseline['clients'], 1)
        extra = subprocess.Popen([self.psql, '--quiet', '--no-psqlrc', '--no-password', '-At'],
            env=self.environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            extra.stdin.write(b'SELECT 1;\n');extra.stdin.flush()
            with root.selectors.DefaultSelector() as selector:
                selector.register(extra.stdout, root.selectors.EVENT_READ)
                self.assertTrue(selector.select(4));self.assertEqual(extra.stdout.readline(), b'1\n')
            changed = self.prototype('exclusion');self.assertEqual(changed['clients'], 2)
            self.assertEqual(self.prepared.original(self.subject, 'exclusion'), changed)
        finally:
            extra.communicate(b'\\q\n', timeout=5)

    def test_role_change_after_preparation_refuses_and_never_revives_original_reader(self):
        self.prototype('identity')
        self.command('ALTER ROLE ' + self.name + ' NOLOGIN', self.admin, 'postgres')
        try:
            with self.assertRaises(root.RootDatabaseReaderRefused):self.prototype('identity')
            self.assertFalse(self.subject.usable)
            with self.assertRaises(root.RootDatabaseReaderRefused):self.prototype('identity')
        finally:self.command('ALTER ROLE ' + self.name + ' LOGIN', self.admin, 'postgres')

    def test_original_child_loss_after_preparation_refuses_without_reconnect(self):
        self.prototype('identity');self.child.terminate();self.child.wait(timeout=5)
        with patch.object(root.subprocess, 'Popen') as create:
            with self.assertRaises(root.RootDatabaseReaderRefused):self.prototype('identity')
            create.assert_not_called()
        self.assertFalse(self.subject.usable)

    def test_original_backend_loss_after_preparation_refuses_without_reconnect(self):
        self.prototype('identity');reader = self.subject.reader
        statement = ('SELECT pg_terminate_backend(pid,5000) FROM pg_stat_activity WHERE pid=' + str(reader['backend_pid']) +
            " AND datname='" + self.name + "' AND floor(extract(epoch FROM backend_start)*1000000)::bigint=" +
            reader['backend_birth'])
        self.assertEqual(self.command(statement, self.admin, 'postgres').strip(), b't')
        with patch.object(root.subprocess, 'Popen') as create:
            with self.assertRaises(root.RootDatabaseReaderRefused):self.prototype('identity')
            create.assert_not_called()
        self.assertFalse(self.subject.usable)


if __name__ == '__main__':unittest.main(verbosity=2)
