"""Closed source selection for a future hosted path-body diagnostic.

No compilation, class substitution or filesystem observation occurs here.
Only global loads in selected bodies become explicit live dictionary lookups.
"""
import ast
import copy
import hashlib
import io
import tokenize

TARGETS = {
    'PurePath': ('__init__','with_segments','_parse_path','_load_parts','__str__',
        '__fspath__','_str_normcase','__hash__','drive','root','anchor','parts',
        'parent','parents','__truediv__'),
    'Path': ('resolve','stat','lstat'),
    '_PathParents': ('__len__','__getitem__'),
}
LOOKUP = '_gitgood_path_body_name'


def require(value):
    if not value:raise ValueError('Path body source diagnostic invariant')


def compiler_quoting(text):
    """Use conservative f-string delimiters without changing the parsed tree.

    CPython3.12's unparser may reuse an outer single quote inside an f-string
    expression. The pinned compiler uses an older f-string parser. Alternating
    triple delimiters avoid that syntax; conflicting literal delimiters refuse.
    """
    tokens=[];stack=[]
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type==tokenize.FSTRING_START:
            require(token.string in {"f'",'f"',"f'''",'f"""'})
            quote='"""' if len(stack)%2==0 else "'''"
            stack.append(quote);token=token._replace(string='f'+quote)
        elif token.type==tokenize.FSTRING_END:
            require(stack);token=token._replace(string=stack.pop())
        elif stack and token.type in {tokenize.FSTRING_MIDDLE,tokenize.STRING}:
            require(not any(quote in token.string for quote in stack))
        tokens.append(token)
    require(not stack)
    generated=tokenize.untokenize(tokens)
    require(ast.dump(ast.parse(generated))==ast.dump(ast.parse(text)))
    return generated


class LiveGlobalLoads(ast.NodeTransformer):
    """Preserve Python lexical scopes, including first-iterator evaluation."""
    def __init__(self):
        self.scopes=[];self.loads=0

    @staticmethod
    def locals(node):
        names={arg.arg for arg in [*node.args.posonlyargs,*node.args.args,*node.args.kwonlyargs]}
        for arg in [node.args.vararg,node.args.kwarg]:
            if arg is not None:names.add(arg.arg)
        class Bindings(ast.NodeVisitor):
            def visit_Name(self,item):
                if isinstance(item.ctx,(ast.Store,ast.Del)):names.add(item.id)
            def visit_FunctionDef(self,item):names.add(item.name)
            def visit_ClassDef(self,item):names.add(item.name)
            def visit_Lambda(self,item):pass
            def visit_Import(self,item):
                names.update(alias.asname or alias.name.split('.')[0] for alias in item.names)
            def visit_ImportFrom(self,item):
                require(all(alias.name!='*' for alias in item.names))
                names.update(alias.asname or alias.name for alias in item.names)
            def visit_ExceptHandler(self,item):
                if item.name:names.add(item.name)
                self.generic_visit(item)
            # Comprehension targets do not bind the surrounding function.
            def visit_ListComp(self,item):pass
            def visit_SetComp(self,item):pass
            def visit_DictComp(self,item):pass
            def visit_GeneratorExp(self,item):pass
        visitor=Bindings()
        for item in node.body if isinstance(node,ast.FunctionDef) else [node.body]:visitor.visit(item)
        return names

    def visit_ClassDef(self,node):
        require(not node.bases and not node.keywords and not node.decorator_list)
        require(not self.scopes)  # Donor classes are module-level, never nested.
        node.body=[self.visit(item) for item in node.body]
        return node

    def visit_FunctionDef(self,node):
        # The closed source has only literal defaults. Do not change class-body
        # evaluation or decorators to accommodate an unsupported source shape.
        for value in [*node.args.defaults,*[x for x in node.args.kw_defaults if x is not None]]:
            try:ast.literal_eval(value)
            except (ValueError,TypeError):require(False)
        self.scopes.append(self.locals(node))
        try:node.body=[self.visit(item) for item in node.body]
        finally:self.scopes.pop()
        return node

    def visit_Lambda(self,node):
        node.args.defaults=[self.visit(item) for item in node.args.defaults]
        node.args.kw_defaults=[self.visit(item) if item is not None else None for item in node.args.kw_defaults]
        self.scopes.append(self.locals(node))
        try:node.body=self.visit(node.body)
        finally:self.scopes.pop()
        return node

    def comprehension(self,node,name,values):
        # Python evaluates the first iterable outside the comprehension's
        # implicit function; targets, filters and later iterables are inside.
        first=node.generators[0];first.iter=self.visit(first.iter)
        names={item.id for generator in node.generators for item in ast.walk(generator.target)
            if isinstance(item,ast.Name) and isinstance(item.ctx,ast.Store)}
        self.scopes.append(names)
        try:
            for index,generator in enumerate(node.generators):
                require(not generator.is_async)
                if index:generator.iter=self.visit(generator.iter)
                generator.target=self.visit(generator.target)
                generator.ifs=[self.visit(item) for item in generator.ifs]
            for field in values:setattr(node,field,self.visit(getattr(node,field)))
        finally:self.scopes.pop()
        return node

    def visit_ListComp(self,node):return self.comprehension(node,'listcomp',('elt',))
    def visit_SetComp(self,node):return self.comprehension(node,'setcomp',('elt',))
    def visit_DictComp(self,node):return self.comprehension(node,'dictcomp',('key','value'))
    def visit_GeneratorExp(self,node):return self.comprehension(node,'genexpr',('elt',))

    def visit_Name(self,node):
        if isinstance(node.ctx,ast.Load) and self.scopes:
            if not any(node.id in names for names in self.scopes):
                self.loads+=1
                return ast.copy_location(ast.Call(func=ast.Name(id=LOOKUP,ctx=ast.Load()),
                    args=[ast.Constant(node.id)],keywords=[]),node)
        return node


def redirect_globals(tree):
    """Return transformed donor definitions and a structural equivalence check."""
    original=ast.parse(ast.unparse(tree))
    require(not any(isinstance(item,ast.Name) and item.id==LOOKUP
        or isinstance(item,ast.arg) and item.arg==LOOKUP
        or isinstance(item,(ast.FunctionDef,ast.ClassDef)) and item.name==LOOKUP
        or isinstance(item,ast.alias) and (item.asname==LOOKUP or item.name==LOOKUP)
        for item in ast.walk(original)))
    # Python 3.12 inlines list/set/dict comprehensions. Explicit lexical scopes
    # preserve their bindings without relying on version-specific symtables.
    require(not any(isinstance(item,(ast.NamedExpr,ast.Global,ast.Nonlocal,ast.AsyncFunctionDef))
        for item in ast.walk(original)))
    transformer=LiveGlobalLoads()
    transformed=ast.fix_missing_locations(transformer.visit(copy.deepcopy(original)))
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


def select_source(source):
    """Select only the exact bounded allowlist from the hosted stdlib source."""
    require(type(source) is str and 0<len(source.encode('utf-8'))<=262144)
    tree=ast.parse(source);require(sum(1 for _ in ast.walk(tree))<=30000)
    classes={item.name:item for item in tree.body if isinstance(item,ast.ClassDef)}
    donors=[];rows=[]
    for owner,names in TARGETS.items():
        require(owner in classes)
        methods={item.name:item for item in classes[owner].body if isinstance(item,ast.FunctionDef)}
        selected=[]
        for name in names:
            require(name in methods);method=copy.deepcopy(methods[name])
            require(not any(isinstance(item,(ast.Global,ast.Nonlocal,ast.AsyncFunctionDef,ast.NamedExpr,ast.AnnAssign))
                or isinstance(item,ast.arg) and item.annotation is not None
                or isinstance(item,ast.FunctionDef) and item.returns is not None
                or isinstance(item,ast.Name) and item.id in {'super','__class__',LOOKUP}
                for item in ast.walk(method)))
            decorators=[ast.unparse(item) for item in method.decorator_list]
            require(decorators in ([],['classmethod'],['property']))
            selected.append(method)
            rows.append({'owner':owner,'method':name,'descriptor':decorators[0] if decorators else 'function',
                'body_ast_sha256':hashlib.sha256(ast.dump(method).encode()).hexdigest()})
        donors.append(ast.ClassDef(name=owner,bases=[],keywords=[],body=selected,decorator_list=[]))
    donor=ast.fix_missing_locations(ast.Module(body=donors,type_ignores=[]))
    generated,loads=redirect_globals(donor)
    require(len(rows)==20 and 0<loads<=2048)
    # Syntax validation only. Never execute the supplied source in this tool.
    compile(generated,'<path-body-source>','exec')
    return generated,{'original_source_sha256':hashlib.sha256(source.encode()).hexdigest(),
        'generated_source_sha256':hashlib.sha256(generated.encode()).hexdigest(),
        'bodies':rows,'live_global_loads':loads,'global_loads_only_transformed':True,
        'original_classes_replaced':False,'compiled':False}
