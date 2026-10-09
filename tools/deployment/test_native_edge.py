import asyncio
import base64
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from native_edge import caddy_source, guardian, route_ssh, routing_profile, start_edge, verification_caddy_source
from upgrade_journal import UpgradeRefused


def configuration():
    return {"forge": {"GITGOOD_PUBLIC_URL": "https://localhost:54420", "GITGOOD_WEB_ORIGIN": "https://localhost:54420",
                      "GITGOOD_SSH_PUBLIC_HOST": "localhost", "GITGOOD_SSH_PUBLIC_PORT": "54422",
                      "GITGOOD_SSH_PORT": "50022", "PORT": "50021", "GITGOOD_PROXY_KEY": base64.b64encode(b"x" * 32).decode()},
            "web": {"PORT": "50020", "GITGOOD_API_URL": "http://127.0.0.1:50021"},
            "edge": {"tls_certificate": "tls-certificate.pem", "tls_key": "tls-key.pem"}}


class EdgeProfileTest(unittest.TestCase):
    def test_origin_command_injection_and_colliding_ports_refuse(self):
        self.assertEqual(routing_profile(configuration())["ports"]["ssh"], 54422)
        cases = [("GITGOOD_PUBLIC_URL", "https://localhost:54420/\nrespond secret"),
                 ("GITGOOD_PUBLIC_URL", "https://localhost:\n54420"),
                 ("GITGOOD_PUBLIC_URL", "https://actor:secret@localhost:54420"),
                 ("GITGOOD_SSH_PUBLIC_HOST", "different.invalid"),
                 ("GITGOOD_SSH_PUBLIC_PORT", "50022"), ("PORT", "50020"), ("PORT", "-1")]
        for field, value in cases:
            config = configuration()
            config["forge"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(UpgradeRefused):
                routing_profile(config)
        config = configuration()
        config["web"]["GITGOOD_API_URL"] = "http://external.invalid:50021"
        with self.assertRaises(UpgradeRefused):
            routing_profile(config)

    def test_maintenance_and_active_routing_are_fixed_and_do_not_expand_secrets(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            private = root / "configuration"
            private.mkdir(mode=0o700)
            for name in ["tls-certificate.pem", "tls-key.pem"]:
                path = private / name
                path.write_text("inert private fixture")
                path.chmod(0o600)
            config = configuration()
            with patch("native_edge.private_bytes", side_effect=lambda path: path.read_bytes()):
                maintenance = caddy_source(root, config, "maintenance")
                active = caddy_source(root, config, "active")
            self.assertIn('respond "Gitgood maintenance" 503', maintenance)
            self.assertNotIn("reverse_proxy", maintenance)
            self.assertIn("reverse_proxy 127.0.0.1:50021", active)
            self.assertIn("reverse_proxy 127.0.0.1:50020", active)
            for source in [maintenance, active]:
                self.assertNotIn(config["forge"]["GITGOOD_PROXY_KEY"], source)
                self.assertIn("persist_config off", source)
                self.assertIn("admin off", source)
                self.assertIn("request>headers delete", source)
                self.assertIn("resp_headers delete", source)
            self.assertIn("{$GITGOOD_PROXY_KEY}", active)

    def test_unowned_stage_refuses_before_observation_or_launch(self):
        class Actions:
            def _owned(self, stages):
                raise UpgradeRefused("inert unowned fixture")
        with patch("native_edge.subprocess.Popen") as launch, patch("native_edge.cgroup_identity") as group, self.assertRaises(UpgradeRefused):
            start_edge(Actions(), "active")
        launch.assert_not_called()
        group.assert_not_called()

    def test_verification_profile_requires_and_explicitly_binds_loopback(self):
        config = configuration()
        with self.assertRaises(UpgradeRefused):
            verification_caddy_source(Path("/unobserved"), config)
        config["forge"].update(GITGOOD_PUBLIC_URL="https://127.0.0.1:54420", GITGOOD_WEB_ORIGIN="https://127.0.0.1:54420",
                               GITGOOD_SSH_PUBLIC_HOST="127.0.0.1")
        with patch("native_edge.private_bytes", return_value=b"inert private boundary"):
            source = verification_caddy_source(Path("/unobserved"), config)
        self.assertIn("https://127.0.0.1:54420 {\n  bind 127.0.0.1\n", source)
        self.assertIn("reverse_proxy 127.0.0.1:50021", source)


class RealSSHSocketTest(unittest.IsolatedAsyncioTestCase):
    async def begin_router(self, mode, upstream_port, *, loopback=False):
        # Reserve an actual loopback socket, then let the router bind its own socket.
        server = await asyncio.start_server(lambda reader, writer: writer.close(), "127.0.0.1", 0)
        public_port = server.sockets[0].getsockname()[1]
        server.close()
        await server.wait_closed()
        stopped = asyncio.Event()
        task = asyncio.create_task(route_ssh(mode, upstream_port, public_port, stopped, loopback=loopback))
        for _ in range(100):
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", public_port)
                return task, stopped, public_port, reader, writer
            except OSError:
                await asyncio.sleep(.01)
        self.fail("Owned test router did not listen")

    async def test_verification_router_uses_actual_loopback_socket_and_binary_upstream(self):
        async def echo(reader, writer):
            try:
                data = await reader.readexactly(256)
                writer.write(data)
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
        server = await asyncio.start_server(echo, "127.0.0.1", 0)
        original = asyncio.start_server
        bound = []
        async def capture(*args, **kwargs):
            actual = await original(*args, **kwargs)
            bound.extend(item.getsockname() for item in actual.sockets)
            return actual
        try:
            with patch("native_edge.asyncio.start_server", side_effect=capture):
                task, stopped, public, reader, writer = await self.begin_router("active", server.sockets[0].getsockname()[1], loopback=True)
            try:
                self.assertEqual([address[0] for address in bound if address[1] == public], ["127.0.0.1", "127.0.0.1"])
                payload = bytes(range(256))
                writer.write(payload)
                await writer.drain()
                self.assertEqual(await asyncio.wait_for(reader.readexactly(256), 2), payload)
            finally:
                writer.close()
                await writer.wait_closed()
                stopped.set()
                await asyncio.wait_for(task, 2)
        finally:
            server.close()
            await server.wait_closed()

    async def test_maintenance_closes_actual_socket_without_opening_upstream(self):
        upstream_calls = []
        async def upstream(reader, writer):
            upstream_calls.append(True)
            writer.close()
        server = await asyncio.start_server(upstream, "127.0.0.1", 0)
        task, stopped, _, reader, writer = await self.begin_router("maintenance", server.sockets[0].getsockname()[1])
        try:
            self.assertEqual(await asyncio.wait_for(reader.read(), 2), b"")
            self.assertEqual(upstream_calls, [])
        finally:
            writer.close()
            await writer.wait_closed()
            stopped.set()
            await asyncio.wait_for(task, 2)
            server.close()
            await server.wait_closed()

    async def test_active_forwards_binary_bytes_and_shutdown_closes_live_connections(self):
        upstream_finished = asyncio.Event()
        async def upstream(reader, writer):
            try:
                while data := await reader.read(65_536):
                    writer.write(data)
                    await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
                upstream_finished.set()
        server = await asyncio.start_server(upstream, "127.0.0.1", 0)
        task, stopped, _, reader, writer = await self.begin_router("active", server.sockets[0].getsockname()[1])
        try:
            payload = b"SSH-2.0-controlled-fixture\r\n" + bytes(range(256)) * 1024
            writer.write(payload)
            await writer.drain()
            self.assertEqual(await asyncio.wait_for(reader.readexactly(len(payload)), 2), payload)
            stopped.set()
            await asyncio.wait_for(task, 2)
            self.assertEqual(await asyncio.wait_for(reader.read(), 2), b"")
            await asyncio.wait_for(upstream_finished.wait(), 2)
        finally:
            stopped.set()
            await task
            writer.close()
            await writer.wait_closed()
            server.close()
            await server.wait_closed()


@unittest.skipIf(sys.platform == "linux", "Foreign-platform early refusal")
class UnsupportedEdgeTest(unittest.TestCase):
    def test_guardian_refuses_before_observing_resources(self):
        with self.assertRaises(UpgradeRefused):
            guardian("unowned-path")
