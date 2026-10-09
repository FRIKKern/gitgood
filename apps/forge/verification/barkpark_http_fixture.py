"""Private loopback wire fixture; never contacts a configured Barkpark source."""
import http.server
import hashlib
import copy
import uuid
import urllib.parse
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
hold_documents = False
document_status = 200
journal_lock = threading.Lock()
journal_documents = {}
journal_snapshots = {}
stale_reads = False
outage_after_write = False
journal_receipts = {}
journal_posts = []
hold_mutations = False
lost_reply = False
prewrite_lost = False


def announce(value):
    with output_lock:
        print(value, flush=True)


def journal_document(identity, kind="paper"):
    with journal_lock:
        if identity not in journal_documents:
            journal_documents[identity] = {"_id": identity, "_type": kind,
                "_rev": "fixture-revision", "title": "Private source specification",
                "purpose": "Source owns this intention.", "description": "Source owns this specification.",
                "blocks": [{"id": "source-intent", "type": "paragraph",
                    "content": [{"type": "text", "value": "Unselected source content"}]}]}
            if kind == "task":
                journal_documents[identity]["acceptance_criteria"] = [
                    {"criterion": "Fixture-A: Restore the private repository.", "met": True, "evidence": "Upstream claim must not become a native pass"},
                    {"criterion": "Fixture-B: Deny unauthorized artifact reads.", "met": False, "evidence": ""}]
        journal_snapshots.setdefault(identity, copy.deepcopy(journal_documents[identity]))
        return copy.deepcopy(journal_snapshots[identity] if stale_reads else journal_documents[identity])


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
            permissions = ["read", "admin"] if token == "synthetic-broad-credential" else (["read"] if token == "synthetic-read-credential" else ["read", "write"])
            token_id = "82990b0a-ddf1-4747-aec9-10bb1df9608b" if token == "synthetic-second-credential" else ("d6c87ac9-f908-4b7b-9d14-f1c0e359fb47" if token != "synthetic-outsider-credential" else "f6e2925b-348e-4a84-83ae-387a5fd71d4b")
            expiry = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z")
            self.send(200, json.dumps({"token": {"id":token_id, "kind":"api", "label":"Fixture service",
              "permissions":permissions, "expires_at":expiry, "workspace":workspace, "workspace_id":workspace_id},
              "memberships":[{"workspace_id":workspace_id,"workspace_slug":workspace,"role":"member"}]}).encode())
        elif self.path.startswith("/v1/capabilities?"):
            self.send(200, json.dumps({"auth_tier":("read" if token == "synthetic-read-credential" else "write"),"token":{"public_read":False},
              "build":{"version":"fixture-1","commit":"fixture-source-commit","built_at":"2026-10-08T00:00:00Z"}}).encode())
        elif self.path == "/api/workspaces/fixture-workspace/projects":
            self.send(200, json.dumps({"workspace":{"id":workspace_id},
              "projects":[{"id":project_id,"slug":"default"}]}).encode())
        elif self.path == "/api/workspaces/fixture-workspace/projects/default/datasets":
            self.send(200, json.dumps({"workspace":{"id":workspace_id}, "project":{"id":project_id,"slug":"default"},
              "datasets":[{"id":"7f26cba1-258d-4434-9e0f-fc0496a4a098","slug":"production"}]}).encode())
        elif self.path.startswith("/w/fixture-workspace/p/default/v1/data/doc/production/"):
            document_id = self.path.split("?", 1)[0].rsplit("/", 1)[-1]
            document_type = self.path.split("?", 1)[0].split("/")[-2]
            if hold_documents:
                announce("BLOCKED_DOCUMENT")
                released.wait()
            if document_status != 200:
                self.send(document_status, b'{"error":{"code":"refused","private_title":"Must not leak"}}')
            elif token == "synthetic-outsider-credential" or document_id == "denied-document":
                self.send(403, b'{"error":{"code":"forbidden","private_title":"Must not leak"}}')
            elif document_id == "missing-document":
                self.send(404, b'{"error":{"code":"not_found","private_title":"Must not leak"}}')
            elif document_id == "unavailable-document":
                self.send(503, b'{"error":{"code":"unavailable","private_title":"Must not leak"}}')
            elif document_id == "wrong-identity":
                self.send(200, b'{"result":{"_id":"different-document","_type":"paper","_rev":"fixture-revision"}}')
            else:
                self.send(200, json.dumps({"result": journal_document(document_id, document_type)}).encode())
        elif self.path == "/journal/stats":
            with journal_lock:
                self.send(200, json.dumps({"posts": journal_posts, "receipts": list(journal_receipts.values()),
                    "documents": journal_documents}).encode())
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
        global document_status, hold_mutations, lost_reply, prewrite_lost, stale_reads, outage_after_write
        if self.path == "/control/evidence-change":
            value = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.headers.get("Authorization") != "Bearer synthetic-fixture-control" or set(value) != {"revision", "criterion"} or any(not isinstance(item, bool) for item in value.values()):
                self.send(403, b"{}")
            else:
                with journal_lock:
                    for doc in journal_documents.values():
                        if doc.get("acceptance_criteria"):
                            if value["revision"]:
                                doc["_rev"] = uuid.uuid4().hex
                            if value["criterion"]:
                                doc["acceptance_criteria"][0]["criterion"] = "Fixture-A: A changed requirement."
                self.send(200, b'{"fixture":true}')
            return
        if self.path == "/control/journal-state":
            value = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            allowed = {"lost_reply", "prewrite_lost", "stale_reads", "outage_after_write"}
            if self.headers.get("Authorization") != "Bearer synthetic-fixture-control" or set(value) - allowed or any(not isinstance(v, bool) for v in value.values()):
                self.send(403, b"{}")
            else:
                lost_reply = value.get("lost_reply", lost_reply)
                prewrite_lost = value.get("prewrite_lost", prewrite_lost)
                stale_reads = value.get("stale_reads", stale_reads)
                outage_after_write = value.get("outage_after_write", outage_after_write)
                self.send(200, b'{"fixture":true}')
            return
        if self.path == "/control/document-state":
            value = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.headers.get("Authorization") != "Bearer synthetic-fixture-control" or value.get("status") not in [200, 403, 404, 503]:
                self.send(403, b"{}")
            else:
                document_status = value["status"]
                self.send(200, b'{"fixture":true}')
            return
        if self.path == "/w/fixture-workspace/p/default/v1/data/mutate/production":
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            token = self.headers.get("Authorization", "").removeprefix("Bearer ")
            key = self.headers.get("Idempotency-Key")
            digest = hashlib.sha256(raw).hexdigest()
            if hold_mutations:
                announce("BLOCKED_MUTATION")
                released.wait()
            with journal_lock:
                journal_posts.append({"key": key, "sha256": digest})
                if prewrite_lost:
                    self.close_connection = True
                    return
                if token in ["synthetic-outsider-credential", "synthetic-read-credential"]:
                    self.send(403, b'{"error":{"code":"forbidden","private_content":"Must not leak"}}')
                    return
                existing = journal_receipts.get(key)
                if existing:
                    if existing["sha256"] != digest:
                        self.send(409, b'{"error":{"code":"idempotency_conflict"}}')
                    else:
                        self.send(200, json.dumps({"transactionId": existing["transactionId"]}).encode())
                    return
                try:
                    payload = json.loads(raw)
                    patch = payload["mutations"][0]["patch"]
                    identity = patch["id"]
                    current = journal_documents[identity]
                    if patch["ifRevisionID"] != current["_rev"]:
                        self.send(409, b'{"error":{"code":"revision_conflict"}}')
                        return
                    if patch["type"] != "paper" or list(patch["set"]) != ["blocks"]:
                        self.send(422, b'{"error":{"code":"unsupported"}}')
                        return
                    current["blocks"] = patch["set"]["blocks"]
                    current["_rev"] = uuid.uuid4().hex
                    tx = str(uuid.uuid4())
                    journal_receipts[key] = {"transactionId": tx, "sha256": digest}
                    if lost_reply:
                        if outage_after_write:
                            document_status = 503
                        self.close_connection = True
                        return
                    self.send(200, json.dumps({"transactionId": tx}).encode())
                except (KeyError, ValueError, TypeError):
                    self.send(422, b'{"error":{"code":"invalid"}}')
            return
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        actual = self.headers.get("Authorization") == "Bearer synthetic-fixture-credential"
        self.send(200, json.dumps({"authorized": actual, "payload": payload,
                                  "key": self.headers.get("Idempotency-Key")}).encode())


def main():
    global hold_documents, document_status, hold_mutations, lost_reply, prewrite_lost, stale_reads
    with tempfile.TemporaryDirectory(prefix="gitgood-barkpark-wire-") as directory:
        cert, key = Path(directory)/"certificate.pem", Path(directory)/"key.pem"
        subprocess.run([sys.argv[1], "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-keyout", str(key), "-out", str(cert), "-days", "1",
                        "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"],
                       check=True, capture_output=True, timeout=15)
        if len(sys.argv) > 2:
            Path(sys.argv[2]).write_bytes(cert.read_bytes())
        http_server = FixtureServer(("127.0.0.1", 0), Handler)
        https_server = FixtureServer(("127.0.0.1", 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        https_server.socket = context.wrap_socket(https_server.socket, server_side=True)
        servers = [http_server, https_server]
        wrong_host = None
        if len(sys.argv) > 2:
            wrong_key, wrong_csr, wrong_cert = Path(directory)/"wrong.key", Path(directory)/"wrong.csr", Path(directory)/"wrong.pem"
            extension = Path(directory)/"wrong.ext"
            extension.write_text("basicConstraints=CA:FALSE\nsubjectAltName=DNS:wrong-host.example.invalid\n", encoding="utf-8")
            subprocess.run([sys.argv[1], "req", "-new", "-newkey", "rsa:2048", "-nodes",
                "-keyout", str(wrong_key), "-out", str(wrong_csr), "-subj", "/CN=wrong-host.example.invalid"],
                check=True, capture_output=True, timeout=15)
            subprocess.run([sys.argv[1], "x509", "-req", "-in", str(wrong_csr), "-CA", str(cert),
                "-CAkey", str(key), "-CAcreateserial", "-out", str(wrong_cert), "-days", "1",
                "-extfile", str(extension)], check=True, capture_output=True, timeout=15)
            subprocess.run([sys.argv[1], "verify", "-CAfile", str(cert), str(wrong_cert)],
                check=True, capture_output=True, timeout=15)
            wrong_host = FixtureServer(("127.0.0.1", 0), Handler)
            wrong_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            wrong_context.load_cert_chain(wrong_cert, wrong_key)
            wrong_host.socket = wrong_context.wrap_socket(wrong_host.socket, server_side=True)
            servers.append(wrong_host)
        for server in servers:
            threading.Thread(target=server.serve_forever, daemon=True).start()
        announce(f"READY {http_server.server_port} {https_server.server_port}" +
            (f" {wrong_host.server_port}" if wrong_host else ""))
        try:
            for line in sys.stdin:
                if line.strip().startswith("doc-state "):
                    document_status = int(line.strip().split()[1])
                    announce("DOC_STATE " + str(document_status))
                if line.strip() == "hold-docs":
                    hold_documents = True
                    announce("HOLDING_DOCS")
                command = line.strip()
                if command == "hold-mutations":
                    released.clear()
                    hold_mutations = True
                    announce("HOLDING_MUTATIONS")
                elif command.startswith("journal-lost "):
                    lost_reply = command.split()[1] == "1"
                    announce("JOURNAL_LOST")
                elif command.startswith("journal-prewrite-lost "):
                    prewrite_lost = command.split()[1] == "1"
                    announce("JOURNAL_PREWRITE_LOST")
                elif command.startswith("journal-stale "):
                    stale_reads = command.split()[1] == "1"
                    announce("JOURNAL_STALE")
                elif command == "journal-owner-edit":
                    with journal_lock:
                        for doc in journal_documents.values():
                            doc["blocks"].append({"id":"owner-edit","type":"paragraph","content":[{"type":"text","value":"Owner changed this."}]})
                            doc["_rev"] = uuid.uuid4().hex
                    announce("JOURNAL_OWNER_EDIT")
                elif command == "evidence-criterion-change":
                    with journal_lock:
                        for doc in journal_documents.values():
                            if doc.get("acceptance_criteria"):
                                doc["acceptance_criteria"][0]["criterion"] = "Fixture-A: A changed requirement."
                    announce("EVIDENCE_CRITERION_CHANGE")
                if command == "release":
                    hold_mutations = False

                    hold_documents = False
                    released.set()
                if line.strip() == "quit":
                    break
        finally:
            released.set()
            for server in servers:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    main()
