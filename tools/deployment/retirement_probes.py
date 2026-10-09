"""Fixed recovery-mode, independent actor and actual HTTPS/SSH transport probes."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import ssl
import subprocess
import time
import urllib.error
import urllib.request

from native_inventory import database_environment, directory_identity, private_bytes
from native_probes import NoRedirect, SCHEMA_SQL, probe_credentials
from retirement_snapshot import retained_file_identity
from upgrade_journal import canonical, require, unique_object


class RetirementProbes:
    def __init__(self, runtime):
        self.runtime = runtime
        require(runtime.full["protocol"] == 3)
        self.inputs = {}
        self.current()
        context = ssl.create_default_context()
        context.load_verify_locations(cafile=str(runtime.root / "configuration" / runtime.configuration["edge"]["tls_certificate"]))
        self.opener = urllib.request.build_opener(NoRedirect(), urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))

    def current(self):
        self.runtime.reobserve()
        full = self.runtime.full
        for actor, directory_key, digest_key in [("owner", "probe_directory", "probe_sha256"),
                                                  ("outsider", "outsider_probe_directory", "outsider_probe_sha256")]:
            directory = Path(full[directory_key]["path"])
            require(directory_identity(directory, private=True) == full[directory_key])
            credentials, ssh = probe_credentials(directory, full[digest_key], self.runtime.journal.plan["installation"])
            self.inputs[actor] = {"directory": directory, "credentials": credentials, "ssh": ssh}
        owner, outsider = [self.inputs[name]["credentials"] for name in ["owner", "outsider"]]
        for key in ["username", "session_token", "git_token", "ssh_private_key_sha256"]:
            require(owner[key] != outsider[key])
        require((owner["team"], owner["repository"]) != (outsider["team"], outsider["repository"]))
        require(retained_file_identity(full["outsider_token"]["path"], 128) == full["outsider_token"])
        require(private_bytes(full["outsider_token"]["path"], 128).decode() == outsider["session_token"])

    def request(self, origin, path, actor=None):
        self.current()
        headers = {} if actor is None else {"Authorization": "Bearer " + self.inputs[actor]["credentials"]["session_token"]}
        try:
            with self.opener.open(urllib.request.Request(origin + path, headers=headers, method="GET"), timeout=5) as response:
                raw = response.read(1_048_577)
                require(len(raw) <= 1_048_576)
                return response.status, raw
        except urllib.error.HTTPError as error:
            error.close()
            return error.code, b""

    def ready(self):
        candidate = self.runtime.journal.plan["candidate"]
        ports = self.runtime.target["ports"]
        origins = ["http://127.0.0.1:" + str(ports[name]) for name in ["forge", "web"]] + ["https://127.0.0.1:" + str(ports["https"])]
        observations = []
        deadline = time.monotonic() + 90
        for origin in origins:
            while True:
                require(all(process.poll() is None for name, process in self.runtime.processes.items() if name in {"native", "web", "edge"}))
                try:
                    status, raw = self.request(origin, "/health/ready")
                    value = json.loads(raw, object_pairs_hook=unique_object) if status == 200 else {}
                    if status == 200:
                        require(value.get("operational_mode") == "recovery_verification")
                        require(value.get("candidate") == candidate and value.get("dirty") is False)
                        if value.get("service") == "gitgood-web":
                            require(value.get("forge_candidate") == candidate)
                        else:
                            require(value.get("service") == "gitgood")
                            checks = value.get("checks", {})
                            require(set(checks) == {"database", "storage", "artifact", "executables", "installation", "ssh"} and all(check is True for check in checks.values()))
                        if value.get("status") == "ready":
                            observations.append({"service": value["service"], "candidate": candidate, "operational_mode": "recovery_verification"})
                            break
                except (OSError, ValueError):
                    pass
                require(time.monotonic() < deadline)
                time.sleep(.2)
        return observations

    def git(self, actor, transport, context_actor, *, permitted):
        self.current()
        require(actor in self.inputs and context_actor in self.inputs and transport in {"https", "ssh"} and type(permitted) is bool)
        runtime = self.runtime
        inputs, repository = self.inputs[actor], self.inputs[context_actor]["credentials"]
        credentials = inputs["credentials"]
        environment = {"PATH": "/usr/bin:/bin", "HOME": str(runtime.directory), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
                       "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0"}
        if transport == "https":
            token = base64.b64encode((credentials["username"] + ":" + credentials["git_token"]).encode()).decode()
            environment.update(GIT_CONFIG_COUNT="3", GIT_CONFIG_KEY_0="credential.helper", GIT_CONFIG_VALUE_0="",
                               GIT_CONFIG_KEY_1="http.extraHeader", GIT_CONFIG_VALUE_1="Authorization: Basic " + token,
                               GIT_CONFIG_KEY_2="http.followRedirects", GIT_CONFIG_VALUE_2="false",
                               GIT_SSL_CAINFO=str(runtime.root / "configuration" / runtime.configuration["edge"]["tls_certificate"]))
            url = "https://127.0.0.1:" + str(runtime.target["ports"]["https"]) + "/git/" + repository["team"] + "/" + repository["repository"] + ".git"
        else:
            public = private_bytes(runtime.root / "ssh/ssh_host_ed25519_key.pub").decode().split()
            require(len(public) >= 2 and public[0] == "ssh-ed25519" and re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", public[1]))
            known = runtime.directory / "known-hosts"
            expected = "[127.0.0.1]:" + str(runtime.target["ports"]["ssh"]) + " " + public[0] + " " + public[1] + "\n"
            if known.exists() or known.is_symlink():
                require(private_bytes(known).decode() == expected)
            else:
                runtime._write(known, expected.encode())
            command = shlex.join([inputs["ssh"]["path"], "-F", "/dev/null", "-i", str(inputs["directory"] / "ssh-private-key"),
                                  "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                                  "-o", "UserKnownHostsFile=" + str(known), "-o", "GlobalKnownHostsFile=/dev/null", "-o", "ConnectTimeout=5"])
            environment.update(GIT_SSH_VARIANT="ssh", GIT_SSH_COMMAND=command)
            url = "ssh://" + credentials["username"] + "@127.0.0.1:" + str(runtime.target["ports"]["ssh"]) + "/" + repository["team"] + "/" + repository["repository"] + ".git"
        process = runtime._launch("maintenance", [runtime.executables["git"], "ls-remote", url, "refs/heads/" + repository["branch"]], environment, runtime.directory)
        try:
            code = process.wait(timeout=90)
        finally:
            runtime.stop_group("maintenance")
        raw = private_bytes(process.gitgood_log, 8192)
        if permitted:
            require(code == 0 and raw.decode().strip() == repository["commit_sha"] + "\trefs/heads/" + repository["branch"])
        else:
            require(code != 0 and repository["commit_sha"].encode() not in raw and b"\trefs/heads/" not in raw)
            if transport == "https":
                require(b"returned error: 404" in raw or b"fatal: repository " in raw and b" not found" in raw)
            else:
                require(b"Gitgood: command, identity or repository unavailable." in raw)
        self.current()
        return hashlib.sha256(raw).hexdigest()

    def functional(self):
        ready = self.ready()
        runtime = self.runtime
        stage = runtime.reobserve()
        environment = database_environment(runtime.configuration["forge"]["DATABASE_URL"])
        result = subprocess.run([runtime.executables["psql"], "--no-psqlrc", "--tuples-only", "--no-align", "--set=ON_ERROR_STOP=1", "--command", SCHEMA_SQL],
                                env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)
        require(result.returncode == 0 and 0 < len(result.stdout) <= 8192 and json.loads(result.stdout) == stage["migrations"])
        origin = "https://127.0.0.1:" + str(runtime.target["ports"]["https"])
        actors = {}
        for actor in ["owner", "outsider"]:
            status, raw = self.request(origin, "/api/session", actor)
            value = json.loads(raw, object_pairs_hook=unique_object) if status == 200 else {}
            user = value.get("user", {})
            require(status == 200 and user.get("username") == self.inputs[actor]["credentials"]["username"])
            require(type(user.get("id")) is int and user["id"] > 0)
            actors[actor] = user["id"]
            credentials = self.inputs[actor]["credentials"]
            path = "/api/repos/" + credentials["team"] + "/" + credentials["repository"] + "/branches"
            status, raw = self.request(origin, path, actor)
            value = json.loads(raw, object_pairs_hook=unique_object) if status == 200 else {}
            require(status == 200 and any(row.get("name") == credentials["branch"] and row.get("sha") == credentials["commit_sha"] for row in value.get("branches", [])))
        require(actors["owner"] != actors["outsider"])
        owner = self.inputs["owner"]["credentials"]
        private = "/api/repos/" + owner["team"] + "/" + owner["repository"] + "/branches"
        require(self.request(origin, private)[0] == 401)
        require(self.request(origin, private, "outsider")[0] in {403, 404})
        outsider = self.inputs["outsider"]["credentials"]
        witness = "/api/repos/" + outsider["team"] + "/" + outsider["repository"] + "/branches"
        require(self.request(origin, witness, "owner")[0] in {403, 404})
        transports = {}
        for transport in ["https", "ssh"]:
            transports["owner_" + transport] = self.git("owner", transport, "owner", permitted=True)
            transports["outsider_witness_" + transport] = self.git("outsider", transport, "outsider", permitted=True)
            transports["outsider_private_refusal_" + transport] = self.git("outsider", transport, "owner", permitted=False)
            transports["outsider_witness_after_refusal_" + transport] = self.git("outsider", transport, "outsider", permitted=True)
        observations = {"candidate": runtime.journal.plan["candidate"], "mode": "recovery_verification", "ready": ready,
                        "schema_sha256": hashlib.sha256(result.stdout).hexdigest(), "independent_actors_verified": True,
                        "recovered_private_branch_verified": True, "anonymous_refused": True, "outsider_private_refused": True,
                        "transport_sha256": transports}
        runtime._write(runtime.directory / "functional-observations.json", canonical(observations) + b"\n")
        return observations
