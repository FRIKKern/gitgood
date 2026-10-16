#!/usr/bin/env python3
"""Descriptor restoration and actual hosted path-body equivalence/refusals."""
import ast
import builtins
import io
import os
from pathlib import Path
import pathlib
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock,patch

sys.dont_write_bytecode=True
import path_body_probe as probe
from path_body_source import TARGETS,LOOKUP,redirect_globals


def model_modules():
    original=types.ModuleType('original_path_model');native=types.ModuleType('native_path_model')
    rows=[]
    for owner,names in TARGETS.items():
        rows.append('class '+owner+':')
        for name in names:
            if name=='_parse_path':rows.extend([' @classmethod',' def '+name+'(cls,*args): return cls'])
            elif name in {'_str_normcase','drive','root','anchor','parts','parent','parents'}:
                rows.extend([' @property',' def '+name+'(self): return value'])
            else:rows.append(' def '+name+'(self,*args,**kwargs): return value')
    text='\n'.join(rows)+'\n';original.value={'fresh':True};exec(text,vars(original))
    generated,_=redirect_globals(ast.parse(text));state={};missing=object()
    def lookup(name):
        value=state['globals'].get(name,missing)
        if value is missing:value=state['builtins'].get(name,missing)
        if value is missing:raise NameError("name "+repr(name)+" is not defined",name=name)
        return value
    def bind_original(globals_dict,builtin_dict):
        state.update(globals=globals_dict,builtins=builtin_dict);return True
    vars(native)[LOOKUP]=lookup;native.bind_original=bind_original
    exec(generated,vars(native));return original,native


class DescriptorAdapterTest(unittest.TestCase):
    def setUp(self):
        self.module,self.native=model_modules()
        self.adapter=probe.Adapter(self.module,self.native,owner_check=lambda:None)
        self.classes={name:getattr(self.module,name) for name in TARGETS}

    def test_original_classes_receivers_properties_and_classmethods_are_retained(self):
        subject=object.__new__(self.module.Path)
        with self.adapter.installed():
            self.assertTrue(all(getattr(self.module,name) is value for name,value in self.classes.items()))
            self.assertEqual(subject.resolve(),{'fresh':True})
            self.assertEqual(object.__new__(self.module.PurePath).drive,{'fresh':True})
            self.assertIs(self.module.PurePath._parse_path('/'),self.classes['PurePath'])
            self.module.value={'changed':True};self.assertEqual(subject.resolve(),{'changed':True})
        self.assertEqual(self.adapter.calls,2);self.assertTrue(self.adapter.restored())

    def test_nested_installation_and_foreign_class_identity_refuse(self):
        with self.adapter.installed():
            with self.assertRaises(ValueError):
                with self.adapter.installed():pass
        self.assertTrue(self.adapter.restored())
        self.module.Path=type('ForeignPath',(),{})
        with self.assertRaises(ValueError):
            with self.adapter.installed():pass
        self.assertTrue(self.adapter.restored())

    def test_interruption_and_partial_install_restore_every_descriptor_and_original_exception(self):
        failure=KeyboardInterrupt('original')
        with self.assertRaises(KeyboardInterrupt) as caught:
            with self.adapter.installed():raise failure
        self.assertIs(caught.exception,failure);self.assertTrue(self.adapter.restored())
        def install(owner,name,value):
            if owner is self.module.Path and name=='lstat' and value is not vars(owner)[name]:raise failure
            builtins.setattr(owner,name,value)
        with patch.object(probe,'setattr',side_effect=install,create=True),self.assertRaises(KeyboardInterrupt) as caught:
            with self.adapter.installed():pass
        self.assertIs(caught.exception,failure);self.assertTrue(self.adapter.restored());self.assertFalse(self.adapter.active)

    def test_cleanup_failure_attempts_remaining_restores_without_masking_original_error(self):
        failure=KeyboardInterrupt('original');restores=[]
        originals={(id(owner),name):old for owner,name,old,_ in self.adapter.entries}
        def install(owner,name,value):
            if value is originals[id(owner),name]:
                restores.append((id(owner),name))
                if owner is self.module.Path and name=='resolve':raise RuntimeError('cleanup')
            builtins.setattr(owner,name,value)
        try:
            with patch.object(probe,'setattr',side_effect=install,create=True),self.assertRaises(KeyboardInterrupt) as caught:
                with self.adapter.installed():raise failure
            self.assertIs(caught.exception,failure);self.assertEqual(len(restores),20);self.assertTrue(self.adapter.broken)
            with self.assertRaises(ValueError):self.adapter.check()
        finally:
            for owner,name,old,_ in self.adapter.entries:builtins.setattr(owner,name,old)

    def test_pairs_alternate_restore_before_timers_and_keep_original_guard(self):
        events=[];order=[];original_resolve=vars(self.module.Path)['resolve'];module=self.module
        class Stage:
            state='ready';usable=True
            def check(stage):
                order.append(vars(module.Path)['resolve'] is original_resolve);events.append('guard')
                return module.Path.resolve(object.__new__(module.Path))
        original=Stage.check
        loaded=types.SimpleNamespace(native=self.native,original_codes=None,validate=Mock(),evidence=lambda:{})
        class Measurements:
            def __enter__(inner):events.append('enter')
            def __exit__(inner,*_):events.append('exit')
        with patch.object(probe,'root_owner'),patch.object(probe,'pathlib',self.module):
            with probe.AtFirstGuard(loaded,Stage,Measurements()) as trial:Stage().check()
        self.assertEqual(order[:40],[value for index in range(20) for value in
            ((True,False) if index%2==0 else (False,True))])
        self.assertEqual(events,['guard']*40+['enter','guard','exit']);self.assertTrue(order[-1])
        self.assertIs(Stage.check,original);self.assertTrue(self.adapter.restored())
        self.assertEqual(trial.result['compiled_resolve_calls'],20);loaded.validate.assert_called_once()

    def test_mismatch_and_failed_cleanup_poison_stage_and_allocation_without_revival(self):
        failure=KeyboardInterrupt('original')
        class Stage:
            usable=True;state='ready'
            def __init__(stage):stage.allocation=types.SimpleNamespace(usable=True,close=Mock(side_effect=RuntimeError('cleanup')))
            def check(stage):return None
            close=Mock(side_effect=RuntimeError('cleanup'))
        original=Stage.check;stage=Stage()
        with patch.object(probe,'compare_guard',side_effect=failure),self.assertRaises(KeyboardInterrupt) as caught:
            with probe.AtFirstGuard(None,Stage,Mock()):stage.check()
        self.assertIs(caught.exception,failure);self.assertIs(Stage.check,original)
        self.assertFalse(stage.usable);self.assertFalse(stage.allocation.usable)
        stage.close.assert_called_once();stage.allocation.close.assert_called_once()


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
    and getattr(os,'geteuid',lambda:-1)()==0,'Compiled hosted CPython3.12 and actual Root required')
class HostedPathBodyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.namespace=tempfile.TemporaryDirectory(prefix='gitgood-path-bodies-',dir='/var/lib')
        cls.addClassCleanup(cls.namespace.cleanup);cls.root=Path(cls.namespace.name);cls.root.chmod(0o700)
        ci=Path(__file__).resolve().parent;built=ci.parents[1]/'.gitgood/path-body-probe'
        for source in [ci/'path_body_probe.py',ci/'path_body_source.py',ci/'path-body-build.py',
                *[built/name for name in ('pathlib-original.py','path-body-donor.pyx','manifest.json',probe.extension_name())]]:
            destination=cls.root/source.name;shutil.copyfile(source,destination);destination.chmod(0o644)
        cls.loaded=probe.Loaded(cls.root)

    def adapter(self):return probe.Adapter(pathlib,self.loaded.native,original_codes=self.loaded.original_codes)

    def test_exact_lexical_values_types_and_original_class_identities(self):
        def observe():
            values=[]
            for path in ['.','/','/a//b/../c','/caf\u00e9/\u732b','//server/share/x']:
                for cls in (pathlib.PurePosixPath,pathlib.PureWindowsPath,pathlib.PosixPath):
                    value=cls(path);derived=value/'child'
                    values.append((type(value),str(value),os.fspath(value),value.drive,value.root,value.anchor,
                        value.parts,str(value.parent),tuple(str(parent) for parent in value.parents),hash(value),
                        type(derived),str(derived),value==cls(path)))
            return values
        expected=observe();classes=tuple(getattr(pathlib,name) for name in TARGETS);adapter=self.adapter()
        with adapter.installed():
            self.assertEqual(observe(),expected)
            self.assertEqual(tuple(getattr(pathlib,name) for name in TARGETS),classes)
        self.assertTrue(adapter.restored());self.loaded.validate()

    def test_pathlike_called_once_subclasses_and_original_exception_identity(self):
        failure=KeyboardInterrupt('Original pathlike interruption')
        class PathLike:
            def __init__(self,value):self.value=value;self.calls=0
            def __fspath__(self):
                self.calls+=1
                if isinstance(self.value,BaseException):raise self.value
                return self.value
        class Child(pathlib.PurePosixPath):pass
        for selected in (False,True):
            adapter=self.adapter()
            with adapter.installed() if selected else _nothing():
                good=PathLike('/synthetic/leaf');value=Child(good)
                self.assertIs(type(value/'next'),Child);self.assertEqual(good.calls,1)
                bad=PathLike(failure)
                with self.assertRaises(KeyboardInterrupt) as caught:pathlib.PurePosixPath(bad)
                self.assertIs(caught.exception,failure);self.assertEqual(bad.calls,1)
                for item in (b'bytes',None,7):
                    with self.assertRaises(TypeError):pathlib.PurePosixPath(item)

    def test_fresh_stat_lstat_resolve_symlink_and_replacement_results(self):
        with tempfile.TemporaryDirectory(prefix='files-',dir=self.root) as directory:
            root=Path(directory);leaf=root/'leaf';leaf.write_bytes(b'one');link=root/'link';link.symlink_to('leaf')
            def identity(value):
                self.assertIs(type(value),os.stat_result)
                return tuple(getattr(value,key) for key in ('st_dev','st_ino','st_mode','st_uid','st_gid',
                    'st_nlink','st_size','st_mtime_ns','st_ctime_ns'))
            first=leaf.stat();expected=(identity(first),identity(link.lstat()),link.resolve(strict=True))
            adapter=self.adapter()
            with adapter.installed():
                self.assertEqual((identity(leaf.stat()),identity(link.lstat()),link.resolve(strict=True)),expected)
                leaf.write_bytes(b'longer fresh bytes');self.assertEqual(leaf.stat().st_size,18)
                leaf.rename(root/'retained');leaf.write_bytes(b'new')
                self.assertNotEqual(leaf.stat().st_ino,first.st_ino)
                self.assertEqual(link.resolve(strict=True),leaf)
            self.assertTrue(adapter.restored())

    def test_live_global_rebinding_builtin_shadowing_and_missing_name_metadata(self):
        subject=pathlib.PosixPath('/synthetic');adapter=self.adapter();failure=OSError(5,'synthetic')
        with adapter.installed():
            with patch.object(pathlib,'os',types.SimpleNamespace(stat=Mock(side_effect=failure))):
                with self.assertRaises(OSError) as caught:subject.stat()
                self.assertIs(caught.exception,failure)
            with patch.object(pathlib,'str',lambda value:'shadow',create=True):self.assertEqual(subject.__fspath__(),'shadow')
            original=pathlib.os
            try:
                del pathlib.os
                with self.assertRaises(NameError) as caught:subject.stat()
                self.assertEqual(caught.exception.name,'os');self.assertIsNone(caught.exception.__context__)
            finally:pathlib.os=original
        self.assertTrue(adapter.restored())

    def test_original_372_root_cases_with_original_classes_and_compiled_bodies(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'deployment'))
        suite=unittest.TestSuite()
        for name,count in ROOT_SCOPES:
            scope=unittest.defaultTestLoader.loadTestsFromName(name)
            self.assertEqual(scope.countTestCases(),count);suite.addTest(scope)
        stream=io.StringIO();adapter=self.adapter()
        with adapter.installed():result=unittest.TextTestRunner(stream=stream).run(suite)
        self.assertEqual(result.testsRun,372);self.assertFalse(result.skipped)
        self.assertTrue(result.wasSuccessful(),stream.getvalue());self.assertTrue(adapter.restored())
        self.assertGreater(adapter.calls,0);self.loaded.validate()
        print('path_body_original_root_cases=372',flush=True)


from contextlib import nullcontext as _nothing

if __name__=='__main__':unittest.main(verbosity=2)
