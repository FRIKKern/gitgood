"""Read-only lifecycle inventory under borrowed generation custody.

References retain original responsibility. They never establish reconciliation,
stage authority, current worker admission or installation readiness.
"""
import copy
import itertools
import json
import os
import re
import stat

from enrollment_journal import current_owner
from generation_custody import GenerationRecordCustody
from native_lifecycle_responsibility import (MAX_BYTES, MAX_OPERATIONS, MAX_RECORDS,
    LifecycleResponsibilityRefused, replay, require, sha, unique, validate_inventory)
from resource_generations import canonical, digest, identifier

REFERENCE_FIELDS = {'operation', 'request_sha256', 'origin_sha256', 'snapshot_sha256'}
FILE_FIELDS = ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode', 'st_nlink',
               'st_size', 'st_mtime_ns', 'st_ctime_ns')
DIRECTORY_FIELDS = ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode')


class NativeLifecycleHistory:
    """Observe complete histories without claiming, repairing or writing them.

    Unlike a journal claim, this view can read responsibility belonging to an old
    manager. The caller must already hold original generation custody; this view
    does not acquire a lock or infer absence of an old owner or its effects.
    """
    def __init__(self, custody):
        self.usable = False;self.descriptors = {}
        try:
            require(isinstance(custody, GenerationRecordCustody));custody.check()
            self.custody = custody;self.owner = current_owner()
            self.generations = custody._records()
            self.paths = {'history': custody.directory}
            self.identities = {};self.files = {};self.names = {}
            self.rows = {};self.heads = {}
            for role, parent, name in [('history', None, None),
                    ('lifecycle', 'history', 'lifecycle-responsibility-v2'),
                    ('records', 'lifecycle', 'records'), ('heads', 'lifecycle', 'heads')]:
                if parent is None:
                    fd = os.open(custody.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
                else:
                    self.paths[role] = self.paths[parent]/name
                    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                 dir_fd=self.descriptors[parent])
                self.descriptors[role] = fd;self.identities[role] = self._directory(os.fstat(fd))
            original = self.identities['history']
            require(dict(zip(['device', 'inode', 'uid'], original[:3])) == custody.identity)
            self.usable = True;self._check()
            require(self._names('lifecycle', 2) == ['heads', 'records'])
            for role, maximum in [('records', MAX_RECORDS), ('heads', MAX_OPERATIONS)]:
                names = self._names(role, maximum);self.names[role] = names
                for name in names:
                    # This view cannot complete, ignore or delete a partial.
                    require(not name.startswith('.partial-'))
                    value = self._read(role, name)
                    if role == 'records':
                        require(re.fullmatch(r'[0-9a-f]{64}\.json', name) and sha(value)+'.json' == name)
                        replay(value, self.generations)
                        origin = value['origin'];operation = origin['request']['operation']
                        require(origin['request']['installation'] == custody.installation)
                        self.rows[name[:-5]] = {'operation': operation, 'origin': sha(origin),
                            'previous': value['predecessor_sha256'], 'events': len(value['events']),
                            'events_sha256': sha(value['events']), 'prefix_sha256': sha(value['events'][:-1]),
                            'generation_sha256': value['generation_sha256'], 'request_sha256': origin['request_sha256']}
                    else:
                        require(name.endswith('.json'));identifier(name[:-5])
                        require(type(value) is dict and set(value) == {'protocol', 'kind', 'installation', 'operation', 'snapshot_sha256'})
                        require(type(value['protocol']) is int and value['protocol'] == 2 and value['kind'] == 'native_lifecycle_head')
                        require(value['installation'] == custody.installation and value['operation'] == name[:-5])
                        digest(value['snapshot_sha256']);self.heads[name[:-5]] = value
            validate_inventory(self.rows, self.heads)
            self.check()
        except Exception:
            self.close();raise LifecycleResponsibilityRefused('Native lifecycle history unavailable or uncertain') from None

    @staticmethod
    def _directory(info):
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700)
        return tuple(getattr(info, field) for field in DIRECTORY_FIELDS)

    @staticmethod
    def _file(info):
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1)
        require(stat.S_IMODE(info.st_mode) == 0o600 and 0 < info.st_size <= MAX_BYTES)
        return tuple(getattr(info, field) for field in FILE_FIELDS)

    def _names(self, role, maximum):
        with os.scandir(self.descriptors[role]) as entries:
            names = [entry.name for entry in itertools.islice(entries, maximum+1)]
        require(len(names) <= maximum);return sorted(names)

    def _check(self):
        require(self.usable and current_owner() == self.owner);self.custody.check()
        for role, fd in self.descriptors.items():
            require(self._directory(os.fstat(fd)) == self.identities[role])
            require(self.paths[role].resolve(strict=True) == self.paths[role])
            require(self._directory(self.paths[role].lstat()) == self.identities[role])

    def _read(self, role, name):
        self._check()
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                     dir_fd=self.descriptors[role])
        with os.fdopen(fd, 'rb') as source:
            before = self._file(os.fstat(source.fileno()));raw = source.read(MAX_BYTES+1)
            require(self._file(os.fstat(source.fileno())) == before and len(raw) == before[6])
        require(self._file(os.stat(name, dir_fd=self.descriptors[role], follow_symlinks=False)) == before)
        value = json.loads(raw, object_pairs_hook=unique);require(raw == canonical(value))
        self.files[(role, name)] = before;self._check();return value

    def check(self):
        try:
            self._check();require(self.custody._records() == self.generations)
            require(self._names('lifecycle', 2) == ['heads', 'records'])
            for role, maximum in [('records', MAX_RECORDS), ('heads', MAX_OPERATIONS)]:
                require(self._names(role, maximum) == self.names[role])
            for (role, name), identity in self.files.items():
                require(self._file(os.stat(name, dir_fd=self.descriptors[role], follow_symlinks=False)) == identity)
            self._check()
        except Exception:
            self.close();raise LifecycleResponsibilityRefused('Native lifecycle history unavailable or changed') from None

    def _reference(self, key):
        row = self.rows[key]
        return {'operation': row['operation'], 'request_sha256': row['request_sha256'],
                'origin_sha256': row['origin'], 'snapshot_sha256': key}

    def references(self):
        """All current operation tips, terminal and unfinished, in fixed order."""
        self.check()
        return [self._reference(self.heads[operation]['snapshot_sha256']) for operation in sorted(self.heads)]

    def fingerprint(self):
        self.check()
        # Generation publication writes beside this directory, never within it.
        # Pin lifecycle directory change times as well as every original file.
        directories = {role: (*identity, os.fstat(self.descriptors[role]).st_mtime_ns,
                             os.fstat(self.descriptors[role]).st_ctime_ns)
                       for role, identity in self.identities.items() if role != 'history'}
        result = {'directories': directories,
                  'files': {role+'/'+name: identity for (role, name), identity in self.files.items()}}
        self.check();return copy.deepcopy(result)

    def validate_references(self, references, generation_sha256):
        """Historic references must remain exact retained ancestors of generation."""
        self.check();self._validate_references(references, generation_sha256);self.check()
        return copy.deepcopy(references)

    def _validate_references(self, references, generation_sha256):
        # The publisher brackets a complete transition-chain validation once,
        # rather than rescanning all files for every recursive predecessor.
        require(type(references) is list and len(references) <= MAX_OPERATIONS)
        require(generation_sha256 in self.generations)
        operations = []
        for reference in references:
            require(type(reference) is dict and set(reference) == REFERENCE_FIELDS)
            identifier(reference['operation'])
            for name in REFERENCE_FIELDS - {'operation'}:digest(reference[name])
            key = reference['snapshot_sha256'];require(key in self.rows)
            require(reference == self._reference(key));operations.append(reference['operation'])
            ancestor = generation_sha256;seen = set()
            while ancestor != self.rows[key]['generation_sha256']:
                require(ancestor in self.generations and ancestor not in seen and len(seen) < 128)
                seen.add(ancestor);ancestor = self.generations[ancestor]['predecessor_sha256']
        require(operations == sorted(set(operations)))

    def close(self):
        self.usable = False
        for fd in self.descriptors.values():os.close(fd)
        self.descriptors.clear()
        # Borrowed custody and every original file remain the caller's.
