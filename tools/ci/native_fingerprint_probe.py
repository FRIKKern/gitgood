"""Fixture-only fresh fingerprint comparison. No production import or adoption."""
import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import sys
import sysconfig
import time


def require(value):
    if not value:
        raise ValueError('Diagnostic fingerprint invariant')


def extension_name():
    suffix = sysconfig.get_config_var('EXT_SUFFIX')
    require(type(suffix) is str and '/' not in suffix and suffix.endswith('.so'))
    return '_fingerprint_probe' + suffix


def load_native(directory):
    """Load the one owned module, recording only bounded public code hashes."""
    require(sys.platform == 'linux' and os.getuid() == os.geteuid() == 0)
    directory = Path(directory)
    require(directory.is_absolute() and directory.anchor == '/' and '..' not in directory.parts)
    for parent in (directory, *directory.parents):
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022)
    names = ('native-fingerprint-probe.c', 'native_fingerprint_probe.py', extension_name())
    hashes = []
    def identity(info):
        return tuple(getattr(info, name) for name in ('st_dev', 'st_ino', 'st_size',
            'st_mtime_ns', 'st_ctime_ns', 'st_uid', 'st_gid', 'st_mode', 'st_nlink'))
    for name in names:
        path = directory / name
        info = path.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == info.st_gid == 0
            and info.st_nlink == 1 and not info.st_mode & 0o022 and 0 < info.st_size <= 1048576)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(fd, 'rb') as source:
            require(identity(os.fstat(source.fileno())) == identity(info))
            data = source.read(1048577)
            require(len(data) == info.st_size and identity(os.fstat(source.fileno())) == identity(info)
                and identity(path.lstat()) == identity(info))
        hashes.append(hashlib.sha256(data).hexdigest())
    require('_fingerprint_probe' not in sys.modules)
    spec = importlib.util.spec_from_file_location('_fingerprint_probe', directory / extension_name())
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Import must not have changed the owned files being identified.
    for name, expected in zip(names, hashes):
        require(hashlib.sha256((directory / name).read_bytes()).hexdigest() == expected)
    require(callable(module.fingerprint))
    return module, dict(zip(('c_sha256', 'adapter_sha256', 'elf_sha256'), hashes))


def adapter(service, native, original):
    """Fallback preserves the original domain; never retain metadata results."""
    def fingerprint(path, maximum, executable):
        # Check types before canonicalization, so the original path protocol is
        # invoked exactly once even on the unsupported-input fallback.
        if type(maximum) is not int or not 0 < maximum < 2**63 or type(executable) is not bool:
            return original(path, maximum, executable)
        path = service._root_file_path(path)
        if len(str(path)) > 1024 or len(path.parts) > 64:
            return original(path, maximum, executable)
        parents = tuple(name for _parent, name in service._root_file_parents(path))
        value = native.fingerprint(str(path), parents, maximum, executable)
        service.require(value is not None)
        return value
    return fingerprint


def compare_guard(service, native, original_guard, stage):
    """Forty fresh read-only checks; no profile, effects or actor substitution."""
    require(stage.usable and stage.state == 'ready' and sys.getprofile() is None)
    monitoring = getattr(sys, 'monitoring', None)
    require(monitoring is None or monitoring.get_tool(monitoring.PROFILER_ID) is None)
    owner = service._CapturedRootFiles
    descriptor = vars(owner)['_fingerprint']
    require(type(descriptor) is staticmethod)
    original = descriptor.__func__
    calls = 0
    class Counted:
        def fingerprint(self, *arguments):
            nonlocal calls
            calls += 1
            return native.fingerprint(*arguments)
    prototype = staticmethod(adapter(service, Counted(), original))
    started = time.monotonic_ns()
    rows = []
    try:
        for number in range(20):
            elapsed = {};values = {}
            for selected in ((0, 1) if number % 2 == 0 else (1, 0)):
                require(stage.usable and stage.state == 'ready')
                setattr(owner, '_fingerprint', prototype if selected else descriptor)
                before = time.monotonic_ns();before_calls = calls
                try:
                    values[selected] = original_guard(stage)
                finally:
                    elapsed[selected] = max(0, time.monotonic_ns() - before)
                    setattr(owner, '_fingerprint', descriptor)
                require(stage.usable and stage.state == 'ready')
                require(calls > before_calls if selected else calls == before_calls)
            require(values[0] == values[1])
            require(all(type(value) is int and 0 <= value <= 1200000000000 for value in elapsed.values()))
            rows.append({'baseline_us': elapsed[0] // 1000, 'prototype_us': elapsed[1] // 1000})
        require(0 < calls <= 10000000)
    finally:
        setattr(owner, '_fingerprint', descriptor)
    require(vars(owner)['_fingerprint'] is descriptor)
    elapsed_ms = (time.monotonic_ns() - started) // 1000000
    require(0 <= elapsed_ms <= 1200000)
    return {'diagnostic_only': True, 'pairs': rows, 'extra_read_only_checks': 40,
        'native_fingerprint_calls': calls, 'elapsed_ms': elapsed_ms,
        'original_fingerprint_restored': True, 'production_adoption': False}


class BeforeStageComparison:
    """Compare before starting existing timers; restore all pointers on exit."""
    def __init__(self, service, native, stage_owner, measurements):
        self.service = service;self.native = native;self.stage_owner = stage_owner
        self.measurements = measurements;self.entered = False;self.attempted = False
        self.original = vars(stage_owner)['check'];self.result = None

    def __enter__(self):
        require(callable(self.original))
        def first(stage, *arguments, **keywords):
            try:
                require(not self.attempted and not arguments and not keywords)
                self.attempted = True
                self.result = compare_guard(self.service, self.native, self.original, stage)
                setattr(self.stage_owner, 'check', self.original)
                self.measurements.__enter__();self.entered = True
                return self.stage_owner.check(stage)
            except BaseException:
                # Restoration does not revive an observer after refusal or a
                # mismatch. Preserve the original close/poison behavior.
                stage.close();stage.allocation.close()
                raise
        setattr(self.stage_owner, 'check', first)
        return self

    def __exit__(self, *_):
        try:
            if self.entered:self.measurements.__exit__(None, None, None)
        finally:
            setattr(self.stage_owner, 'check', self.original)
