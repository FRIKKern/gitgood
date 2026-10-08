"""Private loopback wire fixture; never contacts a configured Barkpark source."""
import http.server
from datetime import datetime, timedelta, timezone
import json
import ssl
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

released = threading.Event()
output_lock = threading.Lock()
redirect_reads = 0


def announce(value):
    with output_lock:
        print(value, flush=True)


class FixtureServer(http.server.ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def send(self, status, body, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        global redirect_reads
        token = self.headers.get("Authorization", "").removeprefix("Bearer ")
        workspace = "fixture-workspace"
        workspace_id = "dd274974-028d-4849-a457-b92b8c02bb99"
        project_id = "506f8590-ddb5-4eac-945d-9e3f07b625bb"
        if self.path == "/v1/tokens/current":
            if token == "synthetic-held-credential":
                announce("BLOCKED")
                released.wait()
            if token == "synthetic-unavailable-credential":
                self.send(503, b'{"error":{"code":"unavailable"}}')
                return
            permissions = ["read", "admin"] if token == "synthetic-broad-credential" else ["read", "write"]
            expiry = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z")
            self.send(200, json.dumps({"token": {"id":"d6c87ac9-f908-4b7b-9d14-f1c0e359fb47", "kind":"api", "label":"Fixture service",
              "permissions":permissions, "expires_at":expiry, "workspace":workspace, "workspace_id":workspace_id},
              "memberships":[{"workspace_id":workspace_id,"workspace_slug":workspace,"role":"member"}]}).encode())
        elif self.path.startswith("/v1/capabilities?"):
            self.send(200, json.dumps({"auth_tier":"write","token":{"public_read":False},
              "build":{"version":"fixture-1","commit":"fixture-source-commit","built_at":"2026-10-08T00:00:00Z"}}).encode())
        elif self.path == "/api/workspaces/fixture-workspace/projects":
            self.send(200, json.dumps({"workspace":{"id":workspace_id},
              "projects":[{"id":project_id,"slug":"default"}]}).encode())
        elif self.path == "/api/workspaces/fixture-workspace/projects/default/datasets":
            self.send(200, json.dumps({"workspace":{"id":workspace_id}, "project":{"id":project_id,"slug":"default"},
              "datasets":[{"id":"7f26cba1-258d-4434-9e0f-fc0496a4a098","slug":"production"}]}).encode())
        elif self.path == "/blocked":
            announce("BLOCKED")
            released.wait()
            self.send(200, b'{"ok":true}')
        elif self.path == "/redirect":
            self.send(302, b"{}", {"Location": "/redirect-target"})
        elif self.path == "/redirect-target":
            redirect_reads += 1
            self.send(200, b'{"must_not_be_read":true}')
        elif self.path == "/redirect-count":
            self.send(200, json.dumps({"count": redirect_reads}).encode())
        elif self.path == "/oversize":
            self.send_response(200)
            self.send_header("Content-Length", "1048577")
            self.end_headers()
            self.close_connection = True
        elif self.path == "/unbounded":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.close_connection = True
            try:
                self.wfile.write(b"x" * 1_048_577)
            except (BrokenPipeError, ConnectionResetError):
                pass
        elif self.path == "/exact-limit":
            self.send(200, b'{"value":"' + b"x" * (1_048_576 - 12) + b'"}')
        elif self.path == "/malformed":
            self.send(200, b"invalid JSON with private response text")
        elif self.path == "/compressed":
            self.send(200, b"{}", {"Content-Encoding": "gzip"})
        elif self.path == "/denied":
            self.send(403, b'{"error":{"code":"forbidden"}}')
        elif self.path == "/missing":
            self.send(404, b'{"error":{"code":"not_found"}}')
        elif self.path == "/unavailable":
            self.send(503, b'{"error":{"code":"storage_unavailable"}}')
        else:
            actual = self.headers.get("Authorization") == "Bearer synthetic-fixture-credential"
            self.send(200, json.dumps({"authorized": actual}).encode())

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        actual = self.headers.get("Authorization") == "Bearer synthetic-fixture-credential"
        self.send(200, json.dumps({"authorized": actual, "payload": payload,
                                  "key": self.headers.get("Idempotency-Key")}).encode())


def main():
    with tempfile.TemporaryDirectory(prefix="gitgood-barkpark-wire-") as directory:
        cert, key = Path(directory)/"certificate.pem", Path(directory)/"key.pem"
        subprocess.run([sys.argv[1], "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-keyout", str(key), "-out", str(cert), "-days", "1",
                        "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"],
                       check=True, capture_output=True, timeout=15)
        http_server = FixtureServer(("127.0.0.1", 0), Handler)
        https_server = FixtureServer(("127.0.0.1", 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        https_server.socket = context.wrap_socket(https_server.socket, server_side=True)
        for server in (http_server, https_server):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        announce(f"READY {http_server.server_port} {https_server.server_port}")
        try:
            for line in sys.stdin:
                if line.strip() == "release":
                    released.set()
                if line.strip() == "quit":
                    break
        finally:
            released.set()
            for server in (http_server, https_server):
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    main()
