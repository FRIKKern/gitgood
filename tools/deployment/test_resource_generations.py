import copy
import json
import unittest

from resource_generations import GenerationRefused, canonical, generation_sha256, make_generation, parse_generation, validate_generation, validate_successor


class ResourceGenerationRecordTest(unittest.TestCase):
    def setUp(self):
        self.installation = "00000000-0000-4000-8000-000000000001"
        unit = "gitgood-installation-" + self.installation + ".service"
        parent = "/sys/fs/cgroup/system.slice/" + unit
        self.scope = {"protocol": 2, "profile": "systemd", "installation": self.installation,
                      "boot_id": "00000000-0000-4000-8000-000000000002", "uid": 65503, "gid": 1000,
                      "unit": unit, "unit_definition": {"path": "/etc/systemd/system/" + unit, "device": 100, "inode": 200, "bytes": 600, "sha256": "a" * 64},
                      "manager": {"pid": 2000, "birth": "30000", "uid": 65503, "mount_namespace": "mnt:[4026532000]", "cgroup_namespace": "cgroup:[4026532001]",
                                  "security": {"gid": 1000, "supplementary_groups": [1000], "capabilities": {name: 0 for name in ["CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"]}, "no_new_privileges": True}},
                      "parent": {"path": parent, "device": 27, "inode": 300, "uid": 65503},
                      "groups": {name: {"path": parent + "/" + name, "device": 27, "inode": 301 + index, "uid": 65503} for index, name in enumerate(["driver", "native", "web", "edge", "maintenance"])},
                      "limits": {"cpu_quota_us": 200000, "cpu_period_us": 100000, "memory_bytes": 268435456, "swap_bytes": 0},
                      "service_scope_observed": True, "installation_readiness_established": False}
        self.first = make_generation(self.scope, "b" * 64, generation="00000000-0000-4000-8000-000000000003", created_at="2026-10-10T05:00:00.000000Z")
        following = copy.deepcopy(self.scope)
        following["boot_id"] = "00000000-0000-4000-8000-000000000004"
        self.second = make_generation(following, "b" * 64, generation="00000000-0000-4000-8000-000000000005", created_at="2026-10-10T05:01:00.000000Z", previous=self.first)

    def test_genesis_roundtrips_with_explicit_absent_predecessor(self):
        self.assertIsNone(self.first["predecessor_sha256"])
        self.assertEqual(parse_generation(canonical(self.first)), self.first)
        self.assertEqual(generation_sha256(self.first), generation_sha256(parse_generation(canonical(self.first))))

    def test_real_successor_links_exact_predecessor_without_mutating_inputs(self):
        before = copy.deepcopy(self.first)
        validate_successor(self.first, self.second)
        self.assertEqual(self.second["predecessor_sha256"], generation_sha256(self.first))
        self.assertEqual(self.first, before)
        self.scope["limits"]["memory_bytes"] = 536870912
        self.assertEqual(self.first["scope"]["limits"]["memory_bytes"], 268435456)

    def test_unchanged_resources_cannot_be_renamed_as_a_new_generation(self):
        with self.assertRaises(GenerationRefused):
            make_generation(self.scope, "b" * 64, generation="00000000-0000-4000-8000-000000000005", created_at="2026-10-10T05:01:00.000000Z", previous=self.first)

    def test_wrong_missing_or_reordered_predecessor_refuses(self):
        for value in [None, "c" * 64, generation_sha256(self.second)]:
            current = copy.deepcopy(self.second)
            current["predecessor_sha256"] = value
            with self.subTest(value=value), self.assertRaises(GenerationRefused):
                validate_successor(self.first, current)

    def test_foreign_installation_cannot_enter_the_existing_chain(self):
        current = copy.deepcopy(self.second)
        current["installation"] = "00000000-0000-4000-8000-000000000099"
        with self.assertRaises(GenerationRefused):
            validate_successor(self.first, current)

    def test_changed_durable_identity_requires_a_separate_continuity_protocol(self):
        current = copy.deepcopy(self.second)
        current["durable_binding_sha256"] = "c" * 64
        with self.assertRaises(GenerationRefused):
            validate_successor(self.first, current)

    def test_generation_uuid_cannot_be_reused(self):
        current = copy.deepcopy(self.second)
        current["generation"] = self.first["generation"]
        with self.assertRaises(GenerationRefused):
            validate_successor(self.first, current)

    def test_unknown_fields_cannot_smuggle_commands_credentials_or_claims(self):
        for path in [[], ["scope"], ["scope", "manager"], ["scope", "manager", "security"], ["scope", "limits"], ["scope", "groups", "native"]]:
            record = copy.deepcopy(self.first)
            target = record
            for key in path:
                target = target[key]
            target["unexpected_command_or_credential"] = "private-test-value"
            with self.subTest(path=path), self.assertRaises(GenerationRefused):
                validate_generation(record)

    def test_transient_admission_cannot_claim_installation_readiness(self):
        for key, value in [("installation_readiness_established", True), ("service_scope_observed", False), ("service_scope_observed", 1)]:
            record = copy.deepcopy(self.first)
            record["scope"][key] = value
            with self.subTest(key=key), self.assertRaises(GenerationRefused):
                validate_generation(record)

    def test_boolean_zero_and_out_of_range_kernel_identities_refuse(self):
        for path, value in [(["protocol"], True), (["scope", "uid"], True), (["scope", "gid"], 0), (["scope", "parent", "device"], False),
                            (["scope", "groups", "edge", "inode"], 0), (["scope", "manager", "pid"], 2**31),
                            (["scope", "manager", "birth"], "030000"), (["scope", "limits", "swap_bytes"], True)]:
            record = copy.deepcopy(self.first)
            target = record
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(GenerationRefused):
                validate_generation(record)

    def test_privileged_group_capability_or_missing_no_new_privileges_refuses(self):
        for change in ["group", "capability", "boolean_capability", "no_new_privileges"]:
            record = copy.deepcopy(self.first)
            security = record["scope"]["manager"]["security"]
            if change == "group":
                security["supplementary_groups"] = [0, 1000]
            elif change == "capability":
                security["capabilities"]["CapAmb"] = 1
            elif change == "boolean_capability":
                security["capabilities"]["CapEff"] = False
            else:
                security["no_new_privileges"] = False
            with self.subTest(change=change), self.assertRaises(GenerationRefused):
                validate_generation(record)

    def test_alias_or_foreign_group_paths_cannot_rebind_existing_resources(self):
        for change in ["inode", "path", "device", "uid"]:
            record = copy.deepcopy(self.first)
            group = record["scope"]["groups"]["edge"]
            group[change] = {"inode": 301, "path": "/sys/fs/cgroup/foreign/edge", "device": 28, "uid": 65504}[change]
            with self.subTest(change=change), self.assertRaises(GenerationRefused):
                validate_generation(record)

    def test_malformed_uuid_digest_timestamp_and_namespace_refuse(self):
        for key, value in [("generation", "../other"), ("durable_binding_sha256", "B" * 64), ("created_at", "2026-10-10T05:00:00+00:00"), ("created_at", "2026-02-31T05:00:00.000000Z")]:
            record = copy.deepcopy(self.first)
            record[key] = value
            with self.subTest(key=key), self.assertRaises(GenerationRefused):
                validate_generation(record)
        for field, value in [("mount_namespace", "mnt:[../other]"),
                             ("mount_namespace", "mnt:[" + str(2**64) + "]"),
                             ("cgroup_namespace", "cgroup:[" + str(2**64) + "]")]:
            record = copy.deepcopy(self.first)
            record["scope"]["manager"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(GenerationRefused):
                validate_generation(record)

    def test_duplicate_fields_refuse_at_every_json_level(self):
        raw = canonical(self.first)
        for malformed in [raw.replace(b'"protocol":2', b'"protocol":2,"protocol":2', 1), raw.replace(b'"CapAmb":0', b'"CapAmb":0,"CapAmb":1', 1)]:
            with self.assertRaises(GenerationRefused):
                parse_generation(malformed)

    def test_oversized_invalid_nonfinite_and_deeply_nested_payloads_refuse(self):
        for raw in [b"x" * 16385, b"\xff", b"not-json", b"[" * 2000 + b"]" * 2000, canonical(self.first).replace(b'"cpu_quota_us":200000', b'"cpu_quota_us":NaN')]:
            with self.subTest(length=len(raw)), self.assertRaises(GenerationRefused):
                parse_generation(raw)

    def test_malformed_constructor_input_is_a_refusal(self):
        for scope in [None, [], {}, {**self.scope, "unexpected": "value"}]:
            with self.assertRaises(GenerationRefused):
                make_generation(scope, "b" * 64, generation="00000000-0000-4000-8000-000000000003", created_at="2026-10-10T05:00:00.000000Z")


if __name__ == "__main__":
    unittest.main()
