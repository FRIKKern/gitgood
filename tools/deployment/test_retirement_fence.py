import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import unittest
from unittest.mock import patch

from retirement_fence import RetirementFence
from retirement_journal import RetirementJournal
from upgrade_journal import UpgradeRefused
import test_retirement_stores


@unittest.skipUnless(sys.platform == "linux", "Native retirement custody requires Linux")
class RetirementFenceTest(unittest.TestCase):
    def setUp(self):
        self.fixture = test_retirement_stores.RetirementStoresTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.history = self.fixture.base / "fence-history"
        # Copy only this test's inert terminal upgrade record. The new history
        # independently admits retirement; no prior retirement event is erased.
        shutil.copytree(self.fixture.history, self.history,
                        ignore=shutil.ignore_patterns("retirement-journal-v1.json"))
        adapter = patch("retirement_fence.cgroup_identity", side_effect=lambda installation, name: self.fixture.bindings["cgroups"][name])
        adapter.start()
        self.addCleanup(adapter.stop)

    def claim(self):
        return RetirementJournal(self.history, self.fixture.plan, self.fixture.plan_digest)

    def fence(self, journal):
        return RetirementFence(journal, self.fixture.resource_plan)

    def test_durable_same_intent_publication_stays_outside_selected_stores(self):
        with self.claim() as journal:
            journal.begin("quiesce")
            fence = self.fence(journal)
            observed = fence.install()
            self.assertTrue(observed["retirement_fence_verified"])
            self.assertEqual(fence.install(), observed)
            self.assertEqual(fence.path.parent, self.fixture.root)
            self.assertEqual(fence.path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(fence.observe(), observed)
        self.fixture.assert_retained()

    def test_changed_or_aliased_fence_refuses_without_replacing_original(self):
        path = self.fixture.root / ".gitgood-retirement-v1.json"
        with self.claim() as journal:
            journal.begin("quiesce")
            path.write_bytes(b"another intent")
            path.chmod(0o600)
            with self.assertRaises(UpgradeRefused):
                self.fence(journal).install()
            self.assertEqual(path.read_bytes(), b"another intent")
            # Remove only the just-created disposable adversarial test entry.
            path.unlink()
            path.symlink_to(self.fixture.archive)
            with self.assertRaises(UpgradeRefused):
                self.fence(journal).install()
            self.assertTrue(path.is_symlink())
        self.fixture.assert_retained()

    def test_wrong_stage_cannot_publish_and_lost_sync_reply_keeps_fence_for_retry(self):
        with self.claim() as journal:
            with self.assertRaises(UpgradeRefused):
                self.fence(journal).install()
            journal.begin("quiesce")
            with patch("retirement_fence.os.fsync", side_effect=OSError("controlled sync failure")):
                with self.assertRaises(OSError):
                    self.fence(journal).install()
            self.assertTrue(self.fence(journal).observe()["retirement_fence_verified"])
            self.assertTrue(self.fence(journal).install()["retirement_fence_verified"])
        self.fixture.assert_retained()

    def test_actual_killed_owner_retains_fence_and_uncertain_stage(self):
        code = """import json,os,signal,sys
from unittest.mock import patch
from retirement_fence import RetirementFence
from retirement_journal import RetirementJournal
resources=json.loads(sys.argv[4])
with patch('retirement_fence.cgroup_identity',side_effect=lambda installation,name: resources['bindings']['cgroups'][name]):
 with RetirementJournal(sys.argv[1],json.loads(sys.argv[2]),sys.argv[3]) as journal:
  journal.begin('quiesce')
  RetirementFence(journal,resources).install()
  print('durable-fence-before-acknowledgement',flush=True)
  os.kill(os.getpid(),signal.SIGKILL)
"""
        child = subprocess.Popen([sys.executable, "-c", code, str(self.history), json.dumps(self.fixture.plan),
                                  self.fixture.plan_digest, json.dumps(self.fixture.resource_plan)],
                                 env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(Path(__file__).parent)},
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), "durable-fence-before-acknowledgement")
            child.communicate(timeout=10)
            self.assertEqual(child.returncode, -signal.SIGKILL)
            with self.claim() as journal:
                self.assertEqual(journal.record["status"], "uncertain")
                self.assertTrue(self.fence(journal).observe()["retirement_fence_verified"])
                with self.assertRaises(UpgradeRefused):
                    self.fence(journal).install()
                self.assertEqual(journal.record["status"], "uncertain")
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=10)
        self.fixture.assert_retained()
