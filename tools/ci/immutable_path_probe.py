"""Fixture-only immutable lexical reuse; never retain an observation result."""
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path
import sys
import time

MODULE_NAMES = ('native_service_scope', 'native_durable_binding', 'native_root_database_reader')


def require(value):
    if not value:raise ValueError('Immutable path diagnostic invariant')


class PathFactory:
    def __init__(self, original=Path):
        self.original = original;self.concrete = type(original('/'))
        self.cache = OrderedDict();self.calls = 0;self.reused = 0;self.hits = 0;self.constructed = 0

    def __call__(self, *arguments, **keywords):
        self.calls += 1;require(self.calls <= 10000000)
        if not keywords and len(arguments) == 1 and type(arguments[0]) is self.concrete:
            self.reused += 1;return arguments[0]
        key = arguments if not keywords and 0 < len(arguments) <= 64 and all(type(value) is str
            for value in arguments) and sum(len(value) for value in arguments) <= 1024 else None
        if key is not None and key in self.cache:
            self.hits += 1;self.cache.move_to_end(key);return self.cache[key]
        value = self.original(*arguments, **keywords);self.constructed += 1
        if key is not None and type(value) is self.concrete and len(str(value)) <= 1024 and len(value.parts) <= 64:
            self.cache[key] = value
            if len(self.cache) > 64:self.cache.popitem(last=False)
        return value

    def values(self):
        return {'constructor_calls': self.calls, 'exact_path_reuses': self.reused,
            'string_plan_hits': self.hits, 'constructed': self.constructed, 'retained_lexical_plans': len(self.cache)}


@contextmanager
def installed(modules, factory):
    require(tuple(module.__name__ for module in modules) == MODULE_NAMES)
    originals = [(module, module.Path) for module in modules]
    require(all(original is factory.original for _module, original in originals))
    try:
        for module, _original in originals:module.Path = factory
        yield
    finally:
        for module, original in originals:module.Path = original


def compare_guard(modules, original_guard, stage):
    """Forty fresh read-only guards on original actors, then restore all symbols."""
    require(stage.usable and stage.state == 'ready' and sys.getprofile() is None)
    monitoring = getattr(sys, 'monitoring', None)
    require(monitoring is None or monitoring.get_tool(monitoring.PROFILER_ID) is None)
    factory = PathFactory();rows = [];started = time.monotonic_ns()
    try:
        for number in range(20):
            values = {};elapsed = {}
            for selected in ((0, 1) if number % 2 == 0 else (1, 0)):
                require(stage.usable and stage.state == 'ready')
                if selected:
                    with installed(modules, factory):
                        before = time.monotonic_ns()
                        try:values[selected] = original_guard(stage)
                        finally:elapsed[selected] = max(0, time.monotonic_ns() - before)
                else:
                    before = time.monotonic_ns()
                    try:values[selected] = original_guard(stage)
                    finally:elapsed[selected] = max(0, time.monotonic_ns() - before)
                require(all(module.Path is Path for module in modules))
                require(stage.usable and stage.state == 'ready')
            require(values[0] == values[1])
            require(all(type(value) is int and 0 <= value <= 1200000000000 for value in elapsed.values()))
            rows.append({'baseline_us': elapsed[0] // 1000, 'prototype_us': elapsed[1] // 1000})
        counts = factory.values();require(counts['constructor_calls'] > 0
            and counts['exact_path_reuses'] + counts['string_plan_hits'] > 0)
        return {'diagnostic_only': True, 'production_adopted': False, 'pairs': rows,
            'module_symbols_restored': True, 'metadata_results_retained': False,
            'observations_equal': True, 'same_original_actors': True, **counts,
            'elapsed_ms': min(1200000, max(0, (time.monotonic_ns() - started) // 1000000))}
    finally:factory.cache.clear()


class AtFirstGuard:
    """Run the read-only comparison before original method/CPU/profile counters."""
    def __init__(self, modules, stage_owner, measurements):
        self.modules = modules;self.stage_owner = stage_owner;self.measurements = measurements
        self.original = vars(stage_owner)['check'];self.entered = False;self.attempted = False;self.result = None

    def __enter__(self):
        require(callable(self.original))
        def first(stage, *arguments, **keywords):
            try:
                require(not self.attempted and not arguments and not keywords);self.attempted = True
                self.result = compare_guard(self.modules, self.original, stage)
                setattr(self.stage_owner, 'check', self.original)
                self.measurements.__enter__();self.entered = True
                return self.stage_owner.check(stage)
            except BaseException:
                stage.usable = False;stage.allocation.usable = False
                for close in (stage.close,stage.allocation.close):
                    try:close()
                    except BaseException:pass
                raise
        setattr(self.stage_owner, 'check', first);return self

    def __exit__(self, *_):
        try:
            if self.entered:self.measurements.__exit__(None, None, None)
        finally:setattr(self.stage_owner, 'check', self.original)
