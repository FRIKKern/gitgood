#!/usr/bin/env python3
"""Lexical plans, complete restoration and original hosted Root refusals."""
import io
import os
from pathlib import Path
import pathlib
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

sys.dont_write_bytecode=True
import lexical_path_probe as probe


def modules():return tuple(SimpleNamespace(__name__=name,Path=Path) for name in probe.MODULE_NAMES)
def adapter(targets=None):return probe.Adapter(modules() if targets is None else targets,owner_check=lambda:None)


class LexicalPlansTest(unittest.TestCase):
    def test_sdk_validation_reads_code_objects_without_executing_source(self):
        text=b"def dangerous(): raise RuntimeError('must not execute')\ndangerous()\nclass PurePath:\n def with_segments(self, *pathsegments):\n  'original documentation'\n  return type(self)(*pathsegments)\n"
        codes,digest=probe.sdk_code(text,'fixed-sdk.py')
        self.assertIn(('PurePath','with_segments'),codes)
        self.assertEqual(codes['PurePath','with_segments'].co_filename,'fixed-sdk.py')
        self.assertEqual(len(digest),64)
        real,digest=probe.sdk_code(Path(pathlib.__file__).read_bytes(),pathlib.__file__)
        self.assertEqual(real['PurePath','with_segments'],vars(pathlib.PurePath)['with_segments'].__code__)

    def test_sdk_changed_body_signature_decorator_and_size_refuse(self):
        bodies=(b'class PurePath:\n pass\n',
            b'class PurePath:\n def with_segments(self, *pathsegments): return 42\n',
            b'class PurePath:\n def with_segments(self, pathsegments): return type(self)(*pathsegments)\n',
            b'class PurePath:\n @staticmethod\n def with_segments(self, *pathsegments): return type(self)(*pathsegments)\n',
            b' '*262145,b'')
        for raw in bodies:
            with self.subTest(size=len(raw)),self.assertRaises(ValueError):probe.sdk_code(raw,'fixed-sdk.py')

    def test_original_classes_lexical_values_and_derived_paths_match(self):
        def observe():
            rows=[]
            for cls in (pathlib.PurePosixPath,pathlib.PureWindowsPath,type(Path('/'))):
                for raw in ('.','/','/a//b/../c','//server/share','/caf\u00e9/\u732b'):
                    value=cls(raw);derived=value/'child'
                    rows.append((type(derived),str(derived),derived.parts,derived.anchor,
                        str(derived.parent),tuple(str(parent) for parent in derived.parents),hash(derived)))
            return rows
        expected=observe();a=adapter();classes=(pathlib.Path,pathlib.PurePath,pathlib.PurePosixPath,pathlib.PureWindowsPath)
        with a.installed():
            self.assertEqual(observe(),expected);self.assertEqual(observe(),expected)
            self.assertEqual((pathlib.Path,pathlib.PurePath,pathlib.PurePosixPath,pathlib.PureWindowsPath),classes)
        self.assertTrue(a.restored());self.assertGreater(a.joins.hits,0)

    def test_pathlike_subclasses_and_original_baseexception_are_not_cached(self):
        failure=KeyboardInterrupt('synthetic private');calls=[]
        class PathLike:
            def __init__(self,value):self.value=value;self.calls=0
            def __fspath__(self):
                self.calls+=1
                if isinstance(self.value,BaseException):raise self.value
                return self.value
        class Child(pathlib.PurePosixPath):
            def __init__(self,*args):calls.append(args);super().__init__(*args)
        a=adapter();subject=pathlib.PurePosixPath('/synthetic');child=Child('/synthetic');calls.clear()
        with a.installed():
            for _ in range(2):
                value=PathLike('leaf');self.assertEqual(subject.with_segments(subject,value),subject/'leaf')
                self.assertEqual(value.calls,1)
                derived=child/'leaf';self.assertIs(type(derived),Child)
            bad=PathLike(failure)
            with self.assertRaises(KeyboardInterrupt) as caught:subject.with_segments(bad)
            self.assertIs(caught.exception,failure);self.assertEqual(bad.calls,1)
        self.assertEqual(len(calls),2);self.assertTrue(a.restored())

    def test_invalid_values_and_keywords_preserve_original_error_arguments(self):
        subject=pathlib.PurePosixPath('/synthetic');original=vars(pathlib.PurePath)['with_segments']
        def error(call):
            try:call()
            except TypeError as failure:return failure.args
            self.fail('Expected original TypeError')
        expected=[error(lambda item=item:original(subject,item)) for item in (b'bytes',None,7)]
        keyword=error(lambda:original(subject,unsupported=True));a=adapter()
        with a.installed():
            self.assertEqual([error(lambda item=item:subject.with_segments(item)) for item in (b'bytes',None,7)],expected)
            self.assertEqual(error(lambda:subject.with_segments(unsupported=True)),keyword)
        self.assertEqual(len(a.joins.cache),0)

    def test_mixed_path_flavours_and_raw_lexical_component_bounds_preserve_values(self):
        posix=pathlib.PurePosixPath('/base');windows=pathlib.PureWindowsPath('C:/base')
        original=vars(pathlib.PurePath)['with_segments']
        expected=[original(posix,windows,'leaf'),original(windows,posix,'leaf')];a=adapter()
        with a.installed():
            for _ in range(2):
                self.assertEqual([posix.with_segments(windows,'leaf'),windows.with_segments(posix,'leaf')],expected)
            before=list(a.joins.cache)
            many=pathlib.PurePosixPath(*(['']*64))
            self.assertEqual(posix.with_segments(many,many),pathlib.PurePosixPath('.'))
            self.assertEqual(list(a.joins.cache),before)

    def test_cache_is_bounded_lexical_only_with_eviction_and_long_deep_fallback(self):
        a=adapter();subject=pathlib.PurePosixPath('/synthetic')
        with a.installed():
            first=subject/'first'
            for number in range(1000):self.assertEqual(str(subject/str(number)),'/synthetic/'+str(number))
            self.assertEqual(len(a.joins.cache),256)
            self.assertIsNot(subject/'first',first);before=list(a.joins.cache)
            for value in ('a'*1025,'/'.join(['a']*65)):
                result=subject/value;self.assertEqual(str(result),'/synthetic/'+value)
            self.assertEqual(list(a.joins.cache),before)
            self.assertTrue(all(type(value) is pathlib.PurePosixPath for value in a.joins.cache.values()))
        a.clear();self.assertEqual(len(a.joins.cache),0);self.assertEqual(len(a.factory.cache),0)

    def test_lexical_plans_never_observe_filesystem(self):
        a=adapter();subject=pathlib.PurePosixPath('/synthetic')
        with patch.object(os,'stat',side_effect=AssertionError('No stat')), \
                patch.object(os,'lstat',side_effect=AssertionError('No lstat')), \
                patch.object(os,'readlink',side_effect=AssertionError('No readlink')):
            with a.installed():
                for _ in range(3):self.assertEqual(str(subject/'leaf'),'/synthetic/leaf')
        self.assertTrue(a.restored());self.assertEqual(a.joins.hits,2)

    def test_stat_lstat_and_replacement_observations_remain_fresh(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);leaf=root/'leaf';leaf.write_bytes(b'one');original=leaf.stat();a=adapter()
            with a.installed():
                held=root/'leaf';self.assertIs(root/'leaf',held)
                self.assertEqual(held.stat().st_size,3)
                leaf.write_bytes(b'changed bytes');self.assertEqual(held.lstat().st_size,13)
                leaf.rename(root/'retained');leaf.write_bytes(b'new file')
                self.assertEqual(held.stat().st_size,8);self.assertNotEqual(held.stat().st_ino,original.st_ino)
            self.assertTrue(a.restored())

    def test_nested_foreign_owner_and_namespace_changes_refuse(self):
        a=adapter()
        with a.installed():
            with self.assertRaises(ValueError):
                with a.installed():pass
        with patch.object(probe.threading,'get_ident',return_value=a.owner[1]+1),self.assertRaises(ValueError):a.check()
        try:
            with self.assertRaises(ValueError):
                with a.installed():pathlib.lexical_probe_unknown=object()
        finally:del pathlib.lexical_probe_unknown
        self.assertTrue(a.restored())
        original=pathlib.PurePath
        try:
            with self.assertRaises(ValueError):
                with a.installed():pathlib.PurePath=type('ForeignPath',(),{})
        finally:pathlib.PurePath=original
        self.assertTrue(a.restored())

    def test_descriptor_and_module_restoration_preserves_interruption(self):
        targets=modules();a=adapter(targets);failure=KeyboardInterrupt('synthetic')
        with self.assertRaises(KeyboardInterrupt) as caught:
            with a.installed():raise failure
        self.assertIs(caught.exception,failure);self.assertTrue(a.restored())
        self.assertTrue(all(module.Path is Path for module in targets))

    def test_foreign_thread_join_uses_original_constructor_without_plan_reuse(self):
        a=adapter();subject=pathlib.PurePosixPath('/synthetic')
        with a.installed():
            first=subject/'leaf';before=list(a.joins.cache);hits=a.joins.hits
            with patch.object(probe.threading,'get_ident',return_value=a.owner[1]+1):
                value=subject/'leaf';self.assertEqual(value,first);self.assertIsNot(value,first)
            self.assertEqual(list(a.joins.cache),before);self.assertEqual(a.joins.hits,hits)

    def test_partial_installation_restores_all_original_symbols(self):
        targets=modules();a=adapter(targets);failure=RuntimeError('synthetic install');changed=[]
        def assign(owner,name,value):
            changed.append((owner,name,value))
            if owner is targets[1] and value is a.factory:raise failure
            setattr(owner,name,value)
        with patch.object(probe,'setattr',assign,create=True),self.assertRaises(RuntimeError) as caught:
            with a.installed():self.fail('Partial installation entered')
        self.assertIs(caught.exception,failure);self.assertTrue(a.restored())
        self.assertTrue(any(owner is a.path_owner and value is a.original for owner,_name,value in changed))

    def test_cleanup_attempts_every_restore_and_preserves_pending_error(self):
        targets=modules();a=adapter(targets);failure=KeyboardInterrupt('synthetic');restored=[]
        def assign(owner,name,value):
            if owner is targets[0] and value is Path:raise RuntimeError('synthetic restore')
            setattr(owner,name,value);restored.append((owner,name,value))
        try:
            with patch.object(probe,'setattr',assign,create=True),self.assertRaises(KeyboardInterrupt) as caught:
                with a.installed():
                    del targets[0].Path
                    raise failure
            self.assertIs(caught.exception,failure);self.assertTrue(a.broken)
            self.assertIs(vars(a.path_owner)['with_segments'],a.original)
            self.assertIs(targets[1].Path,Path);self.assertIs(targets[2].Path,Path)
        finally:targets[0].Path=Path

    def test_twenty_pairs_keep_original_actors_and_restore_before_each_baseline(self):
        targets=modules();events=[];stage=SimpleNamespace(usable=True,state='ready');held=[]
        original_adapter=probe.Adapter
        def make_adapter(*args,**kwargs):
            value=original_adapter(*args,owner_check=lambda:None,**kwargs);held.append(value);return value
        loaded=SimpleNamespace(original_code=vars(pathlib.PurePath)['with_segments'].__code__,
            original_codes={(getattr(raw,'__func__',raw).__qualname__.split('.')[0],getattr(raw,'__func__',raw).__name__):getattr(raw,'__func__',raw).__code__
                for _owner,_name,raw in adapter().roles if hasattr(getattr(raw,'__func__',raw),'__code__')},validate=Mock(),evidence=lambda:{})
        def guard(subject):
            self.assertIs(subject,stage);events.append(targets[0].Path is not Path)
            self.assertEqual(str(targets[0].Path('/synthetic')/'leaf'),str(Path('/synthetic')/'leaf'))
            return {'same':True}
        with patch.object(probe,'root_owner'),patch.object(probe,'Adapter',make_adapter):
            result=probe.compare_guard(loaded,targets,guard,stage)
        self.assertEqual(events,[value for number in range(20) for value in ((False,True) if number%2==0 else (True,False))])
        self.assertEqual(len(result['pairs']),20);self.assertGreater(result['join_hits'],0)
        self.assertFalse(result['production_adopted']);self.assertFalse(result['observation_results_retained'])
        self.assertTrue(held[0].restored());self.assertEqual(len(held[0].joins.cache),0)
        self.assertEqual(len(held[0].factory.cache),0);loaded.validate.assert_called_once_with()

    def test_first_guard_failure_poisons_and_closes_both_original_views(self):
        failure=KeyboardInterrupt('synthetic')
        class Stage:
            usable=True;state='ready'
            def check(self):return None
        stage=Stage();stage.allocation=SimpleNamespace(usable=True,close=Mock())
        stage.close=Mock(side_effect=RuntimeError('synthetic cleanup'));original=vars(Stage)['check'];measurements=SimpleNamespace(__enter__=Mock(),__exit__=Mock())
        with patch.object(probe,'compare_guard',side_effect=failure),self.assertRaises(KeyboardInterrupt) as caught:
            with probe.AtFirstGuard(None,modules(),Stage,measurements):stage.check()
        self.assertIs(caught.exception,failure);self.assertIs(vars(Stage)['check'],original)
        self.assertFalse(stage.usable);self.assertFalse(stage.allocation.usable)
        stage.close.assert_called_once();stage.allocation.close.assert_called_once();measurements.__enter__.assert_not_called()

    def test_comparison_restores_symbols_before_measurement_and_effect_guard(self):
        targets=modules();events=[];original_descriptor=vars(pathlib.PurePath)['with_segments']
        class Stage:
            usable=True;state='ready'
            def check(self):events.append('guard');return {'same':True}
        class Measurements:
            def __enter__(self):
                self_outer.assertIs(vars(pathlib.PurePath)['with_segments'],original_descriptor)
                self_outer.assertTrue(all(module.Path is Path for module in targets));events.append('measurements')
            def __exit__(self,*_):events.append('restored')
        self_outer=self;original=vars(Stage)['check'];stage=Stage();result={'private_comparison':True}
        with patch.object(probe,'compare_guard',return_value=result) as compare:
            with probe.AtFirstGuard(None,targets,Stage,Measurements()) as comparison:
                self.assertEqual(stage.check(),{'same':True});self.assertIs(comparison.result,result)
        self.assertEqual(events,['measurements','guard','restored']);self.assertIs(vars(Stage)['check'],original)
        compare.assert_called_once_with(None,targets,original,stage)


ROOT_SCOPES=(('test_native_protected_artifact',20),('test_native_root_lifecycle',31),
    ('test_native_root_controller_request',17),('test_native_root_artifact_policy',16),
    ('test_native_artifact_controller',17),('test_native_root_artifact_dispatch',12),
    ('test_native_artifact_canonical_paths',16),('test_native_root_observation_pass',14),
    ('test_native_root_database_reader',24),('test_native_tcp_socket_observation',14),
    ('test_native_service_file_custody',16),('test_native_root_file_parent_plan',15),
    ('test_native_process_status',11),('test_native_systemd_properties',33),
    ('test_native_executable_capture',14),('test_native_durable_binding',17),
    ('test_native_persistent_fingerprint',30),('test_native_private_directory',14),
    ('test_native_root_configuration',20),('test_native_stage_controller_observer',10),
    ('test_native_root_live_binding',11))


@unittest.skipUnless(sys.platform=='linux' and sys.version_info[:2]==(3,12)
    and getattr(os,'geteuid',lambda:-1)()==0,'Actual Linux CPython3.12 Root required')
class HostedLexicalPlansTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.namespace=tempfile.TemporaryDirectory(prefix='gitgood-lexical-plans-',dir='/var/lib')
        cls.addClassCleanup(cls.namespace.cleanup);cls.root=Path(cls.namespace.name);cls.root.chmod(0o700)
        cls.ci=Path(__file__).resolve().parent
        for name in ('lexical_path_probe.py','immutable_path_probe.py'):
            shutil.copyfile(cls.ci/name,cls.root/name);(cls.root/name).chmod(0o644)
        cls.loaded=probe.Loaded(cls.root)

    def test_sdk_body_and_code_custody_are_verified_without_sdk_changes(self):
        self.assertEqual(vars(pathlib.PurePath)['with_segments'].__code__,self.loaded.original_code)
        self.loaded.validate()
        with tempfile.TemporaryDirectory(prefix='changed-',dir=self.root) as directory:
            root=Path(directory)
            for name in ('lexical_path_probe.py','immutable_path_probe.py'):shutil.copyfile(self.ci/name,root/name)
            loaded=probe.Loaded(root)
            with (root/'lexical_path_probe.py').open('ab') as output:output.write(b'\n# synthetic mutation\n')
            with self.assertRaises(ValueError):loaded.validate()

    def test_fresh_symlink_and_replacement_results_with_plans_active(self):
        targets=modules();a=probe.Adapter(targets,loaded=self.loaded)
        with tempfile.TemporaryDirectory(prefix='files-',dir=self.root) as directory:
            root=Path(directory);leaf=root/'leaf';leaf.write_bytes(b'one');link=root/'link';link.symlink_to('leaf')
            with a.installed():
                held=root/'link';self.assertIs(root/'link',held)
                self.assertTrue(stat_is_link(held));self.assertEqual(held.resolve(strict=True),leaf)
                link.unlink();link.symlink_to('other');other=root/'other';other.write_bytes(b'new')
                self.assertEqual(held.resolve(strict=True),other)
            self.assertTrue(a.restored());self.loaded.validate()

    def test_all_original_372_root_refusals_with_combined_plans_active(self):
        sys.path.insert(0,str(self.ci.parents[0]/'deployment'))
        import native_service_scope,native_durable_binding,native_root_database_reader
        targets=(native_service_scope,native_durable_binding,native_root_database_reader)
        suite=unittest.TestSuite()
        for name,count in ROOT_SCOPES:
            scope=unittest.defaultTestLoader.loadTestsFromName(name)
            self.assertEqual(scope.countTestCases(),count);suite.addTest(scope)
        a=probe.Adapter(targets,loaded=self.loaded);stream=io.StringIO()
        with a.installed():result=unittest.TextTestRunner(stream=stream).run(suite)
        self.assertEqual(result.testsRun,372);self.assertFalse(result.skipped)
        self.assertTrue(result.wasSuccessful(),stream.getvalue());self.assertTrue(a.restored())
        self.assertGreater(a.joins.hits,0);self.assertGreater(a.factory.calls,0);self.loaded.validate()
        print('lexical_path_original_root_cases=372',flush=True)


def stat_is_link(path):
    import stat
    value=path.lstat();return type(value) is os.stat_result and stat.S_ISLNK(value.st_mode)


if __name__=='__main__':unittest.main(verbosity=2)
