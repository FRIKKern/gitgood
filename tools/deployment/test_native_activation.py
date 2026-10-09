import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import uuid

from native_activation import NativeActivation
from native_actions import verify_runtime_stage
import test_native_actions as action_fixtures
from upgrade_history import UpgradeHistory
from upgrade_journal import UpgradeRefused, canonical


@unittest.skipUnless(sys.platform == "linux", "Native activation custody requires Linux")
class ActivationCustodyTest(unittest.TestCase):
    def setUp(self):
        self.fixture = action_fixtures.NativeActionsTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root / "history"
        self.root.mkdir(mode=0o700)
        self.operation = str(uuid.uuid4())
        self.intent = {"installation": str(uuid.uuid4()), "old_candidate": self.fixture.fixture.candidate,
                       "new_candidate": self.fixture.fixture.candidate, "old_artifact_sha256": self.fixture.digest,
                       "new_artifact_sha256": self.fixture.digest, "bindings_sha256": "e" * 64, "rollback_policy": "same_schema_only"}
        self.history = UpgradeHistory(self.root, self.operation, self.intent)
        self.journal = self.history.__enter__()
        self.addCleanup(self.history.__exit__, None, None, None)
        self.state = NativeActivation(self.history, self.journal)
        self.schema = verify_runtime_stage(self.fixture.stage, self.fixture.fixture.candidate, self.fixture.digest)["migrations"]
        self.probe = {"candidate": self.fixture.fixture.candidate, "public_functional_probe": True, "receipt_sha256": "a" * 64}

    def public_stage(self):
        for stage in ["inspect", "stage", "maintenance", "migrate", "verify", "activate"]:
            self.journal.begin(stage)
            self.journal.succeed(stage, {"receipt_sha256": "b" * 64})
        self.journal.begin("public_verify")

    def activate(self, **kwargs):
        return self.state.activate(self.fixture.stage, self.schema, self.probe, expected_current_sha256=kwargs.get("expected"))

    def test_exact_pointer_persists_and_same_write_retry_is_idempotent(self):
        self.public_stage()
        result = self.activate()
        before = self.state.path.read_bytes()
        self.assertEqual(result["sha256"], hashlib.sha256(before).hexdigest())
        self.assertEqual(result["record"]["operation"], self.operation)
        self.assertEqual(self.activate(), result)
        self.assertEqual(self.state.path.read_bytes(), before)
        self.assertEqual(self.journal.status()["status"], "running", "Pointer write must not complete journal/probes")

    def test_unowned_or_wrong_stage_refuses_before_staged_code_observation(self):
        with patch("native_activation.verify_runtime_stage") as inspect, self.assertRaises(UpgradeRefused):
            self.activate()
        inspect.assert_not_called()
        self.public_stage()
        saved = self.history.lock
        self.history.lock = None
        try:
            with self.assertRaises(UpgradeRefused):
                self.activate()
        finally:
            self.history.lock = saved
        self.assertIsNone(self.state.read())

    def test_wrong_schema_or_probe_identity_refuses_without_pointer(self):
        self.public_stage()
        self.schema = ["20260101000000"]
        with self.assertRaises(UpgradeRefused):
            self.activate()
        self.schema = verify_runtime_stage(self.fixture.stage, self.fixture.fixture.candidate, self.fixture.digest)["migrations"]
        for patch_value in [{"candidate": "f" * 40}, {"public_functional_probe": 1}, {"receipt_sha256": "payload must refuse"}]:
            before = self.probe.copy()
            self.probe.update(patch_value)
            with self.assertRaises(UpgradeRefused):
                self.activate()
            self.probe = before
        self.assertIsNone(self.state.read())

    def test_stale_compare_and_swap_and_foreign_installation_refuse(self):
        self.public_stage()
        result = self.activate()
        before = self.state.path.read_bytes()
        self.probe["receipt_sha256"] = "c" * 64
        with self.assertRaises(UpgradeRefused):
            self.activate()
        self.assertEqual(self.state.path.read_bytes(), before)
        self.assertNotEqual(self.activate(expected=result["sha256"])["sha256"], result["sha256"])
        current = json.loads(self.state.path.read_bytes())
        current["installation"] = str(uuid.uuid4())
        self.state.path.write_bytes(canonical(current))
        digest = hashlib.sha256(self.state.path.read_bytes()).hexdigest()
        with self.assertRaises(UpgradeRefused):
            self.activate(expected=digest)

    def test_lost_write_ack_disables_owner_and_exposes_landed_pointer(self):
        self.public_stage()
        original = os.fsync
        calls = 0
        def lost_ack(descriptor):
            nonlocal calls
            calls += 1
            original(descriptor)
            if calls == 2:
                raise OSError("inert fixture after directory fsync")
        with patch("native_activation.os.fsync", side_effect=lost_ack), self.assertRaises(OSError):
            self.activate()
        self.assertFalse(self.state.usable)
        self.assertEqual(self.state.read()["record"]["candidate"], self.intent["new_candidate"])
        with self.assertRaises(UpgradeRefused):
            self.activate()
        self.assertEqual(self.journal.status()["status"], "running")

    def test_pointer_alias_hardlink_and_shared_mode_refuse(self):
        self.public_stage()
        self.activate()
        data = self.state.path.read_bytes()
        self.state.path.chmod(0o644)
        with self.assertRaises(UpgradeRefused):
            self.state.read()
        self.state.path.chmod(0o600)
        alias = self.root / "alias"
        os.link(self.state.path, alias)
        with self.assertRaises(UpgradeRefused):
            self.state.read()
        alias.unlink()
        self.state.path.unlink()
        self.state.path.symlink_to(self.root / "missing")
        with self.assertRaises((UpgradeRefused, FileNotFoundError)):
            self.state.read()
        self.state.path.unlink()
        self.state.path.write_bytes(data)
        self.state.path.chmod(0o600)
        self.assertEqual(self.state.read()["record"]["operation"], self.operation)


@unittest.skipIf(sys.platform == "linux", "Foreign-platform early refusal")
class UnsupportedActivationTest(unittest.TestCase):
    def test_activation_refuses_before_resource_access(self):
        with self.assertRaises(UpgradeRefused):
            NativeActivation(None, None)
