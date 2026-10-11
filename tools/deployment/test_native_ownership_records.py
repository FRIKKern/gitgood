import copy
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

import native_ownership_records as records
from resource_generations import canonical
import test_resource_generations as generation_fixtures
from test_native_durable_database import GOOD


def fixture(uid=None):
    specification = generation_fixtures.ResourceGenerationRecordTest(); specification.setUp()
    scope = copy.deepcopy(specification.scope)
    if uid is not None:
        scope['uid'], scope['gid'] = uid, os.getgid()
        scope['manager']['uid'] = uid
        scope['manager']['security'].update(gid=os.getgid(), supplementary_groups=[])
        scope['parent']['uid'] = uid
        for value in scope['groups'].values(): value['uid'] = uid
    owner = {**copy.deepcopy(scope['manager']), 'pid':2001, 'birth':'30001'}
    record = {'protocol':2, 'kind':'native_application_ownership', 'installation':scope['installation'],
              'operation':str(uuid.uuid4()), 'candidate':'a'*40, 'mode':'runtime', 'binding_sha256':'b'*64,
              'pointer':{'protocol':2, 'installation':scope['installation'], 'operation':str(uuid.uuid4()),
                         'generation_sha256':'c'*64, 'transition_sha256':'d'*64},
              'scope':scope, 'owner':owner,
              'database_session':{'database':copy.deepcopy(GOOD), 'backend_pid':2222, 'backend_birth':'1770000000000000'},
              'guard':{'scope_sha256':hashlib.sha256(canonical({'scope':scope,'owner':owner,'worker':'native'})).hexdigest(),
                       'history_sha256':'e'*64, 'persistent_files_sha256':'f'*64}}
    return record


class OwnershipRecordShapeTest(unittest.TestCase):
    def test_complete_closed_record_validates_without_mutation(self):
        value = fixture(); before = copy.deepcopy(value)
        self.assertEqual(records.validate_record(value), before)
        self.assertEqual(value, before)

    def test_changed_owner_mode_pointer_database_or_authority_fields_refuse(self):
        for field, value in [('candidate','unconfigured'), ('protocol',True), ('mode','retire'),
                             ('installation',str(uuid.uuid4())), ('password','private fixture')]:
            record = fixture(); record[field] = value
            with self.subTest(field=field), self.assertRaises((records.OwnershipRecordRefused, records.GenerationRefused)):
                records.validate_record(record)
        for path, value in [(['owner','birth'],False), (['owner','uid'],1),
                            (['database_session','backend_pid'],True),
                            (['database_session','database','superuser'],True),
                            (['pointer','installation'],str(uuid.uuid4())),
                            (['guard','scope_sha256'],'0'*64)]:
            record = fixture(); destination = record
            for key in path[:-1]: destination = destination[key]
            destination[path[-1]] = value
            with self.subTest(path=path), self.assertRaises((records.OwnershipRecordRefused, records.GenerationRefused, records.DatabaseRefused)):
                records.validate_record(record)


@unittest.skipUnless(sys.platform == 'linux' and os.getuid() != 0, 'ordinary Linux ownership custody')
class OwnershipRecordCustodyTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='gitgood-ownership-record-')
        self.addCleanup(temporary.cleanup)
        self.storage = Path(temporary.name); self.storage.chmod(0o700)
        value = self.storage.stat()
        self.identity = {'device':value.st_dev,'inode':value.st_ino,'uid':value.st_uid}
        self.record = fixture(os.getuid())
        self.subject = records.NativeOwnershipRecords(self.storage, self.record['installation'], self.identity)
        self.directory = self.storage / '.gitgood-ownership-v2'
        self.target = self.directory / (self.record['operation'] + '.json')

    def snapshot(self):
        return {path.name:(path.lstat().st_ino,path.lstat().st_nlink,path.read_bytes()) for path in self.directory.iterdir()}

    def test_inspection_of_absence_creates_nothing_and_grants_no_replacement(self):
        before = self.storage.stat()
        with patch.object(records.os, 'mkdir', side_effect=AssertionError('inspection must not create')):
            result = self.subject.inspect()
        self.assertEqual(list(self.storage.iterdir()), [])
        self.assertEqual(self.storage.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertEqual(result, {'ownership_directory_present':False, 'records':[],
                                 'installation_readiness_established':False, 'replacement_admitted':False})

    def test_inspection_preserves_complete_records_and_returns_detached_values(self):
        self.subject.retain(self.record)
        second = {**self.record, 'operation':str(uuid.uuid4()), 'candidate':'b'*40}
        self.subject.retain(second)
        before = self.snapshot()
        result = self.subject.inspect()
        expected = sorted([self.record, second], key=lambda value:value['operation'])
        self.assertEqual(result['records'], expected)
        self.assertTrue(result['ownership_directory_present'])
        self.assertFalse(result['replacement_admitted'])
        result['records'][0]['candidate'] = '0'*40
        self.assertEqual(self.subject.inspect()['records'], expected)
        self.assertEqual(self.snapshot(), before)

    def test_inspection_preserves_unknown_partial_and_hardlinked_responsibility(self):
        self.subject.retain(self.record)
        partial = self.directory/'.partial-uncertain'; partial.write_bytes(b'uncertain'); partial.chmod(0o600)
        before = self.snapshot()
        with self.assertRaises(records.OwnershipRecordRefused): self.subject.inspect()
        self.assertEqual(self.snapshot(), before)
        partial.unlink()
        os.link(self.target, partial)
        before = self.snapshot()
        with self.assertRaises(records.OwnershipRecordRefused): self.subject.inspect()
        self.assertEqual(self.snapshot(), before)

    def test_inspection_refuses_identical_bytes_replacement_between_reads(self):
        self.subject.retain(self.record)
        original = self.subject._read
        calls = 0
        def replacement(descriptor, name):
            nonlocal calls
            calls += 1
            if calls == 3:
                source = self.storage/'replacement'; source.write_bytes(canonical(self.record)); source.chmod(0o600)
                os.replace(source, self.target)
            return original(descriptor, name)
        with patch.object(self.subject, '_read', side_effect=replacement):
            with self.assertRaises(records.OwnershipRecordRefused): self.subject.inspect()
        self.assertEqual(self.target.read_bytes(), canonical(self.record))

    def test_inspection_refuses_replaced_directory_without_redirecting_reads(self):
        self.subject.retain(self.record)
        moved = self.storage/'retained-original'
        original = self.subject._layout
        calls = 0
        def replacement(descriptor):
            nonlocal calls
            calls += 1
            if calls == 2:
                self.directory.rename(moved); self.directory.mkdir(mode=0o700)
            return original(descriptor)
        with patch.object(self.subject, '_layout', side_effect=replacement):
            with self.assertRaises(records.OwnershipRecordRefused): self.subject.inspect()
        self.assertEqual(list(self.directory.iterdir()), [])
        self.assertEqual((moved/self.target.name).read_bytes(), canonical(self.record))

    def test_inspection_refuses_replaced_storage_before_absence_result(self):
        with tempfile.TemporaryDirectory(prefix='gitgood-inspection-replacement-') as temporary:
            base = Path(temporary); storage = base/'storage'; storage.mkdir(mode=0o700)
            info = storage.stat()
            subject = records.NativeOwnershipRecords(storage, self.record['installation'],
                {'device':info.st_dev,'inode':info.st_ino,'uid':info.st_uid})
            storage.rename(base/'original'); storage.mkdir(mode=0o700)
            with self.assertRaises(records.OwnershipRecordRefused): subject.inspect()
            self.assertEqual(list(storage.iterdir()), [])

    def test_directory_created_during_absence_observation_refuses(self):
        original = records.os.open
        def concurrent_creation(path, flags, *args, **options):
            if path == '.gitgood-ownership-v2':
                self.directory.mkdir(mode=0o700)
                raise FileNotFoundError('Concurrent fixture creation')
            return original(path, flags, *args, **options)
        with patch.object(records.os, 'open', side_effect=concurrent_creation):
            with self.assertRaises(records.OwnershipRecordRefused): self.subject.inspect()
        self.assertTrue(self.directory.is_dir())
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_atomic_record_and_identical_retry_preserve_bytes_and_inode(self):
        result = self.subject.retain(self.record)
        before = self.snapshot()
        self.assertEqual(self.subject.retain(self.record), result)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.target.read_bytes(), canonical(self.record))
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.target.stat().st_nlink, 1)
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o700)
        self.assertFalse(result['installation_readiness_established'])

    def test_changed_request_for_retained_operation_never_overwrites(self):
        self.subject.retain(self.record); before = self.snapshot()
        changed = {**self.record,'candidate':'b'*40}
        with self.assertRaises(records.OwnershipRecordRefused): self.subject.retain(changed)
        self.assertEqual(self.snapshot(), before)

    def test_failure_before_publication_retains_synced_partial_and_refuses_retry(self):
        with patch.object(records.os,'link',side_effect=OSError('lost publication')):
            with self.assertRaises(records.OwnershipRecordRefused): self.subject.retain(self.record)
        before = self.snapshot()
        self.assertEqual(len(before),1)
        self.assertTrue(next(iter(before)).startswith('.partial-'))
        self.assertEqual(next(iter(before.values()))[2],canonical(self.record))
        with self.assertRaises(records.OwnershipRecordRefused): self.subject.retain(self.record)
        self.assertEqual(self.snapshot(), before)

    def test_failure_after_publication_retains_both_links_and_refuses_retry(self):
        with patch.object(records.os,'unlink',side_effect=OSError('lost unlink acknowledgement')):
            with self.assertRaises(records.OwnershipRecordRefused): self.subject.retain(self.record)
        before = self.snapshot()
        self.assertEqual(len(before),2)
        self.assertTrue(all(item[1] == 2 for item in before.values()))
        self.assertTrue(all(item[2] == canonical(self.record) for item in before.values()))
        with self.assertRaises(records.OwnershipRecordRefused): self.subject.retain(self.record)
        self.assertEqual(self.snapshot(),before)

    def test_unknown_responsibility_permissions_and_symlink_refuse_without_cleanup(self):
        self.subject.retain(self.record)
        unknown = self.directory / '.partial-unknown'; unknown.write_bytes(b'uncertain'); unknown.chmod(0o600)
        before = self.snapshot()
        with self.assertRaises(records.OwnershipRecordRefused): self.subject.retain(self.record)
        self.assertEqual(self.snapshot(),before)
        unknown.unlink(); self.target.chmod(0o644)
        with self.assertRaises(records.OwnershipRecordRefused): self.subject.retain(self.record)
        self.assertEqual(self.target.stat().st_mode & 0o777,0o644)
        self.target.chmod(0o600)
        alias = self.directory / (str(uuid.uuid4())+'.json'); alias.symlink_to(self.target)
        with self.assertRaises(records.OwnershipRecordRefused): self.subject.retain(self.record)
        self.assertTrue(alias.is_symlink())

    def test_replaced_storage_is_refused_before_ownership_directory_creation(self):
        moved = self.storage.with_name(self.storage.name+'-moved')
        self.storage.rename(moved); self.storage.mkdir(mode=0o700)
        self.addCleanup(lambda: moved.rename(self.storage) if not self.storage.exists() else None)
        self.addCleanup(lambda: self.storage.rmdir())
        with self.assertRaises(records.OwnershipRecordRefused): self.subject.retain(self.record)
        self.assertEqual(list(self.storage.iterdir()),[])

    def test_invalid_record_refuses_before_any_filesystem_creation(self):
        with self.assertRaises(records.OwnershipRecordRefused): self.subject.retain({**self.record,'candidate':'unconfigured'})
        self.assertEqual(list(self.storage.iterdir()),[])

    def test_concurrent_named_record_is_never_replaced(self):
        actual = records.os.link
        competing = {**self.record,'candidate':'b'*40}
        def competition(source, destination, **options):
            self.target.write_bytes(canonical(competing)); self.target.chmod(0o600)
            return actual(source,destination,**options)
        with patch.object(records.os,'link',side_effect=competition):
            with self.assertRaises(records.OwnershipRecordRefused): self.subject.retain(self.record)
        self.assertEqual(self.target.read_bytes(),canonical(competing))
        self.assertTrue(any(path.name.startswith('.partial-') for path in self.directory.iterdir()))

    def test_directory_replacement_cannot_redirect_descriptor_based_publication(self):
        actual = records.os.link
        moved = self.storage / 'retained-original-ownership'
        def replacement(source,destination,**options):
            self.directory.rename(moved); self.directory.mkdir(mode=0o700)
            return actual(source,destination,**options)
        with patch.object(records.os,'link',side_effect=replacement):
            with self.assertRaises(records.OwnershipRecordRefused): self.subject.retain(self.record)
        self.assertEqual(list(self.directory.iterdir()),[])
        self.assertEqual((moved/self.target.name).read_bytes(),canonical(self.record))

    def test_record_file_and_directory_synchronization_precede_completed_receipt(self):
        actual = records.os.fsync; kinds = []
        def observed(fd):
            import stat
            kinds.append('directory' if stat.S_ISDIR(os.fstat(fd).st_mode) else 'file')
            return actual(fd)
        with patch.object(records.os,'fsync',side_effect=observed): self.subject.retain(self.record)
        self.assertEqual(kinds, ['directory','file','directory','directory','directory'])
