"""A bounded stdio adapter, never a forge authority. Config and input arrive on stdin, not argv."""
import ctypes
import json
import os
import signal
import subprocess
import sys
import threading

MAX_INPUT = 32 * 1024 * 1024
MAX_OUTPUT = 32 * 1024 * 1024


class WindowsJob:
    """Keep a suspended child and all of its descendants in a kill-on-close job."""
    def __init__(self, proc):
        from ctypes import wintypes as w
        class Limits(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                        ("flags", w.DWORD), ("minimum", ctypes.c_size_t), ("maximum", ctypes.c_size_t),
                        ("active", w.DWORD), ("affinity", ctypes.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]
        class Extended(ctypes.Structure):
            _fields_ = [("limits", Limits), ("io", IO), ("process_memory", ctypes.c_size_t),
                        ("job_memory", ctypes.c_size_t), ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t)]
        class ThreadEntry(ctypes.Structure):
            _fields_ = [("size", w.DWORD), ("usage", w.DWORD), ("thread", w.DWORD), ("owner", w.DWORD),
                        ("base", w.LONG), ("delta", w.LONG), ("flags", w.DWORD)]
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        for name, result, args in [
            ("CreateJobObjectW", w.HANDLE, [ctypes.c_void_p, w.LPCWSTR]),
            ("SetInformationJobObject", w.BOOL, [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]),
            ("AssignProcessToJobObject", w.BOOL, [w.HANDLE, w.HANDLE]),
            ("TerminateJobObject", w.BOOL, [w.HANDLE, w.UINT]),
            ("CloseHandle", w.BOOL, [w.HANDLE]),
            ("CreateToolhelp32Snapshot", w.HANDLE, [w.DWORD, w.DWORD]),
            ("Thread32First", w.BOOL, [w.HANDLE, ctypes.POINTER(ThreadEntry)]),
            ("Thread32Next", w.BOOL, [w.HANDLE, ctypes.POINTER(ThreadEntry)]),
            ("OpenThread", w.HANDLE, [w.DWORD, w.BOOL, w.DWORD]),
            ("ResumeThread", w.DWORD, [w.HANDLE]),
        ]:
            fn = getattr(k, name)
            fn.restype, fn.argtypes = result, args
        self.k, self.handle = k, k.CreateJobObjectW(None, None)
        info = Extended()
        info.limits.flags = 0x2000 | 0x100 | 0x200  # kill-on-close, process memory, job memory
        info.process_memory = 512 * 1024 * 1024
        info.job_memory = 1024 * 1024 * 1024
        if not self.handle or not k.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            raise OSError("job_configuration_failed")
        if not k.AssignProcessToJobObject(self.handle, int(proc._handle)):
            self.close()
            raise OSError("job_assignment_failed")
        snapshot = k.CreateToolhelp32Snapshot(4, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            self.close()
            raise OSError("thread_snapshot_failed")
        resumed = False
        try:
            entry = ThreadEntry()
            entry.size = ctypes.sizeof(entry)
            found = k.Thread32First(snapshot, ctypes.byref(entry))
            while found:
                if entry.owner == proc.pid:
                    thread = k.OpenThread(2, False, entry.thread)
                    if thread:
                        try:
                            if k.ResumeThread(thread) != 0xFFFFFFFF:
                                resumed = True
                        finally:
                            k.CloseHandle(thread)
                found = k.Thread32Next(snapshot, ctypes.byref(entry))
        finally:
            k.CloseHandle(snapshot)
        if not resumed:
            self.close()
            raise OSError("thread_resume_failed")
    def kill(self):
        if self.handle:
            self.k.TerminateJobObject(self.handle, 1)
    def close(self):
        if self.handle:
            self.k.CloseHandle(self.handle)
            self.handle = None


def main():
    line = sys.stdin.buffer.readline(65537)
    if len(line) > 65536:
        raise ValueError("configuration_too_large")
    config = json.loads(line)
    size = config["input_size"]
    limit = min(config.get("output_limit", MAX_OUTPUT), MAX_OUTPUT)
    if not 0 <= size <= MAX_INPUT:
        raise ValueError("input_too_large")
    incoming = sys.stdin.buffer.read(size)
    if len(incoming) != size:
        raise ValueError("input_interrupted")
    windows = os.name == "nt"
    def child_limits():
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (65, 65))
        os.umask(0o077)
    proc = subprocess.Popen(config["args"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=config["env"], start_new_session=not windows,
                            creationflags=(0x08000000 | 4) if windows else 0,
                            preexec_fn=child_limits if not windows else None)
    job = None
    try:
        if windows:
            try:
                job = WindowsJob(proc)
            except Exception:
                proc.kill()
                proc.wait()
                raise
        stopped = threading.Event()
        reason = []
        output = []
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
        def drain(stream, keep, cap):
            total = 0
            while True:
                chunk = stream.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > cap:
                    kill("output_limit")
                    break
                if keep:
                    output.append(chunk)
            stream.close()
        readers = [threading.Thread(target=drain, args=(proc.stdout, True, limit)),
                   threading.Thread(target=drain, args=(proc.stderr, False, 65536))]
        for reader in readers:
            reader.start()
        def watch_parent():
            # The Erlang port remains open while its owner exists. EOF means cancellation or VM exit.
            if not os.read(sys.stdin.fileno(), 1):
                kill("caller_interrupted")
        threading.Thread(target=watch_parent, daemon=True).start()
        timer = threading.Timer(config.get("timeout_ms", 15000) / 1000, lambda: kill("timeout"))
        timer.start()
        try:
            try:
                proc.stdin.write(incoming)
            except BrokenPipeError:
                pass
            finally:
                proc.stdin.close()  # Real EOF for update-ref --stdin and CGI bodies.
            status = proc.wait()
            for reader in readers:
                reader.join()
        finally:
            timer.cancel()
        if reason and reason[0] == "caller_interrupted":
            return
        header = {"status": status, "error": reason[0] if reason else None}
        sys.stdout.buffer.write(json.dumps(header).encode() + b"\n")
        if not reason:
            sys.stdout.buffer.write(b"".join(output))
        sys.stdout.buffer.flush()
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
            sys.stdout.buffer.write(b'{"status":1,"error":"process_adapter_failed"}\n')
            sys.stdout.buffer.flush()
        except OSError:
            os._exit(0)
