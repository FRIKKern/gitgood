"""Fixed TLS and bounded SSH routing in one exact installation-owned cgroup."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
from urllib.parse import urlsplit

if __name__ == "__main__":
    # Isolated interpreter mode does not add the operator installation directory.
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from native_inventory import cgroup_identity, directory_identity, executable_identity, private_bytes
from upgrade_journal import canonical, require, unique_object


def port(value):
    require(isinstance(value, str) and re.fullmatch(r"[1-9][0-9]{0,4}", value))
    number = int(value)
    require(1024 <= number <= 65535)
    return number


def routing_profile(configuration):
    forge, web = configuration["forge"], configuration["web"]
    origin = forge["GITGOOD_PUBLIC_URL"]
    url = urlsplit(origin)
    require(url.scheme == "https" and not url.username and not url.password and not url.query and not url.fragment and url.path in {"", "/"})
    require(url.hostname and re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", url.hostname))
    require(url.port is not None and 1024 <= url.port <= 65535)
    require(forge["GITGOOD_WEB_ORIGIN"] == origin and forge["GITGOOD_SSH_PUBLIC_HOST"] == url.hostname)
    ports = {"https": url.port, "web": port(web["PORT"]), "forge": port(forge["PORT"]),
             "ssh": port(forge["GITGOOD_SSH_PUBLIC_PORT"]), "native_ssh": port(forge["GITGOOD_SSH_PORT"])}
    require(len(set(ports.values())) == len(ports))
    require(web["GITGOOD_API_URL"] == "http://127.0.0.1:" + str(ports["forge"]))
    require(re.fullmatch(r"[A-Za-z0-9+/]{43}=", forge["GITGOOD_PROXY_KEY"]))
    return {"origin": origin.rstrip("/"), "hostname": url.hostname, "ports": ports}


def caddy_source(root, configuration, mode):
    require(mode in {"maintenance", "active"})
    profile = routing_profile(configuration)
    certificate = root / "configuration" / configuration["edge"]["tls_certificate"]
    key = root / "configuration" / configuration["edge"]["tls_key"]
    for value in [certificate, key]:
        private_bytes(value)
    header_filter = "request>headers delete\n        resp_headers delete"
    source = """{
  persist_config off
  admin off
  auto_https off
  log default {
    output stderr
    format filter {
      wrap json
      fields {
        %s
      }
    }
  }
}
%s {
  tls %s %s
  header Cache-Control no-store
""" % (header_filter, profile["origin"], json.dumps(str(certificate)), json.dumps(str(key)))
    if mode == "maintenance":
        source += '  header Retry-After 30\n  respond "Gitgood maintenance" 503\n'
    else:
        source += """  handle /internal/* {
    respond 404
  }
  handle /git/* {
    request_body {
      max_size 33554432
    }
    reverse_proxy 127.0.0.1:%s {
      header_up -X-Gitgood-Edge-Key
      header_up -X-Gitgood-Edge-Client
      header_up -X-Gitgood-Client-Address
      header_up -X-Gitgood-Client-Time
      header_up -X-Gitgood-Client-Signature
      transport http {
        response_header_timeout 80s
      }
    }
  }
  handle {
    reverse_proxy 127.0.0.1:%s {
      header_up X-Gitgood-Edge-Key {$GITGOOD_PROXY_KEY}
      header_up X-Gitgood-Edge-Client {remote_host}
      header_up -X-Gitgood-Client-Address
      header_up -X-Gitgood-Client-Time
      header_up -X-Gitgood-Client-Signature
    }
  }
""" % (profile["ports"]["forge"], profile["ports"]["web"])
    return source + "}\n"


def start_edge(actions, mode):
    """Only the current durable owner can publish fixed maintenance/active routing."""
    require(sys.platform == "linux")
    actions._owned({"maintenance", "activate", "public_verify", "recover"})
    require(mode in {"maintenance", "active"})
    if mode == "active":
        require(actions.journal.record["stage"] in {"activate", "public_verify", "recover"})
    actions.reobserve()
    group = actions.bindings["cgroups"]["edge"]
    require(cgroup_identity(actions.bindings["installation"], "edge") == group)
    require(dict(line.split() for line in (Path(group["path"]) / "cgroup.events").read_text().splitlines())["populated"] == "0")
    profile = routing_profile(actions.configuration)
    # The operator script itself has private, single-file custody. Candidate code
    # cannot supply a command or substitute an edge implementation.
    module = Path(__file__).resolve()
    module_digest = hashlib.sha256(private_bytes(module, 131_072)).hexdigest()
    directory = actions.journal.directory / ("edge-" + str(len(actions.journal.record["events"])))
    directory.mkdir(mode=0o700)
    configuration = directory / "Caddyfile"
    with configuration.open("x", opener=lambda name, flags: os.open(name, flags, 0o600)) as output:
        output.write(caddy_source(actions.root, actions.configuration, mode))
        output.flush()
        os.fsync(output.fileno())
    plan = {"protocol": 1, "root": str(actions.root), "mode": mode, "profile": profile,
            "installation": actions.bindings["installation"], "group": group,
            "configuration_sha256": actions.bindings["configuration_sha256"]["installation.json"],
            "caddy": actions.bindings["executables"]["caddy"], "module_sha256": module_digest,
            "caddyfile_sha256": hashlib.sha256(private_bytes(configuration)).hexdigest()}
    path = directory / "edge-plan.json"
    with path.open("xb", opener=lambda name, flags: os.open(name, flags, 0o600)) as output:
        output.write(canonical(plan) + b"\n")
        output.flush()
        os.fsync(output.fileno())
    environment = {"PATH": "/usr/bin:/bin", "HOME": str(actions.root), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    with (directory / "guardian.log").open("xb", opener=lambda name, flags: os.open(name, flags, 0o600)) as output:
        return subprocess.Popen([actions.executables["python"], "-I", str(module), str(path)],
                                env=environment, cwd=directory, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, umask=0o077)


async def route_ssh(mode, upstream_port, public_port, stopped):
    connections = set()

    async def close_stream(stream):
        stream.close()
        try:
            await asyncio.wait_for(stream.wait_closed(), 1)
        except (OSError, asyncio.TimeoutError):
            stream.transport.abort()
        except asyncio.CancelledError:
            stream.transport.abort()
            raise

    async def connection(reader, writer):
        upstream = None

        async def transfer(source, target):
            while data := await source.read(65_536):
                target.write(data)
                await target.drain()
            try:
                target.write_eof()
            except (OSError, NotImplementedError):
                pass

        try:
            remote, upstream = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", upstream_port), 5)
            await asyncio.wait_for(asyncio.gather(transfer(reader, upstream), transfer(remote, writer)), 120)
        except (OSError, asyncio.TimeoutError, asyncio.CancelledError):
            pass
        finally:
            for stream in [writer, upstream]:
                if stream is not None:
                    await close_stream(stream)

    def accepted(reader, writer):
        if mode != "active" or stopped.is_set() or len(connections) >= 32:
            writer.transport.abort()
            return
        task = asyncio.create_task(connection(reader, writer))
        connections.add(task)
        task.add_done_callback(connections.discard)

    server = await asyncio.start_server(accepted, "0.0.0.0", public_port, limit=65_536)
    try:
        await stopped.wait()
    finally:
        server.close()
        tasks = list(connections)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        # Python 3.12 waits for accepted clients here too: close those before
        # waiting for the server, otherwise live SSH sessions deadlock shutdown.
        await asyncio.wait_for(server.wait_closed(), 3)


async def supervise(plan, configuration, directory):
    environment = {"PATH": "/usr/bin:/bin", "HOME": str(directory), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
                   "XDG_DATA_HOME": str(directory / "data"), "XDG_CONFIG_HOME": str(directory / "config"),
                   "GITGOOD_PROXY_KEY": configuration["forge"]["GITGOOD_PROXY_KEY"]}
    command = [plan["caddy"]["path"], "--config", str(directory / "Caddyfile"), "--adapter", "caddyfile"]
    result = subprocess.run([command[0], "validate", *command[1:]], env=environment,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    require(result.returncode == 0)
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for number in [signal.SIGTERM, signal.SIGINT]:
        loop.add_signal_handler(number, stopped.set)
    with (directory / "caddy.log").open("xb", opener=lambda name, flags: os.open(name, flags, 0o600)) as output:
        process = await asyncio.create_subprocess_exec(command[0], "run", *command[1:], env=environment,
                                                       stdin=subprocess.DEVNULL, stdout=output, stderr=output)
        watcher = asyncio.create_task(process.wait())
        router = asyncio.create_task(route_ssh(plan["mode"], plan["profile"]["ports"]["native_ssh"], plan["profile"]["ports"]["ssh"], stopped))
        stop_waiter = asyncio.create_task(stopped.wait())
        try:
            done, _ = await asyncio.wait([watcher, router, stop_waiter], return_when=asyncio.FIRST_COMPLETED)
            require(watcher not in done and router not in done)
        finally:
            stopped.set()
            # A failed SSH bind must still stop Caddy. Preserve the routing
            # failure without allowing a refused guardian to leave HTTPS live.
            router_result = await asyncio.gather(router, return_exceptions=True)
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(watcher, 10)
                except asyncio.TimeoutError:
                    process.kill()
                    await watcher
            stop_waiter.cancel()
            await asyncio.gather(stop_waiter, return_exceptions=True)
            require(not isinstance(router_result[0], BaseException))


def guardian(path):
    require(sys.platform == "linux")
    path = Path(path)
    directory_identity(path.parent, private=True)
    plan = json.loads(private_bytes(path), object_pairs_hook=unique_object)
    require(set(plan) == {"protocol", "root", "mode", "profile", "installation", "group", "configuration_sha256", "caddy", "module_sha256", "caddyfile_sha256"})
    require(type(plan["protocol"]) is int and plan["protocol"] == 1 and plan["mode"] in {"maintenance", "active"})
    require(hashlib.sha256(private_bytes(Path(__file__).resolve())).hexdigest() == plan["module_sha256"])
    root = Path(plan["root"])
    directory_identity(root, private=True)
    raw = private_bytes(root / "configuration/installation.json")
    require(hashlib.sha256(raw).hexdigest() == plan["configuration_sha256"])
    configuration = json.loads(raw, object_pairs_hook=unique_object)
    require(configuration["installation"] == plan["installation"] and routing_profile(configuration) == plan["profile"])
    require(executable_identity(plan["caddy"]["path"]) == plan["caddy"])
    require(private_bytes(path.parent / "Caddyfile").decode() == caddy_source(root, configuration, plan["mode"]))
    require(hashlib.sha256(private_bytes(path.parent / "Caddyfile")).hexdigest() == plan["caddyfile_sha256"])
    group = cgroup_identity(plan["installation"], "edge")
    require(group == plan["group"])
    driver = cgroup_identity(plan["installation"], "driver")
    require(Path("/proc/self/cgroup").read_text().splitlines() == ["0::" + driver["kernel_path"]])
    require(dict(line.split() for line in (Path(group["path"]) / "cgroup.events").read_text().splitlines())["populated"] == "0")
    (Path(group["path"]) / "cgroup.procs").write_text(str(os.getpid()))
    require(Path("/proc/self/cgroup").read_text().splitlines() == ["0::" + group["kernel_path"]])
    asyncio.run(supervise(plan, configuration, path.parent))


if __name__ == "__main__":
    try:
        guardian(sys.argv[1])
    except Exception:
        print("Native edge refused", file=sys.stderr)
        raise SystemExit(1)
