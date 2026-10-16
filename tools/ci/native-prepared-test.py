#!/usr/bin/env python3
"""Actual fixed SELECT preparation on a newly owned hosted PostgreSQL namespace."""
import contextlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from unittest.mock import Mock, patch
import unittest
import uuid

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'deployment'))
# Actual SQL cases defer on Windows without importing POSIX deployment code.
if sys.platform == 'linux':
    import native_root_database_reader as root


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
        value.prepared_statements = set()
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
        value._exchange('identity')

    def test_actual_fixed_identity_and_exclusion_replies_keep_original_reader_fresh(self):
        subject = self.subject
        for kind in ('identity', 'exclusion'):
            for _ in range(10):
                value = subject._exchange(kind);reader = dict(subject.reader)
                expected = subject.expected if kind == 'identity' else {
                    'database': subject.expected, 'holders': [], 'clients': 1}
                self.assertEqual(value, expected)
                self.assertEqual(subject._exchange(kind), value)
                self.assertEqual(subject.reader, reader);self.assertIs(subject.child, self.child)
                self.assertEqual(subject.reader['read_only'], 'on');self.assertFalse(subject.reader['held'])
        self.assertEqual(subject.prepared_statements, {'identity', 'exclusion'})

    def test_fresh_client_count_changes_after_preparation_without_returned_data_reuse(self):
        baseline = self.subject._exchange('exclusion');self.assertEqual(baseline['clients'], 1)
        extra = subprocess.Popen([self.psql, '--quiet', '--no-psqlrc', '--no-password', '-At'],
            env=self.environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            extra.stdin.write(b'SELECT 1;\n');extra.stdin.flush()
            with root.selectors.DefaultSelector() as selector:
                selector.register(extra.stdout, root.selectors.EVENT_READ)
                self.assertTrue(selector.select(4));self.assertEqual(extra.stdout.readline(), b'1\n')
            changed = self.subject._exchange('exclusion');self.assertEqual(changed['clients'], 2)
            self.assertEqual(self.subject._exchange('exclusion'), changed)
        finally:
            extra.communicate(b'\\q\n', timeout=5)

    def test_role_change_after_preparation_refuses_and_never_revives_original_reader(self):
        self.subject._exchange('identity')
        self.command('ALTER ROLE ' + self.name + ' NOLOGIN', self.admin, 'postgres')
        try:
            with self.assertRaises(root.RootDatabaseReaderRefused):self.subject._exchange('identity')
            self.assertFalse(self.subject.usable)
            with self.assertRaises(root.RootDatabaseReaderRefused):self.subject._exchange('identity')
        finally:self.command('ALTER ROLE ' + self.name + ' LOGIN', self.admin, 'postgres')

    def test_original_child_loss_after_preparation_refuses_without_reconnect(self):
        self.subject._exchange('identity');self.child.terminate();self.child.wait(timeout=5)
        with patch.object(root.subprocess, 'Popen') as create:
            with self.assertRaises(root.RootDatabaseReaderRefused):self.subject._exchange('identity')
            create.assert_not_called()
        self.assertFalse(self.subject.usable)

    def test_original_backend_loss_after_preparation_refuses_without_reconnect(self):
        self.subject._exchange('identity');reader = self.subject.reader
        statement = ('SELECT pg_terminate_backend(pid,5000) FROM pg_stat_activity WHERE pid=' + str(reader['backend_pid']) +
            " AND datname='" + self.name + "' AND floor(extract(epoch FROM backend_start)*1000000)::bigint=" +
            reader['backend_birth'])
        self.assertEqual(self.command(statement, self.admin, 'postgres').strip(), b't')
        with patch.object(root.subprocess, 'Popen') as create:
            with self.assertRaises(root.RootDatabaseReaderRefused):self.subject._exchange('identity')
            create.assert_not_called()
        self.assertFalse(self.subject.usable)


if __name__ == '__main__':unittest.main(verbosity=2)
