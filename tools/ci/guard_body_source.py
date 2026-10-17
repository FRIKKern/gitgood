"""Closed body selection for the hosted installed-code experiment.

No supplied source executes here. Production modules and classes are unchanged.
"""
import ast
import copy
import hashlib

from path_body_source import LOOKUP, LiveGlobalLoads, compiler_quoting

MODULE_NAMES = (
    'native_service_scope','native_systemd_properties','native_kernel_backend',
    'native_durable_binding','native_root_database_reader','native_root_lifecycle',
    'native_generation_lease_guard',
)
# These exclusions retain wrappers/closures exactly on the original interpreter.
EXCLUDED = {
    ('native_service_scope','','_root_file_parent_plan'),
    ('native_systemd_properties','ReadOnlySystemdProperties','_read_selected'),
    ('native_root_database_reader','NativeRootDatabaseReader','_configuration'),
    ('native_root_database_reader','NativeRootDatabaseReader','_stage_observation'),
    ('native_root_lifecycle','_RootReadOnlyCustody','check'),
    ('native_root_lifecycle','_RootLifecycleHistory','__init__'),
    ('native_root_lifecycle','NativeRootLifecycleObservation','_current'),
    ('native_root_lifecycle','NativeRootLifecycleObservation','check'),
}
BODY_COUNT = 116


def require(value):
    if not value:raise ValueError('Installed body source diagnostic invariant')


def constant_default(node):
    """Admit bounded literal arithmetic without evaluating supplied code."""
    try:
        value=ast.literal_eval(node)
        require(value is None or type(value) in {bool,int,float,str,bytes,tuple})
        if type(value) is int:require(abs(value)<=2**64)
        return value
    except (ValueError,TypeError):pass
    require(isinstance(node,ast.BinOp) and type(node.op) in {ast.Add,ast.Sub,ast.Mult,ast.Pow,ast.BitOr})
    left=constant_default(node.left);right=constant_default(node.right)
    require(type(left) is type(right) is int and 0<=left<=2**64 and 0<=right<=2**64)
    if isinstance(node.op,ast.Pow):require(right<=64 and left<=65536)
    if isinstance(node.op,ast.Add):value=left+right
    elif isinstance(node.op,ast.Sub):value=left-right
    elif isinstance(node.op,ast.Mult):value=left*right
    elif isinstance(node.op,ast.Pow):value=left**right
    else:value=left|right
    require(0<=value<=2**64);return value


def redirect_guard_globals(tree):
    original=ast.parse(ast.unparse(tree))
    class Loads(LiveGlobalLoads):
        def visit_FunctionDef(self,node):
            for default in [*node.args.defaults,*[x for x in node.args.kw_defaults if x is not None]]:
                constant_default(default)
            self.scopes.append(self.locals(node))
            try:node.body=[self.visit(item) for item in node.body]
            finally:self.scopes.pop()
            return node
    transformer=Loads();transformed=ast.fix_missing_locations(transformer.visit(copy.deepcopy(original)))
    class Undo(ast.NodeTransformer):
        def visit_Call(self,node):
            if isinstance(node.func,ast.Name) and node.func.id==LOOKUP:
                require(len(node.args)==1 and type(node.args[0]) is ast.Constant
                    and type(node.args[0].value) is str and not node.keywords)
                return ast.copy_location(ast.Name(id=node.args[0].value,ctx=ast.Load()),node)
            return self.generic_visit(node)
    restored=Undo().visit(copy.deepcopy(transformed))
    require(ast.dump(restored)==ast.dump(original))
    return compiler_quoting(ast.unparse(transformed)+'\n'),transformer.loads


def validate_donors(tree,rows):
    """No class or method may silently overwrite another selected body."""
    require(all(isinstance(node,ast.ClassDef) for node in tree.body))
    require(len({node.name for node in tree.body})==len(tree.body))
    actual=[(owner.name,node.name) for owner in tree.body for node in owner.body
        if isinstance(node,ast.FunctionDef)]
    expected=[(row['donor'],row['method']) for row in rows]
    require(len(actual)==len(set(actual))==len(expected)==len(set(expected))
        and set(actual)==set(expected))


def select_sources(sources):
    require(type(sources) is dict and tuple(sources)==MODULE_NAMES)
    donors=[];rows=[];hashes={};loads={};excluded=set()
    for number,(module,raw) in enumerate(sources.items()):
        require(type(raw) is bytes and 0<len(raw)<=262144)
        tree=ast.parse(raw);require(sum(1 for _ in ast.walk(tree))<=30000)
        hashes[module+'.py']=hashlib.sha256(raw).hexdigest()
        selected=[];groups={};first=len(rows)
        for node in tree.body:
            if isinstance(node,ast.FunctionDef):groups.setdefault('',[]).append(node)
            elif isinstance(node,ast.ClassDef):
                require(node.name not in groups)
                groups[node.name]=[item for item in node.body if isinstance(item,ast.FunctionDef)]
        for owner,functions in groups.items():
            bodies=[]
            for original in functions:
                key=(module,owner,original.name)
                if key in EXCLUDED:excluded.add(key);continue
                method=copy.deepcopy(original)
                require([ast.unparse(item) for item in method.decorator_list]
                    in ([],['classmethod'],['staticmethod'],['property']))
                require(not any(isinstance(item,(ast.Global,ast.Nonlocal,ast.AsyncFunctionDef,
                    ast.NamedExpr,ast.AnnAssign))
                    or isinstance(item,ast.arg) and item.annotation is not None
                    or isinstance(item,ast.FunctionDef) and item.returns is not None
                    or isinstance(item,ast.Name) and item.id in {'super','__class__',LOOKUP}
                    or isinstance(item,ast.Attribute) and item.attr.startswith('__')
                        and not item.attr.endswith('__')
                    for item in ast.walk(method)))
                descriptor=ast.unparse(method.decorator_list[0]) if method.decorator_list else 'function'
                donor='GuardBody'+str(number)+'_'+(owner or 'Top')
                rows.append({'module':module,'owner':owner,'method':method.name,'donor':donor,
                    'descriptor':descriptor,'body_ast_sha256':hashlib.sha256(ast.dump(method).encode()).hexdigest()})
                bodies.append(method)
            if bodies:selected.append(ast.ClassDef(name=donor,bases=[],keywords=[],body=bodies,decorator_list=[]))
        donor_tree=ast.fix_missing_locations(ast.Module(body=selected,type_ignores=[]))
        validate_donors(donor_tree,rows[first:])
        transformed,count=redirect_guard_globals(donor_tree)
        # Rename only the helper identifiers, after the existing inverse-AST check.
        transformed_tree=ast.parse(transformed)
        class Rename(ast.NodeTransformer):
            def visit_Name(self,node):
                if node.id==LOOKUP:node.id='_gitgood_guard_name_'+str(number)
                return node
        renamed=ast.fix_missing_locations(Rename().visit(transformed_tree))
        generated=compiler_quoting(ast.unparse(renamed)+'\n')
        validate_donors(ast.parse(generated),rows[first:])
        compile(generated,'<guard-body-source>','exec')
        donors.append(generated);loads[module]=count
    require(len(rows)==BODY_COUNT and excluded==EXCLUDED and all(0<value<=4096 for value in loads.values()))
    body='\n'.join(donors)
    validate_donors(ast.parse(body),rows)
    return body,{'original_source_hashes':hashes,'generated_source_sha256':hashlib.sha256(body.encode()).hexdigest(),
        'bodies':rows,'live_global_loads':loads,'global_loads_only_transformed':True,
        'original_classes_replaced':False,'compiled':False}


def header():
    """Seven fixed live dictionary bindings, with bounded native lookup counters."""
    text='# cython: language_level=3\ncdef object _missing = object()\n'
    for number in range(len(MODULE_NAMES)):
        text+=('cdef object _globals_'+str(number)+' = None\n'
            'cdef object _builtins_'+str(number)+' = None\n'
            'cdef unsigned long long _loads_'+str(number)+' = 0\n')
    text+='\ndef bind_original(globals_list, builtins_list):\n'
    text+='    if type(globals_list) is not list or type(builtins_list) is not list or len(globals_list) != 7 or len(builtins_list) != 7:\n        return False\n'
    for number in range(len(MODULE_NAMES)):
        n=str(number)
        text+='    global _globals_'+n+', _builtins_'+n+'\n'
        text+='    if type(globals_list['+n+']) is not dict or type(builtins_list['+n+']) is not dict:\n        return False\n'
        text+='    if _globals_'+n+' is not None and (_globals_'+n+' is not globals_list['+n+'] or _builtins_'+n+' is not builtins_list['+n+']):\n        return False\n'
    for number in range(len(MODULE_NAMES)):
        n=str(number);text+='    _globals_'+n+' = globals_list['+n+']\n    _builtins_'+n+' = builtins_list['+n+']\n'
    text+='    return True\n\ndef load_counts():\n    return {'
    text+=', '.join(repr(module)+': _loads_'+str(n) for n,module in enumerate(MODULE_NAMES))+'}\n'
    for number in range(len(MODULE_NAMES)):
        n=str(number)
        text+=('\ncdef inline object _gitgood_guard_name_'+n+'(object name):\n'
            '    global _loads_'+n+'\n    cdef object value\n'
            '    if _globals_'+n+' is None or _loads_'+n+' >= 100000000:\n'
            '        raise RuntimeError("Unbound or exhausted installed body diagnostic")\n'
            '    _loads_'+n+' += 1\n'
            '    value = _globals_'+n+'.get(name, _missing)\n'
            '    if value is _missing:\n        value = _builtins_'+n+'.get(name, _missing)\n'
            '    if value is _missing:\n        raise NameError("name " + repr(name) + " is not defined", name=name)\n'
            '    return value\n')
    return text
