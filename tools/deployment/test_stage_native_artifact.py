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

import test_inspect_native_artifact as fixtures
from stage_native_artifact import stage_native_artifact, publish_directory
from upgrade_journal import UpgradeRefused, canonical


@unittest.skipUnless(sys.platform == "linux", "Native staging requires Linux")
class NativeStagingTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ArtifactInspectionTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.root.chmod(0o700)
        self.operation = str(uuid.uuid4())
        self.digest = self.fixture.archive()
        self.target = self.root / ("native-" + self.operation)
        self.partial = self.root / (".native-" + self.operation + ".partial")

    def stage(self, digest=None):
        return stage_native_artifact(self.fixture.path, digest or self.digest,
                                     self.fixture.candidate, self.root, self.operation)

    def test_real_files_staged_with_independent_hash_inventory_and_no_execution(self):
        original = self.fixture.path.read_bytes()
        receipt = self.stage()
        self.assertEqual(receipt["status"], "staged")
        self.assertEqual(receipt["files"], 6)
        self.assertEqual(self.fixture.path.read_bytes(), original)
        self.assertFalse(self.partial.exists())
        inventory = json.loads((self.target / "inventory.json").read_text())
        self.assertEqual(hashlib.sha256(canonical(inventory)).hexdigest(), receipt["inventory_sha256"])
        for value in inventory:
            path = self.target / "code" / value["path"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), value["sha256"])
            self.assertEqual(bool(path.stat().st_mode & 0o111), value["executable"])
            self.assertEqual(path.stat().st_mode & 0o077, 0)
        self.assertEqual((self.target / "code/forge/bin/gitgood").read_text(),
                         "synthetic test entry point; never executed")

    def test_wrong_digest_or_traversal_retains_partial_but_never_publishes(self):
        with self.assertRaises(UpgradeRefused):
            self.stage("f" * 64)
        self.assertFalse(self.target.exists())
        self.assertTrue(self.partial.is_dir())
        self.operation = str(uuid.uuid4())
        member = tarfile.TarInfo("forge/../../outside")
        member.size = 1
        self.digest = self.fixture.archive(extra=[(member, b"x")])
        with self.assertRaises(ValueError):
            self.stage()
        self.assertFalse((self.root / "outside").exists())
        self.assertFalse((self.root / ("native-" + self.operation)).exists())

    def test_existing_targets_and_partial_requests_preserve_unrelated_files(self):
        self.target.mkdir()
        sentinel = self.target / "unrelated"
        sentinel.write_text("retain")
        with self.assertRaises(UpgradeRefused):
            self.stage()
        self.assertEqual(sentinel.read_text(), "retain")
        self.operation = str(uuid.uuid4())
        partial = self.root / (".native-" + self.operation + ".partial")
        partial.mkdir()
        (partial / "custody").write_text("unknown prior stage")
        with self.assertRaises(FileExistsError):
            self.stage()
        self.assertEqual((partial / "custody").read_text(), "unknown prior stage")

    def test_atomic_publication_cannot_replace_a_racing_empty_directory(self):
        def race(source, destination):
            Path(destination).mkdir()
            publish_directory(source, destination)
        with patch("stage_native_artifact.publish_directory", side_effect=race), self.assertRaises(FileExistsError):
            self.stage()
        self.assertEqual(list(self.target.iterdir()), [])
        self.assertTrue((self.partial / "receipt.json").is_file())

    def test_shared_parent_or_source_symlink_refuses(self):
        self.root.chmod(0o755)
        with self.assertRaises(UpgradeRefused):
            self.stage()
        self.assertEqual(list(self.root.iterdir()), [])
        self.root.chmod(0o700)
        link = self.fixture.path.parent / "archive-link"
        link.symlink_to(self.fixture.path)
        with self.assertRaises(OSError):
            stage_native_artifact(link, self.digest, self.fixture.candidate, self.root, self.operation)
        self.assertFalse(self.target.exists())

    def test_internal_existing_symlink_is_retained_without_external_writes(self):
        member = tarfile.TarInfo("web/package-link")
        member.type, member.linkname = tarfile.SYMTYPE, "package.json"
        self.digest = self.fixture.archive(extra=[(member, None)])
        receipt = self.stage()
        self.assertEqual(receipt["symlinks"], 1)
        self.assertEqual(os.readlink(self.target / "code/web/package-link"), "package.json")


class UnsupportedStagingPlatformTest(unittest.TestCase):
    @unittest.skipIf(sys.platform == "linux", "Linux is the supported operational profile")
    def test_foreign_platform_refuses_before_any_directory_creation(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(UpgradeRefused):
                stage_native_artifact("missing", "a" * 64, "b" * 40, Path(root), str(uuid.uuid4()))
            self.assertEqual(list(Path(root).iterdir()), [])
