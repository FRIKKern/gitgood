import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import uuid

import test_native_enrollment_custody as fixtures
from enrollment_journal import STAGES
from native_enrollment import NativeEnrollment
from native_initial_baseline import read_initial_baseline, seal_initial_baseline
from native_inventory import directory_identity
from native_operator import read_status
from retirement_journal import DIGESTS, RetirementJournal
from upgrade_history import UpgradeHistory
from upgrade_journal import canonical, UpgradeRefused, STAGES as UPGRADE_STAGES


@unittest.skipUnless(sys.platform == "linux", "Private installation baseline requires Linux")
class NativeInitialBaselineTest(unittest.TestCase):
    save = fixtures.InitialLifecycleCustodyTest.save
    custody = fixtures.InitialLifecycleCustodyTest.custody

    def setUp(self):
        fixtures.InitialLifecycleCustodyTest.setUp(self)
        self.stage = self.root / "staging" / ("native-" + self.request["operation"])
        self.stage.mkdir(mode=0o700)
        self.pointer = {"protocol":1, "installation":self.installation, "operation":self.request["operation"],
                        "candidate":self.request["intent"]["candidate"], "artifact_sha256":self.request["intent"]["artifact_sha256"],
                        "bindings_sha256":self.allocation["bindings_sha256"], "stage":directory_identity(self.stage,private=True),
                        "stage_inventory_sha256":"8" * 64, "schema":["20261007000000"], "public_probe_sha256":"9" * 64}
        self.probe = {"candidate":self.pointer["candidate"], **{key:True for key in ["initial_access_probe", "anonymous_private_api_denied",
                      "owner_login_verified", "current_owner_membership_verified", "authorized_repository_list_verified", "probe_session_revoked"]}}
        self.probe["receipt_sha256"] = hashlib.sha256(canonical(self.probe)).hexdigest()
        self.pointer["public_probe_sha256"] = self.probe["receipt_sha256"]
        path = self.history / "current-release-v1.json"; path.write_bytes(canonical(self.pointer) + b"\n"); path.chmod(0o600)
        # These tests exercise custody/record semantics only. An inert fixture
        # cannot establish real artifact or installed runtime verification.
        adapter = patch("native_initial_baseline.verify_runtime_stage", return_value={"inventory_sha256":"8" * 64, "migrations":self.pointer["schema"]})
        adapter.start(); self.addCleanup(adapter.stop)
        self.operation = str(uuid.uuid4())
        self.intent = {"installation":self.installation, "old_candidate":self.pointer["candidate"],
                       "new_candidate":"b" * 40, "old_artifact_sha256":self.pointer["artifact_sha256"],
                       "new_artifact_sha256":"c" * 64, "bindings_sha256":self.pointer["bindings_sha256"],
                       "rollback_policy":"same_schema_only"}

    def finish(self, custody):
        engine = NativeEnrollment(custody.inputs.directory,custody.inputs.request_sha256)
        for stage in STAGES:
            result = {"inert_unit_fixture":True}
            if stage == "bootstrap": result = {"outcome":"created", "installation":self.installation, "user_id":1, "role_at_creation":"owner"}
            if stage in {"migrate", "verify"}: result = {"schema":self.pointer["schema"]}
            if stage in {"activate", "enroll"}: result = {"schema":self.pointer["schema"], "pointer_sha256":hashlib.sha256(canonical(self.pointer) + b"\n").hexdigest(), "public_access":self.probe}
            custody.journal.begin(stage); custody.journal.succeed(stage,engine._receipt(custody,stage,result))

    def sealed(self):
        with self.custody() as custody:
            self.finish(custody)
            return seal_initial_baseline(custody)

    def upgrade(self, intent=None, operation=None):
        return UpgradeHistory(self.history,operation or self.operation,intent or self.intent)

    def stamp(self):
        return {str(p):(p.stat().st_ino,p.read_bytes()) for p in self.history.rglob("*") if p.is_file()}

    def test_initial_status_and_first_real_upgrade_keep_distinct_operation_history(self):
        baseline = self.sealed(); before = self.stamp()
        status = read_status(self.history,self.installation)
        self.assertEqual(status["upgrades"],[])
        self.assertEqual(status["initial_enrollment"]["operation"],self.request["operation"])
        self.assertEqual(status["activation_record"]["candidate"],self.pointer["candidate"])
        self.assertFalse((self.history / "operations").exists())
        self.assertFalse((self.history / "upgrade-history-v1.json").exists())
        self.assertEqual(self.stamp(),before)
        with self.upgrade() as journal:
            status = read_status(self.history,self.installation)
            self.assertEqual(len(status["upgrades"]),1)
            self.assertEqual(status["upgrades"][0]["operation"],self.operation)
            self.assertEqual(status["activation_record"]["operation"],baseline["operation"])
            for stage in UPGRADE_STAGES:
                journal.begin(stage); journal.succeed(stage,self.evidence)
            pointer = {**self.pointer,"operation":self.operation,"candidate":self.intent["new_candidate"],"artifact_sha256":self.intent["new_artifact_sha256"]}
            (self.history / "current-release-v1.json").write_bytes(canonical(pointer) + b"\n")
        self.assertEqual(read_initial_baseline(self.history),baseline)
        self.assertEqual(read_status(self.history,self.installation)["upgrades"][0]["status"],"complete")
        second = {**self.intent,"old_candidate":self.intent["new_candidate"],"old_artifact_sha256":self.intent["new_artifact_sha256"],"new_candidate":"d" * 40}
        with self.upgrade(second,str(uuid.uuid4())): pass
        self.assertEqual(len(read_status(self.history,self.installation)["upgrades"]),2)

    def test_wrong_initial_parent_bindings_and_reused_initial_operation_refuse_before_reservation(self):
        self.sealed()
        for intent in [{**self.intent,"old_candidate":"0" * 40},{**self.intent,"old_artifact_sha256":"0" * 64},{**self.intent,"bindings_sha256":"0" * 64}]:
            with self.assertRaises(UpgradeRefused):
                with self.upgrade(intent): pass
            self.assertFalse((self.history / "operations").exists())
        with self.assertRaises(UpgradeRefused):
            with self.upgrade(operation=self.request["operation"]): pass

    def test_pending_or_terminal_without_handoff_never_admits_upgrade(self):
        with self.custody() as custody:
            with self.assertRaises(UpgradeRefused): seal_initial_baseline(custody)
            self.finish(custody)
        before = self.stamp()
        with self.assertRaises(UpgradeRefused):
            with self.upgrade(): pass
        self.assertEqual(self.stamp(),before)
        with self.custody() as terminal:
            seal_initial_baseline(terminal)
        self.assertEqual(read_status(self.history,self.installation)["upgrades"],[])

    def test_lost_publication_acknowledgement_poison_then_exact_terminal_reopen_is_unchanged(self):
        with self.custody() as custody:
            self.finish(custody)
            with patch("native_initial_baseline.sync_directory",side_effect=OSError("inert lost handoff acknowledgement")):
                with self.assertRaises(OSError): seal_initial_baseline(custody)
            self.assertFalse(custody.usable)
            with self.assertRaises(UpgradeRefused): seal_initial_baseline(custody)
        before = self.stamp()
        with self.custody() as reopened:
            self.assertEqual(seal_initial_baseline(reopened),read_initial_baseline(self.history))
        self.assertEqual(self.stamp(),before)

    def test_changed_terminal_journal_anchor_or_pointer_refuses_without_upgrading(self):
        self.sealed()
        for name in ["initial-enrollment-v1.json","initial-lifecycle-anchor-v1.json","current-release-v1.json"]:
            path = self.history / name; raw = path.read_bytes(); path.write_bytes(raw + b" ")
            before = self.stamp()
            with self.subTest(name=name),self.assertRaises(UpgradeRefused):
                with self.upgrade(): pass
            self.assertEqual(self.stamp(),before)
            path.write_bytes(raw)
        self.assertEqual(read_status(self.history,self.installation)["upgrades"],[])

    def test_retirement_can_claim_real_initial_baseline_before_any_upgrade(self):
        baseline = self.sealed()
        plan = {"protocol":1,"operation":str(uuid.uuid4()),"installation":self.installation,"candidate":self.pointer["candidate"],
                **{key:"f" * 64 for key in DIGESTS},"bindings_sha256":self.pointer["bindings_sha256"],
                "artifact_sha256":self.pointer["artifact_sha256"],"current_sha256":baseline["activation_sha256"]}
        with RetirementJournal(self.history,plan,hashlib.sha256(canonical(plan)).hexdigest()) as journal:
            journal.begin("quiesce")
            before = self.stamp(); status = read_status(self.history,self.installation)
            self.assertEqual(status["upgrades"],[])
            self.assertEqual(status["retirement"]["status"],"running")
            self.assertEqual(self.stamp(),before)
        self.assertFalse((self.history / "upgrade-history-v1.json").exists())

    def test_changed_initial_chain_is_refused_when_existing_upgrade_history_is_read(self):
        self.sealed()
        with self.upgrade(): pass
        path = self.history / "upgrade-history-v1.json"; value = json.loads(path.read_bytes())
        value["operations"][0]["intent"]["old_candidate"] = "0" * 40
        path.write_bytes(canonical(value) + b"\n")
        with self.assertRaises(UpgradeRefused): read_status(self.history,self.installation)

    def test_unsealed_progress_is_read_only_and_terminal_waits_for_handoff(self):
        with self.custody() as custody:
            custody.journal.begin("inspect")
            before = self.stamp(); status = read_status(self.history,self.installation)
            self.assertEqual(status["initial_enrollment"]["status"],"running")
            self.assertFalse(status["initial_enrollment"]["baseline_sealed"])
            self.assertEqual(status["upgrades"],[])
            self.assertEqual(self.stamp(),before)
            custody.journal.succeed("inspect",self.evidence)
            for stage in STAGES[1:]:
                custody.journal.begin(stage); custody.journal.succeed(stage,self.evidence)
        before = self.stamp(); status = read_status(self.history,self.installation)
        self.assertEqual(status["initial_enrollment"]["status"],"awaiting_handoff")
        self.assertEqual(status["initial_enrollment"]["recorded_status"],"complete")
        self.assertFalse(status["initial_enrollment"]["baseline_sealed"])
        self.assertEqual(self.stamp(),before)

    def test_metadata_only_terminal_receipts_cannot_establish_initial_baseline(self):
        with self.custody() as custody:
            for stage in STAGES:
                custody.journal.begin(stage); custody.journal.succeed(stage,self.evidence)
            before = self.stamp()
            with self.assertRaises((UpgradeRefused,OSError)): seal_initial_baseline(custody)
            self.assertEqual(self.stamp(),before)
            self.assertFalse((self.history / "initial-baseline-v1.json").exists())

    def test_missing_or_changed_completed_observation_refuses_first_upgrade(self):
        self.sealed()
        for path in list(self.history.glob("enrollment-observation-*.json")):
            raw = path.read_bytes(); path.write_bytes(raw + b" ")
            before = self.stamp()
            with self.subTest(stage=json.loads(raw)["stage"]), self.assertRaises(UpgradeRefused):
                with self.upgrade(): pass
            self.assertEqual(self.stamp(),before)
            path.write_bytes(raw)
        path = next(self.history.glob("enrollment-observation-*.json")); raw = path.read_bytes(); path.unlink()
        before = self.stamp()
        with self.assertRaises((UpgradeRefused,OSError)):
            with self.upgrade(): pass
        self.assertEqual(self.stamp(),before)
        path.write_bytes(raw); path.chmod(0o600)

    def test_changed_probe_fails_handoff_even_with_its_observation_digest_rebound(self):
        with self.custody() as custody:
            self.probe["probe_session_revoked"] = False
            self.finish(custody)
            before = self.stamp()
            with self.assertRaises(UpgradeRefused): seal_initial_baseline(custody)
            self.assertEqual(self.stamp(),before)
