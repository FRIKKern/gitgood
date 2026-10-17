"""Historical fixed SELECT experiment for the pre-preparation exchange AST.

Not active in the Root proof or production. Retained to explain the controlled
comparison; current preparation is tested through production reader methods.
"""
import ast
import copy
import hashlib
import inspect
from pathlib import Path
import sys
import textwrap
import time
from types import MethodType
import uuid


def require(value):
    if not value:raise ValueError('Prepared SELECT diagnostic invariant')


class PreparedExchange:
    """Change only statement construction in the exact original exchange AST.

    Retain session statement names, never query results or validation. The
    production function's framing, fresh base checks and poison path remain.
    """
    NAMES = {'identity': 'gitgood_probe_identity', 'exclusion': 'gitgood_probe_exclusion'}

    def __init__(self, module, reader):
        self.module = module;self.reader = reader;self.child = reader.child
        self.prepared = set();self.calls = 0
        self.original = vars(module.NativeRootDatabaseReader)['_exchange']
        require(inspect.isfunction(self.original) and self.original.__name__ == '_exchange')
        source = textwrap.dedent(inspect.getsource(self.original))
        tree = ast.parse(source)
        require(len(tree.body) == 1 and isinstance(tree.body[0], ast.FunctionDef)
            and tree.body[0].name == '_exchange' and not tree.body[0].decorator_list)
        assignments = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)
            and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'raw']
        expected = ast.parse('("SELECT json_build_object(\'nonce\',\'"+nonce+"\',\'reader\',("+READER_SQL+"),\'value\',("+statement+"));\\n").encode()', mode='eval').body
        require(len(assignments) == 1 and ast.dump(assignments[0].value) == ast.dump(expected))
        original_tree = copy.deepcopy(tree)
        assignments[0].value = ast.parse('_diagnostic_query(self, kind, nonce, statement)', mode='eval').body
        namespace = dict(self.original.__globals__)
        namespace['_diagnostic_query'] = self.query
        exec(compile(ast.fix_missing_locations(tree), __file__, 'exec'), namespace)
        self.function = namespace['_exchange']
        # An exact inverse transformation must recover every original node.
        assignments[0].value = expected
        require(ast.dump(tree) == ast.dump(original_tree))
        self.source_sha256 = hashlib.sha256(source.encode()).hexdigest()

    def query(self, reader, kind, nonce, statement):
        require(reader is self.reader and reader.child is self.child)
        require(type(kind) is str and kind in self.NAMES)
        require(type(nonce) is str and str(uuid.UUID(nonce)) == nonce)
        expected = self.module.SQL if kind == 'identity' else self.module.ROOT_EXCLUSION_SQL
        require(statement == expected)
        name = self.NAMES[kind];prefix = ''
        if kind not in self.prepared:
            prefix = ("PREPARE " + name + "(text) AS SELECT json_build_object('nonce',$1,'reader',(" +
                self.module.READER_SQL + "),'value',(" + statement + "));\n")
            self.prepared.add(kind)
        self.calls += 1
        return (prefix + "EXECUTE " + name + "('" + nonce + "');\n").encode()

    def cleanup(self):
        """Remove only these session plans, then verify an original fresh reply."""
        if not self.prepared:return
        reader = self.reader
        require(reader.usable and reader.child is self.child)
        reader._base()
        raw = ''.join('DEALLOCATE ' + self.NAMES[kind] + ';\n' for kind in sorted(self.prepared)).encode()
        require(reader.child.stdin.write(raw) == len(raw));reader.child.stdin.flush()
        # Quiet psql suppresses command tags. This original framed exchange
        # independently catches an error, stray output or changed original actor.
        self.original(reader, 'identity')
        reader._base();self.prepared.clear()


def compare_guard(module, original_guard, stage):
    require(stage.usable and stage.state == 'ready' and sys.getprofile() is None)
    monitoring = getattr(sys, 'monitoring', None)
    require(monitoring is None or monitoring.get_tool(monitoring.PROFILER_ID) is None)
    reader = stage.allocation.exclusion.live.database_reader
    require(type(reader) is module.NativeRootDatabaseReader and reader.usable)
    sentinel = object();original_attribute = vars(reader).get('_exchange', sentinel)
    require(original_attribute is sentinel)
    probe = PreparedExchange(module, reader)
    prototype = MethodType(probe.function, reader)
    started = time.monotonic_ns();rows = []
    def restore():
        if original_attribute is sentinel:
            if '_exchange' in vars(reader):delattr(reader, '_exchange')
        else:setattr(reader, '_exchange', original_attribute)
    try:
        for number in range(20):
            elapsed = {};values = {}
            for selected in ((0, 1) if number % 2 == 0 else (1, 0)):
                require(stage.usable and stage.state == 'ready' and reader.usable)
                if selected:reader._exchange = prototype
                else:restore()
                before = time.monotonic_ns();calls = probe.calls
                try:values[selected] = original_guard(stage)
                finally:
                    elapsed[selected] = max(0, time.monotonic_ns() - before);restore()
                require(stage.usable and stage.state == 'ready' and reader.usable)
                require(probe.calls > calls if selected else probe.calls == calls)
            require(values[0] == values[1])
            require(all(0 <= value <= 1200000000000 for value in elapsed.values()))
            rows.append({'baseline_us': elapsed[0] // 1000, 'prototype_us': elapsed[1] // 1000})
        require(0 < probe.calls <= 10000000)
        probe.cleanup()
    finally:restore()
    require('_exchange' not in vars(reader) and vars(module.NativeRootDatabaseReader)['_exchange'] is probe.original)
    elapsed_ms = (time.monotonic_ns() - started) // 1000000
    require(0 <= elapsed_ms <= 1200000)
    return {'diagnostic_only': True, 'pairs': rows, 'extra_read_only_checks': 40,
        'prepared_exchange_calls': probe.calls, 'cleanup_original_exchanges': 1,
        'elapsed_ms': elapsed_ms, 'original_exchange_restored': True,
        'session_plans_removed': True, 'production_adoption': False,
        'adapter_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'original_exchange_sha256': probe.source_sha256}


class BeforeStageComparison:
    def __init__(self, module, stage_owner, measurements):
        self.module = module;self.stage_owner = stage_owner;self.measurements = measurements
        self.entered = False;self.attempted = False;self.result = None
        self.original = vars(stage_owner)['check']

    def __enter__(self):
        require(callable(self.original))
        def first(stage, *arguments, **keywords):
            try:
                require(not self.attempted and not arguments and not keywords);self.attempted = True
                self.result = compare_guard(self.module, self.original, stage)
                setattr(self.stage_owner, 'check', self.original)
                self.measurements.__enter__();self.entered = True
                return self.stage_owner.check(stage)
            except BaseException:
                stage.close();stage.allocation.close();raise
        setattr(self.stage_owner, 'check', first)
        return self

    def __exit__(self, *_):
        try:
            if self.entered:self.measurements.__exit__(None, None, None)
        finally:setattr(self.stage_owner, 'check', self.original)
