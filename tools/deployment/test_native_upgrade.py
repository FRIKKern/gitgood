import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

from native_inventory import directory_identity
from native_upgrade import NativeUpgrade
from upgrade_journal import canonical, UpgradeRefused


@unittest.skipUnless(sys.platform == "linux", "Native execution requires Linux")
class PlanCustodyTest(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.root.chmod(0o700)
        self.history = self.root / "history"
        self.history.mkdir(mode=0o700)
        (self.history / "plans").mkdir(mode=0o700)
        for name in ["old", "stages", "credentials"]:
            (self.root / name).mkdir(mode=0o700)
        self.operation = str(uuid.uuid4())
        installation = str(uuid.uuid4())
        bindings = {"installation": installation, "resources": {"root": directory_identity(self.root, private=True)}}
        digest = hashlib.sha256(canonical(bindings)).hexdigest()
        self.inventory = {"bindings": bindings, "bindings_sha256": digest}
        self.intent = {"installation": installation, "old_candidate": "a" * 40, "new_candidate": "b" * 40,
                       "old_artifact_sha256": "c" * 64, "new_artifact_sha256": "d" * 64,
                       "bindings_sha256": digest, "rollback_policy": "same_schema_only"}
        self.plan = {"protocol": 1, "operation": self.operation, "intent_sha256": hashlib.sha256(canonical(self.intent)).hexdigest(),
                     "old_stage": str(self.root / "old"), "new_archive": str(self.root / "archive.tar.gz"),
                     "stages": str(self.root / "stages"), "credentials": str(self.root / "credentials"),
                     "credentials_sha256": "e" * 64, "expected_current_sha256": "f" * 64}
        self.path = self.history / "plans" / (self.operation + ".json")

    def save(self):
        self.path.write_bytes(canonical(self.plan) + b"\n")
        self.path.chmod(0o600)
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def create(self, digest):
        return NativeUpgrade(self.root, self.inventory, self.history, self.operation, self.intent, digest)

    def test_plan_digest_intent_and_closed_descriptor_refuse_before_actions(self):
        digest = self.save()
        self.create(digest)
        self.assertFalse((self.history / "upgrade-history-v1.json").exists())
        with self.assertRaises(UpgradeRefused):
            self.create("0" * 64)
        for name, value in [("operation", str(uuid.uuid4())), ("intent_sha256", "0" * 64), ("command", "arbitrary")]:
            before = self.plan.copy()
            self.plan[name] = value
            with self.subTest(name=name), self.assertRaises(UpgradeRefused):
                self.create(self.save())
            self.plan = before
        self.assertFalse((self.history / "operations").exists())

    def test_plan_alias_shared_permissions_and_mutated_bindings_refuse(self):
        digest = self.save()
        self.path.chmod(0o644)
        with self.assertRaises(UpgradeRefused):
            self.create(digest)
        self.path.chmod(0o600)
        original = self.path.read_bytes()
        self.path.unlink()
        target = self.root / "aliased"
        target.write_bytes(original)
        target.chmod(0o600)
        self.path.symlink_to(target)
        with self.assertRaises(UpgradeRefused):
            self.create(digest)
        self.path.unlink()
        digest = self.save()
        self.inventory["bindings"]["installation"] = str(uuid.uuid4())
        with self.assertRaises(UpgradeRefused):
            self.create(digest)

    def test_replaced_installation_directory_refuses_retained_resource_digest(self):
        digest = self.save()
        self.inventory["bindings"]["resources"]["root"]["inode"] += 1
        bindings_digest = hashlib.sha256(canonical(self.inventory["bindings"])).hexdigest()
        self.inventory["bindings_sha256"] = self.intent["bindings_sha256"] = bindings_digest
        self.plan["intent_sha256"] = hashlib.sha256(canonical(self.intent)).hexdigest()
        with self.assertRaises(UpgradeRefused):
            self.create(self.save())


@unittest.skipIf(sys.platform == "linux", "Foreign-platform early refusal")
class UnsupportedUpgradeTest(unittest.TestCase):
    def test_execution_refuses_before_resources_are_accessed(self):
        with self.assertRaises(UpgradeRefused):
            NativeUpgrade(None, None, None, None, None, None)
