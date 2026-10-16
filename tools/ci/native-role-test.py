#!/usr/bin/env python3
"""Portable code-context lifecycle only; no fused C execution evidence."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock,patch

sys.dont_write_bytecode=True
import native_path_probe as sdk
from native_role_probe import RoleContext

spec=importlib.util.spec_from_file_location('_role_descriptor_contract',Path(__file__).with_name('native-descriptor-test.py'))
descriptor=importlib.util.module_from_spec(spec);spec.loader.exec_module(descriptor)


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


if __name__=='__main__':unittest.main(verbosity=2)
