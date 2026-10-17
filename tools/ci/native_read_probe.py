"""Diagnostic eight-role fresh filesystem backend; never production adoption.

The four metadata roles retain their original classes and observations. Complete
reads retain CPython buffering, separate fingerprints, and post-close checks.
Only immutable lexical/code/schema inputs can survive a call.
"""
import builtins
import cProfile
from contextlib import contextmanager
from functools import wraps
import hashlib
import importlib
import io
import math
import os
from pathlib import Path
import pathlib
import pstats
import sys
import time
import types

import native_metadata_probe as metadata
from native_metadata_probe import require, Unsupported, raw_function
from path_body_probe import _read_owned

HELPERS=(*metadata.HELPERS,'native_read_probe.py')
READ_FAMILIES=('root_file','private_file','read_bytes','kernel_read')
FAMILIES=(*metadata.FAMILIES,*READ_FAMILIES)
NATIVE_APIS=('fingerprint','persistent','custody','same_bindings','counts','read_file','read_counts','prepare_tables')


class Loaded:
    def __init__(self,directory,*,base=None):
        self.base=metadata.Loaded(directory) if base is None else base
        require(Path(directory)==self.base.directory)
        self.directory=self.base.directory;self.modules=self.base.modules;self.native=self.base.native
        require(all(type(getattr(self.native,name,None)) is types.BuiltinFunctionType
            and getattr(self.native,name).__module__=='_native_metadata_probe'
            for name in NATIVE_APIS))
        self.native_apis={name:getattr(self.native,name) for name in NATIVE_APIS}
        self.kernel=importlib.import_module('native_kernel_backend')
        self.extra_files={'native_read_probe.py':_read_owned(self.directory/'native_read_probe.py',262144)}
        require(self.extra_files['native_read_probe.py'][0]==Path(__file__).read_bytes())
        self.runtime_files={};self.original_codes=dict(self.base.original_codes);self.extra_functions=[]
        # fdopen may have a frozen code filename. Authenticate its actual SDK
        # source with that same compile filename rather than treating it as a path.
        for fn in (self.modules[0].root_file,self.modules[0].read_bytes,self.modules[1].private_file,
                self.modules[1]._canonical_private_path,self.kernel._read,self.kernel.require,os.fdopen):
            require(type(fn) is types.FunctionType)
            source=Path(os.__file__) if fn is os.fdopen else Path(fn.__code__.co_filename)
            if source not in self.runtime_files:self.runtime_files[source]=_read_owned(source,262144)
            codes=metadata.functions(compile(self.runtime_files[source][0],fn.__code__.co_filename,'exec'))
            require(fn.__code__==codes.get(fn.__code__.co_qualname))
            self.original_codes[id(fn)]=fn.__code__;self.extra_functions.append(fn)
        self.validate()

    def validate(self):
        # Reject changed I/O code before the base loader re-reads files with it.
        # These identity checks do not invoke the suspect helper or the OS.
        require(all(vars(self.native).get(name) is value for name,value in self.native_apis.items()))
        for fn in self.extra_functions:require(fn.__code__==self.original_codes[id(fn)])
        self.base.validate()
        for name,expected in self.extra_files.items():require(_read_owned(self.directory/name,262144)==expected)
        for path,expected in self.runtime_files.items():require(_read_owned(path,262144)==expected)

    def evidence(self):
        evidence=self.base.evidence()
        evidence['source_hashes']={**evidence['source_hashes'],**{
            name:hashlib.sha256(value[0]).hexdigest() for name,value in self.extra_files.items()}}
        evidence['original_source_hashes']={**evidence['original_source_hashes'],**{
            path.name:hashlib.sha256(value[0]).hexdigest() for path,value in self.runtime_files.items()}}
        return evidence


class Adapter(metadata.Adapter):
    def __init__(self,modules,native,kernel,*,owner_check=None,original_codes=None,_class_owners=False):
        super().__init__(modules,native,owner_check=owner_check,original_codes=original_codes,
            _class_owners=_class_owners)
        self.admission=native.same_bindings
        require(kernel.__name__=='native_kernel_backend');self.kernel=kernel
        self.calls.update({name:0 for name in READ_FAMILIES});self.fallbacks.update({name:0 for name in READ_FAMILIES})
        original_reads=(self.service.root_file,self.binding.private_file,self.service.read_bytes,kernel._read)
        if original_codes is not None:
            require(all(id(fn) in original_codes and fn.__code__==original_codes[id(fn)] for fn in original_reads))
        self.read_originals=original_reads
        self.installed_directory=Path(self.service.__file__).parent if hasattr(self.service,'__file__') else None
        self.alias_entries=();self.last_alias_count=0

        def fallback(family,fn,*args,**kwargs):
            self.fallbacks[family]+=1;require(self.fallbacks[family]<=10000000)
            return fn(*args,**kwargs)

        def admitted(family,path,maximum,uid=0,executable=False):
            return (self.eligible(family) and type(path) in {str,self.path_type}
                and type(maximum) is int and 0<=maximum<=16777216
                and type(uid) is int and 0<=uid<2**64 and type(executable) is bool)

        def read(family,kind,path,maximum,uid=0,executable=False,parents=()):
            value=self.native.read_file(kind,str(path),parents,uid,maximum,executable,io.open,io.BufferedReader)
            if value is NotImplemented:return value
            self.count(family)
            # A native refusal/error never falls back or repeats an observation.
            owner=self.binding if kind==1 else self.kernel if kind==3 else self.service
            owner.require(value is not None);self.after(family)
            return value

        @wraps(original_reads[0])
        def root_file(path,maximum=16777216,*,executable=False):
            if not admitted('root_file',path,maximum,executable=executable) or maximum==0:
                return fallback('root_file',original_reads[0],path,maximum,executable=executable)
            original_path=path;path=self.service._root_file_path(path)
            if len(str(path))>8192 or len(path.parts)>64:
                return fallback('root_file',original_reads[0],original_path,maximum,executable=executable)
            parents=tuple(name for _parent,name in self.service._root_file_parents(path))
            value=read('root_file',0,path,maximum,executable=executable,parents=parents)
            if value is NotImplemented:return fallback('root_file',original_reads[0],original_path,maximum,executable=executable)
            raw,before,after=value
            self.service.require(len(raw)==before[2]);self.service.require(before==after)
            return {'path':str(path),'device':before[0],'inode':before[1],
                'bytes':before[2],'sha256':self.service.hashlib.sha256(raw).hexdigest()},raw

        @wraps(original_reads[1])
        def private_file(path,uid,maximum=131072):
            if not admitted('private_file',path,maximum,uid=uid) or maximum==0:
                return fallback('private_file',original_reads[1],path,uid,maximum)
            original_path=path;path=self.binding.Path(path)
            self.binding.require(path.is_absolute() and path.anchor=='/' and '..' not in path.parts)
            if len(str(path))>8192 or len(path.parts)>64:
                return fallback('private_file',original_reads[1],original_path,uid,maximum)
            # _canonical_private_path includes ancestor observations. Its admitted
            # lexical portion runs above; the C role performs those lstats once.
            parents=tuple(str(parent) for parent in path.parents)
            value=read('private_file',1,path,maximum,uid=uid,parents=parents)
            if value is NotImplemented:return fallback('private_file',original_reads[1],original_path,uid,maximum)
            raw,before,after=value
            self.binding.require(len(raw)==before[2] and before==after)
            return {'path':str(path),'device':before[0],'inode':before[1],'uid':uid,
                'bytes':before[2],'sha256':self.binding.hashlib.sha256(raw).hexdigest()},raw

        @wraps(original_reads[2])
        def read_bytes(path,maximum=16384):
            if not admitted('read_bytes',path,maximum):return fallback('read_bytes',original_reads[2],path,maximum)
            value=read('read_bytes',2,path,maximum)
            if value is NotImplemented:return fallback('read_bytes',original_reads[2],path,maximum)
            raw,_before,_after=value
            self.service.require(len(raw)<=maximum);return raw

        @wraps(original_reads[3])
        def kernel_read(path,maximum=16384):
            if not admitted('kernel_read',path,maximum):return fallback('kernel_read',original_reads[3],path,maximum)
            value=read('kernel_read',3,path,maximum)
            if value is NotImplemented:return fallback('kernel_read',original_reads[3],path,maximum)
            raw,_before,_after=value
            self.kernel.require(0<len(raw)<=maximum);return raw.decode('ascii')

        self.read_replacements=(root_file,private_file,read_bytes,kernel_read)
        targets=((self.service,'root_file'),(self.binding,'private_file'),(self.service,'read_bytes'),(kernel,'_read'))
        self.read_entries=tuple((owner,name,old,new) for (owner,name),old,new in
            zip(targets,original_reads,self.read_replacements))
        self.entries=(*self.entries,*self.read_entries)

        def bindings(specifications):
            found=[];functions={}
            for owner,names in specifications:
                namespace=vars(owner)
                target=owner if _class_owners and isinstance(owner,type) else namespace
                for name in names:
                    require(name in namespace);value=namespace[name];found.append((target,name,value))
                    fn=raw_function(value)
                    if type(fn) is types.FunctionType:functions[id(fn)]=fn
            found.extend((fn,'__code__',fn.__code__) for fn in functions.values())
            return found
        lexical=[(pathlib,('os','Path','PurePath','PosixPath','WindowsPath')),
            (builtins,('type','str','int','isinstance','len','getattr','all','__import__'))]
        shared=bindings((*lexical,(os,('open','fdopen','fstat','fspath','O_RDONLY','O_NOFOLLOW','O_CLOEXEC','O_NONBLOCK')),
            (io,('open','BufferedReader','FileIO')),(sys,('modules',))))
        shared.extend((sys.modules,name,sys.modules[name]) for name in ('io','_io'))
        for name in ('__fspath__','__str__','__init__','__new__','_load_parts','_parse_path',
                '_format_parsed_parts','_from_parsed_parts','_flavour','with_segments','parts','anchor',
                'is_absolute','parents','parent','name','__eq__','__hash__','__getattribute__'):
            value=getattr(self.path_type,name);shared.append((self.path_type,name,value))
            fn=raw_function(value)
            if type(fn) is types.FunctionType:shared.append((fn,'__code__',fn.__code__))
        full=bindings(((self.service,('hashlib','require','_root_file_path','_root_file_parents','_root_file_parent_plan')),
            (self.binding,('hashlib','require','_canonical_private_path')),(hashlib,('sha256',))))
        raw_service=bindings(((self.service,('os','require')),))
        raw_kernel=bindings(((kernel,('os','require')),))
        preparation=[]
        for owner in self.owners:
            preparation.append((owner,'__getattribute__',getattr(owner,'__getattribute__')))
        preparation.extend((self.path_type,name,getattr(self.path_type,name)) for name in ('__eq__','__hash__','__getattribute__'))
        for _owner,_name,value in tuple(preparation):
            fn=raw_function(value)
            if type(fn) is types.FunctionType:preparation.append((fn,'__code__',fn.__code__))
        self.family_bindings={name:tuple((*self.bindings,*preparation)) for name in metadata.FAMILIES}
        self.family_bindings.update(root_file=tuple((*self.bindings,*shared,*full)),
            private_file=tuple((*self.bindings,*shared,*full)),
            read_bytes=tuple((*shared,*raw_service)),kernel_read=tuple((*shared,*raw_kernel)))
        for family,fn in zip(READ_FAMILIES,original_reads):
            self.family_bindings[family]=(*self.family_bindings[family],(fn,'__code__',fn.__code__))
        # Drop duplicate identities only, never a live admission check.
        self.family_bindings={name:tuple({(id(owner),key,id(value)):(owner,key,value)
            for owner,key,value in values}.values()) for name,values in self.family_bindings.items()}
        if type(self.admission) is types.BuiltinFunctionType:
            native_bindings=tuple((vars(native),name,getattr(native,name)) for name in NATIVE_APIS)
            self.family_bindings={name:(*values,*native_bindings) for name,values in self.family_bindings.items()}
        require(all(len(values)<=256 for values in self.family_bindings.values()))

    def eligible(self,family=None):
        names=FAMILIES if family is None else (family,)
        return all(self.admission(self.family_bindings[name],*self.owner) for name in names)

    def plan_arguments(self,subject):
        value=self.native.prepare_tables(0,subject,self.owners[2],self.path_type)
        if value is NotImplemented:raise Unsupported()
        return value

    def custody_arguments(self,subject):
        value=self.native.prepare_tables(1,subject,self.owners[3],self.path_type)
        if value is NotImplemented:raise Unsupported()
        return value

    def aliases(self,replacements=False):
        selected=self.read_replacements if replacements else self.read_originals
        found=[]
        for module in tuple(sys.modules.values()):
            if type(module) is not types.ModuleType:continue
            filename=vars(module).get('__file__')
            if type(filename) is not str or self.installed_directory is None or Path(filename).parent!=self.installed_directory:continue
            for name,value in tuple(vars(module).items()):
                for index,expected in enumerate(selected):
                    if value is expected:found.append((module,name,self.read_originals[index],self.read_replacements[index]))
        require(len(found)<=1024)
        return tuple(found)

    def restored(self):
        return (super().restored() and all(vars(owner).get(name) is old for owner,name,old,_new in self.alias_entries)
            and not self.aliases(replacements=True))

    @contextmanager
    def installed(self):
        self.check();require(not self.active and self.restored());self.active=True;changed=[]
        try:
            self.alias_entries=self.aliases();self.last_alias_count=len(self.alias_entries)
            entries={(id(owner),name):(owner,name,old,new) for owner,name,old,new in (*self.entries,*self.alias_entries)}
            for owner,name,old,new in entries.values():
                changed.append((owner,name,old));setattr(owner,name,new)
            yield
            self.check();require(all(vars(owner).get(name) is new for owner,name,_old,new in entries.values()))
        finally:
            pending=sys.exception();errors=[]
            # A module first imported during an admitted read can bind a direct
            # alias to the temporary helper. Restore those aliases as well.
            try:
                late=self.aliases(replacements=True)
                known={(id(owner),name) for owner,name,_old in changed}
                changed.extend((owner,name,old) for owner,name,old,_new in late if (id(owner),name) not in known)
                self.alias_entries=tuple({(id(owner),name):(owner,name,old,new)
                    for owner,name,old,new in (*self.alias_entries,*late)}.values())
            except BaseException as error:errors.append(error)
            for owner,name,old in reversed(changed):
                try:setattr(owner,name,old)
                except BaseException as error:errors.append(error)
            self.active=False;self.broken=bool(errors) or not self.restored()
            if pending is None:require(not self.broken)


def counts(native):return {**native.counts(),**native.read_counts()}


def compare_guard(loaded,original_guard,stage):
    metadata.root_owner();require(stage.usable and stage.state=='ready' and sys.getprofile() is None)
    monitoring=getattr(sys,'monitoring',None)
    require(monitoring is None or monitoring.get_tool(monitoring.PROFILER_ID) is None)
    adapter=Adapter(loaded.modules,loaded.native,loaded.kernel,original_codes=loaded.original_codes)
    rows=[];initial=counts(loaded.native);started=time.monotonic_ns()
    for number in range(20):
        values={};elapsed={}
        for selected in ((0,1) if number%2==0 else (1,0)):
            adapter.check();require(stage.usable and stage.state=='ready');before_counts=counts(loaded.native)
            if selected:
                with adapter.installed():
                    before=time.monotonic_ns()
                    try:values[selected]=original_guard(stage)
                    finally:elapsed[selected]=max(0,time.monotonic_ns()-before)
            else:
                before=time.monotonic_ns()
                try:values[selected]=original_guard(stage)
                finally:elapsed[selected]=max(0,time.monotonic_ns()-before)
            after=counts(loaded.native)
            require(adapter.restored() and stage.usable and stage.state=='ready')
            require(sum(after.values())>sum(before_counts.values()) if selected else after==before_counts)
        require(values[0]==values[1])
        require(all(type(value) is int and 0<=value<=1200000000000 for value in elapsed.values()))
        rows.append({'baseline_us':elapsed[0]//1000,'prototype_us':elapsed[1]//1000})
    loaded.validate();adapter.check();require(adapter.restored())
    final=counts(loaded.native);delta={name:final[name]-initial[name] for name in initial}
    require(set(delta)=={'fingerprint','persistent','custody','read','prepare'}
        and all(type(value) is int and 0<value<=10000000 for value in delta.values()))
    require(all(value>0 for value in adapter.calls.values()) and not any(adapter.fallbacks.values()))
    return {'diagnostic_only':True,'production_adopted':False,'pairs':rows,
        'original_descriptors_restored':True,'original_classes_retained':True,'direct_aliases_restored':True,
        'observations_equal':True,'same_original_actors':True,'observation_results_retained':False,
        'native_calls':delta,'families':adapter.calls.copy(),'fallbacks':adapter.fallbacks.copy(),
        'elapsed_ms':min(1200000,max(0,(time.monotonic_ns()-started)//1000000)),**loaded.evidence()}


class AtFirstGuard:
    """Compare before measurements; restore originals before profiles/effects."""
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
    ('Adapter.eligible','eligible'),('Adapter.eligible.<locals>.<genexpr>','eligible_each'),
    ('Adapter.plan_arguments','plan_arguments'),('Adapter.custody_arguments','custody_arguments'),
    *((f'Adapter.__init__.<locals>.{name}',name) for name in
        ('admitted','read','fallback','root_file','private_file','read_bytes','kernel_read')))


def native_profile_codes(native):
    """Discover genuine C labels with argument-count refusal, never file I/O."""
    require(sys.getprofile() is None)
    monitoring=getattr(sys,'monitoring',None)
    require(monitoring is None or monitoring.get_tool(monitoring.PROFILER_ID) is None)
    for name in NATIVE_APIS:
        fn=getattr(native,name)
        require(type(fn) is types.BuiltinFunctionType and fn.__module__=='_native_metadata_probe' and fn.__name__==name)
    before=counts(native);empty=cProfile.Profile();empty.runcall(lambda:None)
    require(set(before)=={'fingerprint','persistent','custody','read','prepare'}
        and all(type(value) is int and 0<=value<=10000000 for value in before.values()))
    excluded={entry.code for entry in empty.getstats() if type(entry.code) is str};result={}
    for name in NATIVE_APIS:
        fn=getattr(native,name)
        require(type(fn) is types.BuiltinFunctionType and fn.__module__=='_native_metadata_probe' and fn.__name__==name)
        profile=cProfile.Profile()
        try:profile.runcall(fn)
        except TypeError:require(name not in {'counts','read_counts'})
        codes={entry.code for entry in profile.getstats() if type(entry.code) is str}-excluded
        require(len(codes)==1 and counts(native)==before)
        code=codes.pop();require(0<len(code)<=1024 and code not in result);result[code]=name
    return result


def profile_costs(stats,sources,native_codes):
    """Closed public labels; eight native slots and at most eight Python rows."""
    require(type(stats) is dict and type(native_codes) is dict and len(native_codes)==8
        and set(native_codes.values())==set(NATIVE_APIS)
        and all(type(key) is str and 0<len(key)<=1024 for key in native_codes))
    require(type(sources) is dict and set(sources)=={'native_metadata_probe.py','native_read_probe.py'}
        and all(type(raw) is bytes and 0<len(raw)<=262144 for raw in sources.values()))
    python={}
    for name,filename,inventory,label in (
            ('native_metadata_probe.py',metadata.__file__,metadata.PROFILE_PYTHON,'native-metadata-self.py'),
            ('native_read_probe.py',__file__,PROFILE_PYTHON,'native-read-self.py')):
        code=metadata.functions(compile(sources[name],filename,'exec'))
        for qualified,function in inventory:
            fn=code[qualified];python[fn.co_filename,fn.co_firstlineno,fn.co_name]=(label,function)
    native_rows={name:{'file':'native-read-api.py','function':name,'line':0,
        'calls':0,'self_us':0,'cumulative_us':0} for name in NATIVE_APIS};python_rows=[]
    for key,value in stats.items():
        if type(key) is not tuple or len(key)!=3:continue
        filename,line,name=key
        if type(filename) is not str or type(line) is not int or type(name) is not str:continue
        if key in python:label,function=python[key]
        elif filename=='~' and line==0 and name in native_codes:label='native-read-api.py';function=native_codes[name]
        else:continue
        require(type(value) is tuple and len(value)==5)
        calls,total,cumulative=value[1:4]
        require(type(calls) is int and 0<=calls<=10000000 and 0<=line<10000)
        require(all(type(v) in {int,float} and 0<=v<=1200 and math.isfinite(v) for v in (total,cumulative))
            and total<=cumulative)
        row={'file':label,'function':function,'line':line,'calls':calls,
            'self_us':int(total*1000000),'cumulative_us':int(cumulative*1000000)}
        if label=='native-read-api.py':native_rows[function]=row
        else:python_rows.append(row)
    selected=sorted(python_rows,key=lambda r:(-r['self_us'],-r['cumulative_us'],r['file'],r['function'],r['line']))[:8]
    return sorted([*native_rows.values(),*selected],key=lambda r:(r['file'],r['function'],r['line']))


class GuardTenSample(metadata.GuardTenSample):
    """Profile the rejected eight-role backend once in the existing tenth guard."""
    def __init__(self,loaded,sample):
        self.loaded=loaded;self.sample=sample;self.result=None;self.attempted=False;self.active=False
        self.adapter=Adapter(loaded.modules,loaded.native,loaded.kernel,original_codes=loaded.original_codes)
        self.native_codes=native_profile_codes(loaded.native)

    def __enter__(self):
        require(not self.active and not self.attempted and self.sample.calls==0
            and self.sample.profile is None and not self.sample.completed);self.active=True
        self.had_wrap='wrap' in vars(self.sample);self.raw_wrap=vars(self.sample).get('wrap');original_wrap=self.sample.wrap
        def wrap(original):
            checked=original_wrap(original)
            def call(*args,**kwargs):
                if self.sample.calls!=9:return checked(*args,**kwargs)
                require(not self.attempted and sys.getprofile() is None);self.attempted=True
                monitoring=getattr(sys,'monitoring',None)
                require(monitoring is None or monitoring.get_tool(monitoring.PROFILER_ID) is None)
                initial=counts(self.loaded.native)
                with self.adapter.installed():value=checked(*args,**kwargs)
                require(self.adapter.restored() and self.sample.completed)
                self.loaded.validate()
                final=counts(self.loaded.native);delta={name:final[name]-initial[name] for name in initial}
                require(set(delta)=={'fingerprint','persistent','custody','read','prepare'}
                    and all(type(v) is int and 0<v<=10000000 for v in delta.values()))
                require(all(v>0 for v in self.adapter.calls.values()) and not any(self.adapter.fallbacks.values()))
                sources={'native_metadata_probe.py':self.loaded.base.files['native_metadata_probe.py'][0],
                    'native_read_probe.py':self.loaded.extra_files['native_read_probe.py'][0]}
                rows=profile_costs(pstats.Stats(self.sample.profile).stats,sources,self.native_codes)
                require({r['function'] for r in rows if r['file']=='native-read-api.py' and r['calls']>0}
                    >=set(NATIVE_APIS)-{'counts','read_counts'})
                self.result={'diagnostic_only':True,'production_adopted':False,'guard_number':10,'profiled_checks':1,
                    'extra_guard_calls':0,'original_descriptors_restored':True,'original_classes_retained':True,
                    'direct_aliases_restored':True,'same_original_actors':True,'observation_results_retained':False,
                    'native_calls':delta,'families':self.adapter.calls.copy(),'fallbacks':self.adapter.fallbacks.copy(),
                    'rows':rows,**self.loaded.evidence()}
                return value
            return call
        self.sample.wrap=wrap;return self


class AtFirstGuardProfile(metadata.AtFirstGuardProfile):
    """Original measurement start with no repeated rejected paired comparison."""
    def __init__(self,loaded,stage_owner,measurements):
        self.stage_owner=stage_owner;self.measurements=measurements
        self.original=vars(stage_owner)['check'];self.entered=False;self.attempted=False
        self.sample=GuardTenSample(loaded,measurements.sample)
