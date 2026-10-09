import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest
from unittest.mock import Mock, patch
import urllib.request
import uuid

from native_probes import NativeProbes, NoRedirect
import test_native_edge as edge_fixtures
from upgrade_journal import UpgradeRefused


@unittest.skipUnless(sys.platform == "linux", "Native probe custody requires Linux")
class ProbeCustodyTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.root.chmod(0o700)
        self.configuration = edge_fixtures.configuration()
        self.private = self.root / "probes"
        self.private.mkdir(mode=0o700)
        self.key = self.private / "ssh-private-key"
        self.key.write_text("inert key fixture, never executed")
        self.key.chmod(0o600)
        self.installation = str(uuid.uuid4())
        self.ssh = {"path": "/usr/bin/ssh", "sha256": "a" * 64}
        self.actions = Mock(root=self.root, bindings={"installation": self.installation}, configuration=self.configuration)
        self.value = {"protocol": 1, "installation": self.installation, "username": "owner", "team": "team", "repository": "private-repo",
                      "branch": "main", "commit_sha": "b" * 40, "session_token": "synthetic_session_token_12345", "git_token": "synthetic_git_token_12345",
                      "ssh_executable": "/usr/bin/ssh", "ssh_sha256": self.ssh["sha256"], "ssh_private_key_sha256": hashlib.sha256(self.key.read_bytes()).hexdigest()}

    def capture(self):
        path = self.private / "credentials.json"
        path.write_text(json.dumps(self.value))
        path.chmod(0o600)
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def create(self, digest=None):
        with patch("native_probes.executable_identity", return_value=self.ssh), patch("native_probes.ssl.create_default_context"):
            return NativeProbes(self.actions, self.private, digest if digest is not None else self.capture())

    def test_independent_manifest_and_binary_key_identities_refuse_substitution(self):
        self.capture()
        with self.assertRaises(UpgradeRefused):
            self.create("c" * 64)
        for field, value in [("installation", str(uuid.uuid4())), ("ssh_sha256", "d" * 64), ("ssh_private_key_sha256", "e" * 64)]:
            original = self.value[field]
            self.value[field] = value
            with self.subTest(field=field), self.assertRaises(UpgradeRefused):
                self.create()
            self.value[field] = original
        self.assertEqual(self.create().credentials["username"], "owner")

    def test_verification_readiness_cannot_be_used_for_private_or_public_activation(self):
        probe = self.create()
        response = {"status": "ready", "candidate": "b" * 40, "dirty": False,
                    "operational_mode": "recovery_verification", "service": "gitgood"}
        with patch.object(probe, "_owned"), patch.object(probe, "_request", return_value=(200, json.dumps(response).encode())) as request:
            for public in [False, True]:
                with self.assertRaises(UpgradeRefused):
                    probe.readiness("b" * 40, public=public)
            self.assertEqual(request.call_count, 2)

    def test_header_path_and_descriptor_command_injection_refuse(self):
        for field, value in [("session_token", "token\r\nInjected: value"), ("git_token", "space token"),
                             ("repository", "../other"), ("username", "actor@elsewhere"), ("branch", "main*"), ("branch", "main/../secret")]:
            original = self.value[field]
            self.value[field] = value
            with self.subTest(field=field), self.assertRaises(UpgradeRefused):
                self.create()
            self.value[field] = original
        self.value["command"] = "arbitrary descriptor command"
        with self.assertRaises(UpgradeRefused):
            self.create()

    def test_credentials_alias_and_shared_mode_refuse(self):
        digest = self.capture()
        path = self.private / "credentials.json"
        path.chmod(0o644)
        with self.assertRaises(UpgradeRefused):
            self.create(digest)
        path.chmod(0o600)
        data = path.read_bytes()
        path.unlink()
        target = self.root / "aliased"
        target.write_bytes(data)
        target.chmod(0o600)
        path.symlink_to(target)
        with self.assertRaises(UpgradeRefused):
            self.create(digest)

    def test_wrong_candidate_or_failed_readiness_cannot_pass(self):
        probe = self.create()
        with patch.object(probe, "_owned"), patch.object(probe, "_request", return_value=(200, json.dumps({"candidate": "c" * 40, "dirty": False, "status": "ready", "service": "gitgood-web", "forge_candidate": "c" * 40}).encode())), patch("native_probes.time.monotonic", side_effect=[0, 100]), self.assertRaises(UpgradeRefused):
            probe.readiness("b" * 40, public=True)


class ActualRedirectTest(unittest.TestCase):
    def test_authenticated_request_never_follows_actual_redirect(self):
        received = []
        class Target(BaseHTTPRequestHandler):
            def do_GET(self):
                received.append(self.headers.get("Authorization"))
                self.send_response(200)
                self.end_headers()
            def log_message(self, *_):
                pass
        target = ThreadingHTTPServer(("127.0.0.1", 0), Target)
        class Redirect(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", "http://127.0.0.1:" + str(target.server_port) + "/private")
                self.end_headers()
            def log_message(self, *_):
                pass
        source = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
        threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in [target, source]]
        for thread in threads:
            thread.start()
        try:
            probe = NativeProbes.__new__(NativeProbes)
            probe.credentials = {"session_token": "inert_fixture_session_token"}
            probe.opener = urllib.request.build_opener(NoRedirect(), urllib.request.ProxyHandler({}))
            with self.assertRaises(UpgradeRefused):
                probe._request("http://127.0.0.1:" + str(source.server_port), "/private")
            self.assertEqual(received, [])
        finally:
            for server in [source, target]:
                server.shutdown()
                server.server_close()
            for thread in threads:
                thread.join(timeout=3)


@unittest.skipIf(sys.platform == "linux", "Foreign-platform early refusal")
class UnsupportedProbesTest(unittest.TestCase):
    def test_probes_refuse_before_resource_access(self):
        with self.assertRaises(UpgradeRefused):
            NativeProbes(None, "unowned", "a" * 64)
