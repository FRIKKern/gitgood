import copy
import unittest
from unittest.mock import patch

from native_service_scope import ServiceRefused
from native_worker_scope import _ancestry, observe_worker


class WorkerAdmissionBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.scope = {"uid": 1000, "gid": 1000, "manager": {"pid": 41, "mount_namespace": "mnt:[9]", "cgroup_namespace": "cgroup:[8]"},
                      "groups": {"native": {"path": "/sys/fs/cgroup/owned/native"}, "maintenance": {"path": "/sys/fs/cgroup/owned/maintenance"}}}
        self.parents = {43: 42, 42: 40}
        self.identities = {pid: {"pid": pid, "birth": str(pid * 10), "mount_namespace": "mnt:[9]", "cgroup_namespace": "cgroup:[8]"} for pid in [42, 43]}
        self.patches = [patch("native_worker_scope.os.getpid", return_value=43),
                        patch("native_worker_scope.process_identity", side_effect=lambda pid, *args: copy.deepcopy(self.identities[pid])),
                        patch("native_worker_scope.read_bytes", side_effect=self.stat)]
        for item in self.patches:item.start();self.addCleanup(item.stop)

    def stat(self, path):
        pid = int(path.parent.name)
        fields = ["S", str(self.parents[pid])] + ["0"] * 17 + [self.identities[pid]["birth"]]
        return (str(pid) + " (worker with spaces) " + " ".join(fields)).encode()

    def call(self, **options):
        defaults = {"worker": "native", "owner_pid": 42, "cpu_quota_us": 200000, "memory_bytes": 268435456}
        return observe_worker("00000000-0000-4000-8000-000000000001", "a" * 64, **{**defaults, **options})

    def test_fixed_roles_and_bounded_real_pid_are_required_before_host_observation(self):
        for worker, owner in [("driver", 42), ("web", 42), ("edge", 42), ("../native", 42), ([], 42), ("native", True), ("native", 1), ("native", 2147483648)]:
            with self.subTest(worker=worker, owner=owner), patch("native_worker_scope._observe_service") as service, self.assertRaises(ServiceRefused):
                self.call(worker=worker, owner_pid=owner)
            service.assert_not_called()

    def test_actual_owner_and_helper_ancestry_is_retained_without_readiness_claim(self):
        with patch("native_worker_scope._observe_service", return_value=self.scope) as service:
            result = self.call()
        self.assertEqual(result["owner"], self.identities[42]);self.assertEqual(result["caller"], self.identities[43])
        self.assertFalse(result["generation_publication_established"]);self.assertFalse(result["installation_readiness_established"])
        self.assertEqual(service.call_count, 2);self.assertTrue(all(call.kwargs == {"caller_group": "native"} for call in service.call_args_list))

    def test_manager_cannot_be_borrowed_as_runtime_owner(self):
        with patch("native_worker_scope._observe_service", return_value=self.scope), self.assertRaises(ServiceRefused):
            self.call(owner_pid=41)

    def test_ancestry_cycle_or_unrelated_owner_refuses(self):
        for parent in [43, 1]:
            self.parents[43] = parent
            with self.subTest(parent=parent), self.assertRaises(ServiceRefused):_ancestry(42, self.scope, "native")

    def test_owner_in_other_namespace_cannot_authorize_the_helper(self):
        for namespace in ["mount_namespace", "cgroup_namespace"]:
            identities = copy.deepcopy(self.identities);identities[42][namespace] = "foreign:[7]"
            with self.subTest(namespace=namespace), patch("native_worker_scope.process_identity", side_effect=lambda pid, *args: identities[pid]), self.assertRaises(ServiceRefused):
                _ancestry(42, self.scope, "native")

    def test_birth_change_and_reparenting_during_observation_refuse(self):
        calls = 0
        def changed(path):
            nonlocal calls
            calls += 1
            result = self.stat(path)
            if calls > 1:result = result.replace(b"S 42 ", b"S 40 ")
            return result
        with patch("native_worker_scope.read_bytes", side_effect=changed), self.assertRaises(ServiceRefused):_ancestry(42, self.scope, "native")
        self.identities[43]["birth"] = "431"
        with patch("native_worker_scope.read_bytes", return_value=b"43 (worker) S 42 " + b"0 " * 17 + b"430"), self.assertRaises(ServiceRefused):
            _ancestry(42, self.scope, "native")

    def test_replaced_service_and_owner_between_complete_observations_refuse(self):
        replacement = copy.deepcopy(self.scope);replacement["manager"]["pid"] = 44
        with patch("native_worker_scope._observe_service", side_effect=[self.scope, replacement]), self.assertRaises(ServiceRefused):self.call()
        with patch("native_worker_scope._observe_service", return_value=self.scope), patch("native_worker_scope._ancestry", side_effect=[[self.identities[43], self.identities[42]], [self.identities[43], {**self.identities[42], "birth": "421"}]]), self.assertRaises(ServiceRefused):self.call()

    def test_missing_process_or_denied_observation_is_a_closed_refusal(self):
        for failure in [FileNotFoundError(), PermissionError(), ValueError(), KeyError("missing")]:
            with self.subTest(failure=type(failure)), patch("native_worker_scope._observe_service", side_effect=failure), self.assertRaises(ServiceRefused):self.call()


if __name__ == "__main__":unittest.main()
