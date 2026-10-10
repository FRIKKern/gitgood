import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import test_native_enrollment_custody as fixtures
from initial_staging_retention import retain_initial_partial
from native_inventory import directory_identity
from upgrade_journal import UpgradeRefused


@unittest.skipUnless(sys.platform == "linux", "Private interrupted staging custody requires Linux")
class InitialStagingRetentionTest(unittest.TestCase):
    save = fixtures.InitialLifecycleCustodyTest.save
    custody = fixtures.InitialLifecycleCustodyTest.custody

    def setUp(self):
        fixtures.InitialLifecycleCustodyTest.setUp(self)
        self.partial = self.root / "staging" / (".native-" + self.request["operation"] + ".partial")

    def stage(self,custody):
        custody.journal.begin("inspect"); custody.journal.succeed("inspect",self.evidence)
        custody.journal.begin("stage")

    def create(self):
        self.partial.mkdir(mode=0o700)
        path = self.partial / "incomplete-archive"; path.write_bytes(b"retained inert partial bytes"); path.chmod(0o600)
        return directory_identity(self.partial,private=True)

    def test_absent_partial_requires_no_mutation_and_wrong_stage_refuses(self):
        with self.custody() as custody:
            custody.journal.begin("inspect")
            with self.assertRaises(UpgradeRefused): retain_initial_partial(custody)
            custody.journal.succeed("inspect",self.evidence); custody.journal.begin("stage")
            before = {p.name:p.read_bytes() for p in self.history.iterdir()}
            self.assertEqual(retain_initial_partial(custody)["retained_partials"],[])
            self.assertEqual({p.name:p.read_bytes() for p in self.history.iterdir()},before)

    def test_exact_partial_moves_once_preserving_inode_and_all_original_bytes(self):
        original = self.create()
        with self.custody() as custody:
            self.stage(custody); result = retain_initial_partial(custody)
            self.assertEqual(len(result["retained_partials"]),1)
            retained = result["retained_partials"][0]["directory"]
            self.assertEqual(retained,{**original,"path":retained["path"]})
            self.assertEqual((Path(retained["path"]) / "incomplete-archive").read_bytes(),b"retained inert partial bytes")
            before = {str(p):(p.stat().st_ino,p.read_bytes()) for p in self.history.iterdir()}
            self.assertEqual(retain_initial_partial(custody),result)
            self.assertEqual({str(p):(p.stat().st_ino,p.read_bytes()) for p in self.history.iterdir()},before)

    def test_next_partial_is_retained_separately_without_adopting_an_earlier_attempt(self):
        self.create()
        with self.custody() as custody:
            self.stage(custody); first = retain_initial_partial(custody)
            next_identity = self.create(); second = retain_initial_partial(custody)
            self.assertEqual(len(second["retained_partials"]),2)
            identities = [item["directory"]["inode"] for item in second["retained_partials"]]
            self.assertIn(next_identity["inode"],identities)
            self.assertIn(first["retained_partials"][0]["directory"]["inode"],identities)

    def test_lost_rename_acknowledgement_poison_then_reopen_preserves_original_partial(self):
        self.create()
        with self.custody() as custody:
            self.stage(custody)
            with patch("initial_staging_retention.sync_directory",side_effect=[None,OSError("inert lost rename acknowledgement")]):
                with self.assertRaises(OSError): retain_initial_partial(custody)
            self.assertFalse(custody.usable)
        with self.custody() as reopened:
            self.assertEqual(reopened.journal.record["status"],"uncertain")
            reopened.journal.reconcile(applied=False,evidence=self.evidence); reopened.journal.begin("stage")
            result = retain_initial_partial(reopened)
            self.assertEqual(len(result["retained_partials"]),1)
            self.assertEqual((Path(result["retained_partials"][0]["directory"]["path"]) / "incomplete-archive").read_bytes(),b"retained inert partial bytes")

    def test_alias_shared_or_replaced_reserved_partial_refuses_preserving_data(self):
        outside = self.base / "outside"; outside.mkdir(mode=0o700)
        self.partial.symlink_to(outside,target_is_directory=True)
        with self.custody() as custody:
            self.stage(custody)
            with self.assertRaises(UpgradeRefused): retain_initial_partial(custody)
        self.assertTrue(self.partial.is_symlink()); self.assertFalse(list(outside.iterdir()))

    def test_replaced_retained_directory_or_damaged_record_cannot_authorize_new_staging(self):
        self.create()
        with self.custody() as custody:
            self.stage(custody); result = retain_initial_partial(custody)
        retained = Path(result["retained_partials"][0]["directory"]["path"])
        retained.rename(self.base / "retained-original-partial"); retained.mkdir(mode=0o700)
        with self.custody() as custody:
            custody.journal.reconcile(applied=False,evidence=self.evidence); custody.journal.begin("stage")
            with self.assertRaises(UpgradeRefused): retain_initial_partial(custody)
        self.assertEqual((self.base / "retained-original-partial/incomplete-archive").read_bytes(),b"retained inert partial bytes")

    def test_existing_published_stage_is_never_retained_as_a_partial(self):
        target = self.root / "staging" / ("native-" + self.request["operation"]); target.mkdir(mode=0o700)
        original = target.stat().st_ino
        with self.custody() as custody:
            self.stage(custody)
            with self.assertRaises(UpgradeRefused): retain_initial_partial(custody)
        self.assertEqual(target.stat().st_ino,original)
