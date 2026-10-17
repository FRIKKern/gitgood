"""Hosted installed-body diagnostic on the original classes and live actors."""
import ast
from contextlib import contextmanager
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import sysconfig
import threading
import time
import types

import guard_body_source
from guard_body_source import BODY_COUNT,MODULE_NAMES,header,select_sources
import path_body_probe
from path_body_probe import _read_owned,root_owner

HELPERS=('guard_body_probe.py','guard_body_source.py','guard-body-build.py',
    'path_body_source.py','path_body_probe.py','path-body-build.py')


def require(value):
    if not value:raise ValueError('Installed body diagnostic invariant')


def extension_name():
    suffix=sysconfig.get_config_var('EXT_SUFFIX')
    require(type(suffix) is str and '/' not in suffix and suffix.endswith('.so'))
    return '_guard_body_probe'+suffix


def function(raw):
    if type(raw) in {classmethod,staticmethod}:return raw.__func__
    if type(raw) is property:
        require(raw.fget is not None and raw.fset is None and raw.fdel is None);return raw.fget
    return raw


class Loaded:
    def __init__(self,directory):
        root_owner();self.directory=Path(directory)
        self.names=(*HELPERS,*(name+'.py' for name in MODULE_NAMES),
            'guard-body-donor.pyx','manifest.json',extension_name())
        self.files={name:_read_owned(self.directory/name,16777216 if name==extension_name() else 262144)
            for name in self.names}
        raw={name:value[0] for name,value in self.files.items()}
        self.hashes={name:hashlib.sha256(value).hexdigest() for name,value in raw.items()}
        import path_body_source
        for module in (sys.modules[__name__],guard_body_source,path_body_probe,path_body_source):
            require(self.hashes[Path(module.__file__).name]==hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest())
        old_builder=ast.parse(raw['path-body-build.py'])
        literals={item.targets[0].id:ast.literal_eval(item.value) for item in old_builder.body
            if isinstance(item,ast.Assign) and len(item.targets)==1 and isinstance(item.targets[0],ast.Name)
            and item.targets[0].id in {'DIRECTIVES','WHEEL_SHA256','WHEEL_BYTES'}}
        require(set(literals)=={'DIRECTIVES','WHEEL_SHA256','WHEEL_BYTES'})
        body,expected=select_sources({name:raw[name+'.py'] for name in MODULE_NAMES})
        manifest=json.loads(raw['manifest.json']);self.manifest=manifest
        for key,value in expected.items():require(manifest[key]==(True if key=='compiled' else value))
        require(manifest['compiler_version']=='3.1.8' and manifest['compiler_wheel_sha256']==literals['WHEEL_SHA256']
            and manifest['compiler_wheel_bytes']==literals['WHEEL_BYTES']
            and manifest['compiler_directives']==literals['DIRECTIVES']
            and manifest['python_version']==sys.version.split()[0]
            and manifest['runtime_verified'] is False and manifest['production_adopted'] is False)
        require(raw['guard-body-donor.pyx']==(header()+body).encode()
            and manifest['donor_source_sha256']==self.hashes['guard-body-donor.pyx']
            and manifest['elf_sha256']==self.hashes[extension_name()])
        self.rows=expected['bodies'];self.modules=tuple(importlib.import_module(name) for name in MODULE_NAMES)
        self.original_codes={};self.runtime_files={}
        for module in self.modules:
            path=Path(module.__file__);value=_read_owned(path,262144)
            require(value[0]==raw[module.__name__+'.py']);self.runtime_files[module.__name__]=(path,value)
            code=compile(value[0],module.__file__,'exec')
            for row in (row for row in self.rows if row['module']==module.__name__):
                parent=code
                if row['owner']:
                    parent=next(item for item in code.co_consts if isinstance(item,types.CodeType) and item.co_name==row['owner'])
                self.original_codes[row['module'],row['owner'],row['method']]=next(
                    item for item in parent.co_consts if isinstance(item,types.CodeType) and item.co_name==row['method'])
        require('_guard_body_probe' not in sys.modules)
        spec=importlib.util.spec_from_file_location('_guard_body_probe',self.directory/extension_name())
        self.native=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.native)
        require(callable(self.native.bind_original) and callable(self.native.load_counts));self.validate()

    def validate(self):
        root_owner()
        for name,expected in self.files.items():require(_read_owned(self.directory/name,
            16777216 if name==extension_name() else 262144)==expected)
        for path,expected in self.runtime_files.values():require(_read_owned(path,262144)==expected)

    def evidence(self):
        return {'source_hashes':self.hashes,'compiler_version':'3.1.8',
            'compiler_wheel_sha256':self.manifest['compiler_wheel_sha256'],
            'original_source_hashes':self.manifest['original_source_hashes'],
            'bodies':self.rows,'live_global_loads':self.manifest['live_global_loads']}


class Adapter:
    def __init__(self,modules,native,rows,*,original_codes=None,alias_modules=None,owner_check=None):
        self.modules=tuple(modules);self.native=native;self.rows=rows
        self.owner_check=root_owner if owner_check is None else owner_check
        self.owner_check();self.owner=(os.getpid(),threading.get_ident())
        require(tuple(module.__name__ for module in self.modules)==MODULE_NAMES)
        self.classes=[];self.entries=[];self.active=False;self.broken=False
        builtins=[];replacements={};seen=set()
        by_name={module.__name__:module for module in self.modules}
        for module in self.modules:
            self.classes.extend((module,name,value) for name,value in vars(module).items()
                if type(value) is type and value.__module__==module.__name__)
            builtins.append(None)
        for row in rows:
            module=by_name[row['module']];owner=getattr(module,row['owner']) if row['owner'] else module
            name=row['method'];raw=vars(owner)[name];original=function(raw)
            donor=getattr(native,row['donor']);replacement=vars(donor)[name];new=function(replacement)
            require(type(original) is types.FunctionType and original.__globals__ is vars(module)
                and callable(new) and hasattr(new,'__get__'))
            require(type(raw) in {types.FunctionType,classmethod,staticmethod,property})
            if type(raw) is not types.FunctionType:require(type(replacement) is type(raw))
            if original_codes is not None:require(original.__code__==original_codes[row['module'],row['owner'],name])
            number=MODULE_NAMES.index(module.__name__)
            if builtins[number] is None:builtins[number]=original.__builtins__
            require(builtins[number] is original.__builtins__ and type(builtins[number]) is dict)
            key=(id(owner),name);require(key not in seen);seen.add(key)
            self.entries.append((owner,name,raw,replacement))
            if not row['owner']:replacements[id(raw)]=(raw,replacement)
        require(0<len(self.entries)<=BODY_COUNT)
        if alias_modules is None:
            directories={Path(module.__file__).parent for module in self.modules};require(len(directories)==1)
            directory=directories.pop()
            alias_modules=tuple(module for module in tuple(sys.modules.values())
                if type(module) is types.ModuleType and type(vars(module).get('__file__')) is str
                and Path(vars(module)['__file__']).parent==directory)
        require(len(alias_modules)<=256)
        for module in alias_modules:
            for name,value in tuple(vars(module).items()):
                pair=replacements.get(id(value));key=(id(module),name)
                if pair is not None and value is pair[0] and key not in seen:
                    require(len(self.entries)<1024);seen.add(key);self.entries.append((module,name,*pair))
        self.aliases=len(self.entries)-len(rows)
        require(native.bind_original([vars(module) for module in self.modules],builtins) is True)

    def check(self):
        self.owner_check();require(self.owner==(os.getpid(),threading.get_ident()) and not self.broken)
        require(all(vars(module).get(name) is original for module,name,original in self.classes))

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
    adapter=Adapter(loaded.modules,loaded.native,loaded.rows,original_codes=loaded.original_codes)
    rows=[];started=time.monotonic_ns();initial=loaded.native.load_counts()
    require(set(initial)==set(MODULE_NAMES) and all(type(value) is int and 0<=value<=100000000 for value in initial.values()))
    for number in range(20):
        values={};elapsed={}
        for selected in ((0,1) if number%2==0 else (1,0)):
            adapter.check();require(stage.usable and stage.state=='ready');calls=loaded.native.load_counts()
            if selected:
                with adapter.installed():
                    before=time.monotonic_ns()
                    try:values[selected]=original_guard(stage)
                    finally:elapsed[selected]=max(0,time.monotonic_ns()-before)
            else:
                before=time.monotonic_ns()
                try:values[selected]=original_guard(stage)
                finally:elapsed[selected]=max(0,time.monotonic_ns()-before)
            after=loaded.native.load_counts()
            require(adapter.restored() and stage.usable and stage.state=='ready')
            require(sum(after.values())>sum(calls.values()) if selected else after==calls)
        require(values[0]==values[1])
        require(all(type(value) is int and 0<=value<=1200000000000 for value in elapsed.values()))
        rows.append({'baseline_us':elapsed[0]//1000,'prototype_us':elapsed[1]//1000})
    loaded.validate();adapter.check();require(adapter.restored())
    counts={name:loaded.native.load_counts()[name]-initial[name] for name in MODULE_NAMES}
    require(all(type(value) is int and 0<value<=100000000 for value in counts.values()))
    return {'diagnostic_only':True,'production_adopted':False,'pairs':rows,
        'original_descriptors_restored':True,'module_aliases_restored':True,'original_classes_retained':True,
        'observations_equal':True,'same_original_actors':True,'observation_results_retained':False,
        'compiled_bodies':len(loaded.rows),'patched_aliases':adapter.aliases,'compiled_global_loads':counts,
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
