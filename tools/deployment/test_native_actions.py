import hashlib
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import uuid

from native_actions import NativeActions, verify_runtime_stage
from stage_native_artifact import stage_native_artifact
import test_inspect_native_artifact as fixtures
from upgrade_journal import UpgradeJournal, UpgradeRefused, canonical


@unittest.skipUnless(sys.platform == "linux", "Native lifecycle operations require Linux")
class NativeActionsTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ArtifactInspectionTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.root.chmod(0o700)
        self.operation = str(uuid.uuid4())
        extras = []
        for name in ["forge/lib/gitgood-0.1.0/priv/operations", "web/dist/server", "web/node_modules", "web/node_modules/srvx", "web/node_modules/srvx/bin"]:
            member = tarfile.TarInfo(name)
            member.type = tarfile.DIRTYPE
            member.mode = 0o755
            extras.append((member, None))
        for name in ["forge/lib/gitgood-0.1.0/priv/operations/runtime_cgroup.py", "web/client-address.mjs", "web/package-lock.json",
                     "web/dist/server/server.js", "web/node_modules/srvx/bin/srvx.mjs"]:
            data = b"inert fixture; never executed"
            member = tarfile.TarInfo(name)
            member.size = len(data)
            member.mode = 0o644
            extras.append((member, data))
        self.digest = self.fixture.archive(extra=extras)
        stage_native_artifact(self.fixture.path, self.digest, self.fixture.candidate, self.root, self.operation)
        self.stage = self.root / ("native-" + self.operation)

    def verify(self):
        return verify_runtime_stage(self.stage, self.fixture.candidate, self.digest)

    def test_actual_staged_inventory_refuses_changed_or_extra_code_before_execution(self):
        self.assertEqual(self.verify()["code"], self.stage / "code")
        server = self.stage / "code/web/server.mjs"
        original = server.read_bytes()
        server.write_bytes(b"different code")
        with self.assertRaises(UpgradeRefused):
            self.verify()
        server.write_bytes(original)
        extra = self.stage / "code/web/unrecorded.mjs"
        extra.write_bytes(b"must not execute")
        with self.assertRaises(UpgradeRefused):
            self.verify()
        extra.unlink()
        self.assertEqual(self.verify()["code"], self.stage / "code")

    def test_code_alias_hardlink_and_shared_mode_refuse(self):
        server = self.stage / "code/web/server.mjs"
        original = server.read_bytes()
        server.unlink()
        server.symlink_to(self.fixture.path)
        with self.assertRaises(UpgradeRefused):
            self.verify()
        server.unlink()
        server.write_bytes(original)
        server.chmod(0o700)
        os.link(server, self.root / "alias")
        with self.assertRaises(UpgradeRefused):
            self.verify()
        (self.root / "alias").unlink()
        server.chmod(0o755)
        with self.assertRaises(UpgradeRefused):
            self.verify()

    def test_rewritten_private_manifest_cannot_rebind_changed_code_to_original_artifact(self):
        server = self.stage / "code/web/server.mjs"
        server.write_bytes(b"changed fixture code")
        path = self.stage / "inventory.json"
        inventory = json.loads(path.read_text())
        entry = next(value for value in inventory if value["path"] == "web/server.mjs")
        entry.update(bytes=server.stat().st_size, sha256=hashlib.sha256(server.read_bytes()).hexdigest())
        path.write_bytes(canonical(inventory))
        receipt_path = self.stage / "receipt.json"
        receipt = json.loads(receipt_path.read_text())
        receipt["inventory_sha256"] = hashlib.sha256(canonical(inventory)).hexdigest()
        receipt_path.write_bytes(canonical(receipt))
        with self.assertRaises(UpgradeRefused):
            self.verify()
    def test_wrong_candidate_digest_and_incomplete_runtime_refuse(self):
        for candidate, digest in [("b" * 40, self.digest), (self.fixture.candidate, "b" * 64)]:
            with self.assertRaises(UpgradeRefused):
                verify_runtime_stage(self.stage, candidate, digest)
        # The inspector's inert minimal artifact is insufficient for execution.
        simple = self.fixture.archive()
        operation = str(uuid.uuid4())
        stage_native_artifact(self.fixture.path, simple, self.fixture.candidate, self.root, operation)
        with self.assertRaises(UpgradeRefused):
            verify_runtime_stage(self.root / ("native-" + operation), self.fixture.candidate, simple)

    def test_lifecycle_action_requires_running_owned_stage_before_kernel_access(self):
        journal_root = self.root / "journal"
        journal_root.mkdir(mode=0o700)
        intent = {"installation": str(uuid.uuid4()), "old_candidate": "a" * 40, "new_candidate": "b" * 40,
                  "old_artifact_sha256": "c" * 64, "new_artifact_sha256": "d" * 64, "bindings_sha256": "e" * 64,
                  "rollback_policy": "forward_only"}
        with UpgradeJournal(journal_root, str(uuid.uuid4()), intent) as journal:
            actions = NativeActions.__new__(NativeActions)
            actions.journal = journal
            with patch("native_actions.cgroup_identity") as group, self.assertRaises(UpgradeRefused):
                actions.stop_group("native")
            group.assert_not_called()
            journal.begin("inspect")
            with patch("native_actions.cgroup_identity") as group, self.assertRaises(UpgradeRefused):
                actions.migrate(self.stage)
            group.assert_not_called()

    def test_forged_bindings_and_unapproved_environment_refuse_before_launch(self):
        installation = str(uuid.uuid4())
        intent = {"installation": installation, "bindings_sha256": "a" * 64}
        journal = type("FixtureJournal", (), {"intent": intent})()
        with self.assertRaises(UpgradeRefused):
            NativeActions(self.root, {"bindings": {}, "bindings_sha256": "a" * 64}, journal)
        bindings = {"installation": installation, "executables": {name: {"path": "/trusted/" + name} for name in ["python", "node", "git", "psql", "caddy"]}}
        digest = hashlib.sha256(canonical(bindings)).hexdigest()
        journal.intent["bindings_sha256"] = digest
        config = self.root / "configuration"
        config.mkdir(mode=0o700)
        file = config / "installation.json"
        file.write_text(json.dumps({"forge": {"LD_PRELOAD": "unapproved"}, "web": {"PORT": "1", "GITGOOD_API_URL": "http://127.0.0.1:2", "GITGOOD_PROXY_KEY": "inert", "NODE_ENV": "production"}}))
        file.chmod(0o600)
        with patch.object(NativeActions, "reobserve") as probe, patch("native_actions.subprocess.Popen") as launch, self.assertRaises(UpgradeRefused):
            NativeActions(self.root, {"bindings": bindings, "bindings_sha256": digest}, journal)
        probe.assert_not_called()
        launch.assert_not_called()


@unittest.skipIf(sys.platform == "linux", "Foreign-platform early refusal")
class UnsupportedNativeActionsTest(unittest.TestCase):
    def test_actions_refuse_before_observing_or_changing_resources(self):
        with self.assertRaises(UpgradeRefused):
            NativeActions("unowned-path", {}, None)
