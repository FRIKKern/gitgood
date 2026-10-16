"""Fixture-only selected Get loop on the original bus; no production adoption."""
from contextlib import contextmanager
import ctypes
import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import sys
import sysconfig
import time


def require(value):
    if not value:raise ValueError('Selected bus diagnostic invariant')


def extension_name():
    suffix = sysconfig.get_config_var('EXT_SUFFIX')
    require(type(suffix) is str and '/' not in suffix and suffix.endswith('.so'))
    return '_selected_bus_probe' + suffix


def load_native(directory):
    """Verify the Root-owned source/adapter/ELF before loading one fixed module."""
    require(sys.platform == 'linux' and os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0)
    directory = Path(directory)
    require(directory.is_absolute() and directory.anchor == '/' and '..' not in directory.parts)
    for parent in (directory, *directory.parents):
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022)
    names = ('selected-bus-probe.c','selected_bus_probe.py',extension_name());hashes = []
    def identity(info):
        return tuple(getattr(info,name) for name in ('st_dev','st_ino','st_size','st_mtime_ns',
            'st_ctime_ns','st_uid','st_gid','st_mode','st_nlink'))
    for name in names:
        path = directory / name;info = path.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == info.st_gid == 0 and info.st_nlink == 1
            and not info.st_mode & 0o022 and 0 < info.st_size <= 1048576)
        fd = os.open(path,os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(fd,'rb') as source:
            require(identity(os.fstat(source.fileno())) == identity(info));data = source.read(1048577)
            require(len(data) == info.st_size and identity(os.fstat(source.fileno())) == identity(info)
                and identity(path.lstat()) == identity(info))
        hashes.append(hashlib.sha256(data).hexdigest())
    require('_selected_bus_probe' not in sys.modules)
    spec = importlib.util.spec_from_file_location('_selected_bus_probe',directory / extension_name())
    native = importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
    for name,expected in zip(names,hashes):require(hashlib.sha256((directory/name).read_bytes()).hexdigest() == expected)
    require(callable(native.bind_owner) and callable(native.read_selected))
    return native,dict(zip(('c_sha256','adapter_sha256','elf_sha256'),hashes))


class Adapter:
    def __init__(self, module, native):
        self.module = module;self.native = native;self.owner = module.ReadOnlySystemdProperties
        self.original = vars(self.owner)['_read_selected'];self.bindings = {};self.calls = 0;self.fallbacks = 0

    def read(self, subject, path, properties):
        # Model fixtures retain their original Python callbacks exactly once.
        if (type(subject) is not self.owner or type(subject.library) is not ctypes.CDLL
                or type(subject.bus) is not ctypes.c_void_p or type(path) is not str
                or type(properties) is not tuple or any(type(item) is not tuple or len(item) != 3
                    or any(type(value) is not str for value in item) for item in properties)):
            self.fallbacks += 1;return self.original(subject,path,properties)
        self.module.require(not getattr(subject,'_selected_active',False))
        subject._selected_active = True
        try:
            if subject not in self.bindings:
                self.module.require(len(self.bindings) < 8)
                binding = self.native.bind_owner(subject);self.module.require(binding is not None)
                self.bindings[subject] = binding
            self.calls += 1;self.module.require(self.calls <= 10000000)
            result = self.native.read_selected(self.bindings[subject],path,properties)
            self.module.require(type(result) is dict and set(result) == {name for _,name,_ in properties}
                and all(type(value) is str for value in result.values()))
            return result
        finally:subject._selected_active = False

    @contextmanager
    def installed(self):
        require(vars(self.owner)['_read_selected'] is self.original)
        def read(subject,path,properties):return self.read(subject,path,properties)
        try:
            self.owner._read_selected = read
            yield
        finally:self.owner._read_selected = self.original

    def close(self):self.bindings.clear()  # Does not close the original bus.


def compare_guard(module, native, original_guard, stage):
    require(stage.usable and stage.state == 'ready' and sys.getprofile() is None)
    monitoring = getattr(sys,'monitoring',None)
    require(monitoring is None or monitoring.get_tool(monitoring.PROFILER_ID) is None)
    adapter = Adapter(module,native);rows = [];started = time.monotonic_ns()
    try:
        for number in range(20):
            elapsed = {};values = {}
            for selected in ((0,1) if number % 2 == 0 else (1,0)):
                require(stage.usable and stage.state == 'ready');before_calls = adapter.calls
                if selected:
                    with adapter.installed():
                        before = time.monotonic_ns()
                        try:values[selected] = original_guard(stage)
                        finally:elapsed[selected] = max(0,time.monotonic_ns()-before)
                else:
                    before = time.monotonic_ns()
                    try:values[selected] = original_guard(stage)
                    finally:elapsed[selected] = max(0,time.monotonic_ns()-before)
                require(vars(adapter.owner)['_read_selected'] is adapter.original)
                require(adapter.calls > before_calls if selected else adapter.calls == before_calls)
                require(stage.usable and stage.state == 'ready')
            require(values[0] == values[1])
            require(all(type(value) is int and 0 <= value <= 1200000000000 for value in elapsed.values()))
            rows.append({'baseline_us':elapsed[0]//1000,'prototype_us':elapsed[1]//1000})
        require(0 < len(adapter.bindings) <= 8 and adapter.fallbacks == 0)
        return {'diagnostic_only':True,'production_adopted':False,'pairs':rows,
            'original_selected_method_restored':True,'observations_equal':True,'same_original_actors':True,
            'native_selected_calls':adapter.calls,'original_bus_bindings':len(adapter.bindings),
            'observation_results_retained':False,
            'elapsed_ms':min(1200000,max(0,(time.monotonic_ns()-started)//1000000))}
    finally:adapter.close()


class AtFirstGuard:
    def __init__(self, module, native, stage_owner, measurements):
        self.module = module;self.native = native;self.stage_owner = stage_owner;self.measurements = measurements
        self.original = vars(stage_owner)['check'];self.entered = False;self.attempted = False;self.result = None

    def __enter__(self):
        require(callable(self.original))
        def first(stage,*arguments,**keywords):
            try:
                require(not self.attempted and not arguments and not keywords);self.attempted = True
                self.result = compare_guard(self.module,self.native,self.original,stage)
                self.stage_owner.check = self.original
                self.measurements.__enter__();self.entered = True
                return self.stage_owner.check(stage)
            except BaseException:
                stage.usable = False;stage.allocation.usable = False
                for close in (stage.close,stage.allocation.close):
                    try:close()
                    except BaseException:pass
                raise
        self.stage_owner.check = first;return self

    def __exit__(self,*_):
        try:
            if self.entered:self.measurements.__exit__(None,None,None)
        finally:self.stage_owner.check = self.original
