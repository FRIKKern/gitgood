#!/usr/bin/env python3
"""Lexical-only reuse, original guard custody and hosted Root refusal checks."""
import ast
from contextlib import ExitStack
import io
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import immutable_path_probe as probe


def modules():return tuple(SimpleNamespace(__name__=name,Path=Path) for name in probe.MODULE_NAMES)


class LexicalFactoryTest(unittest.TestCase):
    def test_exact_paths_reuse_and_string_results_match_original_constructor(self):
        factory=probe.PathFactory();value=Path('/synthetic/leaf')
        self.assertIs(factory(value),value)
        for arguments in [('/',),('/a','b'),('.','a','..','b'),('unicođe','leaf')]:
            expected=Path(*arguments);first=factory(*arguments)
            self.assertEqual((type(first),first.parts,str(first)),(type(expected),expected.parts,str(expected)))
            self.assertIs(factory(*arguments),first)
        self.assertEqual(factory.values()['exact_path_reuses'],1)
        self.assertEqual(factory.values()['string_plan_hits'],4)

    def test_foreign_pathlike_and_subclasses_use_original_constructor_once(self):
        class PathLike:
            calls=0
            def __fspath__(self):self.calls+=1;return '/synthetic/leaf'
        original=Mock(wraps=Path);factory=probe.PathFactory(original);original.reset_mock()
        value=PathLike();self.assertEqual(factory(value),Path('/synthetic/leaf'))
        self.assertEqual(value.calls,1);original.assert_called_once_with(value)
        class SubPath(type(Path('/'))):pass
        original.reset_mock();value=SubPath('/synthetic/leaf')
        result=factory(value);self.assertIsNot(result,value);original.assert_called_once_with(value)
        self.assertEqual(factory.values()['retained_lexical_plans'],0)

    def test_retention_eviction_and_long_or_deep_constructor_inputs_are_bounded(self):
        factory=probe.PathFactory();first=factory('/synthetic/first')
        for number in range(1000):self.assertEqual(factory('/synthetic/'+str(number)),Path('/synthetic/'+str(number)))
        self.assertEqual(len(factory.cache),64);self.assertEqual(factory('/synthetic/first'),first)
        self.assertIsNot(factory('/synthetic/first'),first)
        before=list(factory.cache)
        for value in ['/'+'a'*1025,'/'+'/'.join(['a']*65)]:self.assertEqual(factory(value),Path(value))
        self.assertEqual(list(factory.cache),before)
        self.assertTrue(all(type(key) is tuple and all(type(part) is str for part in key)
            and type(value) is type(Path('/')) for key,value in factory.cache.items()))

    def test_constructor_errors_and_keywords_are_forwarded_without_revival(self):
        failure=RuntimeError('synthetic private');original=Mock(wraps=Path)
        factory=probe.PathFactory(original);original.reset_mock();original.side_effect=failure
        with self.assertRaises(RuntimeError) as caught:factory('/synthetic',unsupported=True)
        self.assertIs(caught.exception,failure);original.assert_called_once_with('/synthetic',unsupported=True)
        self.assertEqual(len(factory.cache),0)

    def test_lexical_planning_performs_no_filesystem_observation(self):
        value=Path('/synthetic/leaf');factory=probe.PathFactory()
        with patch.object(os,'stat',side_effect=AssertionError('No stat')), \
                patch.object(os,'lstat',side_effect=AssertionError('No lstat')), \
                patch.object(os,'readlink',side_effect=AssertionError('No readlink')):
            self.assertIs(factory(value),value)
            self.assertEqual(factory('/synthetic','leaf'),value)
            self.assertEqual(factory('/synthetic','leaf'),value)

    def test_symbol_restoration_on_interruption_preserves_exception_identity(self):
        targets=modules();factory=probe.PathFactory();failure=KeyboardInterrupt('synthetic')
        with self.assertRaises(KeyboardInterrupt) as caught:
            with probe.installed(targets,factory):
                self.assertTrue(all(module.Path is factory for module in targets));raise failure
        self.assertIs(caught.exception,failure);self.assertTrue(all(module.Path is Path for module in targets))

    def test_twenty_pairs_alternate_on_same_stage_and_restore_every_symbol(self):
        targets=modules();stage=SimpleNamespace(usable=True,state='ready');events=[]
        def guard(original):
            self.assertIs(original,stage);events.append(targets[0].Path is not Path)
            value=targets[0].Path('/synthetic/leaf');self.assertEqual(targets[1].Path(value),value)
            return {'original':True}
        result=probe.compare_guard(targets,guard,stage)
        self.assertEqual(events,[value for number in range(20) for value in ((False,True) if number%2==0 else (True,False))])
        self.assertEqual(len(result['pairs']),20);self.assertFalse(result['production_adopted'])
        self.assertFalse(result['metadata_results_retained']);self.assertTrue(all(module.Path is Path for module in targets))

    def test_failed_guard_restores_module_symbols_without_repeating_call(self):
        targets=modules();stage=SimpleNamespace(usable=True,state='ready');failure=RuntimeError('synthetic')
        def guard(_):
            if targets[0].Path is not Path:raise failure
            return None
        with self.assertRaises(RuntimeError) as caught:probe.compare_guard(targets,guard,stage)
        self.assertIs(caught.exception,failure);self.assertTrue(all(module.Path is Path for module in targets))

    def test_first_guard_restores_pointer_and_poisons_original_stage_on_failure(self):
        failure=KeyboardInterrupt('synthetic');measurements=SimpleNamespace(__enter__=Mock(),__exit__=Mock())
        class Stage:
            usable=True;state='ready'
            def __init__(self):self.allocation=Mock();self.closed=False
            def check(self):return None
            def close(self):self.closed=True;self.usable=False
        original=vars(Stage)['check'];stage=Stage()
        with patch.object(probe,'compare_guard',side_effect=failure),self.assertRaises(KeyboardInterrupt) as caught:
            with probe.AtFirstGuard(modules(),Stage,measurements):stage.check()
        self.assertIs(caught.exception,failure);self.assertIs(vars(Stage)['check'],original)
        self.assertTrue(stage.closed);stage.allocation.close.assert_called_once_with();measurements.__enter__.assert_not_called()

    def test_comparison_precedes_measurements_and_original_guard_runs_after_restoration(self):
        targets=modules();events=[]
        class Stage:
            usable=True;state='ready'
            def check(self):
                targets[0].Path('/synthetic/leaf');events.append('guard');return {'original':True}
        original=vars(Stage)['check']
        class Measurements:
            def __enter__(self):events.append('measurements-entered');return self
            def __exit__(self,*_):events.append('measurements-exited')
        with probe.AtFirstGuard(targets,Stage,Measurements()) as comparison:
            Stage().check()
            self.assertIs(vars(Stage)['check'],original)
        self.assertEqual(events,['guard']*40+['measurements-entered','guard','measurements-exited'])
        self.assertEqual(len(comparison.result['pairs']),20);self.assertTrue(all(module.Path is Path for module in targets))

    def test_cleanup_failures_do_not_mask_comparison_error_or_skip_other_close(self):
        failure=KeyboardInterrupt('original');measurements=SimpleNamespace(__enter__=Mock(),__exit__=Mock())
        class Stage:
            usable=True;state='ready'
            def __init__(self):self.allocation=SimpleNamespace(usable=True,close=Mock(side_effect=RuntimeError('cleanup')))
            def check(self):return None
            close=Mock(side_effect=RuntimeError('cleanup'))
        original=vars(Stage)['check'];stage=Stage()
        with patch.object(probe,'compare_guard',side_effect=failure),self.assertRaises(KeyboardInterrupt) as caught:
            with probe.AtFirstGuard(modules(),Stage,measurements):stage.check()
        self.assertIs(caught.exception,failure);self.assertIs(vars(Stage)['check'],original)
        self.assertFalse(stage.usable);self.assertFalse(stage.allocation.usable)
        stage.close.assert_called_once_with();stage.allocation.close.assert_called_once_with()

    def test_selected_modules_use_path_only_as_constructor(self):
        deployment=Path(__file__).resolve().parents[1]/'deployment'
        for name in probe.MODULE_NAMES:
            tree=ast.parse((deployment/(name+'.py')).read_bytes())
            parents={child:parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
            for node in ast.walk(tree):
                if isinstance(node,ast.Name) and node.id=='Path':
                    self.assertIsInstance(parents[node],ast.Call);self.assertIs(parents[node].func,node)


@unittest.skipUnless(sys.platform=='linux' and getattr(os,'getuid',lambda:-1)()==0,'Actual Linux Root required')
class ActualRootReuseTest(unittest.TestCase):
    def test_original_root_file_binding_and_reader_scopes_with_factory_active(self):
        deployment=Path(__file__).resolve().parents[1]/'deployment';sys.path.insert(0,str(deployment))
        import native_service_scope, native_durable_binding, native_root_database_reader
        targets=(native_service_scope,native_durable_binding,native_root_database_reader)
        suite=unittest.TestSuite()
        for name in ('test_native_service_file_custody','test_native_durable_binding','test_native_root_database_reader'):
            suite.addTests(unittest.defaultTestLoader.loadTestsFromName(name))
        factory=probe.PathFactory()
        with probe.installed(targets,factory):
            result=unittest.TextTestRunner(stream=io.StringIO()).run(suite)
        self.assertEqual(result.testsRun,57);self.assertFalse(result.skipped)
        failed=[]
        for test,_detail in [*result.errors,*result.failures]:
            original=getattr(test,'test_case',test)
            failed.append(type(original).__module__+'.'+type(original).__name__+'.'+original._testMethodName)
        self.assertTrue(result.wasSuccessful(), 'Original Root component refusal checks failed: '+','.join(failed))
        self.assertGreater(factory.calls,0);self.assertLessEqual(len(factory.cache),64)
        self.assertTrue(all(module.Path is Path for module in targets))
        print('immutable_path_original_root_cases=57',flush=True)

if __name__=='__main__':sys.dont_write_bytecode=True;unittest.main(verbosity=2)
