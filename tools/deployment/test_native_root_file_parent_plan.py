"""Lexical planning only; filesystem custody remains freshly observed."""
from pathlib import PurePosixPath
import stat
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import native_service_scope as service
import test_native_service_file_custody as custody


class RootFileParentPlanTest(unittest.TestCase):
    def setUp(self):
        service._root_file_parent_plan.cache_clear()
        self.addCleanup(service._root_file_parent_plan.cache_clear)

    def test_plan_has_only_immutable_lexical_paths_and_original_parent_order(self):
        for raw in ['/', '/etc/os-release', '/root/./a//b', '/root/unicodé/leaf']:
            path=PurePosixPath(raw)
            expected=tuple((parent,str(parent)) for parent in path.parents)
            first=service._root_file_parents(path)
            self.assertEqual(first,expected)
            self.assertIs(service._root_file_parents(PurePosixPath(raw)),first)
            self.assertTrue(all(type(parent) is PurePosixPath and type(name) is str for parent,name in first))

    def test_retention_stays_bounded_and_eviction_changes_no_parent_walk(self):
        first=PurePosixPath('/synthetic/first/leaf')
        original=service._root_file_parents(first)
        for number in range(1000):service._root_file_parents(PurePosixPath('/synthetic',str(number),'leaf'))
        self.assertEqual(service._root_file_parent_plan.cache_info().currsize,64)
        self.assertEqual(service._root_file_parents(first),original)
        self.assertIsNot(service._root_file_parents(first),original)

    def test_long_or_deep_paths_keep_lazy_unretained_original_walk(self):
        for path in [PurePosixPath('/'+'a'*1025+'/leaf'),PurePosixPath('/'+'/'.join(['a']*65)+'/leaf')]:
            before=service._root_file_parent_plan.cache_info()
            value=service._root_file_parents(path)
            self.assertIs(iter(value),value)
            self.assertEqual(tuple(value),tuple((parent,str(parent)) for parent in path.parents))
            self.assertEqual(service._root_file_parent_plan.cache_info(),before)

    def test_each_fingerprint_repeats_every_ordered_parent_and_leaf_observation(self):
        events=[];changed={}
        class ModelPath(PurePosixPath):
            def lstat(self):
                events.append(str(self))
                value=dict(st_mode=stat.S_IFREG|0o600 if self.name=='leaf' else stat.S_IFDIR|0o700,
                    st_uid=0,st_nlink=1,st_size=8,st_dev=1,st_ino=2,st_mtime_ns=3,st_ctime_ns=4)
                value.update(changed.get(str(self),{}))
                return SimpleNamespace(**value)
        with patch.object(service,'Path',ModelPath):
            first=service._CapturedRootFiles._fingerprint('/root/parent/leaf',4096,False)
            expected=['/root/parent','/root','/','/root/parent/leaf']
            self.assertEqual(events,expected);events.clear()
            self.assertEqual(service._CapturedRootFiles._fingerprint('/root/parent/leaf',4096,False),first)
            self.assertEqual(events,expected);events.clear()
            changed['/root/parent']={'st_ino':99}
            self.assertNotEqual(service._CapturedRootFiles._fingerprint('/root/parent/leaf',4096,False),first)
            self.assertEqual(events,expected);events.clear()
            for mutation in [{'st_uid':1},{'st_mode':stat.S_IFDIR|0o777},{'st_mode':stat.S_IFLNK|0o777}]:
                changed['/root/parent']=mutation
                with self.assertRaises(service.ServiceRefused):service._CapturedRootFiles._fingerprint('/root/parent/leaf',4096,False)
                self.assertEqual(events,['/root/parent']);events.clear()


class WarmRootFileReplacementTest(custody.RootFileReplacementTest):
    """Repeat all actual Root mutation cases after the lexical plan is warm."""
    def setUp(self):
        service._root_file_parent_plan.cache_clear()
        self.addCleanup(service._root_file_parent_plan.cache_clear)
        super().setUp()
        path=service._root_file_path(self.path)
        first=service._root_file_parents(path)
        self.assertIs(service._root_file_parents(path),first)
        self.assertEqual(self.subject.read(self.path),self.original)

    def test_repeated_actual_metadata_and_content_observations_remain_fresh(self):
        expected=service._CapturedRootFiles._fingerprint(self.path,16777216,False)
        started=time.monotonic_ns()
        for _ in range(20):
            self.assertEqual(service._CapturedRootFiles._fingerprint(self.path,16777216,False),expected)
            self.assertEqual(service.root_file(self.path),self.original)
        print('actual_warm_root_file_observation_pairs=20 elapsed_ms='+str((time.monotonic_ns()-started)//1000000),flush=True)


if __name__=='__main__':unittest.main()
