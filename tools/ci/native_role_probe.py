"""Complete native observation-role diagnostic with original SDK descriptors.

Only immutable lexical parse inputs survive a role. Source, defaults, owner and
code admission stay fresh; the original ordered I/O implementations are reused.
This is a candidate boundary, not evidence of native execution or acceptance.
"""
import _collections_abc
import ast
from contextlib import contextmanager
from functools import wraps
import hashlib
import inspect
import io
import os
import pathlib
import sys
import threading
import time
import types

import native_path_probe as sdk
import native_read_probe as read_backend
from native_metadata_probe import require,raw_function
from path_body_probe import _read_owned

APIS=('role_prepare','role_observe','role_admit','role_counts','role_configure','role_imports','role_code_watch')
FAMILIES=read_backend.FAMILIES
HELPERS=(*sdk.HELPERS,'native_role_probe.py')
ROLE_AST={
    '_PathParents.__init__':'37d6f2c89355b64cf5ee04e8401658baf980c8815931566f4ce210b7f8a352ab',
    '_PathParents.__len__':'25ce0df09a7d99f706f95c8e717af795399d7fa183948e34d9b60a8242bcd95f',
    '_PathParents.__getitem__':'3e10b87dfea197084b0c1ad78a68b86b2e92f22b73fc2c14c3041688ea65cc32',
    'PurePath._from_parsed_parts':'483f6f0aae4500d7352dc10be6d9c34cfdc91a803baf3fcd9880748c86768d9e',
    'PurePath.anchor':'9278c7a5098438cdbbeec0b15d44feffae3c5e0b8a7a711ae8225fae5e1e8596',
    'PurePath.parts':'3a424123c81d2ccbfa516d3ae66669dd2471a7331728b31c12565d9681fba468',
    'PurePath.parent':'20352617bc98b46a28bddf5a7a0a3dd6d596bf269a89911c4b2e9707bb5e3e24',
    'PurePath.parents':'1f341e610d928488e1a4fed92ac49ca6628f71ba64a7e57169d8c3e0225f8f1d',
    'PurePath.is_absolute':'fb8af10a4a597be309dd785709206ebc78026da7e9f228c1fe8e00acf5d3dea8',
    'PurePath.name':'18e7ff1d0eb7efe1d9063b38335c3bd115662cbd2127d5e474126f620e31dbbd',
}
SEQUENCE_AST={'Sequence.__iter__':'4a086e76281364abf81c7e6855d85958329fc54d93f334152ab3c5823548d0e8'}
ROLE_ALTERNATIVES={'PurePath.is_absolute':{
    # Ubuntu moves ntpath out of python-minimal and imports it in each body.
    '5aa5f7addb8b30e625ab935bc6e784abf6d6f51919d25369eb1427669792012b'}}


def contract_code(raw,filename,expected,alternatives=None):
    require(type(raw) is bytes and 0<len(raw)<=262144)
    tree=ast.parse(raw);require(sum(1 for _ in ast.walk(tree))<=30000);found={}
    for owner in tree.body:
        if not isinstance(owner,ast.ClassDef):continue
        for node in owner.body:
            name=owner.name+'.'+getattr(node,'name','')
            if name not in expected:continue
            require(isinstance(node,ast.FunctionDef) and name not in found)
            if (node.body and isinstance(node.body[0],ast.Expr) and isinstance(node.body[0].value,ast.Constant)
                    and type(node.body[0].value.value) is str):node.body=node.body[1:]
            found[name]=hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest()
    alternatives={} if alternatives is None else alternatives
    different=[name for name,value in expected.items() if found.get(name)!=value
        and found.get(name) not in alternatives.get(name,())]
    require(set(found)==set(expected))
    if different:raise ValueError('SDK role body differs: '+','.join(sorted(different)))
    return sdk.metadata.functions(compile(raw,filename,'exec'))


def declared_defaults(raw):
    """Extract literal defaults from authenticated source without executing it."""
    found={}
    def visit(nodes,prefix=''):
        for node in nodes:
            if isinstance(node,ast.ClassDef):visit(node.body,prefix+node.name+'.')
            elif isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                name=prefix+node.name
                try:
                    positional=tuple(ast.literal_eval(value) for value in node.args.defaults) or None
                    keyword={key.arg:ast.literal_eval(value) for key,value in zip(node.args.kwonlyargs,node.args.kw_defaults)
                        if value is not None} or None
                    found[name]=(positional,keyword)
                except (ValueError,TypeError):pass
                visit(node.body,name+'.<locals>.')
    visit(ast.parse(raw).body)
    return found


def same_defaults(fn,expected):
    # bool and int compare equal in Python, but are different admitted inputs.
    def literal(a,b):return type(a) is type(b) and a==b
    positional,keyword=expected;actual=fn.__defaults__;kwactual=fn.__kwdefaults__
    return ((actual is None if positional is None else type(actual) is tuple and len(actual)==len(positional)
        and all(literal(a,b) for a,b in zip(actual,positional)))
        and (kwactual is None if keyword is None else type(kwactual) is dict and kwactual.keys()==keyword.keys()
        and all(literal(kwactual[key],value) for key,value in keyword.items())))


def role_environment():
    sdk.sdk_environment();parents=pathlib._PathParents;sequence=_collections_abc.Sequence
    concrete=pathlib.PosixPath if os.name=='posix' else pathlib.WindowsPath
    for owner in (parents,concrete):require(not any('__del__' in vars(base) for base in owner.__mro__))
    require(type(_collections_abc) is types.ModuleType and pathlib.Sequence is sequence
        and parents.__module__=='pathlib' and parents.__bases__==(sequence,)
        and inspect.getattr_static(parents,'__iter__') is vars(sequence)['__iter__']
        and inspect.getattr_static(parents,'__new__') is vars(object)['__new__']
        and inspect.getattr_static(type(parents),'__call__') is vars(type)['__call__'])
    for owner in (parents,sequence,type(parents)):
        require(inspect.getattr_static(owner,'__getattribute__') is vars(object if owner is not type(parents) else type)['__getattribute__'])
        require(not any('__getattr__' in vars(base) for base in owner.__mro__))
    require(inspect.getattr_static(parents,'__setattr__') is vars(object)['__setattr__'])
    for name in ('bool','int','tuple','list','slice','range','IndexError','TypeError','BytesWarning'):
        cls=vars(sdk.builtins)[name]
        require(type(cls) is type and cls.__name__==name and cls.__module__=='builtins' and not cls.__flags__&512)
    for name in ('anchor','parts','parent','parents','name'):
        require(type(vars(pathlib.PurePath)[name]) is property)
    for qualified in ROLE_AST:
        owner,name=qualified.split('.')
        if owner=='PurePath':require(inspect.getattr_static(concrete,name) is vars(pathlib.PurePath)[name])
    for name in ('_path','_drv','_root','_tail'):
        slot=vars(parents)[name]
        require(type(slot) is types.MemberDescriptorType and slot.__objclass__ is parents and slot.__name__==name)


def merge_bindings(*groups):
    """Normalise class rows to raw descriptors for the native MRO checker."""
    rows={}
    for group in groups:
        for owner,name,value in group:
            require(type(owner) in {dict,types.FunctionType,types.CellType} or isinstance(owner,type))
            if isinstance(owner,type):
                raw=inspect.getattr_static(owner,name)
                if type(value) is types.MethodType:
                    require(raw_function(raw) is value.__func__);value=raw
                elif raw_function(raw) is value:value=raw
            key=(id(owner),name)
            if key in rows:require(rows[key][2] is value)
            rows[key]=(owner,name,value)
    require(0<len(rows)<=512)
    return tuple(rows.values())


def role_bindings(concrete):
    rows=[]
    for module,names in ((pathlib,('_PathParents','Sequence','warnings')),(os,('name',)),
            (sdk.posixpath,('genericpath',)),
            (sdk.builtins,('bool','int','tuple','list','slice','range','IndexError','TypeError','BytesWarning'))):
        rows.extend((vars(module),name,vars(module)[name]) for name in names)
    parents=pathlib._PathParents;sequence=_collections_abc.Sequence
    for owner,names in ((parents,('__init__','__len__','__getitem__','__iter__','__new__','__getattribute__','__setattr__',
                '_path','_drv','_root','_tail')),(type(parents),('__call__','__getattribute__','__setattr__')),
            (concrete,('_from_parsed_parts','anchor','parts','parent','parents','is_absolute','name',
                '__eq__','__hash__','_str_normcase','_parts_normcase','_str_normcase_cached','_hash'))):
        rows.extend((owner,name,inspect.getattr_static(owner,name)) for name in names)
    rows.append((sequence,'__iter__',vars(sequence)['__iter__']))
    for _owner,_name,value in tuple(rows):
        fn=raw_function(value)
        if type(fn) is types.FunctionType:
            rows.append((fn,'__code__',fn.__code__))
            rows.extend((cell,'cell_contents',cell.cell_contents) for cell in fn.__closure__ or ())
    return tuple(rows)


class Loaded:
    def __init__(self,directory,*,base=None):
        self.base=sdk.Loaded(directory) if base is None else base
        self.directory=self.base.directory;require(pathlib.Path(directory)==self.directory)
        self.native=self.base.native;self.modules=self.base.base.modules;self.kernel=self.base.base.kernel
        self.original_codes=self.base.base.original_codes;self.codes=dict(self.base.codes)
        require(all(type(getattr(self.native,name,None)) is types.BuiltinFunctionType
            and getattr(self.native,name).__module__=='_native_metadata_probe'
            and getattr(self.native,name).__name__==name for name in APIS))
        self.apis={name:getattr(self.native,name) for name in APIS}
        self.file=_read_owned(self.directory/'native_role_probe.py',262144)
        require(self.file[0]==pathlib.Path(__file__).read_bytes())
        self.sequence_path=pathlib.Path(_collections_abc.__file__);self.sequence=_read_owned(self.sequence_path,262144)
        self.codes.update(contract_code(self.base.sdk[0],str(self.base.sdk_path),ROLE_AST,ROLE_ALTERNATIVES))
        iteration=_collections_abc.Sequence.__iter__
        self.sequence_codes=contract_code(self.sequence[0],iteration.__code__.co_filename,SEQUENCE_AST)
        self.sdk_defaults=declared_defaults(self.base.sdk[0])
        self.role_functions=[]
        for qualified in ROLE_AST:
            owner,name=qualified.split('.');fn=raw_function(vars(getattr(pathlib,owner))[name])
            self.role_functions.append((fn,self.codes[qualified],vars(pathlib)))
        self.role_functions.append((iteration,self.sequence_codes['Sequence.__iter__'],vars(_collections_abc)))
        own_codes=sdk.metadata.functions(compile(self.file[0],__file__,'exec'));self.own_codes=own_codes
        for value in (*vars(sys.modules[__name__]).values(),
                *(v for owner in (Loaded,RoleContext,Adapter) for v in vars(owner).values())):
            fn=raw_function(value)
            for candidate in (fn,getattr(fn,'__wrapped__',None)):
                if type(candidate) is types.FunctionType and candidate.__code__.co_filename==__file__:
                    self.role_functions.append((candidate,own_codes[candidate.__code__.co_qualname],globals()))
        self.helper_files={}
        for fn in (require,read_backend.metadata.Adapter.count,read_backend.metadata.Adapter.after):
            name=pathlib.Path(fn.__code__.co_filename).name
            if name not in self.helper_files:self.helper_files[name]=_read_owned(self.directory/name,262144)
            code=sdk.metadata.functions(compile(self.helper_files[name][0],fn.__code__.co_filename,'exec'))
            self.role_functions.append((fn,code[fn.__code__.co_qualname],vars(sys.modules[fn.__module__])))
        self.function_closures={id(fn):(fn.__closure__,tuple((cell,cell.cell_contents) for cell in fn.__closure__ or ()))
            for fn,_code,_namespace in self.role_functions}
        for fn,_code,namespace in self.role_functions:
            for name,cell in zip(fn.__code__.co_freevars,fn.__closure__ or ()):
                if name=='__class__':require(cell.cell_contents is namespace[fn.__qualname__.split('.')[0]])
        sources={**self.base.base.base.runtime_files,**self.base.base.runtime_files,
            self.base.sdk_path:self.base.sdk,self.base.posix_path:self.base.posix,
            self.sequence_path:self.sequence,pathlib.Path(__file__):self.file}
        sources.update({pathlib.Path(fn.__code__.co_filename):self.helper_files[pathlib.Path(fn.__code__.co_filename).name]
            for fn,_code,_namespace in self.role_functions if pathlib.Path(fn.__code__.co_filename).name in self.helper_files})
        declarations={path:declared_defaults(value[0]) for path,value in sources.items()}
        self.defaults=[]
        functions={id(fn):fn for fn in (*self.base.base.base.original_functions,*self.base.base.extra_functions,
            *(fn for fn,_code,_namespace in self.role_functions))}
        for fn in functions.values():
            source=(pathlib.Path(os.__file__) if fn is os.fdopen else self.sequence_path if fn is iteration
                else pathlib.Path(fn.__code__.co_filename))
            expected=declarations.get(source,{}).get(fn.__code__.co_qualname)
            # Every captured role/code input must have authenticated defaults.
            require(expected is not None);self.defaults.append((fn,expected))
        self.validate()

    def validate(self):
        for qualified in ROLE_AST:
            owner,name=qualified.split('.');current=raw_function(vars(getattr(pathlib,owner))[name])
            require(any(fn is current and code==self.codes[qualified] for fn,code,_space in self.role_functions))
        require(_collections_abc.Sequence.__iter__ is self.role_functions[len(ROLE_AST)][0])
        concrete=pathlib.PosixPath if os.name=='posix' else pathlib.WindowsPath
        for name in ('stat','lstat','resolve','iterdir','__fspath__','__eq__','__hash__','_str_normcase','_parts_normcase'):
            fn=raw_function(inspect.getattr_static(concrete,name))
            require(type(fn) is types.FunctionType and fn.__globals__ is vars(pathlib)
                and fn.__builtins__ is vars(sdk.builtins) and fn.__code__==self.codes.get(fn.__code__.co_qualname)
                and same_defaults(fn,self.sdk_defaults[fn.__code__.co_qualname]))
        for module in self.modules:
            require(vars(module).get('Path') is pathlib.Path)
            if 'os' in vars(module):require(vars(module)['os'] is os)
            if 'stat' in vars(module):require(vars(module)['stat'] is read_backend.metadata.stat)
        for name in ('stat','lstat','fstat','open','listdir','scandir','fspath'):
            fn=vars(os)[name]
            require(type(fn) is types.BuiltinFunctionType and fn.__module__==os.name and fn.__name__==name)
        for name in ('S_ISDIR','S_ISREG','S_IMODE'):
            fn=vars(read_backend.metadata.stat)[name]
            require(type(fn) is types.BuiltinFunctionType and fn.__module__=='_stat' and fn.__name__==name)
        service,binding,_generation,lifecycle=self.modules
        for owner,names in ((service,('_root_file_path','_root_file_parents','_root_file_parent_plan')),
                (binding,('_canonical_private_path',)),(lifecycle._RootReadOnlyCustody,('_file','_names','_directory_metadata'))):
            for name in names:
                raw=vars(owner)[name];fn=raw_function(raw)
                if name=='_root_file_parent_plan':
                    require(type(raw).__module__=='functools' and type(raw).__name__=='_lru_cache_wrapper')
                    fn=raw.__wrapped__
                if name in ('_names','_directory_metadata'):require(type(raw) is staticmethod)
                require(type(fn) is types.FunctionType and fn.__code__==self.original_codes.get(id(fn)))
        for fn,code,namespace in self.role_functions:
            require(type(fn) is types.FunctionType and fn.__code__==code and fn.__globals__ is namespace
                and fn.__builtins__ is vars(sdk.builtins))
            closure,cells=self.function_closures[id(fn)]
            require(fn.__closure__ is closure and all(cell.cell_contents is value for cell,value in cells))
        require(all(same_defaults(fn,expected) for fn,expected in self.defaults))
        require(all(vars(self.native).get(name) is value for name,value in self.apis.items()))
        role_environment();self.base.validate()
        require(_read_owned(self.directory/'native_role_probe.py',262144)==self.file)
        require(_read_owned(self.sequence_path,262144)==self.sequence)
        for name,value in self.helper_files.items():require(_read_owned(self.directory/name,262144)==value)

    def evidence(self):
        value=self.base.evidence()
        value['source_hashes']={**value['source_hashes'],'native_role_probe.py':hashlib.sha256(self.file[0]).hexdigest()}
        contract=(sorted(ROLE_AST.items()),sorted((name,sorted(values)) for name,values in ROLE_ALTERNATIVES.items()),
            sorted(SEQUENCE_AST.items()))
        value['role_ast_sha256']=hashlib.sha256(repr(contract).encode()).hexdigest()
        value['original_source_hashes']={**value['original_source_hashes'],
            '_collections_abc.py':hashlib.sha256(self.sequence[0]).hexdigest()}
        return value


class RoleContext:
    def __init__(self,loaded,*,owner_check=None,bindings=(),modules=()):
        self.loaded=loaded;self.native=loaded.native
        self.owner_check=sdk.metadata.root_owner if owner_check is None else owner_check
        self.owner_check();sdk.sdk_environment();loaded.validate()
        prepared=sdk.Adapter(self.native,owner_check=owner_check,sdk_codes=loaded.codes,_prepare_only=True)
        self.owner=prepared.owner;self.originals=prepared.originals
        self.tables=prepared.binding_tables((*sdk.DESCRIPTOR_APIS,*(APIS if bindings else ())),originals=True)
        if bindings:
            merged=merge_bindings(self.tables[0],bindings)
            self.tables=tuple(merged for _ in sdk.ROLES)
        self.apis={name:getattr(self.native,name) for name in sdk.DESCRIPTOR_APIS}
        self.active=False;self.closed=False;self.broken=False;self.final_details=None
        self.absolute_import=False
        self.plan=self.apis['descriptor_plan'](prepared.concrete,self.originals,*self.owner,256,prepared.import_globals)
        try:
            # The current context API requires issuing its descriptors once.
            # They are discarded here: no SDK class receives a replacement.
            self.apis['descriptor_entries'](self.plan)
            if bindings:
                absolute=raw_function(vars(pathlib.PurePath)['is_absolute'])
                self.absolute_import='ntpath' in absolute.__code__.co_varnames
                require(not self.absolute_import or prepared.import_globals is vars(pathlib))
                self.native.role_configure(self.plan,self.absolute_import)
            bound_modules=tuple({id(module):module for module in
                (pathlib,sdk.builtins,os,sys,sdk.posixpath,sdk.ntpath,self.native,*modules)}.values())
            require(len(bound_modules)<=16)
            self.apis['descriptor_bind'](self.plan,self.tables,bound_modules)
            require(self.sdk_original())
        except BaseException:
            pending=sys.exception()
            try:self.apis['descriptor_close'](self.plan)
            except BaseException:pass
            self.plan=None;self.tables=();self.closed=True;self.broken=True
            raise pending

    def sdk_original(self):
        return all(vars(owner).get(name) is original
            for (owner,name),original in zip(sdk.TARGETS,self.originals))

    def check(self):
        self.owner_check()
        require(not self.closed and not self.broken and self.owner==(os.getpid(),threading.get_ident()))

    @contextmanager
    def admitted(self):
        self.check();require(not self.active and self.sdk_original())
        self.loaded.validate()
        try:
            self.apis['descriptor_phase'](self.plan,0);self.active=True
            yield self
            self.check();require(self.sdk_original())
        finally:
            pending=sys.exception();failure=None
            try:self.apis['descriptor_phase'](self.plan,1)
            except BaseException as error:failure=error
            self.active=False;self.broken=failure is not None or not self.sdk_original()
            if pending is None:
                if failure is not None:raise failure
                require(not self.broken)

    def close(self):
        if self.closed:return
        require(not self.active);pending=sys.exception()
        try:
            self.apis['descriptor_close'](self.plan)
            self.final_details=self.apis['descriptor_counts'](self.plan)
            require(self.final_details['phase']=='closed' and not self.final_details['watching']
                and self.final_details['code_inputs']==0 and self.final_details['cache_entries']==0)
        except BaseException:
            self.broken=True
            if pending is None:raise
        finally:
            self.plan=None;self.tables=();self.closed=True


class Adapter(read_backend.Adapter):
    """Replace the eight complete roles; leave every SDK descriptor original."""
    def __init__(self,loaded,*,owner_check=None):
        loaded.validate();role_environment()
        super().__init__(loaded.modules,loaded.native,loaded.kernel,owner_check=owner_check,
            original_codes=loaded.original_codes,_class_owners=True)
        self.loaded=loaded;self.closed=False;self.final_roles=None;self.final_imports=None;self.final_code_watch=None
        self.role_apis={name:getattr(self.native,name) for name in APIS}
        self.callbacks=(os.listdir,self.names_callback,io.open,io.BufferedReader)
        original_root=self.originals[0].__func__;original_exec=self.originals[1].__func__
        original_plan=self.originals[2];original_custody=self.originals[3]
        original_reads=self.read_originals;plan_owner=self.owners[2];custody_owner=self.owners[3]

        def fallback(family,fn,*args,**kwargs):
            self.fallbacks[family]+=1;require(self.fallbacks[family]<=10000000)
            return fn(*args,**kwargs)

        def prepare(kind,payload,owner=None):
            if not self.eligible(FAMILIES[kind]):return NotImplemented
            return self.role_apis['role_prepare'](self.context.plan,kind,payload,owner)

        def observe(kind,arguments):
            value=self.role_apis['role_observe'](self.context.plan,kind,arguments,self.callbacks)
            # A supported prepared role must never retry through its original
            # after observation dispatch, even if a callback changed admission.
            require(value is not NotImplemented);self.count(FAMILIES[kind])
            owner=(self.service,self.binding,self.generation,self.lifecycle,
                self.service,self.binding,self.service,self.kernel)[kind]
            owner.require(value is not None);self.after(FAMILIES[kind]);return value

        @wraps(original_root)
        def root_files(path,maximum,executable):
            arguments=prepare(0,(path,maximum,executable))
            if arguments is NotImplemented:return fallback('root_files',original_root,path,maximum,executable)
            return observe(0,arguments)

        @wraps(original_exec)
        def executables(raw):
            arguments=prepare(1,(raw,))
            if arguments is NotImplemented:return fallback('executables',original_exec,raw)
            value=observe(1,arguments);return arguments[0],value[0],value[1]

        @wraps(original_plan)
        def persistent(subject):
            arguments=prepare(2,subject,plan_owner)
            if arguments is NotImplemented:return fallback('persistent',original_plan,subject)
            return observe(2,arguments)

        @wraps(self.original_custody_body)
        def custody(subject):
            if type(subject) is not custody_owner or any(key in vars(subject) for key in ('_file','_names','_directory_metadata')):
                return fallback('custody',self.original_custody_body,subject)
            if vars(subject).get('usable') is not True or vars(subject).get('owner')!=self.owner:
                return fallback('custody',self.original_custody_body,subject)
            arguments=prepare(3,subject,custody_owner)
            if arguments is NotImplemented:return fallback('custody',self.original_custody_body,subject)
            self.lifecycle.require(subject.usable and self.lifecycle.root_owner()==subject.owner)
            self.lifecycle.require(self.lifecycle.private_directory(subject.root,subject.uid,subject.gid)==subject.root_custody)
            self.lifecycle.require(observe(3,arguments) is True)

        @wraps(original_reads[0])
        def root_file(path,maximum=16777216,*,executable=False):
            arguments=prepare(4,(path,0,maximum,executable))
            if arguments is NotImplemented:return fallback('root_file',original_reads[0],path,maximum,executable=executable)
            raw,before,after=observe(4,arguments)
            self.service.require(len(raw)==before[2]);self.service.require(before==after)
            return {'path':arguments[0],'device':before[0],'inode':before[1],
                'bytes':before[2],'sha256':self.service.hashlib.sha256(raw).hexdigest()},raw

        @wraps(original_reads[1])
        def private_file(path,uid,maximum=131072):
            arguments=prepare(5,(path,uid,maximum,False))
            if arguments is NotImplemented:return fallback('private_file',original_reads[1],path,uid,maximum)
            raw,before,after=observe(5,arguments)
            self.binding.require(len(raw)==before[2] and before==after)
            return {'path':arguments[0],'device':before[0],'inode':before[1],'uid':uid,
                'bytes':before[2],'sha256':self.binding.hashlib.sha256(raw).hexdigest()},raw

        @wraps(original_reads[2])
        def read_bytes(path,maximum=16384):
            arguments=prepare(6,(path,maximum))
            if arguments is NotImplemented:return fallback('read_bytes',original_reads[2],path,maximum)
            raw,_before,_after=observe(6,arguments)
            self.service.require(len(raw)<=maximum);return raw

        @wraps(original_reads[3])
        def kernel_read(path,maximum=16384):
            arguments=prepare(7,(path,maximum))
            if arguments is NotImplemented:return fallback('kernel_read',original_reads[3],path,maximum)
            raw,_before,_after=observe(7,arguments)
            self.kernel.require(0<len(raw)<=maximum);return raw.decode('ascii')

        wrapped_custody=self.lifecycle._within_root_observation_pass(custody)
        replacements=(staticmethod(root_files),staticmethod(executables),persistent,wrapped_custody,
            root_file,private_file,read_bytes,kernel_read)
        self.entries=tuple((owner,name,old,new) for (owner,name,old,_previous),new in zip(self.entries,replacements))
        self.read_replacements=replacements[4:];self.read_entries=self.entries[4:]
        rows=merge_bindings(*(self.family_bindings[name] for name in FAMILIES),role_bindings(self.path_type))
        # These original helpers are captured as code, while only their public
        # role entry points are temporarily replaced in the active schema.
        entries={(id(owner),name):(owner,name,new) for owner,name,_old,new in self.entries}
        adjusted=[]
        for owner,name,value in rows:
            key=(id(owner),name)
            replacement=entries.get(key)
            if replacement is None and type(owner) is dict:
                replacement=next(((owner,name,new) for target,key,_old,new in self.entries
                    if name==key and owner is vars(target)),None)
            adjusted.append((owner,name,value) if replacement is None else replacement)
        rows=tuple(adjusted)
        code_inputs=[]
        for fn,key,_value in rows:
            if type(fn) is types.FunctionType:
                code_inputs.extend((cell,'cell_contents',cell.cell_contents) for cell in fn.__closure__ or ())
        for fn in (fallback,prepare,observe,*(raw_function(value) for value in replacements),custody,
                Adapter.eligible,read_backend.metadata.Adapter.count,read_backend.metadata.Adapter.after,require):
            if fn.__code__.co_filename==__file__ and hasattr(loaded,'own_codes'):
                require(fn.__code__==loaded.own_codes[fn.__code__.co_qualname])
            code_inputs.append((fn,'__code__',fn.__code__))
            code_inputs.extend((cell,'cell_contents',cell.cell_contents) for cell in fn.__closure__ or ())
        extra=(*rows,*code_inputs,
            (Adapter,'eligible',vars(Adapter)['eligible']),
            (read_backend.metadata.Adapter,'count',vars(read_backend.metadata.Adapter)['count']),
            (read_backend.metadata.Adapter,'after',vars(read_backend.metadata.Adapter)['after']),
            (globals(),'require',require),(globals(),'FAMILIES',FAMILIES),
            *((self.role_apis,name,value) for name,value in self.role_apis.items()),
            *((owner if isinstance(owner,type) else vars(owner),name,value) for owner,name,_old,value in self.entries))
        modules=(*self.modules,self.kernel,io,sys.modules['_io'],read_backend.metadata.stat,hashlib)
        self.context=RoleContext(loaded,owner_check=owner_check,bindings=extra,modules=modules)

    def eligible(self,family=None):
        return (not self.closed and not self.broken and self.active and self.context.active
            and self.role_apis['role_admit'](self.context.plan))

    @contextmanager
    def installed(self):
        require(not self.closed)
        with super().installed():
            with self.context.admitted():yield self

    def values(self):
        if self.closed:return self.final_roles
        value=self.role_apis['role_counts'](self.context.plan)
        require(type(value) is tuple and len(value)==2 and all(type(row) is tuple and len(row)==8
            and all(type(v) is int and 0<=v<=10000000 for v in row) for row in value))
        return value

    def imports(self):
        if self.closed:return self.final_imports
        value=self.role_apis['role_imports'](self.context.plan)
        require(type(value) is tuple and len(value)==2 and type(value[0]) is bool
            and type(value[1]) is int and 0<=value[1]<=10000000
            and value[0] is self.context.absolute_import and (value[0] or value[1]==0))
        return value

    def code_watch(self):
        if self.closed:return self.final_code_watch
        value=self.role_apis['role_code_watch'](self.context.plan)
        require(type(value) is tuple and len(value)==5 and type(value[0]) is bool
            and all(type(v) is int and 0<=v<=10000000 for v in value[1:]))
        return value

    def close(self):
        if self.closed:return
        pending=sys.exception()
        try:self.final_roles=self.values();self.final_imports=self.imports();self.final_code_watch=self.code_watch()
        except BaseException:
            if pending is None:raise
        finally:
            try:self.context.close()
            finally:self.closed=True


def compare_guard(loaded,original_guard,stage):
    """Same twenty alternating whole-guard pairs, with all role witnesses."""
    sdk.metadata.root_owner();loaded.validate()
    require(stage.usable and stage.state=='ready' and sys.getprofile() is None)
    monitoring=getattr(sys,'monitoring',None)
    require(monitoring is None or monitoring.get_tool(monitoring.PROFILER_ID) is None)
    adapter=Adapter(loaded);rows=[];started=time.monotonic_ns()
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
                require(adapter.restored() and adapter.context.sdk_original() and stage.usable and stage.state=='ready')
                after=adapter.values()
                require(all(a>=b if selected else a==b for old,new in zip(before,after) for b,a in zip(old,new)))
                if selected:require(all(sum(new)>sum(old) for old,new in zip(before,after)))
            require(values[0]==values[1]);values.clear()
            require(all(type(value) is int and 0<value<=1200000000000 for value in elapsed.values()))
            rows.append({'baseline_us':max(1,elapsed[0]//1000),'prototype_us':max(1,elapsed[1]//1000)})
        final=adapter.values()
        prepares=dict(zip(FAMILIES,(a-b for a,b in zip(final[0],initial[0]))))
        observations=dict(zip(FAMILIES,(a-b for a,b in zip(final[1],initial[1]))))
        details=adapter.context.apis['descriptor_counts'](adapter.context.plan)
        absolute,import_calls=adapter.imports()
        watching,activations,full_checks,fresh_checks,changes=adapter.code_watch()
        require(observations==adapter.calls and all(value>0 for value in prepares.values())
            and not any(adapter.fallbacks.values()) and all(value>0 for value in details['calls'].values())
            and not details['watching'] and not details['code_changed'])
        require(import_calls>0 if absolute else import_calls==0)
        require(not watching and activations>=20 and full_checks>=activations and fresh_checks>0 and changes==0)
        result={'diagnostic_only':True,'production_adopted':False,'implementation':'C-complete-observation-roles',
            'original_classes_retained':True,'original_descriptors_retained':True,'same_original_actors':True,
            'observations_equal':True,'observation_results_retained':False,'admission_results_retained':False,
            'pairs':rows,'paired_checks':40,'role_prepares':prepares,'native_calls':observations,
            'lexical_calls':details['calls'],'fallbacks':adapter.fallbacks.copy(),
            'absolute_import_required':absolute,'absolute_import_calls':import_calls,
            'function_watch_activations':activations,'full_function_checks':full_checks,
            'fresh_function_checks':fresh_checks,'function_mutations':changes,
            'cache_capacity':256,'lexical_cache_entries':details['cache_entries'],
            'lexical_cache_hits':details['cache_hits'],'lexical_cache_misses':details['cache_misses']}
    finally:adapter.close()
    require(adapter.restored() and adapter.context.sdk_original() and adapter.context.final_details['cache_entries']==0
        and adapter.context.final_details['code_inputs']==0 and not adapter.context.final_details['watching']
        and adapter.final_code_watch[0] is False)
    loaded.validate()
    result.update(lexical_cache_cleared=True,dictionary_notifications_removed=True,function_notifications_removed=True,code_inputs_released=True,
        elapsed_ms=min(1200000,max(0,(time.monotonic_ns()-started)//1000000)),**loaded.evidence())
    return result
