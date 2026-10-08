"""Bounded binary streaming adapter. Forge authority and sensitive configuration stay in Elixir."""
import json
import os
import signal
import struct
import subprocess
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from git_worker import WindowsJob

MAX = 32 * 1024 * 1024

def main():
    line = sys.stdin.buffer.readline(65537)
    if len(line) > 65536:
        raise ValueError("configuration_limit")
    config = json.loads(line)
    windows = os.name == "nt"
    def limits():
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (65, 65))
        os.umask(0o077)
    proc = subprocess.Popen(config["args"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, env=config["env"], start_new_session=not windows,
        creationflags=(0x08000000 | 4) if windows else 0, preexec_fn=limits if not windows else None)
    job = None
    lock = threading.Lock()
    stopped = threading.Event()
    reason = []
    def frame(kind, body):
        with lock:
            sys.stdout.buffer.write(bytes([kind]) + struct.pack(">I", len(body)) + body)
            sys.stdout.buffer.flush()
    def kill(why):
        if not stopped.is_set():
            reason.append(why)
            stopped.set()
            if job:
                job.kill()
            else:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
    def exact(size):
        body = bytearray()
        while len(body) < size:
            chunk = sys.stdin.buffer.read(size - len(body))
            if not chunk:
                raise EOFError()
            body.extend(chunk)
        return bytes(body)
    def input_loop():
        total = 0
        try:
            while True:
                header = exact(5)
                kind, length = header[0], struct.unpack(">I", header[1:])[0]
                if length > 65536 or kind not in (0, 1) or (kind == 1 and length != 0):
                    kill("input_limit")
                    return
                if kind == 1:
                    proc.stdin.close()
                    # Keep watching the controlling port after half-close.
                    if not os.read(sys.stdin.fileno(), 1) and proc.poll() is None:
                        kill("caller_interrupted")
                    return
                total += length
                if total > MAX:
                    kill("input_limit")
                    return
                proc.stdin.write(exact(length))
                proc.stdin.flush()
        except EOFError:
            if proc.poll() is None:
                kill("caller_interrupted")
        except (BrokenPipeError, OSError):
            pass
    def output_loop(stream, kind, cap):
        total = 0
        try:
            while True:
                chunk = stream.read1(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > cap:
                    kill("output_limit")
                    break
                frame(kind, chunk)
        except (BrokenPipeError, OSError):
            kill("caller_interrupted")
        finally:
            stream.close()
    try:
        if windows:
            try:
                job = WindowsJob(proc)
            except Exception:
                proc.kill()
                proc.wait()
                raise
        readers = [threading.Thread(target=output_loop, args=(proc.stdout, 0, min(config["output_limit"], MAX))),
                   threading.Thread(target=output_loop, args=(proc.stderr, 1, 65536))]
        for reader in readers:
            reader.start()
        threading.Thread(target=input_loop, daemon=True).start()
        timer = threading.Timer(min(config["timeout_ms"], 60000) / 1000, lambda: kill("timeout"))
        timer.start()
        try:
            status = proc.wait()
            for reader in readers:
                reader.join()
            frame(2, json.dumps({"status": status, "error": reason[0] if reason else None}).encode())
        finally:
            timer.cancel()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        if job:
            job.close()

if __name__ == "__main__":
    try:
        main()
    except Exception:
        try:
            body = b'{"status":1,"error":"process_failed"}'
            sys.stdout.buffer.write(bytes([2]) + struct.pack(">I", len(body)) + body)
            sys.stdout.buffer.flush()
        except OSError:
            pass
    finally:
        # The controlling input thread can still be blocked after the child exits.
        # Frames are flushed and the job is closed above; avoid CPython finalizing
        # a buffered stdin while that daemon thread owns its lock.
        os._exit(0)
