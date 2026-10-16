"""Hosted read-only lexical join comparison; no observation results retained."""
import ast
from collections import OrderedDict
from contextlib import contextmanager
import hashlib
import inspect
import os
from pathlib import Path
import pathlib
import stat
import sys
import threading
import time
import types

from immutable_path_probe import MODULE_NAMES, PathFactory


def require(value):
    if not value:raise ValueError('Lexical path diagnostic invariant')


def root_owner():
    require(sys.platform=='linux' and sys.version_info[:2]==(3,12)
        and os.getuid()==os.geteuid()==os.getgid()==os.getegid()==0)


def _read_owned(path):
    path=Path(path);require(path.is_absolute() and path.anchor=='/' and '..' not in path.parts)
    for parent in path.parents:
        value=parent.lstat()
        require(stat.S_ISDIR(value.st_mode) and value.st_uid==value.st_gid==0 and not value.st_mode & 0o022)
    fields=('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_mode','st_uid','st_gid','st_nlink')
    identity=lambda value:tuple(getattr(value,name) for name in fields)
    info=path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid==info.st_gid==0 and info.st_nlink==1
        and not info.st_mode & 0o022 and 0<info.st_size<=262144)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    with os.fdopen(fd,'rb') as source:
        require(identity(os.fstat(source.fileno()))==identity(info));raw=source.read(262145)
        require(len(raw)==info.st_size and identity(os.fstat(source.fileno()))==identity(info)
            and identity(path.lstat())==identity(info))
    return raw,identity(info)


def sdk_code(raw,filename):
    require(type(raw) is bytes and 0<len(raw)<=262144)
    tree=ast.parse(raw);require(sum(1 for _ in ast.walk(tree))<=30000)
    owners=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='PurePath'];require(len(owners)==1)
    methods=[n for n in owners[0].body if isinstance(n,ast.FunctionDef) and n.name=='with_segments'];require(len(methods)==1)
    method=methods[0]
    expected=ast.parse('def with_segments(self, *pathsegments):\n return type(self)(*pathsegments)\n').body[0]
    body=ast.FunctionDef(name=method.name,args=method.args,body=[n for n in method.body
        if not (isinstance(n,ast.Expr) and isinstance(n.value,ast.Constant) and type(n.value.value) is str)],
        decorator_list=method.decorator_list,returns=method.returns,type_comment=method.type_comment,
        type_params=method.type_params)
    require(ast.dump(body)==ast.dump(expected))
    code=compile(raw,filename,'exec')
    original_codes={(owner.co_name,method.co_name):method for owner in code.co_consts
        if isinstance(owner,types.CodeType) and owner.co_name in {'PurePath','Path','PurePosixPath','PureWindowsPath','PosixPath','WindowsPath'}
        for method in owner.co_consts if isinstance(method,types.CodeType)}
    require(('PurePath','with_segments') in original_codes)
    return original_codes,hashlib.sha256(ast.dump(expected).encode()).hexdigest()


class Loaded:
    """Authenticate the actual SDK body and retained diagnostic code."""
    def __init__(self,directory):
        root_owner();self.directory=Path(directory)
        import immutable_path_probe
        imported={'lexical_path_probe.py':Path(__file__),
            'immutable_path_probe.py':Path(immutable_path_probe.__file__)}
        self.files={name:_read_owned(self.directory/name) for name in imported}
        require(all(value[0]==imported[name].read_bytes() for name,value in self.files.items()))
        self.sdk_path=Path(pathlib.__file__);self.sdk=_read_owned(self.sdk_path)
        self.original_codes,self.body_hash=sdk_code(self.sdk[0],str(self.sdk_path))
        self.original_code=self.original_codes['PurePath','with_segments'];self.validate()

    def validate(self):
        root_owner()
        require(all(_read_owned(self.directory/name)==value for name,value in self.files.items()))
        require(_read_owned(self.sdk_path)==self.sdk)

    def evidence(self):
        return {'source_hashes':{name:hashlib.sha256(value[0]).hexdigest() for name,value in self.files.items()},
            'original_stdlib_sha256':hashlib.sha256(self.sdk[0]).hexdigest(),'with_segments_ast_sha256':self.body_hash}


class JoinPlans:
    """Bounded lexical values only; metadata methods always remain original."""
    def __init__(self,original,classes):
        self.original=original;self.classes=tuple(classes);self.cache=OrderedDict()
        self.owner=(os.getpid(),threading.get_ident())
        self.calls=0;self.hits=0;self.constructed=0

    def __call__(self,subject,*segments,**keywords):
        self.calls+=1;require(self.calls<=10000000)
        key=None
        if (self.owner==(os.getpid(),threading.get_ident()) and not keywords
                and type(subject) in self.classes and 0<len(segments)<=64):
            parts=[];length=0;components=0
            for item in segments:
                if type(item) is str:raw=(item,)
                elif type(item) in self.classes and type(item._raw_paths) is list:raw=tuple(item._raw_paths)
                else:break
                if not (0<len(raw)<=64 and all(type(value) is str for value in raw)):break
                length+=sum(len(value) for value in raw);components+=len(raw)
                if length>1024 or components>64:break
                parts.append((type(item),raw))
            else:key=(type(subject),tuple(parts))
        if key is not None and key in self.cache:
            self.hits+=1;self.cache.move_to_end(key);return self.cache[key]
        value=self.original(subject,*segments,**keywords);self.constructed+=1
        if key is not None and type(value) is type(subject) and len(str(value))<=1024 and len(value.parts)<=64:
            self.cache[key]=value
            if len(self.cache)>256:self.cache.popitem(last=False)
        return value

    def values(self):
        return {'join_calls':self.calls,'join_hits':self.hits,'join_constructed':self.constructed,
            'retained_join_plans':len(self.cache)}


class Adapter:
    def __init__(self,modules,*,loaded=None,owner_check=None):
        self.owner_check=root_owner if owner_check is None else owner_check;self.owner_check()
        self.owner=(os.getpid(),threading.get_ident());self.modules=tuple(modules)
        require(tuple(module.__name__ for module in self.modules)==MODULE_NAMES)
        require(all(module.Path is Path for module in self.modules))
        self.path_owner=pathlib.PurePath;self.original=vars(self.path_owner)['with_segments']
        require(type(self.original) is types.FunctionType and self.original.__globals__ is vars(pathlib))
        if loaded is not None:require(self.original.__code__==loaded.original_code)
        self.namespace=tuple(vars(pathlib).items())
        self.builtins=self.original.__builtins__;self.builtin_values=tuple(self.builtins.items())
        classes=(type(Path('/')),pathlib.PurePosixPath,pathlib.PureWindowsPath)
        self.roles=tuple((owner,name,inspect.getattr_static(owner,name)) for owner in
            {pathlib.PurePath,pathlib.Path,*classes} for name in ('__init__','__new__','_flavour','_parse_path','_from_parsed_parts'))
        if loaded is not None:
            for _owner,_name,raw in self.roles:
                value=raw.__func__ if type(raw) in {classmethod,staticmethod} else raw
                if type(value) is types.FunctionType:
                    require(value.__globals__ is vars(pathlib) and value.__code__==loaded.original_codes[
                        value.__qualname__.split('.')[0],value.__name__])
        self.fspath=pathlib.os.fspath
        self.factory=PathFactory();self.joins=JoinPlans(self.original,classes)
        joins=self.joins
        def with_segments(subject,*segments,**keywords):return joins(subject,*segments,**keywords)
        self.replacement=with_segments;self.active=False;self.broken=False

    def check(self):
        self.owner_check();require(not self.broken and self.owner==(os.getpid(),threading.get_ident()))
        require(len(vars(pathlib))==len(self.namespace) and all(vars(pathlib).get(name) is value for name,value in self.namespace))
        require(len(self.builtins)==len(self.builtin_values) and all(self.builtins.get(name) is value for name,value in self.builtin_values))
        require(pathlib.os.fspath is self.fspath and all(inspect.getattr_static(owner,name) is value for owner,name,value in self.roles))

    def restored(self):
        return vars(self.path_owner).get('with_segments') is self.original and all(vars(module).get('Path') is Path for module in self.modules)

    @contextmanager
    def installed(self):
        self.check();require(not self.active and self.restored());self.active=True;changed=[]
        try:
            changed.append((self.path_owner,'with_segments',self.original))
            setattr(self.path_owner,'with_segments',self.replacement)
            for module in self.modules:
                changed.append((module,'Path',Path));setattr(module,'Path',self.factory)
            yield
            self.check()
            require(vars(self.path_owner)['with_segments'] is self.replacement
                and all(module.Path is self.factory for module in self.modules))
        finally:
            pending=sys.exception();errors=[]
            for owner,name,original in reversed(changed):
                try:setattr(owner,name,original)
                except BaseException as error:errors.append(error)
            self.active=False;self.broken=bool(errors) or not self.restored()
            if pending is None:require(not self.broken)

    def clear(self):
        self.factory.cache.clear();self.joins.cache.clear()


def compare_guard(loaded,modules,original_guard,stage):
    root_owner();require(stage.usable and stage.state=='ready' and sys.getprofile() is None)
    monitoring=getattr(sys,'monitoring',None)
    require(monitoring is None or monitoring.get_tool(monitoring.PROFILER_ID) is None)
    adapter=Adapter(modules,loaded=loaded);rows=[];started=time.monotonic_ns()
    try:
        for number in range(20):
            values={};elapsed={}
            for selected in ((0,1) if number%2==0 else (1,0)):
                adapter.check();require(stage.usable and stage.state=='ready');calls=adapter.joins.calls
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
                require(adapter.joins.calls>calls if selected else adapter.joins.calls==calls)
            require(values[0]==values[1])
            require(all(type(value) is int and 0<=value<=1200000000000 for value in elapsed.values()))
            rows.append({'baseline_us':elapsed[0]//1000,'prototype_us':elapsed[1]//1000})
        loaded.validate();adapter.check();require(adapter.restored() and adapter.joins.hits>0)
        return {'diagnostic_only':True,'production_adopted':False,'pairs':rows,'original_classes_retained':True,
            'original_descriptors_restored':True,'module_symbols_restored':True,'same_original_actors':True,
            'observations_equal':True,'observation_results_retained':False,**adapter.factory.values(),**adapter.joins.values(),
            'elapsed_ms':min(1200000,max(0,(time.monotonic_ns()-started)//1000000)),**loaded.evidence()}
    finally:adapter.clear()


class AtFirstGuard:
    def __init__(self,loaded,modules,stage_owner,measurements):
        self.loaded=loaded;self.modules=modules;self.stage_owner=stage_owner;self.measurements=measurements
        self.original=vars(stage_owner)['check'];self.entered=False;self.attempted=False;self.result=None

    def __enter__(self):
        require(callable(self.original))
        def first(stage,*args,**keywords):
            try:
                require(not self.attempted and not args and not keywords);self.attempted=True
                self.result=compare_guard(self.loaded,self.modules,self.original,stage)
                self.stage_owner.check=self.original;self.measurements.__enter__();self.entered=True
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
