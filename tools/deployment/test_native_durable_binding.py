import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from native_durable_binding import BindingRefused, configuration, directory, executable, observe_durable_binding, private_file
from native_service_scope import ServiceRefused
from resource_generations import canonical
import test_resource_generations as record_fixture


class DurableBindingAdmissionTest(unittest.TestCase):
    def setUp(self):
        fixture = record_fixture.ResourceGenerationRecordTest()
        fixture.setUp()
        self.scope = fixture.scope
        self.root = "/var/lib/gitgood/installations/" + fixture.installation
        self.installation = fixture.installation
        self.options = {"cpu_quota_us": 200000, "memory_bytes": 268435456}
        self.executables = {name: "/trusted/" + name for name in ["python", "node", "git", "psql", "caddy"]}

    def test_two_equal_persistent_observations_and_service_brackets(self):
        binding = {"opaque_fixture_identity": "unit test only"}
        with patch("native_durable_binding.observe_service", return_value=self.scope) as service, patch("native_durable_binding.persistent_identity", return_value=binding) as persistent:
            result = observe_durable_binding(self.root, self.installation, "a" * 64, self.executables, **self.options)
        self.assertEqual(result["binding_sha256"], hashlib.sha256(canonical(binding)).hexdigest())
        self.assertFalse(result["installation_readiness_established"])
        self.assertFalse(result["generation_publication_established"])
        self.assertEqual(service.call_count, 2)
        self.assertEqual(persistent.call_count, 2)

    def test_replaced_persistent_resource_or_changed_manager_refuses(self):
        changed = copy.deepcopy(self.scope)
        changed["manager"]["birth"] = "40000"
        cases = [([self.scope, self.scope], [{"inode": 10}, {"inode": 11}]),
                 ([self.scope, changed], [{"inode": 10}, {"inode": 10}])]
        for scopes, bindings in cases:
            with patch("native_durable_binding.observe_service", side_effect=scopes), patch("native_durable_binding.persistent_identity", side_effect=bindings), self.assertRaises(BindingRefused):
                observe_durable_binding(self.root, self.installation, "a" * 64, self.executables, **self.options)

    def test_unsupported_service_never_reads_persistent_data_or_database(self):
        with patch("native_durable_binding.observe_service", side_effect=ServiceRefused()), patch("native_durable_binding.persistent_identity") as persistent, self.assertRaises(BindingRefused):
            observe_durable_binding(self.root, self.installation, "a" * 64, self.executables, **self.options)
        persistent.assert_not_called()

    def test_invalid_installation_refuses_before_host_observation(self):
        for installation in [None, [], "other", self.installation.upper()]:
            if installation == self.installation:
                continue
            with patch("native_durable_binding.observe_service") as service, self.assertRaises(BindingRefused):
                observe_durable_binding(self.root, installation, "a" * 64, self.executables, **self.options)
            service.assert_not_called()


@unittest.skipUnless(sys.platform == "linux", "Persistent file identities require Linux")
class ActualDurableFileCustodyTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.root.chmod(0o700)
        self.path = self.root / "private"
        self.path.write_bytes(b"synthetic private bytes")
        self.path.chmod(0o600)

    def test_actual_file_hash_and_directory_replacement_identity(self):
        record, raw = private_file(self.path, os.getuid())
        self.assertEqual(record["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertNotIn("synthetic private bytes", str(record))
        original = self.root / "storage"
        original.mkdir(mode=0o700)
        before = directory(original, os.getuid())
        original.rename(self.root / "retained-storage")
        original.mkdir(mode=0o700)
        self.assertNotEqual(directory(original, os.getuid()), before)
        self.assertEqual((self.root / "retained-storage").stat().st_ino, before["inode"])

    def test_actual_file_alias_hard_link_shared_mode_and_empty_payload_refuse(self):
        alias = self.root / "alias"
        alias.symlink_to(self.path)
        with self.assertRaises(BindingRefused):
            private_file(alias, os.getuid())
        alias.unlink()
        os.link(self.path, alias)
        with self.assertRaises(BindingRefused):
            private_file(self.path, os.getuid())
        alias.unlink()
        self.path.chmod(0o644)
        with self.assertRaises(BindingRefused):
            private_file(self.path, os.getuid())
        self.path.chmod(0o600)
        self.path.write_bytes(b"")
        with self.assertRaises(BindingRefused):
            private_file(self.path, os.getuid())

    def test_actual_bounds_wrong_owner_and_directory_alias_refuse(self):
        with self.assertRaises(BindingRefused):
            private_file(self.path, os.getuid(), maximum=2)
        with self.assertRaises(BindingRefused):
            private_file(self.path, os.getuid() + 1)
        alias = self.root / "alias"
        alias.symlink_to(self.root)
        with self.assertRaises(BindingRefused):
            directory(alias, os.getuid())
        self.root.chmod(0o750)
        with self.assertRaises(BindingRefused):
            directory(self.root, os.getuid())

    def test_actual_fifo_refuses_without_waiting_for_a_writer(self):
        fifo = self.root / "fifo"
        os.mkfifo(fifo, 0o600)
        with self.assertRaises(BindingRefused):
            private_file(fifo, os.getuid())

    def test_actual_root_binary_hash_and_ordinary_binary_refusal(self):
        observed = executable("/usr/bin/true")
        self.assertEqual(observed["sha256"], hashlib.sha256(Path(observed["path"]).read_bytes()).hexdigest())
        self.path.chmod(0o700)
        if os.getuid() != 0:
            with self.assertRaises(BindingRefused):
                executable(str(self.path))

    def test_actual_configuration_hash_contains_no_plaintext_secrets(self):
        installation = "00000000-0000-4000-8000-000000000001"
        config = self.root / "configuration"
        config.mkdir(mode=0o700)
        value = {"protocol": 1, "installation": installation,
                 "forge": {"GITGOOD_INSTALLATION_ID": installation, "GITGOOD_STORAGE": str(self.root / "storage"),
                           "GITGOOD_SSH_HOST_KEY_DIRECTORY": str(self.root / "ssh-host"), "GITGOOD_PROXY_KEY": "private-fixture-secret",
                           "DATABASE_URL": "postgresql://ordinary:private-fixture@127.0.0.1:55432/owned_fixture"},
                 "web": {"PORT": "4500", "GITGOOD_API_URL": "http://127.0.0.1:4400", "NODE_ENV": "production", "GITGOOD_PROXY_KEY": "private-fixture-secret"},
                 "edge": {"tls_certificate": "tls-certificate.pem", "tls_key": "tls-key.pem"}}
        path = config / "installation.json"
        for name in ["tls-certificate.pem", "tls-key.pem"]:
            item = config / name
            item.write_bytes(b"private synthetic fixture")
            item.chmod(0o600)
        path.write_text(json.dumps(value))
        path.chmod(0o600)
        records, database_url = configuration(self.root, installation, os.getuid())
        self.assertEqual(database_url, value["forge"]["DATABASE_URL"])
        self.assertNotIn("private-fixture", str(records))
        self.assertEqual(records["installation.json"]["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        for mutate in [lambda v: v["forge"].update({"COMMAND": "shell"}),
                       lambda v: v["web"].update({"GITGOOD_PROXY_KEY": "other"}),
                       lambda v: v["edge"].update({"tls_key": "../foreign"}),
                       lambda v: v.update({"protocol": True}),
                       lambda v: v["forge"].update({"GITGOOD_STORAGE": "/other"})]:
            changed = copy.deepcopy(value)
            mutate(changed)
            path.write_text(json.dumps(changed))
            with self.assertRaises(BindingRefused):
                configuration(self.root, installation, os.getuid())


if __name__ == "__main__":
    unittest.main()
