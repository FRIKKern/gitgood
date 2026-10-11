import copy
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import native_kernel_backend as kernel
from native_durable_database import DatabaseRefused
from test_native_durable_database import GOOD, URL


SCOPE = {'boot_id': '11111111-1111-4111-8111-111111111111',
         'pid_namespace': 'pid:[12345]', 'time_namespace': 'time:[4441]', 'postgres_uid': 1001}
SNAPSHOT = {'database': GOOD, 'backend_pid': 1234, 'backend_birth': '1770000000000000'}


class KernelBackendBoundaryTest(unittest.TestCase):
    def record(self):
        return copy.deepcopy({'protocol': 2, 'kind': 'native_backend_kernel_identity',
                              'server_scope': SCOPE, 'database_session': SNAPSHOT, 'kernel_birth': '450'})

    def test_retained_kernel_birth_brackets_one_fresh_original_sql_observation(self):
        order=[];record=self.record();before=copy.deepcopy(record)
        with patch.object(kernel,'_check_scope',side_effect=lambda *a:order.append('scope')), \
             patch.object(kernel,'_capture_process',side_effect=lambda *a:(order.append('process') or '450')), \
             patch.object(kernel,'observe_held_session',side_effect=lambda *a,**kw:(order.append('session') or {'owner_connection_observed':True,'lease_acquired':False})):
            result=kernel.observe_held_backend_kernel_identity('/trusted/psql',URL,record,GOOD,SCOPE)
        self.assertEqual(order,['scope','process','session','process','scope'])
        self.assertTrue(result['original_backend_kernel_observed'])
        self.assertFalse(result['replacement_admitted']);self.assertFalse(result['lease_acquired'])
        self.assertEqual(record,before)

    def test_changed_or_lost_original_kernel_birth_refuses_without_adoption(self):
        for sequence in [['451'],['450','451'],[FileNotFoundError()],['450',PermissionError()]]:
            with self.subTest(sequence=len(sequence)),patch.object(kernel,'_check_scope'), \
                 patch.object(kernel,'_capture_process',side_effect=sequence), \
                 patch.object(kernel,'observe_held_session',return_value={'owner_connection_observed':True,'lease_acquired':False}) as sql:
                with self.assertRaises(DatabaseRefused):kernel.observe_held_backend_kernel_identity('/trusted/psql',URL,self.record(),GOOD,SCOPE)
            self.assertEqual(sql.call_count,1 if len(sequence)==2 else 0)

    def test_lost_original_socket_or_lease_refuses_before_second_kernel_read(self):
        for value in [DatabaseRefused(),{'owner_connection_observed':False,'lease_acquired':False},
                      {'owner_connection_observed':True,'lease_acquired':True},{}]:
            with patch.object(kernel,'_check_scope'),patch.object(kernel,'_capture_process',return_value='450') as process, \
                 patch.object(kernel,'observe_held_session',side_effect=[value]):
                with self.assertRaises(DatabaseRefused):kernel.observe_held_backend_kernel_identity('/trusted/psql',URL,self.record(),GOOD,SCOPE)
            self.assertEqual(process.call_count,1)

    def test_capture_brackets_kernel_identity_with_original_held_session(self):
        with patch.object(kernel, '_check_scope') as scope, \
             patch.object(kernel, 'observe_held_session') as held, \
             patch.object(kernel, '_capture_process', return_value='450') as process:
            observed = kernel.capture_backend_kernel_identity('/trusted/psql', URL, SNAPSHOT, GOOD, SCOPE)
        self.assertEqual(observed, self.record())
        self.assertEqual(scope.call_count, 2)
        self.assertEqual(held.call_count, 2)
        self.assertEqual(process.call_count, 2)
        self.assertTrue(all(call.args == (1234, SCOPE) for call in process.call_args_list))
        observed['server_scope']['postgres_uid'] = 7
        observed['database_session']['database']['role'] = 'changed'
        self.assertEqual(SCOPE['postgres_uid'], 1001)
        self.assertEqual(GOOD['role'], 'ordinary')

    def test_changed_kernel_birth_during_capture_refuses(self):
        with patch.object(kernel, '_check_scope'), patch.object(kernel, 'observe_held_session'), \
             patch.object(kernel, '_capture_process', side_effect=['450', '451']), self.assertRaises(DatabaseRefused):
            kernel.capture_backend_kernel_identity('/trusted/psql', URL, SNAPSHOT, GOOD, SCOPE)

    def test_lost_lease_before_or_after_kernel_read_refuses(self):
        for sequence in [[DatabaseRefused()], [None, DatabaseRefused()]]:
            with self.subTest(sequence=len(sequence)), patch.object(kernel, '_check_scope'), \
                 patch.object(kernel, 'observe_held_session', side_effect=sequence), \
                 patch.object(kernel, '_capture_process', return_value='450'), self.assertRaises(DatabaseRefused):
                kernel.capture_backend_kernel_identity('/trusted/psql', URL, SNAPSHOT, GOOD, SCOPE)

    def test_live_original_and_zombie_refuse_before_database_query(self):
        for state in ['S', 'Z', 'X']:
            with self.subTest(state=state), patch.object(kernel, '_check_scope'), \
                 patch.object(kernel, '_stat', return_value=('450', state)), \
                 patch.object(kernel, 'observe_prior_backend_absence') as sql, self.assertRaises(DatabaseRefused):
                kernel.observe_prior_backend_identity_absence('/trusted/psql', URL, self.record(), GOOD, SCOPE)
            sql.assert_not_called()

    def test_absent_and_reused_kernel_identity_supply_no_replacement_authority(self):
        for stat in [FileNotFoundError(), ('451', 'S')]:
            with self.subTest(stat=stat), patch.object(kernel, '_check_scope'), \
                 patch.object(kernel, '_stat', side_effect=[stat, stat]), \
                 patch.object(kernel, 'observe_prior_backend_absence', return_value={
                     'original_backend_absent': True, 'backend_activity_absence_observed': True,
                     'kernel_backend_absence_observed': False, 'writer_exclusion_established': False,
                     'owner_process_absence_observed': False, 'descendant_absence_observed': False,
                     'lease_acquired': False}) as sql:
                result = kernel.observe_prior_backend_identity_absence('/trusted/psql', URL, self.record(), GOOD, SCOPE)
            self.assertIs(result['kernel_backend_absence_observed'], True)
            self.assertEqual(result['kernel_pid_reused'], isinstance(stat, tuple))
            for key in ['writer_exclusion_established', 'owner_process_absence_observed',
                        'descendant_absence_observed', 'lease_acquired', 'replacement_admitted']:
                self.assertIs(result[key], False)
            self.assertNotIn('backend_pid', result)
            sql.assert_called_once_with('/trusted/psql', URL, SNAPSHOT, GOOD)

    def test_sql_absence_and_second_kernel_observation_are_both_required(self):
        for sql_result, stat_results in [(DatabaseRefused(), [FileNotFoundError()]),
                                         ({}, [FileNotFoundError(), ('450', 'S')])]:
            with patch.object(kernel, '_check_scope'), patch.object(kernel, '_stat', side_effect=stat_results), \
                 patch.object(kernel, 'observe_prior_backend_absence', side_effect=[sql_result]), \
                 self.assertRaises(DatabaseRefused):
                kernel.observe_prior_backend_identity_absence('/trusted/psql', URL, self.record(), GOOD, SCOPE)

    def test_unknown_or_type_aliased_record_refuses_before_process_or_query(self):
        for key, value in [('protocol', True), ('kernel_birth', '0450'), ('kind', 'other'),
                           ('extra', True), ('server_scope', {**SCOPE, 'postgres_uid': True}),
                           ('database_session', {**SNAPSHOT, 'backend_pid': True})]:
            record = self.record(); record[key] = value
            with self.subTest(key=key), patch.object(kernel, '_stat') as process, \
                 patch.object(kernel, 'observe_prior_backend_absence') as sql, self.assertRaises(DatabaseRefused):
                kernel.observe_prior_backend_identity_absence('/trusted/psql', URL, record, GOOD, SCOPE)
            process.assert_not_called(); sql.assert_not_called()

    def test_changed_server_scope_refuses_even_if_original_pid_is_missing(self):
        for key, value in [('boot_id', '22222222-2222-4222-8222-222222222222'),
                           ('pid_namespace', 'pid:[12346]'), ('time_namespace', 'time:[4442]'), ('postgres_uid', 1002)]:
            scope = {**SCOPE, key: value}
            with self.subTest(key=key), patch.object(kernel, '_stat') as process, self.assertRaises(DatabaseRefused):
                kernel.observe_prior_backend_identity_absence('/trusted/psql', URL, self.record(), GOOD, scope)
            process.assert_not_called()

    def test_permission_or_missing_scope_is_not_process_absence(self):
        for failure in [PermissionError(), FileNotFoundError()]:
            with patch.object(kernel, '_check_scope', side_effect=failure), \
                 patch.object(kernel, '_stat') as process, self.assertRaises(DatabaseRefused):
                kernel.observe_prior_backend_identity_absence('/trusted/psql', URL, self.record(), GOOD, SCOPE)
            process.assert_not_called()

    def test_unreadable_original_stat_refuses_instead_of_becoming_absence(self):
        with patch.object(kernel, '_check_scope'), patch.object(kernel, '_stat', side_effect=PermissionError()), \
             patch.object(kernel, 'observe_prior_backend_absence') as sql, self.assertRaises(DatabaseRefused):
            kernel.observe_prior_backend_identity_absence('/trusted/psql', URL, self.record(), GOOD, SCOPE)
        sql.assert_not_called()

    def test_observer_scope_must_match_actual_boot_and_procfs_pid_mapping(self):
        good = 'Pid:\t4242\nTgid:\t4242\nNSpid:\t4242\nNStgid:\t4242\n'
        for boot, namespace, status in [
                (SCOPE['boot_id'], SCOPE['pid_namespace'], good),
                ('22222222-2222-4222-8222-222222222222', SCOPE['pid_namespace'], good),
                (SCOPE['boot_id'], 'pid:[12346]', good),
                (SCOPE['boot_id'], SCOPE['pid_namespace'], good.replace('NSpid:\t4242', 'NSpid:\t4242 2')),
                (SCOPE['boot_id'], SCOPE['pid_namespace'], good.replace('Pid:\t4242', 'Pid:\t4243'))]:
            with patch.object(kernel.sys, 'platform', 'linux'), patch.object(kernel.os, 'getpid', return_value=4242), \
                 patch.object(kernel.os, 'readlink', side_effect=lambda path: namespace if path.endswith('/pid') else SCOPE['time_namespace']), \
                 patch.object(kernel, '_read', side_effect=[boot, 'monotonic 0 0\nboottime 0 0\n', status]):
                if (boot, namespace, status) == (SCOPE['boot_id'], SCOPE['pid_namespace'], good):
                    kernel._check_scope(SCOPE)
                else:
                    with self.assertRaises(DatabaseRefused): kernel._check_scope(SCOPE)

    def test_changed_time_namespace_or_offsets_refuse_before_kernel_identity(self):
        for namespace, offsets in [('time:[4442]', 'monotonic 0 0\nboottime 0 0\n'),
                                   (SCOPE['time_namespace'], 'monotonic 0 0\nboottime 60 0\n'),
                                   (SCOPE['time_namespace'], 'monotonic 0 1\nboottime 0 0\n')]:
            with self.subTest(namespace=namespace, offsets=offsets), \
                 patch.object(kernel.sys, 'platform', 'linux'), \
                 patch.object(kernel.os, 'readlink', side_effect=lambda path: SCOPE['pid_namespace'] if path.endswith('/pid') else namespace), \
                 patch.object(kernel, '_read', side_effect=[SCOPE['boot_id'], offsets]), \
                 patch.object(kernel, '_stat') as process, \
                 patch.object(kernel, 'observe_prior_backend_absence') as sql, self.assertRaises(DatabaseRefused):
                kernel.observe_prior_backend_identity_absence('/trusted/psql', URL, self.record(), GOOD, SCOPE)
            process.assert_not_called(); sql.assert_not_called()

    def test_process_status_must_show_one_server_namespace_and_exact_account(self):
        good = 'Pid:\t1234\nTgid:\t1234\nNSpid:\t1234\nNStgid:\t1234\nUid:\t1001 1001 1001 1001\n'
        for raw in [good.replace('NSpid:\t1234', 'NSpid:\t1234 5'),
                    good.replace('Uid:\t1001 1001 1001 1001', 'Uid:\t1001 1002 1001 1001'),
                    good + 'Pid:\t1234\n']:
            with patch.object(kernel, '_stat', return_value=('450', 'S')), \
                 patch.object(kernel, '_read', return_value=raw), self.assertRaises(DatabaseRefused):
                kernel._capture_process(1234, SCOPE)

    def test_stat_parsing_handles_parentheses_and_refuses_malformed_identity(self):
        good = '1234 (postgres (worker)) S ' + ' '.join(['0']*18 + ['450', '0'])
        with patch.object(kernel, '_read', return_value=good):
            self.assertEqual(kernel._stat(1234), ('450', 'S'))
        for raw in [good.replace('1234 (', '1235 ('), good.replace('450', '0450'), '1234 (postgres) S 1']:
            with patch.object(kernel, '_read', return_value=raw), self.assertRaises(DatabaseRefused):
                kernel._stat(1234)


@unittest.skipUnless(sys.platform == 'linux' and os.getuid() != 0, 'Actual ordinary Linux procfs required')
class ActualKernelBackendProcessTest(unittest.TestCase):
    def scope(self):
        return {'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                'pid_namespace': os.readlink('/proc/self/ns/pid'),
                'time_namespace': os.readlink('/proc/self/ns/time'), 'postgres_uid': os.getuid()}

    def test_actual_child_is_present_until_reaped_and_then_absent_without_signals(self):
        scope = self.scope()
        kernel._check_scope(scope)
        with subprocess.Popen([sys.executable, '-c', 'import sys;sys.stdin.buffer.read(1)'], stdin=subprocess.PIPE) as child:
            try:
                birth = kernel._capture_process(child.pid, scope)
                record = {'database_session': {'backend_pid': child.pid}, 'kernel_birth': birth}
                with self.assertRaises(DatabaseRefused): kernel._kernel_absence(record, scope)
                child.stdin.write(b'x'); child.stdin.flush(); self.assertEqual(child.wait(timeout=5), 0)
                self.assertIs(kernel._kernel_absence(record, scope), False)
            finally:
                if child.poll() is None:
                    child.stdin.close(); child.wait(timeout=5)

    def test_actual_zombie_is_not_absent_until_original_parent_reaps_it(self):
        scope = self.scope()
        with subprocess.Popen([sys.executable, '-c', 'pass']) as child:
            try:
                deadline = time.monotonic() + 5
                while True:
                    birth, state = kernel._stat(child.pid)
                    if state == 'Z': break
                    self.assertLess(time.monotonic(), deadline); time.sleep(.01)
                record = {'database_session': {'backend_pid': child.pid}, 'kernel_birth': birth}
                with self.assertRaises(DatabaseRefused): kernel._kernel_absence(record, scope)
                self.assertEqual(child.wait(timeout=5), 0)
                self.assertIs(kernel._kernel_absence(record, scope), False)
            finally:
                child.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
