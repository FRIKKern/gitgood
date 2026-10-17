"""Four-role pure lexical SDK diagnostic; no filesystem result cache.

Original Path classes stay installed. Native plans may retain bounded immutable
strings/tuples only; every returned Path and mutable slot/list remains distinct.
The native implementation is diagnostic until hosted semantic and benefit gates pass.
"""
import ast
import builtins
from contextlib import contextmanager
from functools import wraps
import hashlib
import inspect
import ntpath
import os
from pathlib import Path
import pathlib
import posixpath
import sys
import threading
import time
import types

import native_metadata_probe as metadata
import native_read_probe as read_backend
from native_metadata_probe import require,raw_function
from path_body_probe import _read_owned

ROLES=('constructor','load_parts','string','with_segments')
APIS=('path_plan','path_call')
DESCRIPTOR_APIS=('descriptor_plan','descriptor_entries','descriptor_bind','descriptor_phase',
    'descriptor_counts','descriptor_close')
HELPERS=(*read_backend.HELPERS,'native_path_probe.py')
TARGETS=((pathlib.Path,'__init__'),(pathlib.PurePath,'_load_parts'),
    (pathlib.PurePath,'__str__'),(pathlib.PurePath,'with_segments'))
SDK_AST={
    'PurePath.__init__':'dda8755d23ba3ce9199d1d97eacb28060244e25cf81af6cd6033dcf8bda04d09',
    'PurePath.with_segments':'a8ddb7b7f982c3ca4efb9dac4babf83fe268b53bed642f46b1b0ee4bebd7e450',
    'PurePath._parse_path':'8ed8604c0f9d4b833979e2f38893d3b87263dffedbc373e0f6a60da5b11a56f7',
    'PurePath._load_parts':'6fdf4ffc539a7a8348a40118d781eac85bbd48d7c9e444ae084f8bd3810909f0',
    'PurePath._format_parsed_parts':'7b98565dad13ab9ba467d757281f3e17bb413357ae14d738cccc05fc678c1599',
    'PurePath.__str__':'c4f02dc752d28746fb3fb5030c34f771b39491f70a9701154310004c0b044a03',
    'PurePath.drive':'9834bad45b68286e6ee227d2b880fef54b676db3ecdf163b4f8eb34ab599742c',
    'PurePath.root':'abb56bff94760f2d5ebf8fb06e3ee93ae9309fa25aac724fdaefe136dabde3c9',
    'PurePath._tail':'319bf622b995b8c6f4b04fd59bf2394d1197297f77de755165782118951b2487',
    'Path.__init__':'e03baf397526b98eb1b63cc2a79787d717793904ee883cd15dd2fd2e0064eeee',
    'Path.__new__':'fa9cb033a5d0d103b961976c8856e746f81e4c25ba6c8c0f171672144edde93f',
}
# CPython 3.12's older constructor converts a mixed Windows-flavour argument
# differently. Native construction supports only exact strings and the same
# concrete POSIX class; mixed flavours always execute the original SDK body.
SDK_ALTERNATIVES={'PurePath.__init__':{
    '2bb656a796d68eca4898b404a36b63ba98b6475f6a42503647c0c569a262dd4e',
    # Ubuntu/Debian ntpath-import.diff adds a local import to that exact body.
    '568123baa6cd1f9dc899024528b0fa30429b5b7c0a1bf3923af0df4b251ad6c2'}}
POSIX_AST={
    '_get_sep':'9bd3b114d0030168cf40671121828d07b9ef8fe0f054fedeb162c9dd76a2323c',
    'join':'aa1ab3c9e073abc8ccb51208d6b7faf1aa03d673cd6ff83e2f83c8467b476cde',
    'splitdrive':'a1b5c7575676bc9a0b6d58a11e1bdae52781ed124be83d8ad65c31ca54956776',
    'splitroot':'7e582ea1376f84916291312221ca8c9a6a7992306f6c7a80493fdf3398f60305',
}


def sdk_code(raw,filename):
    require(type(raw) is bytes and 0<len(raw)<=262144)
    tree=ast.parse(raw);require(sum(1 for _ in ast.walk(tree))<=30000)
    found={}
    for owner in tree.body:
        if not isinstance(owner,ast.ClassDef):continue
        for node in owner.body:
            name=owner.name+'.'+getattr(node,'name','')
            if name not in SDK_AST:continue
            require(isinstance(node,ast.FunctionDef) and name not in found)
            if (node.body and isinstance(node.body[0],ast.Expr) and isinstance(node.body[0].value,ast.Constant)
                    and type(node.body[0].value.value) is str):node.body=node.body[1:]
            found[name]=hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest()
    require(set(found)==set(SDK_AST) and all(value==SDK_AST[name]
        or value in SDK_ALTERNATIVES.get(name,()) for name,value in found.items()))
    return metadata.functions(compile(raw,filename,'exec'))


def posix_code(raw):
    require(type(raw) is bytes and 0<len(raw)<=262144)
    tree=ast.parse(raw);found={}
    for node in tree.body:
        if not isinstance(node,ast.FunctionDef) or node.name not in POSIX_AST:continue
        require(node.name not in found)
        if (node.body and isinstance(node.body[0],ast.Expr) and isinstance(node.body[0].value,ast.Constant)
                and type(node.body[0].value.value) is str):node.body=node.body[1:]
        found[node.name]=hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest()
    require(found==POSIX_AST)
    return {'posixpath.'+name:metadata.functions(compile(raw,getattr(posixpath,name).__code__.co_filename,'exec'))[name]
        for name in POSIX_AST}


def sdk_environment():
    require(all(type(module) is types.ModuleType for module in (pathlib,os,sys,posixpath,ntpath,builtins)))
    require(pathlib.os is os and pathlib.sys is sys and pathlib.posixpath is posixpath
        and pathlib.Path is TARGETS[0][0] and pathlib.PurePath is TARGETS[1][0]
        and pathlib.PurePosixPath._flavour is posixpath and pathlib.PureWindowsPath._flavour is ntpath
        and type(sys.modules) is dict and sys.modules.get('ntpath') is ntpath
        and posixpath.sep=='/' and posixpath.altsep is None and vars(posixpath).get('os') is os)
    if 'ntpath' in vars(pathlib):require(pathlib.ntpath is ntpath)
    for owner,name,module in ((os,'fspath','posix' if os.name=='posix' else 'nt'),(sys,'intern','sys'),
            (builtins,'len','builtins'),(builtins,'isinstance','builtins'),(builtins,'__import__','builtins')):
        fn=vars(owner)[name]
        require(type(fn) is types.BuiltinFunctionType and fn.__module__==module and fn.__name__==name)
    require(builtins.str is ''.__class__ and builtins.type is ''.__class__.__class__
        and builtins.object is ''.__class__.__base__ and builtins.bytes is b''.__class__
        and type(builtins.map) is type and builtins.map.__module__=='builtins'
        and builtins.map.__name__=='map' and not builtins.map.__flags__&512)
    for name in ('super','AttributeError'):
        cls=vars(builtins)[name]
        require(type(cls) is type and cls.__module__=='builtins' and cls.__name__==name
            and not cls.__flags__&512)  # Canonical immutable builtin, not a heap type.
    for name in ('_raw_paths','_drv','_root','_tail_cached','_str'):
        slot=vars(pathlib.PurePath)[name]
        require(type(slot) is types.MemberDescriptorType and slot.__objclass__ is pathlib.PurePath and slot.__name__==name)
    for name,kind in (('_parse_path',classmethod),('_format_parsed_parts',classmethod),
            ('drive',property),('root',property),('_tail',property)):
        require(type(vars(pathlib.PurePath)[name]) is kind)
    require(type(vars(pathlib.Path)['__new__']) is staticmethod)


class Loaded:
    def __init__(self,directory,*,base=None):
        # Reuse the admission-first SDK/I/O custody checks from the verified
        # read lane without installing its rejected filesystem adapter.
        self.base=read_backend.Loaded(directory) if base is None else base
        require(Path(directory)==self.base.directory)
        self.directory=self.base.directory;self.native=self.base.native
        require(all(type(getattr(self.native,name,None)) is types.BuiltinFunctionType
            and getattr(self.native,name).__module__=='_native_metadata_probe'
            and getattr(self.native,name).__name__==name for name in (*APIS,*DESCRIPTOR_APIS)))
        self.apis={name:getattr(self.native,name) for name in (*APIS,*DESCRIPTOR_APIS)}
        self.extra_files={'native_path_probe.py':_read_owned(self.directory/'native_path_probe.py',262144)}
        require(self.extra_files['native_path_probe.py'][0]==Path(__file__).read_bytes())
        own_codes=metadata.functions(compile(self.extra_files['native_path_probe.py'][0],__file__,'exec'))
        candidates=[]
        for value in (*vars(sys.modules[__name__]).values(),
                *(v for owner in (Loaded,Adapter,DescriptorAdapter,AtFirstGuard) for v in vars(owner).values())):
            fn=raw_function(value)
            for candidate in (fn,getattr(fn,'__wrapped__',None)):
                if type(candidate) is types.FunctionType and candidate.__code__.co_filename==__file__:
                    require(candidate.__code__==own_codes.get(candidate.__code__.co_qualname))
                    candidates.append(candidate)
        self.own_functions=tuple(candidates)
        self.own_codes={id(fn):fn.__code__ for fn in candidates}
        self.own_closures={}
        for fn in candidates:
            closure=fn.__closure__
            for name,cell in zip(fn.__code__.co_freevars,closure or ()):
                if name=='__class__':require(cell.cell_contents is globals()[fn.__qualname__.split('.')[0]])
            self.own_closures[id(fn)]=(closure,tuple((cell,cell.cell_contents) for cell in closure or ()))
        self.sdk_path=Path(pathlib.__file__);self.sdk=_read_owned(self.sdk_path,262144)
        self.codes=sdk_code(self.sdk[0],str(self.sdk_path))
        self.posix_path=Path(posixpath.__file__);self.posix=_read_owned(self.posix_path,262144)
        self.codes.update(posix_code(self.posix[0]));self.validate()

    def validate(self):
        for fn in self.own_functions:
            require(fn.__code__ is self.own_codes[id(fn)] and fn.__globals__ is globals()
                and fn.__builtins__ is vars(builtins))
            closure,cells=self.own_closures[id(fn)]
            require(fn.__closure__ is closure and all(cell.cell_contents is value for cell,value in cells))
        require(all(getattr(self.native,name,None) is value for name,value in self.apis.items()))
        for qualified in SDK_AST:
            owner,name=qualified.split('.');fn=raw_function(vars(getattr(pathlib,owner))[name])
            require(type(fn) is types.FunctionType and fn.__code__==self.codes[qualified]
                and fn.__globals__ is vars(pathlib) and fn.__builtins__ is vars(builtins)
                and fn.__defaults__ is None and fn.__kwdefaults__ is None)
        for name in POSIX_AST:
            fn=getattr(posixpath,name)
            require(type(fn) is types.FunctionType and fn.__code__==self.codes['posixpath.'+name]
                and fn.__globals__ is vars(posixpath) and fn.__builtins__ is vars(builtins)
                and fn.__defaults__ is None and fn.__kwdefaults__ is None)
        sdk_environment()
        self.base.validate()
        require(_read_owned(self.sdk_path,262144)==self.sdk)
        require(_read_owned(self.posix_path,262144)==self.posix)
        for name,value in self.extra_files.items():require(_read_owned(self.directory/name,262144)==value)

    def evidence(self):
        value=self.base.evidence()
        value['source_hashes']={**value['source_hashes'],**{
            name:hashlib.sha256(item[0]).hexdigest() for name,item in self.extra_files.items()}}
        contract=sorted(SDK_AST.items()),sorted((name,sorted(values)) for name,values in SDK_ALTERNATIVES.items())
        value['pathlib_ast_sha256']=hashlib.sha256(repr(contract).encode()).hexdigest()
        value['original_source_hashes']={**value['original_source_hashes'],
            'posixpath.py':hashlib.sha256(self.posix[0]).hexdigest()}
        return value


class Adapter:
    def __init__(self,native,*,owner_check=None,sdk_codes=None,_prepare_only=False):
        self.owner_check=metadata.root_owner if owner_check is None else owner_check;self.owner_check()
        sdk_environment()
        self.owner=(os.getpid(),threading.get_ident())
        self.concrete=pathlib.PosixPath if os.name=='posix' else pathlib.WindowsPath
        self.native=native;self.call=native.path_call;self.active=False;self.broken=False;self.closed=False
        self.calls=dict.fromkeys(ROLES,0);self.fallbacks=dict.fromkeys(ROLES,0)
        self.originals=tuple(vars(owner)[name] for owner,name in TARGETS)
        require(all(type(fn) is types.FunctionType for fn in self.originals))
        if sdk_codes is None:
            # Do not invoke an unauthenticated SDK constructor to authenticate
            # that same constructor. This unprivileged contract path uses only
            # the trusted interpreter's ordinary open; hosted callers supply
            # code already read through Loaded's protected source custody.
            require(owner_check is not None)
            with open(pathlib.__file__,'rb') as source:raw=source.read(262145)
            codes=sdk_code(raw,pathlib.__file__)
            with open(posixpath.__file__,'rb') as source:raw=source.read(262145)
            codes.update(posix_code(raw))
        else:codes=sdk_codes
        for qualified in SDK_AST:
            owner,name=qualified.split('.');fn=raw_function(vars(getattr(pathlib,owner))[name])
            require(type(fn) is types.FunctionType and fn.__code__==codes[qualified]
                and fn.__globals__ is vars(pathlib) and fn.__builtins__ is vars(builtins)
                and fn.__defaults__ is None and fn.__kwdefaults__ is None)
            for variable,cell in zip(fn.__code__.co_freevars,fn.__closure__ or ()):
                if variable=='__class__':require(cell.cell_contents is getattr(pathlib,owner))
        for name in POSIX_AST:
            fn=getattr(posixpath,name)
            require(type(fn) is types.FunctionType and fn.__code__==codes['posixpath.'+name]
                and fn.__globals__ is vars(posixpath) and fn.__builtins__ is vars(builtins)
                and fn.__defaults__ is None and fn.__kwdefaults__ is None)
        self.sdk_functions={qualified:raw_function(vars(getattr(pathlib,qualified.split('.')[0]))[qualified.split('.')[1]])
            for qualified in SDK_AST}
        constructor=self.sdk_functions['PurePath.__init__']
        self.import_globals=constructor.__globals__ if 'ntpath' in constructor.__code__.co_varnames else None

        def replacement(op,original):
            @wraps(original)
            def wrapped(subject,*args,**kwargs):
                if kwargs:return fallback(op,original,subject,args,kwargs)
                value=self.call(op,self.plan,subject,args)
                if value is NotImplemented:return fallback(op,original,subject,args,kwargs)
                name=ROLES[op];self.calls[name]+=1;require(self.calls[name]<=10000000)
                return value
            return wrapped
        def fallback(op,original,subject,args,kwargs):
            name=ROLES[op];self.fallbacks[name]+=1;require(self.fallbacks[name]<=10000000)
            return original(subject,*args,**kwargs)
        self.replacements=tuple(replacement(op,fn) for op,fn in enumerate(self.originals))
        self.entries=tuple((owner,name,old,new) for (owner,name),old,new in zip(TARGETS,self.originals,self.replacements))

        self.tables=self.binding_tables()
        self.plan=None if _prepare_only else native.path_plan(
            self.tables,self.concrete,*self.owner,256,self.import_globals)

    def binding_tables(self,extra=(),*,originals=False):
        shared=[]
        def capture(owner,names):
            namespace=vars(owner)
            for name in names:require(name in namespace);shared.append((namespace,name,namespace[name]))
        capture(pathlib,('Path','PurePath','PosixPath','PurePosixPath','PureWindowsPath','os','sys','posixpath'))
        if 'ntpath' in vars(pathlib):capture(pathlib,('ntpath',))
        capture(builtins,('type','str','isinstance','len','object','super','AttributeError','__import__','map','bytes'))
        capture(os,('fspath',));capture(sys,('intern',))
        capture(sys,('modules',));shared.append((sys.modules,'ntpath',ntpath))
        capture(posixpath,('join','splitroot','splitdrive','_get_sep','os','sep','altsep'))
        shared.extend((vars(self.native),name,getattr(self.native,name)) for name in (*APIS,*extra))
        # Raw class descriptors and function code are separate live bindings.
        # In-place code and class-cell changes must not reuse a prior admission.
        for owner in (pathlib.Path,pathlib.PurePath,pathlib.PurePosixPath,object):
            for name in ('__new__','__getattribute__','__setattr__','_flavour','_raw_paths','_drv','_root','_tail_cached','_str'):
                if name in vars(owner):shared.append((owner,name,vars(owner)[name]))
        for qualified,fn in self.sdk_functions.items():
            shared.append((fn,'__code__',fn.__code__))
            for cell in fn.__closure__ or ():
                shared.append((cell,'cell_contents',cell.cell_contents))
        for owner,name,raw,new in self.entries:shared.append((owner,name,raw if originals else new))
        replacement_names={} if originals else {name:new for _owner,name,_old,new in self.entries}
        # Native class rows resolve raw descriptors through the current MRO.
        # Checking only the defining class would miss a new concrete-class
        # shadow of an inherited slot, flavour or helper.
        for name in ('__new__','__init__','__getattribute__','__setattr__','_flavour',
                '_raw_paths','_drv','_root','_tail_cached','_str','_load_parts','__str__',
                'with_segments','_parse_path','_format_parsed_parts','drive','root','_tail'):
            current=inspect.getattr_static(self.concrete,name)
            defining=(pathlib.Path if name in {'__new__','__init__'} else
                object if name in {'__getattribute__','__setattr__'} else
                (pathlib.PurePosixPath if self.concrete is pathlib.PosixPath else pathlib.PureWindowsPath)
                if name=='_flavour' else pathlib.PurePath)
            require(current is vars(defining)[name])
            shared.append((self.concrete,name,replacement_names.get(name,current)))
        for fn in self.originals if originals else self.replacements:
            if type(fn) is types.FunctionType:shared.append((fn,'__code__',fn.__code__))
        for name in ('_parse_path','_format_parsed_parts','drive','root','_tail'):
            shared.append((pathlib.PurePath,name,vars(pathlib.PurePath)[name]))
        for _owner,_name,value in tuple(shared):
            fn=raw_function(value)
            if type(fn) is types.FunctionType:shared.append((fn,'__code__',fn.__code__))
        shared=list({(id(owner),name,id(value)):(owner,name,value) for owner,name,value in shared}.values())
        tables=tuple(tuple(shared) for _ in ROLES)
        require(all(len(table)<=128 for table in tables))
        return tables

    def check(self):
        self.owner_check();require(not self.broken and not self.closed and self.owner==(os.getpid(),threading.get_ident()))

    def restored(self):return all(vars(owner).get(name) is old for owner,name,old,_new in self.entries)

    def values(self):
        if self.closed:
            require(self.final_values is not None);return self.final_values.copy()
        value=self.call(4,self.plan,None,())
        require(type(value) is dict and set(value)==set(ROLES)|{'cache_entries','cache_hits','cache_misses'})
        require(all(type(v) is int and 0<=v<=10000000 for v in value.values()) and value['cache_entries']<=256)
        return value

    def clear(self):
        self.call(5,self.plan,None,());require(self.values()['cache_entries']==0)

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

    def close(self):
        if self.closed:return
        require(not self.active)
        pending=sys.exception()
        self.final_values=None
        try:
            self.clear();self.final_values=self.values()
        except BaseException:
            self.broken=True
            if pending is None:raise
        finally:
            # The admission tables retain wrapper closures. Drop the capsule
            # even on failure so its owned references cannot keep this context
            # alive after the comparison has ended.
            self.plan=None;self.closed=True


class DescriptorAdapter(Adapter):
    """C-bound methods and code-input notifications; scoped and diagnostic."""
    def __init__(self,native,*,owner_check=None,sdk_codes=None):
        # Authenticate the SDK's super binding before any call through it,
        # including preparation in this helper itself.
        Adapter.__init__(self,native,owner_check=owner_check,sdk_codes=sdk_codes,_prepare_only=True)
        self.descriptor_apis={name:getattr(native,name) for name in DESCRIPTOR_APIS}
        if owner_check is None:
            require(all(type(fn) is types.BuiltinFunctionType and fn.__self__ is native
                and fn.__module__=='_native_metadata_probe' and fn.__name__==name
                for name,fn in self.descriptor_apis.items()))
        self.plan=native.descriptor_plan(self.concrete,self.originals,*self.owner,256,self.import_globals)
        try:
            self.replacements=native.descriptor_entries(self.plan)
            require(type(self.replacements) is tuple and len(self.replacements)==4)
            self.entries=tuple((owner,name,old,new) for (owner,name),old,new in zip(
                TARGETS,self.originals,self.replacements))
            self.tables=self.binding_tables(DESCRIPTOR_APIS)
            self.modules=(pathlib,builtins,os,sys,posixpath,ntpath,native)
            native.descriptor_bind(self.plan,self.tables,self.modules)
            self.values()
        except BaseException:
            pending=sys.exception()
            try:native.descriptor_close(self.plan)
            except BaseException:pass
            self.plan=None;self.closed=True;self.broken=True
            raise pending

    def details(self):
        if self.closed:
            require(self.final_details is not None)
            return {name:value.copy() if type(value) is dict else value for name,value in self.final_details.items()}
        result=self.descriptor_apis['descriptor_counts'](self.plan)
        require(type(result) is dict and set(result)=={'calls','entries','fallbacks','cache_entries',
            'cache_hits','cache_misses','phase','watching','code_changed','code_inputs'})
        for name in ('calls','entries','fallbacks'):
            value=result[name]
            require(type(value) is dict and set(value)==set(ROLES)
                and all(type(v) is int and 0<=v<=10000000 for v in value.values()))
        for name in ('cache_entries','cache_hits','cache_misses','code_inputs'):
            require(type(result[name]) is int and 0<=result[name]<=10000000)
        require(result['cache_entries']<=256 and result['code_inputs']<=256
            and type(result['phase']) is str and result['phase'] in {'prepared','inactive','active','closed'}
            and type(result['watching']) is bool and type(result['code_changed']) is bool)
        return result

    def values(self):
        details=self.details()
        self.calls=details['calls'].copy();self.fallbacks=details['fallbacks'].copy()
        return {**self.calls,**{name:details[name] for name in ('cache_entries','cache_hits','cache_misses')}}

    @contextmanager
    def installed(self):
        self.check();require(not self.active and self.restored());self.active=True;changed=[]
        try:
            for owner,name,old,new in self.entries:
                changed.append((owner,name,old));setattr(owner,name,new)
            self.descriptor_apis['descriptor_phase'](self.plan,0)
            yield
            self.check();require(all(vars(owner).get(name) is new for owner,name,_old,new in self.entries))
        finally:
            pending=sys.exception();errors=[]
            try:self.descriptor_apis['descriptor_phase'](self.plan,1)
            except BaseException as error:errors.append(error)
            for owner,name,old in reversed(changed):
                try:setattr(owner,name,old)
                except BaseException as error:errors.append(error)
            self.active=False;self.broken=bool(errors) or not self.restored()
            if pending is None:require(not self.broken)

    def clear(self):
        # Clearing also ends this context. Reuse requires a fresh prepared
        # schema; a saved descriptor continues through the original SDK.
        self.close()

    def close(self):
        if self.closed:return
        require(not self.active)
        pending=sys.exception();self.final_details=None
        try:
            self.descriptor_apis['descriptor_close'](self.plan)
            self.final_details=self.details()
            require(self.final_details['cache_entries']==0 and not self.final_details['watching']
                and self.final_details['phase']=='closed' and self.final_details['code_inputs']==0)
        except BaseException:
            self.broken=True
            if pending is None:raise
        finally:
            self.plan=None;self.tables=();self.modules=();self.closed=True


def compare_guard(loaded,original_guard,stage,*,adapter_type=None):
    """Twenty alternating original-actor pairs; restore and clear before effects."""
    metadata.root_owner();require(stage.usable and stage.state=='ready' and sys.getprofile() is None)
    monitoring=getattr(sys,'monitoring',None)
    require(monitoring is None or monitoring.get_tool(monitoring.PROFILER_ID) is None)
    adapter=(Adapter if adapter_type is None else adapter_type)(loaded.native,sdk_codes=loaded.codes)
    rows=[];started=time.monotonic_ns()
    try:
        initial=adapter.values()
        for number in range(20):
            values={};elapsed={}
            for selected in ((0,1) if number%2==0 else (1,0)):
                adapter.check();require(stage.usable and stage.state=='ready');before=adapter.values()
                if selected:
                    with adapter.installed():
                        begin=time.monotonic_ns()
                        try:values[selected]=original_guard(stage)
                        finally:elapsed[selected]=max(0,time.monotonic_ns()-begin)
                else:
                    begin=time.monotonic_ns()
                    try:values[selected]=original_guard(stage)
                    finally:elapsed[selected]=max(0,time.monotonic_ns()-begin)
                require(adapter.restored() and stage.usable and stage.state=='ready')
                after=adapter.values()
                for name in ROLES:
                    require(after[name]>before[name] if selected else after[name]==before[name])
            require(values[0]==values[1]);values.clear()
            require(all(type(value) is int and 0<value<=1200000000000 for value in elapsed.values()))
            rows.append({'baseline_us':max(1,elapsed[0]//1000),'prototype_us':max(1,elapsed[1]//1000)})
        final=adapter.values();native={name:final[name]-initial[name] for name in ROLES}
        require(all(0<value<=10000000 for value in native.values())
            and native==adapter.calls and not any(adapter.fallbacks.values()))
        descriptor_details=None
        if isinstance(adapter,DescriptorAdapter):
            descriptor_details=adapter.details()
            require(descriptor_details['entries']==descriptor_details['calls']
                and not descriptor_details['watching'] and not descriptor_details['code_changed'])
        result={'diagnostic_only':True,'production_adopted':False,'original_classes_retained':True,
            'original_descriptors_restored':True,'module_path_symbols_retained':True,'same_original_actors':True,
            'observations_equal':True,'observation_results_retained':False,'admission_results_retained':False,
            'pairs':rows,'paired_checks':40,'native_calls':native,'fallbacks':adapter.fallbacks.copy(),
            'cache_capacity':256,'lexical_cache_entries':final['cache_entries'],
            'lexical_cache_hits':final['cache_hits'],'lexical_cache_misses':final['cache_misses']}
        if descriptor_details is not None:
            result.update(implementation='C-bound-live-code-inputs',native_entries=descriptor_details['entries'],
                dictionary_notifications_removed=True,code_inputs=descriptor_details['code_inputs'])
    finally:adapter.close()
    require(adapter.restored() and adapter.values()['cache_entries']==0)
    loaded.validate()
    result.update(lexical_cache_cleared=True,elapsed_ms=min(1200000,max(0,(time.monotonic_ns()-started)//1000000)),
        **loaded.evidence())
    return result


def compare_descriptor_guard(loaded,original_guard,stage):
    loaded.validate()
    return compare_guard(loaded,original_guard,stage,adapter_type=DescriptorAdapter)


class AtFirstGuard:
    """Run the materially changed comparison before original measurements."""
    def __init__(self,loaded,stage_owner,measurements,*,comparison=None):
        self.loaded=loaded;self.stage_owner=stage_owner;self.measurements=measurements
        self.original=vars(stage_owner)['check'];self.entered=False;self.attempted=False;self.result=None
        self.comparison=comparison
    def __enter__(self):
        def first(stage,*args,**kwargs):
            try:
                require(not self.attempted and not args and not kwargs);self.attempted=True
                self.result=(compare_guard if self.comparison is None else self.comparison)(self.loaded,self.original,stage)
                self.stage_owner.check=self.original;self.measurements.__enter__();self.entered=True
                return self.stage_owner.check(stage)
            except BaseException:
                stage.usable=False;stage.allocation.usable=False
                for close in (stage.close,stage.allocation.close):
                    try:close()
                    except BaseException:pass
                raise
        self.stage_owner.check=first;return self
    def __exit__(self,*exc):
        pending=exc[1];failure=None
        try:
            if self.entered:self.measurements.__exit__(*exc)
        except BaseException as error:failure=error
        try:self.stage_owner.check=self.original
        except BaseException as error:
            if failure is None:failure=error
        if pending is None and failure is not None:raise failure
        return False
