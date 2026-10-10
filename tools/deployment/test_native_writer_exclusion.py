import copy
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import native_writer_exclusion as exclusion
import test_native_durable_database as fixtures


@unittest.skipUnless(sys.platform == "linux" and os.getuid() != 0, "ordinary Linux session custody")
class NativeWriterExclusionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def client(self, fault=""):
        path = self.root / "fixture-client"
        code = "#!/usr/bin/python3\nimport json,os,re,sys,time\ngood=" + repr(fixtures.GOOD) + "\nfault=" + repr(fault) + "\n"
        code += """
assert os.environ['PGPASSFILE']=='/dev/null' and os.environ['PGPASSWORD']=='private-fixture'
assert 'PGSERVICE' not in os.environ and 'LD_PRELOAD' not in os.environ
index=0;pending=''
for part in sys.stdin:
 pending+=part
 if not part.rstrip().endswith(';'):continue
 line=pending;pending=''
 assert ('pg_try_advisory_lock' in line)==(index==0)
 request=re.search("'request','([^']+)'",line).group(1)
 value={'request':request,'identity':good,'held':True,'backend_pid':4242,'backend_birth':'1791615000000000','clients':1}
 if fault=='stale':value['request']='00000000-0000-4000-8000-000000000001'
 if fault=='busy':value['held']=False
 if fault=='other_client':value['clients']=2
 if fault=='bool_pid':value['backend_pid']=True
 if fault=='changed_session' and index:value['backend_pid']=4243
 if fault=='changed_birth' and index:value['backend_birth']='1791615000000001'
 if fault=='changed_role' and index:value['identity']['superuser']=True
 if fault=='extra':value['unexpected']=True
 if fault=='overflow':print('X'*16385,flush=True);time.sleep(100)
 elif fault=='partial':print('{',end='',flush=True);time.sleep(100)
 else:print(json.dumps(value),flush=True)
 index+=1
"""
        path.write_text(code)
        path.chmod(0o700)
        return str(path)

    def open(self, path=None):
        return exclusion.NativeWriterExclusion(path or self.client(), fixtures.URL, fixtures.GOOD)

    def test_fixed_session_rechecks_without_reacquiring_and_env_is_explicit(self):
        with patch.dict(os.environ, {"PGSERVICE": "foreign", "LD_PRELOAD": "/untrusted"}):
            lease = self.open()
            with lease:
                child = lease.child
                for _ in range(3):
                    result = lease.check()
                    self.assertEqual(result["backend_pid"], 4242)
                    self.assertFalse(result["generation_published"])
                    self.assertEqual(result["database"], fixtures.GOOD)
        self.assertIsNotNone(child.returncode)
        self.assertIsNone(lease.child)
        with self.assertRaises(exclusion.WriterExclusionRefused):
            lease.check()

    def test_invalid_inputs_and_privileged_expected_role_refuse_before_launch(self):
        with patch.object(exclusion.subprocess, "Popen") as launch:
            for psql, url in [("psql", fixtures.URL), ("/trusted/psql", fixtures.URL + "?options=x")]:
                with self.assertRaises(exclusion.WriterExclusionRefused):
                    exclusion.NativeWriterExclusion(psql, url, fixtures.GOOD)
            with self.assertRaises(exclusion.WriterExclusionRefused):
                exclusion.NativeWriterExclusion("/trusted/psql", fixtures.URL, dict(fixtures.GOOD, superuser=True))
            launch.assert_not_called()

    def test_closed_acquisition_refuses_busy_other_client_stale_and_malformed(self):
        real = subprocess.Popen
        for fault in ["busy", "other_client", "stale", "bool_pid", "extra"]:
            children = []
            def launch(*args, **kwargs):
                value = real(*args, **kwargs)
                children.append(value)
                return value
            with self.subTest(fault=fault), patch.object(exclusion.subprocess, "Popen", side_effect=launch):
                with self.assertRaises(exclusion.WriterExclusionRefused):
                    with self.open(self.client(fault)):
                        pass
            self.assertIsNotNone(children[0].returncode)

    def test_changed_backend_or_role_poison_and_reap_the_original_child(self):
        for fault in ["changed_session", "changed_birth", "changed_role"]:
            with self.subTest(fault=fault):
                lease = self.open(self.client(fault))
                with lease:
                    child = lease.child
                    with self.assertRaises(exclusion.WriterExclusionRefused):
                        lease.check()
                    self.assertIsNotNone(child.returncode)
                    self.assertFalse(lease.usable)

    def test_actual_output_overflow_reaps_the_owned_child(self):
        lease = self.open(self.client("overflow"))
        real = subprocess.Popen
        children = []
        def launch(*args, **kwargs):
            child = real(*args, **kwargs)
            children.append(child)
            return child
        with patch.object(exclusion.subprocess, "Popen", side_effect=launch):
            with self.assertRaises(exclusion.WriterExclusionRefused):
                with lease:
                    pass
        self.assertIsNotNone(children[0].returncode)

    def test_partial_output_deadline_reaps_the_owned_child(self):
        lease = self.open(self.client("partial"))
        with patch.object(exclusion.time, "monotonic", side_effect=[0, 0, 20]):
            with self.assertRaises(exclusion.WriterExclusionRefused):
                with lease:
                    pass
        self.assertIsNone(lease.child)
        self.assertFalse(lease.usable)

    def test_forked_and_other_thread_cannot_check_or_close_parent_session(self):
        with self.open() as lease:
            outcomes = []
            def foreign():
                try:
                    lease.close()
                except exclusion.WriterExclusionRefused:
                    outcomes.append("refused")
            worker = threading.Thread(target=foreign)
            worker.start()
            worker.join(timeout=2)
            self.assertEqual(outcomes, ["refused"])
            child = os.fork()
            if child == 0:
                try:
                    lease.check()
                except exclusion.WriterExclusionRefused:
                    os._exit(7)
                os._exit(9)
            self.assertEqual(os.waitpid(child, 0)[1], 7 << 8)
            self.assertTrue(lease.check()["held"])

    def test_expected_identity_is_copied_and_cannot_be_changed_by_caller(self):
        expected = copy.deepcopy(fixtures.GOOD)
        lease = exclusion.NativeWriterExclusion(self.client(), fixtures.URL, expected)
        expected["cluster"] = "999"
        with lease:
            self.assertEqual(lease.check()["database"]["cluster"], fixtures.GOOD["cluster"])
