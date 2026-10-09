"""Fixed authenticated version/branch/HTTPS/SSH probes for native upgrades."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request

from native_edge import routing_profile
from native_inventory import database_environment, directory_identity, executable_identity, private_bytes
from upgrade_journal import canonical, require, unique_object

SCHEMA_SQL = "SELECT coalesce(json_agg(version::text ORDER BY version), '[]'::json) FROM public.schema_migrations"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        require(False)


class NativeProbes:
    def __init__(self, actions, directory, expected_sha256):
        require(sys.platform == "linux")
        self.actions = actions
        self.directory = Path(directory)
        directory_identity(self.directory, private=True)
        raw = private_bytes(self.directory / "credentials.json", 8192)
        require(isinstance(expected_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", expected_sha256))
        require(hashlib.sha256(raw).hexdigest() == expected_sha256)
        value = json.loads(raw, object_pairs_hook=unique_object)
        require(isinstance(value, dict) and set(value) == {"protocol", "installation", "username", "team", "repository", "branch", "commit_sha",
                "session_token", "git_token", "ssh_executable", "ssh_sha256", "ssh_private_key_sha256"})
        require(type(value["protocol"]) is int and value["protocol"] == 1 and value["installation"] == actions.bindings["installation"])
        for field in ["username", "team", "repository"]:
            require(isinstance(value[field], str) and re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value[field]))
        require(isinstance(value["branch"], str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}", value["branch"]))
        require(".." not in value["branch"] and "//" not in value["branch"] and not value["branch"].endswith(("/", ".")))
        require(isinstance(value["commit_sha"], str) and re.fullmatch(r"[0-9a-f]{40}", value["commit_sha"]))
        for field in ["session_token", "git_token"]:
            require(isinstance(value[field], str) and re.fullmatch(r"[A-Za-z0-9_-]{20,512}", value[field]))
        for field in ["ssh_sha256", "ssh_private_key_sha256"]:
            require(isinstance(value[field], str) and re.fullmatch(r"[0-9a-f]{64}", value[field]))
        ssh = executable_identity(value["ssh_executable"])
        require(ssh["sha256"] == value["ssh_sha256"])
        require(hashlib.sha256(private_bytes(self.directory / "ssh-private-key", 65_536)).hexdigest() == value["ssh_private_key_sha256"])
        self.ssh = ssh
        self.credentials = value
        self.credentials_sha256 = expected_sha256
        self.profile = routing_profile(actions.configuration)
        context = ssl.create_default_context()
        context.load_verify_locations(cafile=str(actions.root / "configuration" / actions.configuration["edge"]["tls_certificate"]))
        self.opener = urllib.request.build_opener(NoRedirect(), urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))

    def _owned(self, stages=None):
        self.actions._owned(stages if stages is not None else {"inspect", "verify", "public_verify", "recover"})
        self.actions.reobserve()
        require(hashlib.sha256(private_bytes(self.directory / "credentials.json", 8192)).hexdigest() == self.credentials_sha256)
        require(executable_identity(self.ssh["path"]) == self.ssh)
        require(hashlib.sha256(private_bytes(self.directory / "ssh-private-key", 65_536)).hexdigest() == self.credentials["ssh_private_key_sha256"])

    def _request(self, origin, path, authenticated=True):
        headers = {"Authorization": "Bearer " + self.credentials["session_token"]} if authenticated else {}
        request = urllib.request.Request(origin + path, headers=headers, method="GET")
        try:
            with self.opener.open(request, timeout=5) as response:
                raw = response.read(1_048_577)
                require(len(raw) <= 1_048_576)
                return response.status, raw
        except urllib.error.HTTPError as error:
            # Error bodies can contain private context; never put them in receipts.
            error.close()
            return error.code, b""

    def schema(self):
        self._owned({"inspect", "maintenance", "migrate", "verify", "public_verify", "recover"})
        environment = database_environment(self.actions.configuration["forge"]["DATABASE_URL"])
        result = subprocess.run([self.actions.executables["psql"], "--no-psqlrc", "--tuples-only", "--no-align", "--set=ON_ERROR_STOP=1", "--command", SCHEMA_SQL],
                                env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)
        require(result.returncode == 0 and 0 < len(result.stdout) <= 8192)
        value = json.loads(result.stdout)
        require(isinstance(value, list) and 1 <= len(value) <= 256 and value == sorted(set(value)))
        require(all(isinstance(version, str) and re.fullmatch(r"[0-9]{14}", version) for version in value))
        return value

    def readiness(self, candidate, *, public=False):
        self._owned({"inspect", "verify", "activate", "public_verify", "recover"})
        origins = [self.profile["origin"]] if public else ["http://127.0.0.1:" + str(self.profile["ports"][name]) for name in ["forge", "web"]]
        observations = []
        deadline = time.monotonic() + 60
        for origin in origins:
            while True:
                try:
                    status, raw = self._request(origin, "/health/ready", authenticated=False)
                    value = json.loads(raw, object_pairs_hook=unique_object) if status == 200 else {}
                    ready = value.get("candidate") == candidate and value.get("status") == "ready" and value.get("dirty") is False
                    if value.get("service") == "gitgood-web":
                        ready = ready and value.get("forge_candidate") == candidate
                    else:
                        checks = value.get("checks", {})
                        ready = ready and value.get("service") == "gitgood" and set(checks) == {"database", "storage", "artifact", "executables", "installation", "ssh"} and all(check is True for check in checks.values())
                    if ready:
                        observations.append({"candidate": candidate, "service": value["service"], "ready": True})
                        break
                except (OSError, ValueError):
                    pass
                require(time.monotonic() < deadline)
                time.sleep(.2)
        return observations

    def maintenance(self):
        # Internal candidate verification must also establish that public routes
        # remain closed until activation. This probe performs no route mutation.
        self._owned({"maintenance", "verify", "recover"})
        deadline = time.monotonic() + 30
        while True:
            try:
                status, _ = self._request(self.profile["origin"], "/health/ready", authenticated=False)
                if status == 503:
                    break
            except OSError:
                pass
            require(time.monotonic() < deadline)
            time.sleep(.2)
        with socket.create_connection((self.profile["hostname"], self.profile["ports"]["ssh"]), timeout=5) as connection:
            require(connection.recv(1) == b"")
        return {"https_503": True, "ssh_closed": True}

    def _git_read(self, stage, url, environment):
        self._owned()
        process = self.actions._launch("maintenance", stage,
                                      [self.actions.executables["git"], "ls-remote", url, "refs/heads/" + self.credentials["branch"]],
                                      environment, self.actions.root)
        try:
            code = process.wait(timeout=90)
        finally:
            self.actions.stop_group("maintenance")
            process.wait(timeout=15)
        require(code == 0)
        raw = private_bytes(process.gitgood_log, 8192)
        expected = self.credentials["commit_sha"] + "\trefs/heads/" + self.credentials["branch"]
        require(raw.decode().strip() == expected)
        return hashlib.sha256(raw).hexdigest()

    def functional(self, directory, *, previous=False, public=False):
        self._owned()
        stage = self.actions._stage(directory, previous)
        candidate = self.actions.journal.intent[("old" if previous else "new") + "_candidate"]
        ready = self.readiness(candidate, public=public)
        origin = self.profile["origin"] if public else "http://127.0.0.1:" + str(self.profile["ports"]["forge"])
        repository_path = "/api/repos/" + self.credentials["team"] + "/" + self.credentials["repository"]
        status, raw = self._request(origin, repository_path + "/branches")
        value = json.loads(raw, object_pairs_hook=unique_object) if status == 200 else {}
        require(status == 200 and any(branch.get("name") == self.credentials["branch"] and branch.get("sha") == self.credentials["commit_sha"] for branch in value.get("branches", [])))
        status, _ = self._request(origin, repository_path + "/branches", authenticated=False)
        require(status == 401)
        environment = {"PATH": "/usr/bin:/bin", "HOME": str(self.directory), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
                       "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0"}
        git_path = "/git/" + self.credentials["team"] + "/" + self.credentials["repository"] + ".git"
        credential = base64.b64encode((self.credentials["username"] + ":" + self.credentials["git_token"]).encode()).decode()
        https_environment = {**environment, "GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "credential.helper", "GIT_CONFIG_VALUE_0": "",
                             "GIT_CONFIG_KEY_1": "http.extraHeader", "GIT_CONFIG_VALUE_1": "Authorization: Basic " + credential}
        if public:
            https_environment["GIT_SSL_CAINFO"] = str(self.actions.root / "configuration" / self.actions.configuration["edge"]["tls_certificate"])
        https_ref = self._git_read(stage, origin + git_path, https_environment)
        observations = {"candidate": candidate, "ready": ready, "commit": self.credentials["commit_sha"], "anonymous_refused": True, "https_ref_sha256": https_ref}
        if public:
            key = private_bytes(self.actions.root / "ssh-host/ssh_host_ed25519_key.pub").decode().split()
            require(len(key) >= 2 and key[0] == "ssh-ed25519" and re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", key[1]))
            known_hosts = self.actions.journal.directory / "probe-known-hosts"
            expected = "[" + self.profile["hostname"] + "]:" + str(self.profile["ports"]["ssh"]) + " " + key[0] + " " + key[1] + "\n"
            if known_hosts.exists() or known_hosts.is_symlink():
                require(private_bytes(known_hosts).decode() == expected)
            else:
                descriptor = self.actions.journal._private_open(known_hosts, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
                with os.fdopen(descriptor, "w") as output:
                    output.write(expected)
            command = shlex.join([self.ssh["path"], "-F", "/dev/null", "-i", str(self.directory / "ssh-private-key"), "-o", "IdentitiesOnly=yes",
                                  "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile=" + str(known_hosts),
                                  "-o", "GlobalKnownHostsFile=/dev/null", "-o", "ConnectTimeout=5"])
            ssh_url = "ssh://" + self.credentials["username"] + "@" + self.profile["hostname"] + ":" + str(self.profile["ports"]["ssh"]) + "/" + self.credentials["team"] + "/" + self.credentials["repository"] + ".git"
            observations["ssh_ref_sha256"] = self._git_read(stage, ssh_url, {**environment, "GIT_SSH_VARIANT": "ssh", "GIT_SSH_COMMAND": command})
        receipt = {"candidate": candidate, "public_functional_probe": public, "receipt_sha256": hashlib.sha256(canonical(observations)).hexdigest()}
        return {"receipt": receipt, "observations": observations}
