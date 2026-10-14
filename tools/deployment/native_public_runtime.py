"""Fixed web/TLS services borrowed from one original live native controller.

This is a lifecycle component, not an installation/activation receipt. The
controller must keep calling check(); systemd owns whole-service failure if the
controller itself exits. No caller program, environment or artifact is accepted.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
from urllib.parse import urlsplit

from native_durable_binding import directory, private_file, unique
from native_ownership_controller import NativeOwnershipController
from native_ownership_marker_guard import NativeOwnershipMarkerGuard
from native_kernel_backend import observe_held_backend_kernel_identity
from native_service_scope import _CapturedRootFiles, group_identity, members, process_identity, root_file
from resource_generations import canonical


class PublicRuntimeRefused(Exception):
    pass


def require(value):
    if not value:
        raise PublicRuntimeRefused('Native public runtime unavailable or changed')


def fingerprint(info):
    return tuple(getattr(info, field) for field in
        ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_uid', 'st_mode', 'st_nlink'))


def web_inventory(path, candidate):
    """Stream a bounded Root-controlled complete copied web tree, without links."""
    path = Path(path)
    require(path.is_absolute() and path.resolve(strict=True) == path)
    require(type(candidate) is str and re.fullmatch(r'[0-9a-f]{40}', candidate))
    for parent in [path, *path.parents]:
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022)
    files, fingerprints, pending, count, total = {}, {}, [path], 0, 0
    while pending:
        current = pending.pop()
        info = current.lstat()
        require(current.resolve(strict=True) == current and info.st_uid == 0 and not info.st_mode & 0o022)
        count += 1
        require(count <= 30000)
        fingerprints[str(current)] = fingerprint(info)
        if stat.S_ISDIR(info.st_mode):
            # Bounded enumeration; never follow a package link into another tree.
            with os.scandir(current) as entries:
                for entry in entries:
                    require(len(pending) + count < 30000)
                    pending.append(Path(entry.path))
        else:
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and 0 <= info.st_size <= 134217728)
            total += info.st_size
            require(total <= 536870912)
            fd = os.open(current, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
            with os.fdopen(fd, 'rb') as source:
                require(fingerprint(os.fstat(source.fileno())) == fingerprint(info))
                digest = hashlib.file_digest(source, 'sha256').hexdigest()
                require(fingerprint(os.fstat(source.fileno())) == fingerprint(info))
            files[str(current.relative_to(path))] = {'bytes': info.st_size, 'sha256': digest}
    required = {'server.mjs', 'client-address.mjs', 'package.json', 'package-lock.json',
                'dist/build-identity.json', 'dist/server/server.js', 'node_modules/srvx/bin/srvx.mjs'}
    require(required <= set(files) and any(name.startswith('dist/client/') for name in files))
    _, raw = root_file(path / 'dist/build-identity.json', 65536)
    build = json.loads(raw, object_pairs_hook=unique)
    require(type(build) is dict and type(build['schema']) is int and build['schema'] == 1)
    require(build['candidate'] == candidate and build['dirty'] is False)
    return {'path': str(path), 'sha256': hashlib.sha256(canonical(files)).hexdigest(),
            'file_count': len(files), 'bytes': total}, fingerprints


def edge_configuration(template, configuration, root):
    """Render only the protected candidate's direct-edge template and fixed stores."""
    forge, web = configuration['forge'], configuration['web']
    public = forge['GITGOOD_PUBLIC_URL']
    require(type(public) is str and re.fullmatch(r'https://[a-zA-Z0-9.-]+(?::[1-9][0-9]{0,4})?', public))
    url = urlsplit(public)
    require(url.scheme == 'https' and url.hostname and not url.username and not url.password)
    require(url.path in {'', '/'} and not url.query and not url.fragment and public == public.rstrip('/'))
    require(re.fullmatch(r'[a-zA-Z0-9.-]+', url.hostname) and 1 <= (url.port or 443) <= 65535)
    require(forge['GITGOOD_WEB_ORIGIN'] == public)
    require(all(re.fullmatch(r'[1-9][0-9]{0,4}', value) and int(value) <= 65535
                for value in [forge['PORT'], web['PORT']]))
    require(web['GITGOOD_API_URL'] == 'http://127.0.0.1:' + forge['PORT'])
    require(template.count('gitgood.example.invalid {') == 1 and template.count('persist_config off') == 1)
    require('127.0.0.1:47841' in template and '127.0.0.1:47840' in template)
    paths = [root / 'configuration' / configuration['edge'][name] for name in ('tls_certificate', 'tls_key')]
    require(all(re.fullmatch(r'/[a-zA-Z0-9/_.-]+', str(path)) for path in paths))
    return template.replace('persist_config off', 'persist_config off\n  admin off\n  auto_https off').replace(
        'gitgood.example.invalid {', public + ' {\n  tls "' + str(paths[0]) + '" "' + str(paths[1]) + '"').replace(
        '127.0.0.1:47841', '127.0.0.1:' + forge['PORT']).replace('127.0.0.1:47840', '127.0.0.1:' + web['PORT'])


class NativePublicRuntime:
    def __init__(self, controller):
        self.marker = None
        try:
            self._prepare(controller)
        except Exception:
            if self.marker is not None:self.marker.close()
            raise PublicRuntimeRefused('Native public runtime unavailable or changed') from None

    def _prepare(self, controller):
        require(type(controller) is NativeOwnershipController)
        self.controller = controller
        self.processes = {}
        self.usable = True
        self.state = 'preparing'
        self.closed_receipt = None
        self.scope = controller.scope
        self.claim = controller.claim
        self.record = controller.record
        require(controller.state == 'complete' and controller.mode == 'runtime' and type(self.record) is dict)
        controller._base()
        storage = controller.binding['resources']['storage']
        self.marker = NativeOwnershipMarkerGuard(storage['path'], controller.installation,
            {name: storage[name] for name in ('device', 'inode', 'uid')}, self.record)
        self.captured_files = _CapturedRootFiles()
        self._current()
        self.seal = controller._root('public-runtime-v2.json')
        fields = {'protocol', 'kind', 'installation', 'operation', 'candidate', 'binding_sha256', 'web', 'edge_template'}
        require(type(self.seal) is dict and set(self.seal) == fields and type(self.seal['protocol']) is int)
        require(self.seal['protocol'] == 2 and self.seal['kind'] == 'native_public_runtime_seal')
        require(all(self.seal[name] == self.record[name] for name in
                    ('installation', 'operation', 'candidate', 'binding_sha256')))
        self.web, self.fingerprints = web_inventory(self.seal['web']['path'], self.record['candidate'])
        require(self.web == self.seal['web'])
        expected_template = self.seal['edge_template']
        require(type(expected_template) is dict and set(expected_template) == {'path', 'device', 'inode', 'bytes', 'sha256'})
        observed, template = self.captured_files.read(Path(expected_template['path']), 16384)
        require(observed == expected_template)
        # The original controller already binds each private configuration file.
        _, raw = private_file(controller.root / 'configuration/installation.json', self.scope['uid'])
        self.configuration = json.loads(raw, object_pairs_hook=unique)
        self.parent = controller.root / 'staging'
        self.parent_identity = directory(self.parent, self.scope['uid'])
        self.work = self.parent / ('public-' + self.claim)
        require(not self.work.exists() and not self.work.is_symlink())
        self.work.mkdir(mode=0o700)
        self.work_identity = directory(self.work, self.scope['uid'])
        self.config_path = self.work / 'Caddyfile'
        raw = edge_configuration(template.decode('utf-8'), self.configuration, controller.root).encode('utf-8')
        require(len(raw) <= 32768)
        fd = os.open(self.config_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as output:
            output.write(raw);output.flush();os.fsync(output.fileno())
        self.config_identity = private_file(self.config_path, self.scope['uid'])
        for name in ('caddy-data', 'caddy-config'):
            (self.work / name).mkdir(mode=0o700)
        self._current()
        self.state = 'prepared'

    def _current(self):
        require(self.usable and self.controller.state == 'complete' and self.controller.mode == 'runtime')
        require(self.controller.claim == self.claim and self.controller.record == self.record)
        # Publication's transient peer must not be adopted as the runtime owner,
        # and its empty-sibling check intentionally ends before web/edge launch.
        # Reobserve the original owner, held SQL/kernel lease and marker here.
        self.controller._base();self.controller._absent();self.marker.check()
        leaf = self.scope['groups']['native']
        require(process_identity(self.record['owner']['pid'], self.scope['uid'], self.scope['gid'],
            leaf['path'].removeprefix('/sys/fs/cgroup')) == self.record['owner'])
        observed = observe_held_backend_kernel_identity(self.controller.seal['executables']['psql'],
            self.controller.url, self.record['backend_kernel'], self.controller.binding['database'],
            self.controller.backend_scope.check(), owner={name: self.record['owner'][name] for name in ('pid', 'birth', 'uid')})
        require(observed['owner_connection_observed'] is True and observed['original_backend_kernel_observed'] is True)
        require(observed['lease_acquired'] is False)
        lifecycle = self.controller.snapshot.get('lifecycle')
        require(type(lifecycle) is dict and lifecycle['worker'] == 'native')
        require(lifecycle['recorded_status'] == 'running' and lifecycle['stage'] in {'verify', 'activate', 'enroll', 'public_verify'})
        require(lifecycle['operation'] == self.record['operation'] and lifecycle['candidate'] == self.record['candidate'])
        self.marker.check();self.controller._base()

    def _files(self):
        # Root-controlled content was streamed once; unchanged original metadata
        # and exact bounded entry set guard every later launch/current check.
        current = {}
        pending = [Path(self.web['path'])]
        while pending:
            path = pending.pop()
            info = path.lstat()
            require(path.resolve(strict=True) == path)
            current[str(path)] = fingerprint(info)
            require(str(path) in self.fingerprints and current[str(path)] == self.fingerprints[str(path)])
            if stat.S_ISDIR(info.st_mode):
                with os.scandir(path) as entries:
                    for entry in entries:
                        require(len(pending) + len(current) < 30000);pending.append(Path(entry.path))
        require(current == self.fingerprints)
        self.captured_files.read(Path(self.seal['edge_template']['path']), 16384)
        require(directory(self.parent, self.scope['uid']) == self.parent_identity)
        require(directory(self.work, self.scope['uid']) == self.work_identity)
        require(private_file(self.config_path, self.scope['uid']) == self.config_identity)

    def _launch(self, name, arguments, environment, cwd):
        self._current();self._files()
        leaf = self.scope['groups'][name]
        require(group_identity(Path(leaf['path']), self.scope['uid']) == leaf and not members(leaf['path']))
        require('nr_descendants 0' in (Path(leaf['path']) / 'cgroup.stat').read_text())
        group_fd = self._group_descriptor(leaf)
        def enter():
            require(group_identity(Path(leaf['path']), self.scope['uid']) == leaf)
            fd = os.open('cgroup.procs', os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=group_fd)
            try:os.write(fd, str(os.getpid()).encode('ascii'))
            finally:os.close(fd);os.close(group_fd)
        output_path = self.work / (name + '.private.log')
        try:
            with output_path.open('xb') as output:
                process = subprocess.Popen(arguments, cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
                    stdout=output, stderr=subprocess.STDOUT, preexec_fn=enter, umask=0o077, pass_fds=(group_fd,))
        finally:os.close(group_fd)
        self.processes[name] = process
        original = process_identity(process.pid, self.scope['uid'], self.scope['gid'],
                                    leaf['path'].removeprefix('/sys/fs/cgroup'))
        require(process.pid in members(leaf['path']))
        self.births[name] = original
        self._current();self._files()

    def start(self):
        try:
            require(self.state == 'prepared')
            self.births = {}
            environment = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'HOME': str(self.work)}
            web = Path(self.web['path'])
            self._launch('web', [self.controller.seal['executables']['node'], str(web / 'node_modules/srvx/bin/srvx.mjs'),
                '--prod', '-s', 'dist/client', 'server.mjs'], {**environment, **self.configuration['web']}, web)
            self._launch('edge', [self.controller.seal['executables']['caddy'], 'run', '--config', str(self.config_path),
                '--adapter', 'caddyfile'], {**environment, 'GITGOOD_PROXY_KEY': self.configuration['forge']['GITGOOD_PROXY_KEY'],
                'XDG_DATA_HOME': str(self.work / 'caddy-data'), 'XDG_CONFIG_HOME': str(self.work / 'caddy-config')}, self.work)
            self.state = 'running'
            return self.check()
        except Exception:
            self.stop();raise PublicRuntimeRefused('Native public runtime unavailable or changed') from None

    def check(self):
        try:
            require(self.state == 'running')
            self._current();self._files()
            require(set(self.processes) == {'web', 'edge'})
            for name, process in self.processes.items():
                leaf = self.scope['groups'][name]
                require(process.poll() is None and process_identity(process.pid, self.scope['uid'], self.scope['gid'],
                    leaf['path'].removeprefix('/sys/fs/cgroup')) == self.births[name])
                require(process.pid in members(self.scope['groups'][name]['path']))
            self._current()
            return {'original_controller_and_runtime_current': True, 'fixed_public_services_running': True,
                    'public_activation_verified': False, 'complete_journey_acceptance': False}
        except Exception:
            self.stop();raise PublicRuntimeRefused('Native public runtime unavailable or changed') from None

    def stop(self):
        """Quiesce only original leaves under still-held controller/kernel custody.

        This intentionally needs no functioning SQL connection or live owner.
        Changed controller, unit, credentials, boot or cgroup identity refuses.
        Retained journal/ownership/artifact/configuration files are never removed.
        """
        if self.closed_receipt is not None:
            return dict(self.closed_receipt)
        self.usable = False
        self.state = 'stopped'
        self.controller._controller()
        descriptors = {}
        try:
            # Capture all original directory descriptors before the first effect;
            # a pathname replacement cannot redirect a later kill to a new group.
            for name in ('edge', 'web', 'native'):
                leaf = self.scope['groups'][name]
                descriptors[name] = self._group_descriptor(leaf)
                require('nr_descendants 0' in (Path(leaf['path']) / 'cgroup.stat').read_text())
                require(len(members(leaf['path'])) <= 1024)
            self.controller._controller()
            for descriptor in descriptors.values():
                fd = os.open('cgroup.kill', os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=descriptor)
                try:require(os.write(fd, b'1') == 1)
                finally:os.close(fd)
        finally:
            for descriptor in descriptors.values():os.close(descriptor)
        deadline = time.monotonic() + 10
        for name in ('edge', 'web', 'native'):
            leaf = self.scope['groups'][name]
            while 'populated 0' not in (Path(leaf['path']) / 'cgroup.events').read_text():
                require(time.monotonic() < deadline);time.sleep(.05)
            require(group_identity(Path(leaf['path']), self.scope['uid']) == leaf and not members(leaf['path']))
        for process in self.processes.values():
            process.wait(timeout=max(.1, deadline - time.monotonic()))
        self.controller._controller()
        self.marker.close()
        self.closed_receipt = {'original_native_web_edge_leaves_empty': True, 'cleanup_actor': 'native-public-runtime',
                               'retained_responsibility_untouched': True}
        return dict(self.closed_receipt)

    def _group_descriptor(self, leaf):
        require(group_identity(Path(leaf['path']), self.scope['uid']) == leaf)
        fd = os.open(leaf['path'], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            info = os.fstat(fd)
            require((info.st_dev, info.st_ino, info.st_uid) == (leaf['device'], leaf['inode'], leaf['uid']))
            require(group_identity(Path(leaf['path']), self.scope['uid']) == leaf)
            return fd
        except Exception:
            os.close(fd);raise
