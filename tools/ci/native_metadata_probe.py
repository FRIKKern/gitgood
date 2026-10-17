"""Hosted-only fresh native metadata lane; no production import or adoption."""
import ast
import builtins
import cProfile
from contextlib import contextmanager
from functools import wraps
import hashlib
import importlib
import importlib.util
import json
import math
import os
from pathlib import Path
import pathlib
import pstats
import stat
import sys
import sysconfig
import threading
import time
import types

from path_body_probe import _read_owned,root_owner

MODULE_NAMES=('native_service_scope','native_durable_binding',
    'native_generation_lease_guard','native_root_lifecycle')
HELPERS=('native-metadata-probe.c','native_metadata_probe.py','native-metadata-build.py',
    'path_body_probe.py','path_body_source.py')
FAMILIES=('root_files','executables','persistent','custody')


def require(value):
    if not value:raise ValueError('Native metadata diagnostic invariant')


def extension_name():
    suffix=sysconfig.get_config_var('EXT_SUFFIX')
    require(type(suffix) is str and '/' not in suffix and suffix.endswith('.so'))
    return '_native_metadata_probe'+suffix


def functions(code):
    found={code.co_qualname:code}
    for value in code.co_consts:
        if isinstance(value,types.CodeType):found.update(functions(value))
    return found


def raw_function(value):
    if type(value) is types.MethodType:return value.__func__
    if type(value) in {staticmethod,classmethod}:return value.__func__
    if type(value) is property:return value.fget
    return value


class Loaded:
    def __init__(self,directory):
        root_owner();self.directory=Path(directory)
        names=(*HELPERS,'manifest.json',extension_name())
        self.files={name:_read_owned(self.directory/name,16777216 if name==extension_name() else 262144)
            for name in names}
        self.hashes={name:hashlib.sha256(value[0]).hexdigest() for name,value in self.files.items()}
        import path_body_probe,path_body_source
        for module in (sys.modules[__name__],path_body_probe,path_body_source):
            require(self.hashes[Path(module.__file__).name]==hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest())
        self.manifest=json.loads(self.files['manifest.json'][0])
        builder=ast.parse(self.files['native-metadata-build.py'][0])
        flags=ast.literal_eval(next(node.value for node in builder.body if isinstance(node,ast.Assign)
            and any(isinstance(target,ast.Name) and target.id=='FLAGS' for target in node.targets)))
        require(flags==('-shared','-fPIC','-O2','-std=c11','-Wall','-Wextra','-Werror'))
        require(self.manifest=={'protocol':1,'compiler':'system-cc','compiler_flags':list(flags),'python_version':sys.version.split()[0],
            'c_sha256':self.hashes['native-metadata-probe.c'],'elf_sha256':self.hashes[extension_name()],
            'production_adopted':False})
        self.modules=tuple(importlib.import_module(name) for name in MODULE_NAMES)
        self.runtime_files={}
        # Authenticate every original Python helper admitted below, including
        # imported helpers, from its actual Root-owned source and code object.
        self.code_sources={}
        candidates=[]
        for module in self.modules:
            for value in vars(module).values():
                if type(value) is types.FunctionType:candidates.append(value)
                if type(getattr(value,'__wrapped__',None)) is types.FunctionType:candidates.append(value.__wrapped__)
            for name in ('_CapturedRootFiles','_CapturedExecutableDigests','_PersistentFingerprintPlan','_RootReadOnlyCustody'):
                owner=vars(module).get(name)
                if type(owner) is type:
                    for value in vars(owner).values():
                        fn=raw_function(value)
                        if type(fn) is types.FunctionType:
                            candidates.append(fn)
                            if type(getattr(fn,'__wrapped__',None)) is types.FunctionType:candidates.append(fn.__wrapped__)
        for owner in (pathlib.Path,pathlib.PurePath):
            for value in vars(owner).values():
                fn=raw_function(value)
                if type(fn) is types.FunctionType:candidates.append(fn)
        identity=self.modules[3].directory_identity
        if type(identity) is types.FunctionType:
            helper=identity.__globals__.get('require')
            if type(helper) is types.FunctionType:candidates.append(helper)
        for fn in candidates:
            path=Path(fn.__code__.co_filename)
            if path not in self.runtime_files:
                raw,identity=_read_owned(path,262144);self.runtime_files[path]=(raw,identity)
                self.code_sources[path]=functions(compile(raw,str(path),'exec'))
            require(fn.__code__==self.code_sources[path].get(fn.__code__.co_qualname))
        self.original_codes={id(fn):fn.__code__ for fn in candidates}
        self.original_functions=tuple(candidates)
        require('_native_metadata_probe' not in sys.modules)
        spec=importlib.util.spec_from_file_location('_native_metadata_probe',self.directory/extension_name())
        self.native=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.native)
        require(all(callable(getattr(self.native,name)) for name in
            ('fingerprint','persistent','custody','same_bindings','counts')))
        self.validate()

    def validate(self):
        root_owner()
        for fn in self.original_functions:require(fn.__code__==self.original_codes[id(fn)])
        for name,expected in self.files.items():require(_read_owned(self.directory/name,
            16777216 if name==extension_name() else 262144)==expected)
        for path,expected in self.runtime_files.items():require(_read_owned(path,262144)==expected)

    def evidence(self):
        return {'source_hashes':self.hashes,'original_source_hashes':{
            path.name:hashlib.sha256(value[0]).hexdigest() for path,value in self.runtime_files.items()},
            'compiler':'system-cc','compiler_flags':self.manifest['compiler_flags']}


class Unsupported(Exception):pass


class Adapter:
    def __init__(self,modules,native,*,owner_check=None,original_codes=None,_class_owners=False):
        self.modules=tuple(modules);require(tuple(module.__name__ for module in self.modules)==MODULE_NAMES)
        self.service,self.binding,self.generation,self.lifecycle=self.modules
        self.native=native;self.owner_check=root_owner if owner_check is None else owner_check
        self.owner_check();self.owner=(os.getpid(),threading.get_ident())
        self.path_type=type(Path('/'));self.active=False;self.broken=False
        self.calls={name:0 for name in FAMILIES};self.fallbacks={name:0 for name in FAMILIES}
        service_owner=self.service._CapturedRootFiles;executable_owner=self.binding._CapturedExecutableDigests
        plan_owner=self.generation._PersistentFingerprintPlan;custody_owner=self.lifecycle._RootReadOnlyCustody
        self.owners=(service_owner,executable_owner,plan_owner,custody_owner)
        originals=(vars(service_owner)['_fingerprint'],vars(executable_owner)['_fingerprint'],
            vars(plan_owner)['read'],vars(custody_owner)['check'])
        require(type(originals[0]) is type(originals[1]) is staticmethod)
        self.originals=originals
        if original_codes is not None:
            for raw in originals:
                fn=raw_function(raw)
                require(id(fn) in original_codes and fn.__code__==original_codes[id(fn)])
                if hasattr(fn,'__wrapped__'):
                    require(id(fn.__wrapped__) in original_codes and fn.__wrapped__.__code__==original_codes[id(fn.__wrapped__)])
        self.bindings=[]
        def capture(owner,names):
            namespace=vars(owner)
            target=owner if _class_owners and isinstance(owner,type) else namespace
            for name in names:
                require(name in namespace);self.bindings.append((target,name,namespace[name]))
        for module,names in (
                (self.service,('Path','os','stat','require','_root_file_path','_root_file_parents','_root_file_parent_plan','_CapturedRootFiles')),
                (self.binding,('Path','os','stat','require','_CapturedExecutableDigests')),
                (self.generation,('Path','stat','require','_PersistentFingerprintPlan')),
                (self.lifecycle,('Path','os','stat','require','root_owner','private_directory','directory_identity','_within_root_observation_pass','_RootReadOnlyCustody'))):
            capture(module,names)
        capture(custody_owner,('_file','_names','_directory_metadata'))
        capture(pathlib,('os','Path','PurePath','PosixPath','WindowsPath'))
        for name in ('stat','lstat','resolve','iterdir','__init__','__new__','__str__','__fspath__',
                'name','parent','parents','parts','anchor','is_absolute','with_segments','_parse_path',
                '_load_parts','_from_parsed_parts','_format_parsed_parts','_flavour'):
            self.bindings.append((self.path_type,name,getattr(self.path_type,name)))
        identity=self.lifecycle.directory_identity
        if type(identity) is types.FunctionType:
            for name in ('require','stat'):
                if name in identity.__globals__:
                    self.bindings.append((identity.__globals__,name,identity.__globals__[name]))
        capture(pathlib.Path,('stat','lstat','resolve','iterdir','__init__','__new__'))
        capture(pathlib.PurePath,('__init__','__str__','__fspath__','name','parent','parents','parts','anchor','is_absolute',
            'with_segments','_parse_path','_load_parts','_from_parsed_parts','_format_parsed_parts','_flavour'))
        capture(os,('stat','lstat','fstat','listdir','scandir','fspath','getuid','geteuid','getgid','getegid','getpid'))
        capture(stat,('S_ISDIR','S_ISREG','S_IMODE'))
        capture(builtins,('type','str','tuple','list','dict','set','frozenset','len','getattr','all','any'))
        # A function can keep its identity while its code changes. Admit both
        # the live namespace binding and the original Python code object.
        functions_by_id={}
        for value in (*originals,*(expected for _owner,_name,expected in self.bindings)):
            fn=raw_function(value)
            for candidate in (fn,getattr(fn,'__wrapped__',None)):
                if type(candidate) is types.FunctionType:functions_by_id[id(candidate)]=candidate
        self.bindings.extend((fn,'__code__',fn.__code__) for fn in functions_by_id.values())
        require(len(self.bindings)<=256)
        self.bindings=tuple(self.bindings)
        original_root=originals[0].__func__;original_exec=originals[1].__func__
        original_plan=originals[2];original_custody=originals[3]
        require(type(original_custody) is types.FunctionType and hasattr(original_custody,'__wrapped__'))
        self.original_custody_body=original_custody.__wrapped__
        self.names_callback=raw_function(vars(custody_owner)['_names'])
        self.identities={name:getattr(self.modules[index],name) for index,name in
            enumerate(('_CapturedRootFiles','_CapturedExecutableDigests','_PersistentFingerprintPlan','_RootReadOnlyCustody'))}

        def fallback(family,fn,*args,**kwargs):
            self.fallbacks[family]+=1;require(self.fallbacks[family]<=10000000)
            return fn(*args,**kwargs)

        @wraps(original_root)
        def root_files(path,maximum,executable):
            if not self.eligible('root_files') or type(path) not in {str,self.path_type} or type(maximum) is not int or not 0<maximum<2**63 or type(executable) is not bool:
                return fallback('root_files',original_root,path,maximum,executable)
            path=self.service._root_file_path(path)
            if len(str(path))>8192 or len(path.parts)>64:return fallback('root_files',original_root,path,maximum,executable)
            parents=tuple(name for _parent,name in self.service._root_file_parents(path))
            self.count('root_files');value=native.fingerprint(str(path),parents,maximum,executable)
            self.service.require(value is not None);self.after('root_files');return value

        @wraps(original_exec)
        def executables(raw):
            if not self.eligible('executables') or type(raw) not in {str,self.path_type}:return fallback('executables',original_exec,raw)
            path=self.binding.Path(raw).resolve(strict=True)
            if len(str(path))>8192 or len(path.parts)>64:return fallback('executables',original_exec,raw)
            self.count('executables')
            value=native.fingerprint(str(path),tuple(str(parent) for parent in path.parents),268435456,True)
            self.binding.require(value is not None);self.after('executables')
            return str(path),value[0],value[1]

        @wraps(original_plan)
        def persistent(subject):
            if not self.eligible('persistent') or type(subject) is not plan_owner:return fallback('persistent',original_plan,subject)
            try:arguments=self.plan_arguments(subject)
            except (Unsupported,AttributeError):return fallback('persistent',original_plan,subject)
            before=native.counts();value=native.persistent(*arguments,os.listdir)
            if value is NotImplemented:
                require(native.counts()==before);return fallback('persistent',original_plan,subject)
            self.count('persistent');self.generation.require(value is not None);self.after('persistent');return value

        @wraps(self.original_custody_body)
        def custody(subject):
            if not self.eligible('custody') or type(subject) is not custody_owner or any(
                    key in vars(subject) for key in ('_file','_names','_directory_metadata')):
                return fallback('custody',self.original_custody_body,subject)
            if vars(subject).get('usable') is not True or vars(subject).get('owner')!=self.owner:
                return fallback('custody',self.original_custody_body,subject)
            try:arguments=self.custody_arguments(subject)
            except (Unsupported,AttributeError):return fallback('custody',self.original_custody_body,subject)
            self.lifecycle.require(subject.usable and self.lifecycle.root_owner()==subject.owner)
            self.lifecycle.require(self.lifecycle.private_directory(subject.root,subject.uid,subject.gid)==subject.root_custody)
            before=native.counts();value=native.custody(*arguments,self.names_callback)
            if value is NotImplemented:
                # Argument preflight did not observe native metadata. The
                # original body must not repeat private_directory: preflight
                # is completed before any original observation below.
                raise ValueError('Admitted custody arguments were unsupported')
            require(native.counts()!=before);self.count('custody')
            self.lifecycle.require(value is True);self.after('custody')

        wrapped_custody=self.lifecycle._within_root_observation_pass(custody)
        self.entries=((service_owner,'_fingerprint',originals[0],staticmethod(root_files)),
            (executable_owner,'_fingerprint',originals[1],staticmethod(executables)),
            (plan_owner,'read',original_plan,persistent),(custody_owner,'check',original_custody,wrapped_custody))

    def count(self,name):
        self.calls[name]+=1;require(self.calls[name]<=10000000)

    def eligible(self,family=None):
        return self.native.same_bindings(self.bindings,*self.owner)

    def after(self,family=None):
        # A failed admission after native observations is a refusal, never a
        # reason to retry through Python.
        require(self.eligible(family))

    def path(self,value):
        if type(value) is not self.path_type:raise Unsupported()
        return str(value)

    @staticmethod
    def exact(value,kind):
        if type(value) is not kind:raise Unsupported()
        return value

    def plan_arguments(self,subject):
        exact=self.exact
        uid=exact(subject.uid,int);entries=exact(subject.entries,tuple);dirs=exact(subject.directories,tuple)
        files=exact(subject.files,tuple);parents=exact(subject.parents,tuple)
        if len(entries)>16 or len(dirs)>64 or len(files)>64 or len(parents)>256:raise Unsupported()
        def entry(row):
            exact(row,tuple)
            if len(row)!=2:raise Unsupported()
            names=exact(row[1],frozenset)
            if len(names)>1024 or any(type(name) is not str for name in names):raise Unsupported()
            return self.path(row[0]),tuple(names)
        def directory(row):
            exact(row,tuple)
            if len(row)!=5:raise Unsupported()
            return self.path(row[0]),*row[1:]
        def file(row):
            exact(row,tuple)
            if len(row)!=7:raise Unsupported()
            return self.path(row[0]),*row[1:]
        def parent(row):
            exact(row,tuple)
            if len(row)!=4:raise Unsupported()
            return self.path(row[0]),*row[1:]
        return uid,tuple(map(entry,entries)),tuple(map(directory,dirs)),self.path(subject.machine),tuple(map(file,files)),tuple(map(parent,parents))

    def custody_arguments(self,subject):
        exact=self.exact;uid=exact(subject.uid,int);gid=exact(subject.gid,int)
        self.path(subject.root);self.path(subject.directory);self.path(subject.lock_path)
        directories=exact(subject.directories,dict);known=exact(subject.known,dict);retained=exact(subject.retained,dict)
        entries=subject.entries;metadata=exact(subject.directory_metadata,dict)
        if entries is not None:exact(entries,dict)
        if len(directories)>256 or len(known)>1024:raise Unsupported()
        rows=[];leaves=[]
        for path,item in directories.items():
            self.path(path);exact(item,tuple)
            if len(item)!=2:raise Unsupported()
            fd,original=item
            if type(fd) is not int or not 0<=fd<=2147483647 or type(original) is not tuple or len(original)!=7:raise Unsupported()
            parent=None if path==subject.directory else directories.get(path.parent)
            if path!=subject.directory and (type(parent) is not tuple or len(parent)!=2):raise Unsupported()
            extra=None if entries is None else metadata.get(path)
            names=None if entries is None else entries.get(path)
            if entries is not None and (type(extra) is not tuple or len(extra)!=9 or type(names) is not list):raise Unsupported()
            rows.append((str(path) if parent is None else path.name,None if parent is None else parent[0],fd,original,extra,names))
        for path,original in known.items():
            self.path(path);parent=directories.get(path.parent)
            if type(parent) is not tuple or len(parent)!=2:raise Unsupported()
            if path in retained and retained[path] is None:raise Unsupported()
            leaves.append((path.name,parent[0],original,retained.get(path)))
        lock=None if subject.lock is None else (subject.lock,known.get(subject.lock_path))
        # Validate the full finite schema before the first private_directory
        # observation. This must agree with the native preflight.
        def integer(value,signed=False):
            return type(value) is int and (-(2**63)<=value<2**63 if signed else 0<=value<2**64)
        def stats(value,directory=False):
            count=7 if directory else 9
            return type(value) is tuple and len(value)==count and all(integer(v,i>=(5 if directory else 6)) for i,v in enumerate(value))
        def fd(value):return type(value) is int and 0<=value<=2147483647
        if not integer(uid) or not integer(gid):raise Unsupported()
        for name,parent,held,original,extra,names in rows:
            if len(name)>8192 or parent is not None and not fd(parent) or not stats(original,True):raise Unsupported()
            if extra is not None and (not stats(extra) or len(names)>1024 or any(type(x) is not str for x in names)):raise Unsupported()
        for name,parent,original,held in leaves:
            if len(name)>8192 or not fd(parent) or not stats(original) or held is not None and not fd(held):raise Unsupported()
        if lock is not None and (not fd(lock[0]) or not stats(lock[1])):raise Unsupported()
        return uid,gid,tuple(rows),tuple(leaves),lock

    def check(self):
        self.owner_check();require(self.owner==(os.getpid(),threading.get_ident()) and not self.broken)
        require(all(getattr(module,name) is self.identities[name] for module,name in zip(self.modules,self.identities)))

    def restored(self):return all(vars(owner).get(name) is old for owner,name,old,_ in self.entries)

    @contextmanager
    def installed(self):
        self.check();require(not self.active and self.restored());self.active=True;changed=[]
        try:
            for owner,name,old,new in self.entries:
                changed.append((owner,name,old));setattr(owner,name,new)
            yield
            self.check();require(all(vars(owner).get(name) is new for owner,name,_old,new in self.entries))
        finally:
            pending=sys.exception();errors=[]
            for owner,name,old in reversed(changed):
                try:setattr(owner,name,old)
                except BaseException as error:errors.append(error)
            self.active=False;self.broken=bool(errors) or not self.restored()
            if pending is None:require(not self.broken)


def compare_guard(loaded,original_guard,stage):
    root_owner();require(stage.usable and stage.state=='ready' and sys.getprofile() is None)
    monitoring=getattr(sys,'monitoring',None)
    require(monitoring is None or monitoring.get_tool(monitoring.PROFILER_ID) is None)
    adapter=Adapter(loaded.modules,loaded.native,original_codes=loaded.original_codes)
    rows=[];initial=loaded.native.counts();started=time.monotonic_ns()
    for number in range(20):
        values={};elapsed={}
        for selected in ((0,1) if number%2==0 else (1,0)):
            adapter.check();require(stage.usable and stage.state=='ready');calls=loaded.native.counts()
            if selected:
                with adapter.installed():
                    before=time.monotonic_ns()
                    try:values[selected]=original_guard(stage)
                    finally:elapsed[selected]=max(0,time.monotonic_ns()-before)
            else:
                before=time.monotonic_ns()
                try:values[selected]=original_guard(stage)
                finally:elapsed[selected]=max(0,time.monotonic_ns()-before)
            after=loaded.native.counts()
            require(adapter.restored() and stage.usable and stage.state=='ready')
            require(sum(after.values())>sum(calls.values()) if selected else after==calls)
        require(values[0]==values[1])
        require(all(type(value) is int and 0<=value<=1200000000000 for value in elapsed.values()))
        rows.append({'baseline_us':elapsed[0]//1000,'prototype_us':elapsed[1]//1000})
    loaded.validate();adapter.check();require(adapter.restored())
    counts={name:loaded.native.counts()[name]-initial[name] for name in initial}
    require(set(counts)=={'fingerprint','persistent','custody'} and all(type(value) is int and 0<value<=10000000 for value in counts.values()))
    require(all(value>0 for value in adapter.calls.values()))
    return {'diagnostic_only':True,'production_adopted':False,'pairs':rows,
        'original_descriptors_restored':True,'original_classes_retained':True,
        'observations_equal':True,'same_original_actors':True,'observation_results_retained':False,
        'native_calls':counts,'families':adapter.calls,'fallbacks':adapter.fallbacks,
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


PROFILE_PYTHON=(
    ('Adapter.eligible','eligible'),('Adapter.after','after'),('Adapter.count','count'),
    ('Adapter.path','path'),('Adapter.exact','exact'),('Adapter.plan_arguments','plan_arguments'),
    ('Adapter.custody_arguments','custody_arguments'),
    *((f'Adapter.__init__.<locals>.{name}',name) for name in FAMILIES),
    ('Adapter.__init__.<locals>.fallback','fallback'),
    *((f'Adapter.plan_arguments.<locals>.{name}','plan_'+name) for name in ('entry','directory','file','parent')),
    *((f'Adapter.custody_arguments.<locals>.{name}','custody_'+name) for name in ('integer','stats','fd')))
NATIVE_APIS=('fingerprint','persistent','custody','same_bindings','counts')


def native_profile_codes(native):
    """Identify actual profiler labels using argument preflight, never metadata."""
    require(sys.getprofile() is None)
    monitoring=getattr(sys,'monitoring',None)
    require(monitoring is None or monitoring.get_tool(monitoring.PROFILER_ID) is None)
    before=native.counts();empty=cProfile.Profile();empty.runcall(lambda:None)
    excluded={entry.code for entry in empty.getstats() if type(entry.code) is str}
    result={}
    for name in NATIVE_APIS:
        fn=getattr(native,name)
        require(type(fn) is types.BuiltinFunctionType and fn.__module__=='_native_metadata_probe' and fn.__name__==name)
        profile=cProfile.Profile()
        try:profile.runcall(fn)
        except TypeError:require(name!='counts')
        codes={entry.code for entry in profile.getstats() if type(entry.code) is str}-excluded
        require(len(codes)==1 and native.counts()==before)
        code=codes.pop();require(0<len(code)<=1024 and code not in result);result[code]=name
    return result


def profile_costs(stats,source,native_codes):
    """Closed public labels only. Ignore private/unknown rows without their values."""
    require(type(stats) is dict and type(native_codes) is dict and len(native_codes)==5
        and set(native_codes.values())==set(NATIVE_APIS)
        and all(type(k) is str and 0<len(k)<=1024 for k in native_codes))
    code=functions(compile(source,__file__,'exec'))
    python={(code[name].co_filename,code[name].co_firstlineno,code[name].co_name):label for name,label in PROFILE_PYTHON}
    rows=[]
    for key,value in stats.items():
        if type(key) is not tuple or len(key)!=3:continue
        filename,line,name=key
        if type(filename) is not str or type(line) is not int or type(name) is not str:continue
        if key in python:label='native-metadata-self.py';function=python[key]
        elif filename=='~' and line==0 and name in native_codes:label='native-metadata-api.py';function=native_codes[name]
        else:continue
        require(type(value) is tuple and len(value)==5)
        calls,total,cumulative=value[1:4]
        require(type(calls) is int and 0<=calls<=10000000)
        require(all(type(v) in {int,float} and math.isfinite(v) and 0<=v<=1200 for v in (total,cumulative))
            and total<=cumulative)
        require(0<=line<10000)
        rows.append({'file':label,'function':function,'line':line,'calls':calls,'self_us':int(total*1000000),
            'cumulative_us':int(cumulative*1000000)})
    native_rows=[r for r in rows if r['file']=='native-metadata-api.py']
    python_rows=sorted((r for r in rows if r['file']=='native-metadata-self.py'),
        key=lambda r:(-r['self_us'],-r['cumulative_us'],r['function'],r['line']))[:11]
    return sorted(native_rows+python_rows,key=lambda r:(r['file'],r['function'],r['line']))


class GuardTenSample:
    """Enable metadata only within the existing read-only guard-ten profile."""
    def __init__(self,loaded,sample):
        self.loaded=loaded;self.sample=sample;self.result=None;self.attempted=False;self.active=False
        self.adapter=Adapter(loaded.modules,loaded.native,original_codes=loaded.original_codes)
        self.native_codes=native_profile_codes(loaded.native)

    def __enter__(self):
        require(not self.active and not self.attempted and self.sample.calls==0
            and self.sample.profile is None and not self.sample.completed);self.active=True
        self.had_wrap='wrap' in vars(self.sample);self.raw_wrap=vars(self.sample).get('wrap')
        original_wrap=self.sample.wrap
        def wrap(original):
            checked=original_wrap(original)
            def call(*args,**kwargs):
                if self.sample.calls!=9:return checked(*args,**kwargs)
                require(not self.attempted and sys.getprofile() is None);self.attempted=True
                monitoring=getattr(sys,'monitoring',None)
                require(monitoring is None or monitoring.get_tool(monitoring.PROFILER_ID) is None)
                initial=self.loaded.native.counts()
                with self.adapter.installed():value=checked(*args,**kwargs)
                require(self.adapter.restored() and self.sample.completed)
                self.loaded.validate()
                counts={name:self.loaded.native.counts()[name]-initial[name] for name in initial}
                require(set(counts)=={'fingerprint','persistent','custody'} and all(type(v) is int and 0<v<=10000000 for v in counts.values()))
                require(all(v>0 for v in self.adapter.calls.values()) and not any(self.adapter.fallbacks.values()))
                rows=profile_costs(pstats.Stats(self.sample.profile).stats,self.loaded.files['native_metadata_probe.py'][0],self.native_codes)
                require({r['function'] for r in rows if r['file']=='native-metadata-api.py' and r['calls']>0}>=set(NATIVE_APIS)-{'counts'})
                self.result={'diagnostic_only':True,'production_adopted':False,'guard_number':10,'profiled_checks':1,
                    'extra_guard_calls':0,'original_descriptors_restored':True,'original_classes_retained':True,
                    'same_original_actors':True,'observation_results_retained':False,'native_calls':counts,
                    'families':self.adapter.calls.copy(),'fallbacks':self.adapter.fallbacks.copy(),'rows':rows,**self.loaded.evidence()}
                return value
            return call
        self.sample.wrap=wrap;return self

    def __exit__(self,*_):
        try:
            if self.had_wrap:self.sample.wrap=self.raw_wrap
            else:del self.sample.wrap
        finally:self.active=False


class AtFirstGuardProfile:
    """Start original measurements at guard one; no rejected pair rerun."""
    def __init__(self,loaded,stage_owner,measurements):
        self.stage_owner=stage_owner;self.measurements=measurements
        self.original=vars(stage_owner)['check'];self.entered=False;self.attempted=False
        self.sample=GuardTenSample(loaded,measurements.sample)

    @property
    def result(self):return self.sample.result

    def __enter__(self):
        self.sample.__enter__()
        def first(stage,*args,**kwargs):
            try:
                require(not self.attempted and not args and not kwargs);self.attempted=True
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
        finally:
            try:self.stage_owner.check=self.original
            finally:self.sample.__exit__(None,None,None)
