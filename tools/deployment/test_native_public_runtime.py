"""Public runtime refusal/control checks; service and database stand-ins are explicit."""
import copy
from pathlib import Path, PurePosixPath
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

# Local Windows parser/control checks do not perform Linux account lookup.
# Hosted Linux tests import the real module and exercise actual service custody.
try:
    import pwd
except ModuleNotFoundError:
    sys.modules['pwd'] = SimpleNamespace(getpwnam=Mock(side_effect=RuntimeError('Linux account lookup unavailable')))

import native_public_runtime as runtime


class PublicRuntimeTests(unittest.TestCase):
    def configuration(self):
        return {'forge': {'GITGOOD_PUBLIC_URL': 'https://forge.example.invalid:4443',
            'GITGOOD_WEB_ORIGIN': 'https://forge.example.invalid:4443', 'PORT': '4400'},
            'web': {'PORT': '4500', 'GITGOOD_API_URL': 'http://127.0.0.1:4400'},
            'edge': {'tls_certificate': 'tls-certificate.pem', 'tls_key': 'tls-key.pem'}}

    def template(self):
        return (Path(__file__).resolve().parents[2] / 'docs/deployment/Caddyfile.example').read_text()

    def test_only_configured_https_origin_fixed_upstreams_and_private_tls_paths(self):
        rendered = runtime.edge_configuration(self.template(), self.configuration(), PurePosixPath('/var/lib/gitgood/installations/example'))
        self.assertIn('admin off', rendered)
        self.assertIn('https://forge.example.invalid:4443 {', rendered)
        self.assertIn('reverse_proxy 127.0.0.1:4500', rendered)
        self.assertIn('reverse_proxy 127.0.0.1:4400', rendered)
        self.assertIn('handle /internal/*', rendered)
        self.assertIn('header_up X-Gitgood-Edge-Key {$GITGOOD_PROXY_KEY}', rendered)
        self.assertIn('configuration/tls-key.pem', rendered)
        for url in ['http://forge.example.invalid', 'https://user:secret@forge.example.invalid',
                    'https://forge.example.invalid/other', 'https://forge.example.invalid/?token=private',
                    'https://forge.example.invalid#private', 'https://forge.example.invalid\n{',
                    'https://forge.example.invalid:0', 'https://forge.example.invalid/']:
            with self.subTest(url=url):
                configuration = self.configuration()
                configuration['forge']['GITGOOD_PUBLIC_URL'] = url
                configuration['forge']['GITGOOD_WEB_ORIGIN'] = url
                with self.assertRaises((runtime.PublicRuntimeRefused, ValueError)):
                    runtime.edge_configuration(self.template(), configuration, PurePosixPath('/var/lib/gitgood/installations/example'))
        for section, name, value in [('web', 'GITGOOD_API_URL', 'http://remote.invalid:4400'),
                                     ('web', 'PORT', '4500\n{'), ('forge', 'GITGOOD_WEB_ORIGIN', 'https://other.invalid')]:
            configuration = self.configuration();configuration[section][name] = value
            with self.assertRaises(runtime.PublicRuntimeRefused):
                runtime.edge_configuration(self.template(), configuration, PurePosixPath('/var/lib/gitgood/installations/example'))

    def test_original_runtime_claim_and_recorded_window_required(self):
        component = runtime.NativePublicRuntime.__new__(runtime.NativePublicRuntime)
        component.usable = True;component.claim = 'original'
        component.record = {'operation': 'op', 'candidate': 'candidate', 'owner': {'pid': 42, 'birth': '17', 'uid': 123}, 'backend_kernel': {}}
        component.scope = {'uid': 123, 'gid': 123, 'groups': {'native': {'path': '/sys/fs/cgroup/original/native'}}}
        component.marker = Mock()
        component.controller = SimpleNamespace(state='complete', mode='runtime', claim='original', record=copy.deepcopy(component.record),
            _base=Mock(), _absent=Mock(), seal={'executables': {'psql': '/fixed/psql'}}, url='private-url',
            binding={'database': {}}, backend_scope=Mock(), snapshot={'lifecycle': {'worker': 'native', 'recorded_status': 'running',
                'stage': 'verify', 'operation': 'op', 'candidate': 'candidate'}})
        with patch.object(runtime, 'process_identity', return_value=component.record['owner']), \
                patch.object(runtime, 'observe_held_backend_kernel_identity',
                    return_value={'owner_connection_observed': True, 'original_backend_kernel_observed': True, 'lease_acquired': False}):
            component._current()
        for field, value in [('claim', 'replacement'), ('record', {'operation': 'other', 'candidate': 'candidate'}),
                             ('state', 'reserved'), ('mode', 'migrate')]:
            original = getattr(component.controller, field);setattr(component.controller, field, value)
            with self.assertRaises(runtime.PublicRuntimeRefused):component._current()
            setattr(component.controller, field, original)
        for field, value in [('stage', 'migrate'), ('recorded_status', 'complete'), ('worker', 'maintenance'),
                             ('candidate', 'other'), ('operation', 'other')]:
            original = component.controller.snapshot['lifecycle'][field]
            component.controller.snapshot['lifecycle'][field] = value
            with patch.object(runtime, 'process_identity', return_value=component.record['owner']), \
                    patch.object(runtime, 'observe_held_backend_kernel_identity',
                        return_value={'owner_connection_observed': True, 'original_backend_kernel_observed': True, 'lease_acquired': False}):
                with self.assertRaises(runtime.PublicRuntimeRefused):component._current()
            component.controller.snapshot['lifecycle'][field] = original
        component.controller._base.side_effect = RuntimeError('Original lease absent')
        with self.assertRaises(RuntimeError):component._current()

    def test_check_loss_stops_original_leaves_and_refuses_constant_without_adoption(self):
        component = runtime.NativePublicRuntime.__new__(runtime.NativePublicRuntime)
        component.state = 'running';component._current = Mock(side_effect=RuntimeError('private database URL'))
        component.stop = Mock();component._files = Mock()
        with self.assertRaisesRegex(runtime.PublicRuntimeRefused, '^Native public runtime unavailable or changed$'):
            component.check()
        component.stop.assert_called_once_with();component._files.assert_not_called()

    def test_changed_kernel_group_cannot_authorize_cleanup(self):
        component = runtime.NativePublicRuntime.__new__(runtime.NativePublicRuntime)
        component.closed_receipt = None;component.controller = SimpleNamespace(_controller=Mock())
        component.scope = {'uid': 123, 'groups': {'edge': {'path': '/sys/fs/cgroup/original/edge', 'inode': 1}}}
        with patch.object(runtime, 'group_identity', return_value={'path': '/sys/fs/cgroup/original/edge', 'inode': 2}), \
                patch.object(runtime.os, 'write') as writes:
            with self.assertRaises(runtime.PublicRuntimeRefused):component.stop()
            writes.assert_not_called()
        self.assertFalse(component.usable)

    def test_constructor_rejects_caller_authority_and_programs(self):
        for caller in [None, {}, SimpleNamespace(state='complete')]:
            with self.assertRaises(runtime.PublicRuntimeRefused):runtime.NativePublicRuntime(caller)
        with self.assertRaises(TypeError):runtime.NativePublicRuntime(None, program='/bin/sh')


if __name__ == '__main__':
    unittest.main()
