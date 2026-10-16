"""Hosted-only compiled path-body comparison on original classes and actors."""
import ast
from contextlib import contextmanager
from functools import wraps
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pathlib
import stat
import sys
import sysconfig
import threading
import time
import types

from path_body_source import TARGETS, select_source


def require(value):
    if not value:raise ValueError('Path body diagnostic invariant')


def root_owner():
    require(sys.platform=='linux' and sys.version_info[:2]==(3,12)
        and os.getuid()==os.geteuid()==os.getgid()==os.getegid()==0)


def extension_name():
    suffix=sysconfig.get_config_var('EXT_SUFFIX')
    require(type(suffix) is str and '/' not in suffix and suffix.endswith('.so'))
    return '_path_body_probe'+suffix


def _read_owned(path,maximum):
    path=Path(path);require(path.is_absolute() and path.anchor=='/' and '..' not in path.parts)
    for parent in path.parents:
        value=parent.lstat()
        require(stat.S_ISDIR(value.st_mode) and value.st_uid==0 and not value.st_mode & 0o022)
    info=path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid==info.st_gid==0 and info.st_nlink==1
        and not info.st_mode & 0o022 and 0<info.st_size<=maximum)
    fields=('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_mode','st_uid','st_gid','st_nlink')
    def identity(value):return tuple(getattr(value,key) for key in fields)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    with os.fdopen(fd,'rb') as source:
        require(identity(os.fstat(source.fileno()))==identity(info));raw=source.read(maximum+1)
        require(len(raw)==info.st_size and identity(os.fstat(source.fileno()))==identity(info)
            and identity(path.lstat())==identity(info))
    return raw,identity(info)


class Loaded:
    """Retain code identities only; re-read after comparison, before effects."""
    def __init__(self,directory):
        root_owner();self.directory=Path(directory)
        names=('path_body_probe.py','path_body_source.py','path-body-build.py',
            'pathlib-original.py','path-body-donor.pyx','manifest.json',extension_name())
        self.files={name:_read_owned(self.directory/name,8388608 if name==extension_name() else 262144)
            for name in names}
        raw={name:value[0] for name,value in self.files.items()}
        self.hashes={name:hashlib.sha256(value).hexdigest() for name,value in raw.items()}
        require(self.hashes['path_body_probe.py']==hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        import path_body_source
        require(self.hashes['path_body_source.py']==hashlib.sha256(Path(path_body_source.__file__).read_bytes()).hexdigest())
        builder=ast.parse(raw['path-body-build.py'])
        literals={item.targets[0].id:ast.literal_eval(item.value) for item in builder.body
            if isinstance(item,ast.Assign) and len(item.targets)==1 and isinstance(item.targets[0],ast.Name)
            and item.targets[0].id in {'HEADER','DIRECTIVES','WHEEL_SHA256','WHEEL_BYTES'}}
        require(set(literals)=={'HEADER','DIRECTIVES','WHEEL_SHA256','WHEEL_BYTES'})
        self.manifest=json.loads(raw['manifest.json']);manifest=self.manifest
        original=raw['pathlib-original.py'].decode('utf-8');body,expected=select_source(original)
        for key,value in expected.items():
            require(manifest[key]==(True if key=='compiled' else value))
        require(manifest['compiler_version']=='3.1.8' and manifest['compiler_wheel_sha256']==literals['WHEEL_SHA256']
            and manifest['compiler_wheel_bytes']==literals['WHEEL_BYTES']
            and manifest['compiler_directives']==literals['DIRECTIVES']
            and manifest['python_version']==sys.version.split()[0]
            and manifest['runtime_verified'] is False and manifest['production_adopted'] is False)
        require(raw['path-body-donor.pyx']==(literals['HEADER']+body).encode()
            and manifest['donor_source_sha256']==self.hashes['path-body-donor.pyx']
            and manifest['elf_sha256']==self.hashes[extension_name()])
        runtime_source,runtime_identity=_read_owned(Path(pathlib.__file__),262144)
        require(runtime_source==raw['pathlib-original.py'])
        self.runtime_identity=runtime_identity
        compiled=compile(original,pathlib.__file__,'exec')
        self.original_codes={}
        for owner,names in TARGETS.items():
            class_code=next(item for item in compiled.co_consts if isinstance(item,types.CodeType) and item.co_name==owner)
            for name in names:
                code=next(item for item in class_code.co_consts if isinstance(item,types.CodeType) and item.co_name==name)
                self.original_codes[owner,name]=code
        require('_path_body_probe' not in sys.modules)
        spec=importlib.util.spec_from_file_location('_path_body_probe',self.directory/extension_name())
        self.native=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.native)
        require(callable(self.native.bind_original));self.validate()

    def validate(self):
        root_owner()
        for name,expected in self.files.items():require(_read_owned(self.directory/name,
            8388608 if name==extension_name() else 262144)==expected)
        raw,identity=_read_owned(Path(pathlib.__file__),262144)
        require(identity==self.runtime_identity and raw==self.files['pathlib-original.py'][0])

    def evidence(self):
        return {'source_hashes':self.hashes,'compiler_version':'3.1.8',
            'compiler_wheel_sha256':self.manifest['compiler_wheel_sha256'],
            'original_stdlib_sha256':self.manifest['original_source_sha256'],
            'live_global_loads':self.manifest['live_global_loads'],'bodies':self.manifest['bodies']}


def function(raw):
    if type(raw) is classmethod:return raw.__func__
    if type(raw) is property:
        require(raw.fget is not None and raw.fset is None and raw.fdel is None);return raw.fget
    return raw


class Adapter:
    def __init__(self,module,native,*,original_codes=None,owner_check=None):
        self.module=module;self.native=native;self.owner_check=root_owner if owner_check is None else owner_check
        self.owner_check();self.owner=(os.getpid(),threading.get_ident())
        self.classes={name:getattr(module,name) for name in TARGETS};self.entries=[]
        self.calls=0;self.active=False;self.broken=False;builtin_dict=None
        for owner,names in TARGETS.items():
            original_class=self.classes[owner];donor=getattr(native,owner)
            require(original_class is not donor)
            for name in names:
                original=vars(original_class)[name];replacement=vars(donor)[name]
                require(type(original) in {types.FunctionType,classmethod,property})
                require(type(replacement) is type(original) if type(original) in {classmethod,property}
                    else callable(replacement) and hasattr(replacement,'__get__'))
                old_function=function(original);new_function=function(replacement)
                require(type(old_function) is types.FunctionType and callable(new_function)
                    and old_function.__globals__ is vars(module))
                if original_codes is not None:require(old_function.__code__==original_codes[owner,name])
                if builtin_dict is None:builtin_dict=old_function.__builtins__
                require(old_function.__builtins__ is builtin_dict)
                if (owner,name)==('Path','resolve'):
                    def count(body,old):
                        @wraps(old)
                        def counted(subject,*args,**kwargs):
                            self.calls+=1;require(self.calls<=10000000)
                            return body(subject,*args,**kwargs)
                        return counted
                    replacement=count(new_function,old_function)
                self.entries.append((original_class,name,original,replacement))
        require(len(self.entries)==20 and type(builtin_dict) is dict)
        require(native.bind_original(vars(module),builtin_dict) is True)

    def check(self):
        self.owner_check();require(self.owner==(os.getpid(),threading.get_ident()) and not self.broken)
        require(all(getattr(self.module,name) is value for name,value in self.classes.items()))

    def restored(self):return all(vars(owner)[name] is original for owner,name,original,_new in self.entries)

    @contextmanager
    def installed(self):
        self.check();require(not self.active and self.restored());changed=[];self.active=True
        try:
            for owner,name,original,replacement in self.entries:
                changed.append((owner,name,original));setattr(owner,name,replacement)
            yield
            self.check()
            require(all(vars(owner)[name] is replacement for owner,name,_old,replacement in self.entries))
        finally:
            pending=sys.exception();errors=[]
            for owner,name,original in reversed(changed):
                try:setattr(owner,name,original)
                except BaseException as error:errors.append(error)
            self.active=False
            self.broken=bool(errors) or not self.restored()
            if pending is None:require(not self.broken)


def compare_guard(loaded,original_guard,stage):
    root_owner();require(stage.usable and stage.state=='ready' and sys.getprofile() is None)
    monitoring=getattr(sys,'monitoring',None)
    require(monitoring is None or monitoring.get_tool(monitoring.PROFILER_ID) is None)
    adapter=Adapter(pathlib,loaded.native,original_codes=loaded.original_codes)
    rows=[];started=time.monotonic_ns()
    for number in range(20):
        values={};elapsed={}
        for selected in ((0,1) if number%2==0 else (1,0)):
            adapter.check();require(stage.usable and stage.state=='ready');calls=adapter.calls
            if selected:
                with adapter.installed():
                    before=time.monotonic_ns()
                    try:values[selected]=original_guard(stage)
                    finally:elapsed[selected]=max(0,time.monotonic_ns()-before)
            else:
                before=time.monotonic_ns()
                try:values[selected]=original_guard(stage)
                finally:elapsed[selected]=max(0,time.monotonic_ns()-before)
            require(adapter.restored() and stage.usable and stage.state=='ready')
            require(adapter.calls>calls if selected else adapter.calls==calls)
        require(values[0]==values[1])
        require(all(type(value) is int and 0<=value<=1200000000000 for value in elapsed.values()))
        rows.append({'baseline_us':elapsed[0]//1000,'prototype_us':elapsed[1]//1000})
    loaded.validate();adapter.check();require(adapter.restored())
    return {'diagnostic_only':True,'production_adopted':False,'pairs':rows,
        'original_descriptors_restored':True,'original_classes_retained':True,
        'observations_equal':True,'same_original_actors':True,'observation_results_retained':False,
        'compiled_bodies':20,'compiled_resolve_calls':adapter.calls,
        'elapsed_ms':min(1200000,max(0,(time.monotonic_ns()-started)//1000000)),**loaded.evidence()}


class AtFirstGuard:
    def __init__(self,loaded,stage_owner,measurements):
        self.loaded=loaded;self.stage_owner=stage_owner;self.measurements=measurements
        self.original=vars(stage_owner)['check'];self.entered=False;self.attempted=False;self.result=None

    def __enter__(self):
        require(callable(self.original))
        def first(stage,*args,**kwargs):
            try:
                require(not self.attempted and not args and not kwargs);self.attempted=True
                self.result=compare_guard(self.loaded,self.original,stage)
                self.stage_owner.check=self.original
                self.measurements.__enter__();self.entered=True
                return self.stage_owner.check(stage)
            except BaseException:
                stage.usable=False;stage.allocation.usable=False
                for close in (stage.close,stage.allocation.close):
                    try:close()
                    except BaseException:pass
                raise
        self.stage_owner.check=first;return self

    def __exit__(self,*_):
        try:
            if self.entered:self.measurements.__exit__(None,None,None)
        finally:self.stage_owner.check=self.original
