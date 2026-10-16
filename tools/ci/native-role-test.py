#!/usr/bin/env python3
"""Portable role contracts; actual C execution remains a separate hosted gate."""
import _collections_abc
import ast
import builtins
import importlib.util
import inspect
import io
import os
from pathlib import Path
import pathlib
import select
import shutil
import signal
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock,patch

sys.dont_write_bytecode=True
import native_path_probe as sdk
import native_role_probe as probe
from native_role_probe import RoleContext

spec=importlib.util.spec_from_file_location('_role_descriptor_contract',Path(__file__).with_name('native-descriptor-test.py'))
descriptor=importlib.util.module_from_spec(spec);spec.loader.exec_module(descriptor)
spec=importlib.util.spec_from_file_location('_role_read_contract',Path(__file__).with_name('native-read-test.py'))
read_cases=importlib.util.module_from_spec(spec);spec.loader.exec_module(read_cases)


class FakeRoleNative(descriptor.FakeDescriptorNative):
    """Model entry/exit ordering only; this never establishes C execution."""
    def __init__(self):
        super().__init__();self.read=read_cases.FakeNative();self.events=[]
        for name in probe.read_backend.NATIVE_APIS:setattr(self,name,getattr(self.read,name))
        for name in probe.APIS:setattr(self,name,getattr(self,name))
    @staticmethod
    def admitted(table):
        for owner,name,value in table:
            current=(owner.__code__ if type(owner) is types.FunctionType else owner.cell_contents
                if type(owner) is types.CellType else inspect.getattr_static(owner,name)
                if isinstance(owner,type) else owner.get(name))
            if current is not value:return False
        return True
    def descriptor_plan(self,*args):
        plan=super().descriptor_plan(*args);plan.prepares=[0]*8;plan.observations=[0]*8;return plan
    def descriptor_bind(self,plan,*args):
        super().descriptor_bind(plan,*args)
        plan.defaults={id(fn):(fn,fn.__defaults__,fn.__kwdefaults__,dict(fn.__kwdefaults__ or {}))
            for fn,name,_value in plan.tables[0] if type(fn) is types.FunctionType}
    def role_admit(self,plan):
        return (plan.active and self.admitted(plan.tables[0]) and all(fn.__defaults__ is defaults
            and fn.__kwdefaults__ is keyword and dict(keyword or {})==items
            for fn,defaults,keyword,items in plan.defaults.values()))
    def role_prepare(self,plan,kind,payload,owner):
        if not self.role_admit(plan):return NotImplemented
        self.events.append(('prepare',kind))
        if kind in (2,3):
            if type(payload) is not owner or not vars(payload).get('supported'):return NotImplemented
            value=('prepared',)* (6 if kind==2 else 5)
        else:
            path=payload[0]
            if type(path) not in (str,plan.concrete):return NotImplemented
            if kind==0:value=(str(path),(),payload[1],payload[2])
            elif kind==1:value=(str(path),(),268435456,True)
            elif kind in (4,5):value=(str(path),(),*payload[1:])
            else:value=(str(path),(),0,payload[1],False)
        plan.prepares[kind]+=1;return value
    def role_observe(self,plan,kind,arguments,callbacks):
        if not self.role_admit(plan):return NotImplemented
        self.events.append(('observe',kind));plan.observations[kind]+=1
        if kind<2:return self.fingerprint(*arguments)
        if kind==2:return self.persistent(*arguments,callbacks[0])
        if kind==3:return self.custody(*arguments,callbacks[1])
        return self.read_file(kind-4,*arguments,*callbacks[2:])
    def role_counts(self,plan):return tuple(plan.prepares),tuple(plan.observations)


class RoleSourceContractTest(unittest.TestCase):
    def test_actual_sdk_parent_and_iteration_bodies_match_closed_contracts(self):
        for module,contract,filename in ((pathlib,probe.ROLE_AST,pathlib.__file__),
                (_collections_abc,probe.SEQUENCE_AST,_collections_abc.Sequence.__iter__.__code__.co_filename)):
            raw=Path(module.__file__).read_bytes()
            codes=probe.contract_code(raw,filename,contract)
            self.assertTrue(set(contract)<=set(codes))
            tree=ast.parse(raw)
            for owner in tree.body:
                if not isinstance(owner,ast.ClassDef):continue
                for node in owner.body:
                    if owner.name+'.'+getattr(node,'name','') in contract:
                        node.body.append(ast.Return(value=ast.Constant(value=None)))
                        changed=ast.unparse(ast.fix_missing_locations(tree)).encode()
                        with self.assertRaises(ValueError):probe.contract_code(changed,filename,contract)
                        break
                else:continue
                break
    def test_defaults_authentication_distinguishes_bool_int_and_added_defaults(self):
        def no_defaults(path):return path
        self.assertTrue(probe.same_defaults(no_defaults,(None,None)))
        no_defaults.__defaults__=(False,)
        self.assertFalse(probe.same_defaults(no_defaults,(None,None)))
        def defaults(path,maximum=4,*,executable=False):return path
        expected=((4,),{'executable':False})
        self.assertTrue(probe.same_defaults(defaults,expected))
        defaults.__kwdefaults__['executable']=0
        self.assertFalse(probe.same_defaults(defaults,expected))
        declaration=probe.declared_defaults(b'def fn(path,maximum=4,*,executable=False): return path\n')
        self.assertEqual(declaration,{'fn':expected})
    def test_parent_iterator_and_builtin_hooks_refuse_before_context_preparation(self):
        probe.role_environment()
        for owner,name,value in ((pathlib._PathParents,'__iter__',lambda self:iter(())),
                (pathlib,'Sequence',object),(builtins,'range',lambda *args:())):
            with patch.object(owner,name,value,create=True),self.assertRaises(ValueError):probe.role_environment()
    def test_bound_class_rows_use_raw_mro_descriptor_and_conflicts_refuse(self):
        raw=inspect.getattr_static(pathlib.Path,'_from_parsed_parts')
        rows=probe.merge_bindings(((pathlib.Path,'_from_parsed_parts',pathlib.Path._from_parsed_parts),))
        self.assertIs(rows[0][2],raw)
        with self.assertRaises(ValueError):probe.merge_bindings(rows,((pathlib.Path,'_from_parsed_parts',object()),))
    def test_added_sdk_default_refuses_before_a_native_context_is_created(self):
        native=descriptor.FakeDescriptorNative();fn=vars(pathlib.PurePath)['_parse_path'].__func__
        loaded=types.SimpleNamespace(native=native,codes=None,validate=Mock());saved=fn.__defaults__
        try:
            fn.__defaults__=()
            with patch.object(native,'descriptor_plan') as planned,self.assertRaises(ValueError):
                RoleContext(loaded,owner_check=lambda:None)
            planned.assert_not_called()
        finally:fn.__defaults__=saved


class RoleAdapterContractTest(unittest.TestCase):
    def setUp(self):
        for name in ('getuid','geteuid','getgid','getegid'):
            if not hasattr(os,name):self.enterContext(patch.object(os,name,lambda:0,create=True))
        for name in ('O_NOFOLLOW','O_CLOEXEC','O_NONBLOCK'):
            if not hasattr(os,name):self.enterContext(patch.object(os,name,0,create=True))
        self.modules,self.kernel=read_cases.models();self.native=FakeRoleNative()
        self.loaded=types.SimpleNamespace(native=self.native,modules=self.modules,kernel=self.kernel,
            original_codes=None,codes=None,validate=Mock())
        self.adapter=probe.Adapter(self.loaded,owner_check=lambda:None);self.addCleanup(self.adapter.close)

    def test_all_eight_roles_dispatch_and_restore_with_sdk_descriptors_unchanged(self):
        a=self.adapter;service,binding,generation,lifecycle=self.modules
        plan=generation._PersistentFingerprintPlan();plan.supported=True
        custody=lifecycle._RootReadOnlyCustody();custody.supported=True;custody.usable=True;custody.owner=a.owner
        custody.root=Path('/synthetic');custody.uid=1;custody.gid=1;custody.root_custody=('same',)
        with a.installed():
            self.assertTrue(a.context.sdk_original());self.assertTrue(a.eligible())
            self.assertEqual(service._CapturedRootFiles._fingerprint('/synthetic',4,False)[0][:2],(1,2))
            self.assertEqual(binding._CapturedExecutableDigests._fingerprint('/synthetic')[0],'/synthetic')
            self.assertEqual(plan.read(),{'fresh':True});self.assertIsNone(custody.check())
            self.assertEqual(service.root_file('/synthetic')[1],b'one')
            self.assertEqual(binding.private_file('/synthetic',3)[0]['uid'],3)
            self.assertEqual(service.read_bytes('/synthetic'),b'one');self.assertEqual(self.kernel._read('/synthetic'),'one')
            self.assertTrue(a.context.sdk_original())
        self.assertEqual(a.values(),((1,)*8,(1,)*8));self.assertTrue(a.restored())
        self.assertFalse(any(a.fallbacks.values()));a.close()
        self.assertIsNone(a.context.plan);self.assertFalse(a.context.final_details['watching'])

    def test_unsupported_preparation_falls_back_before_observation(self):
        with self.adapter.installed():
            plan=self.modules[2]._PersistentFingerprintPlan()
            self.assertEqual(plan.read(),{'original':True})
            self.assertEqual(self.adapter.fallbacks['persistent'],1)
        self.assertFalse(any(self.adapter.values()[1]))

    def test_observation_refusal_or_error_never_repeats_original(self):
        failure=KeyboardInterrupt('original observation')
        for outcome in (NotImplemented,None,failure):
            with self.adapter.installed(),patch.object(self.native,'read_file',Mock(
                    side_effect=outcome if isinstance(outcome,BaseException) else None,
                    return_value=None if isinstance(outcome,BaseException) else outcome)):
                with self.assertRaises(KeyboardInterrupt if outcome is failure else ValueError) as caught:
                    self.kernel._read('/synthetic')
                if outcome is failure:self.assertIs(caught.exception,failure)
        self.assertEqual(self.adapter.fallbacks['kernel_read'],0);self.assertTrue(self.adapter.restored())

    def test_size_metadata_and_ascii_refusals_follow_native_close_without_retry(self):
        with self.adapter.installed():
            with self.assertRaises(ValueError):self.modules[0].read_bytes('/synthetic',2)
            with patch.object(self.native,'read_file',return_value=(b'\xff',None,None)):
                with self.assertRaises(UnicodeDecodeError):self.kernel._read('/synthetic')
            before=(1,2,3);after=(1,2,4)
            with patch.object(self.native,'read_file',return_value=(b'one',before,after)):
                with self.assertRaises(ValueError):self.modules[0].root_file('/synthetic')
        self.assertFalse(any(self.adapter.fallbacks.values()))

    def test_custody_original_observations_precede_dispatch_and_never_repeat(self):
        a=self.adapter;lifecycle=self.modules[3];events=self.native.events
        subject=lifecycle._RootReadOnlyCustody();subject.supported=True;subject.usable=True;subject.owner=a.owner
        subject.root=Path('/synthetic');subject.uid=1;subject.gid=1;subject.root_custody=('same',)
        # Capture these originals before the schema binds them.
        a.close()
        def private(*args):events.append(('private',3));return ('same',)
        lifecycle.private_directory=private
        self.adapter=a=probe.Adapter(self.loaded,owner_check=lambda:None);self.addCleanup(a.close)
        with a.installed():subject.check()
        self.assertEqual(events,[('prepare',3),('private',3),('observe',3)])

    def test_default_and_sdk_hook_mutations_refuse_before_native_dispatch(self):
        a=self.adapter;fn=pathlib.Path.resolve;original=fn.__defaults__
        try:
            with a.installed():
                fn.__defaults__=(True,);self.assertFalse(a.eligible())
                self.assertEqual(self.kernel._read('/synthetic'),'original-kernel')
        finally:fn.__defaults__=original
        self.assertEqual(a.fallbacks['kernel_read'],1);self.assertFalse(any(a.values()[1]))

    def test_saved_entry_after_close_uses_original_and_interruption_restores(self):
        failure=KeyboardInterrupt('body');a=self.adapter
        with self.assertRaises(KeyboardInterrupt) as caught:
            with a.installed():saved=self.kernel._read;raise failure
        self.assertIs(caught.exception,failure);self.assertTrue(a.restored());self.assertIsNone(self.native.live)
        a.close();self.assertEqual(saved('/synthetic'),'original-kernel')

    def test_replaced_io_callback_falls_back_before_preparation(self):
        a=self.adapter
        with a.installed(),patch.object(io,'open',Mock(side_effect=AssertionError('callback invoked'))):
            self.assertFalse(a.eligible());self.assertEqual(self.kernel._read('/synthetic'),'original-kernel')
        self.assertFalse(any(a.values()[0]));self.assertFalse(any(a.values()[1]))

    def test_alias_imported_during_scope_is_restored_after_interruption(self):
        a=self.adapter;directory=Path.cwd();a.installed_directory=directory
        late=types.ModuleType('_role_late_alias');late.__file__=str(directory/'role_late_alias.py')
        failure=KeyboardInterrupt('body')
        with patch.dict(sys.modules,{'_role_late_alias':late}),self.assertRaises(KeyboardInterrupt) as caught:
            with a.installed():
                late.read=self.kernel._read;self.assertIs(late.read,a.read_replacements[3]);raise failure
        self.assertIs(caught.exception,failure);self.assertIs(late.read,a.read_originals[3]);self.assertTrue(a.restored())


class RoleContextTest(unittest.TestCase):
    def setUp(self):
        self.native=descriptor.FakeDescriptorNative()
        self.loaded=types.SimpleNamespace(native=self.native,codes=None,validate=Mock())
        self.context=RoleContext(self.loaded,owner_check=lambda:None)
        self.addCleanup(self.context.close)
    def test_original_sdk_descriptors_remain_installed_and_tables_are_current(self):
        originals=tuple(vars(owner)[name] for owner,name in sdk.TARGETS)
        self.assertTrue(self.context.sdk_original());self.assertTrue(self.native.admitted(self.context.tables[0]))
        with self.context.admitted():
            self.assertTrue(self.context.active);self.assertIs(self.native.live,self.context.plan)
            self.assertEqual(tuple(vars(owner)[name] for owner,name in sdk.TARGETS),originals)
        self.assertIsNone(self.native.live);self.assertTrue(self.context.sdk_original())
        self.context.close();self.assertIsNone(self.context.plan);self.assertEqual(self.context.tables,())
        self.assertEqual(self.context.final_details['code_inputs'],0);self.assertFalse(self.context.final_details['watching'])
    def test_nested_context_does_not_replace_or_unregister_the_active_context(self):
        other=RoleContext(self.loaded,owner_check=lambda:None);self.addCleanup(other.close)
        with self.context.admitted():
            with self.assertRaises(ValueError):
                with other.admitted():self.fail('nested context entered')
            self.assertIs(self.native.live,self.context.plan);self.assertTrue(self.context.sdk_original())
        self.assertIsNone(self.native.live)
    def test_body_exception_wins_over_teardown_failure(self):
        phase=self.context.apis['descriptor_phase'];failure=KeyboardInterrupt('original body')
        def failed(plan,number):
            phase(plan,number)
            if number==1:raise OSError('teardown')
        self.context.apis['descriptor_phase']=failed
        with self.assertRaises(KeyboardInterrupt) as caught:
            with self.context.admitted():raise failure
        self.assertIs(caught.exception,failure);self.assertTrue(self.context.broken)
        self.assertFalse(self.context.active);self.assertIsNone(self.native.live);self.assertTrue(self.context.sdk_original())
    def test_source_custody_failure_precedes_native_context_creation(self):
        failure=KeyboardInterrupt('source custody');self.loaded.validate.side_effect=failure
        with patch.object(self.native,'descriptor_plan') as planned,self.assertRaises(KeyboardInterrupt) as caught:
            RoleContext(self.loaded,owner_check=lambda:None)
        self.assertIs(caught.exception,failure);planned.assert_not_called()
    def test_bind_failure_closes_partial_context_without_sdk_mutation(self):
        failure=KeyboardInterrupt('bind')
        with patch.object(self.native,'descriptor_bind',side_effect=failure),self.assertRaises(KeyboardInterrupt) as caught:
            RoleContext(self.loaded,owner_check=lambda:None)
        self.assertIs(caught.exception,failure);self.assertTrue(self.native.plans[-1].closed)
        self.assertTrue(self.context.sdk_original());self.assertIsNone(self.native.live)
    def test_close_failure_preserves_pending_body_error_and_releases_owned_context(self):
        failure=KeyboardInterrupt('body');self.context.apis['descriptor_close']=Mock(side_effect=OSError('close'))
        with self.assertRaises(KeyboardInterrupt) as caught:
            try:raise failure
            finally:self.context.close()
        self.assertIs(caught.exception,failure);self.assertIsNone(self.context.plan);self.assertTrue(self.context.closed)
        self.assertEqual(self.context.tables,());self.assertTrue(self.context.broken)


@unittest.skipUnless(sys.platform=='linux' and sys.version_info[:2]==(3,12)
    and getattr(os,'geteuid',lambda:-1)()==0,'Actual hosted Linux CPython3.12 Root required')
class HostedRoleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        descriptor.legacy.HostedPathTest.setUpClass.__func__(cls)
        source=Path(__file__).with_name('native_role_probe.py');target=cls.root/source.name
        shutil.copyfile(source,target);target.chmod(0o644)
        cls.loaded=probe.Loaded(cls.root,base=cls.loaded)

    def adapter(self):
        adapter=probe.Adapter(self.loaded);self.addCleanup(adapter.close);return adapter
    leaf=read_cases.HostedReadTest.leaf
    custody=read_cases.metadata_cases.HostedMetadataTest.custody
    # Run the existing semantic/refusal fixtures against this complete boundary,
    # including the same original owner classes, descriptors and typed errors.
    test_complete_reads_match_original_types_values_and_fresh_replacements=read_cases.HostedReadTest.test_complete_reads_match_original_types_values_and_fresh_replacements
    test_distinct_empty_size_ascii_and_executable_predicates_match=read_cases.HostedReadTest.test_distinct_empty_size_ascii_and_executable_predicates_match
    test_link_owner_mode_and_missing_path_refusals_match_without_descriptor_leaks=read_cases.HostedReadTest.test_link_owner_mode_and_missing_path_refusals_match_without_descriptor_leaks
    test_real_read_error_closes_descriptor_and_preserves_oserror=read_cases.HostedReadTest.test_real_read_error_closes_descriptor_and_preserves_oserror
    test_restored_mtime_still_poisons_original_capture=read_cases.HostedReadTest.test_restored_mtime_still_poisons_original_capture
    test_native_api_replacement_is_rejected_before_observations_and_code_custody=read_cases.HostedReadTest.test_native_api_replacement_is_rejected_before_observations_and_code_custody
    test_sdk_hook_and_source_code_mutation_fall_back_before_native=read_cases.HostedReadTest.test_sdk_hook_and_source_code_mutation_fall_back_before_native
    test_native_fingerprints_match_exact_values_and_stay_fresh=read_cases.metadata_cases.HostedMetadataTest.test_native_fingerprints_match_exact_values_and_stay_fresh
    test_native_persistent_result_matches_original_and_refuses_changed_entries=read_cases.metadata_cases.HostedMetadataTest.test_native_persistent_result_matches_original_and_refuses_changed_entries
    test_native_custody_observes_actual_held_and_named_descriptors=read_cases.metadata_cases.HostedMetadataTest.test_native_custody_observes_actual_held_and_named_descriptors
    test_native_custody_descriptor_rebinding_refuses_without_fallback=read_cases.metadata_cases.HostedMetadataTest.test_native_custody_descriptor_rebinding_refuses_without_fallback
    test_present_retained_none_preserves_original_type_error_before_native=read_cases.metadata_cases.HostedMetadataTest.test_present_retained_none_preserves_original_type_error_before_native
    test_native_custody_metadata_and_entry_change_refuse=read_cases.metadata_cases.HostedMetadataTest.test_native_custody_metadata_and_entry_change_refuse
    test_native_custody_keeps_separate_passes_and_refuses_restored_mtime=read_cases.metadata_cases.HostedMetadataTest.test_native_custody_keeps_separate_passes_and_refuses_restored_mtime

    def test_all_eight_roles_and_four_lexical_witnesses_on_same_original_actors(self):
        service,binding,generation,_=self.loaded.modules;kernel=self.loaded.kernel
        custody,_leaf,_other=self.custody();a=self.adapter()
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            root=Path(directory);root.chmod(0o700)
            executable=root/'executable';executable.write_bytes(b'one');executable.chmod(0o700)
            private=root/'private';private.write_bytes(b'one');private.chmod(0o600)
            machine=root/'machine';machine.write_bytes(b'machine');machine.chmod(0o600)
            plan=generation._PersistentFingerprintPlan.__new__(generation._PersistentFingerprintPlan)
            info=root.lstat();plan.uid=0;plan.entries=((root,frozenset({'executable','private','machine'})),)
            plan.directories=((root,str(root),info.st_dev,info.st_ino,0),);plan.machine=machine
            plan.files=tuple((path,str(path),0,False,path.lstat().st_size,path.lstat().st_dev,path.lstat().st_ino)
                for path in (executable,private));plan.parents=tuple((p,str(p),False,False) for p in root.parents)
            def guard():
                custody.check()
                return (service._CapturedRootFiles._fingerprint(executable,4096,True),
                    binding._CapturedExecutableDigests._fingerprint(str(executable)),plan.read(),
                    service.root_file(executable,4096,executable=True),binding.private_file(private,0),
                    service.read_bytes(private),kernel._read(private))
            expected=guard();before=a.values()
            with a.installed():
                self.assertEqual(guard(),expected);self.assertEqual(guard(),expected)
                self.assertTrue(a.context.sdk_original())
            after=a.values();self.assertTrue(all(x>y for old,new in zip(before,after) for y,x in zip(old,new)))
            details=a.context.apis['descriptor_counts'](a.context.plan)
            self.assertTrue(all(value>0 for value in details['calls'].values()))
            self.assertFalse(any(details['entries'].values()));self.assertFalse(any(a.fallbacks.values()))
            self.assertEqual(dict(zip(probe.FAMILIES,after[1])),a.calls)
            comparison=probe.compare_guard(self.loaded,lambda stage:guard(),
                types.SimpleNamespace(usable=True,state='ready'))
            self.assertEqual(len(comparison['pairs']),20);self.assertEqual(comparison['paired_checks'],40)
            self.assertTrue(all(value>0 for value in comparison['native_calls'].values()))
            self.assertFalse(any(comparison['fallbacks'].values()));self.assertTrue(comparison['code_inputs_released'])
        a.close();self.assertFalse(a.context.final_details['watching']);self.assertEqual(a.context.final_details['code_inputs'],0)
        self.loaded.validate()

    def test_preparation_matches_original_tables_lazy_path_state_and_no_observations(self):
        generation=self.loaded.modules[2];owner=generation._PersistentFingerprintPlan
        subject=owner.__new__(owner);subject.uid=0;subject.entries=();subject.directories=();subject.files=();subject.parents=()
        path=Path('/before');str(path);path._raw_paths[:]=['/after'];path._load_parts();subject.machine=path
        a=self.adapter();before=probe.read_backend.counts(self.loaded.native)
        with a.installed():
            arguments=self.loaded.native.role_prepare(a.context.plan,2,subject,owner)
            self.assertEqual(arguments,(0,(),(),'/before',(),()))
            self.assertEqual(path.parts,('/','after'));self.assertEqual(str(path),'/before')
            raw=self.loaded.native.role_prepare(a.context.plan,6,(path,3),None)
            self.assertEqual(raw,('/before',(),0,3,False))
            # Invalid user-written lazy slots must use original SDK errors,
            # never unchecked Unicode access or a second filesystem attempt.
            path._str=42
            self.assertIs(self.loaded.native.role_prepare(a.context.plan,6,(path,3),None),NotImplemented)
            with self.assertRaises(TypeError):self.loaded.kernel._read(path)
        self.assertEqual(probe.read_backend.counts(self.loaded.native),before)
        self.assertFalse(any(a.values()[1]));self.loaded.validate()

    def test_actual_code_default_and_parent_shadow_changes_refuse_before_observation(self):
        leaf=self.leaf();kernel=self.loaded.kernel
        fn=pathlib.Path.resolve;saved=fn.__defaults__;a=self.adapter()
        try:
            with a.installed():
                before=a.values();fn.__defaults__=(True,)
                self.assertFalse(a.eligible());self.assertEqual(kernel._read(leaf),'one');self.assertEqual(a.values(),before)
                with self.assertRaises(ValueError):self.loaded.validate()
        finally:fn.__defaults__=saved
        a.close();a=self.adapter()
        with a.installed():
            before=a.values()
            with patch.object(pathlib.PosixPath,'parents',property(lambda _:()),create=True):
                self.assertFalse(a.eligible());self.assertEqual(kernel._read(leaf),'one');self.assertEqual(a.values(),before)
        self.loaded.validate()

    def test_actual_role_api_replacement_declines_before_native_and_preserves_original_error(self):
        a=self.adapter();leaf=self.leaf();original=self.loaded.native.role_prepare
        changed=Mock(side_effect=AssertionError('foreign API executed'))
        try:
            with a.installed():
                before=a.values();self.loaded.native.role_prepare=changed
                self.assertEqual(self.loaded.kernel._read(leaf),'one');changed.assert_not_called();self.assertEqual(a.values(),before)
                with self.assertRaises(ValueError):self.loaded.validate()
        finally:self.loaded.native.role_prepare=original
        self.assertEqual(a.fallbacks['kernel_read'],1);self.loaded.validate()

    def test_same_pid_and_thread_real_effective_uid_gid_are_checked_for_each_role(self):
        leaf=self.leaf();read_fd,write_fd=os.pipe();pid=os.fork()
        if pid==0:
            os.close(read_fd);status=1
            try:
                a=probe.Adapter(self.loaded);uid=os.getresuid();gid=os.getresgid()
                changes=((os.setresuid,(65534,0,uid[2])),(os.setresuid,(0,65534,uid[2])),
                    (os.setresgid,(65534,0,gid[2])),(os.setresgid,(0,65534,gid[2])))
                try:
                    for change,values in changes:
                        with a.installed():
                            self.assertTrue(a.eligible());before=a.values();change(*values)
                            try:self.assertFalse(a.eligible())
                            finally:os.setresuid(*uid);os.setresgid(*gid)
                            self.assertEqual(a.values(),before);self.assertTrue(a.eligible())
                            self.assertEqual(self.loaded.kernel._read(leaf),'one')
                finally:os.setresuid(*uid);os.setresgid(*gid);a.close()
                self.assertEqual(a.context.final_details['code_inputs'],0);status=0
            except BaseException:pass
            try:os.write(write_fd,b'passed' if status==0 else b'failed')
            finally:os.close(write_fd);os._exit(status)
        os.close(write_fd)
        try:
            ready,_,_=select.select([read_fd],[],[],20)
            if not ready:os.kill(pid,signal.SIGKILL)
            payload=os.read(read_fd,64) if ready else b'timeout'
        finally:os.close(read_fd)
        _,status=os.waitpid(pid,0);self.assertEqual(status,0);self.assertEqual(payload,b'passed')

    def test_zz_all_original_372_root_cases_with_complete_role_boundary(self):
        spec=importlib.util.spec_from_file_location('_role_original_lexical_cases',Path(__file__).with_name('lexical-path-test.py'))
        original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original);suite=unittest.TestSuite()
        for name,count in original.ROOT_SCOPES:
            scope=unittest.defaultTestLoader.loadTestsFromName(name);self.assertEqual(scope.countTestCases(),count);suite.addTest(scope)
        a=self.adapter();stream=io.StringIO()
        class Progress(unittest.TextTestResult):
            def startTest(self,test):
                print('native_role_root_case='+type(test).__name__+'.'+test._testMethodName,flush=True);super().startTest(test)
        with a.installed():result=unittest.TextTestRunner(stream=stream,resultclass=Progress).run(suite)
        self.assertEqual(result.testsRun,372);self.assertFalse(result.skipped);self.assertTrue(result.wasSuccessful(),stream.getvalue())
        self.assertTrue(a.restored());self.loaded.validate();a.close();self.assertFalse(a.context.final_details['watching'])
        print('native_role_original_root_cases=372',flush=True)


if __name__=='__main__':unittest.main(verbosity=2)
