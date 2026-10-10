import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from native_service_scope import PROPERTIES, ServiceRefused, bounded_command, observe_service, parse_properties, process_security


class ServiceAdmissionBoundaryTest(unittest.TestCase):
    security = "Gid:\t1000 1000 1000 1000\nGroups:\t1000\n" + "\n".join(name + ":\t0000000000000000" for name in ["CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"]) + "\nNoNewPrivs:\t1\n"

    def test_root_other_or_mixed_group_credentials_are_not_ordinary(self):
        self.assertEqual(process_security(self.security, 1000)["gid"], 1000)
        for status, gid in [(self.security, 0), (self.security.replace("Groups:\t1000", "Groups:\t1000 0"), 1000),
                            (self.security.replace("Groups:\t1000", "Groups:\t1000 27"), 1000),
                            (self.security.replace("Gid:\t1000 1000 1000 1000", "Gid:\t1000 0 1000 1000"), 1000)]:
            with self.subTest(gid=gid), self.assertRaises(ServiceRefused):
                process_security(status, gid)

    def test_any_retained_capability_refuses_including_bounding_and_ambient(self):
        for name in ["CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"]:
            with self.subTest(name=name), self.assertRaises(ServiceRefused):
                process_security(self.security.replace(name + ":\t0000000000000000", name + ":\t0000000000000001"), 1000)

    def test_missing_or_duplicate_privilege_state_and_disabled_no_new_privileges_refuse(self):
        for status in [self.security.replace("NoNewPrivs:\t1", "NoNewPrivs:\t0"), self.security.replace("NoNewPrivs:\t1\n", ""),
                       self.security + "NoNewPrivs:\t1\n", self.security.replace("CapAmb:\t0000000000000000", "CapAmb:\tunknown")]:
            with self.subTest(status=status), self.assertRaises(ServiceRefused):
                process_security(status, 1000)

    def test_malformed_installation_refuses_before_any_host_or_manager_access(self):
        for installation in [None, [], "", "../other", "00000000000040008000000000000001", "00000000-0000-4000-8000-00000000000A"]:
            with self.subTest(installation=installation), patch("native_service_scope.pwd.getpwnam") as account, patch("native_service_scope.bounded_command") as command:
                with self.assertRaises(ServiceRefused):
                    observe_service(installation, "a" * 64, cpu_quota_us=200000, memory_bytes=268435456)
                account.assert_not_called()
                command.assert_not_called()

    def test_invalid_digest_cannot_select_an_unpinned_unit(self):
        for digest in [None, [], "A" * 64, "a" * 63, "a" * 64 + "\n"]:
            with self.subTest(digest=digest), patch("native_service_scope.pwd.getpwnam") as account:
                with self.assertRaises(ServiceRefused):
                    observe_service("00000000-0000-4000-8000-000000000001", digest, cpu_quota_us=200000, memory_bytes=268435456)
                account.assert_not_called()

    def test_unbounded_or_boolean_resource_limits_refuse_before_account_lookup(self):
        for cpu, memory in [(False, 268435456), (200000, True), (999, 268435456), (6400001, 268435456), (200000, 134217727), (200000, 68719476737)]:
            with self.subTest(cpu=cpu, memory=memory), patch("native_service_scope.pwd.getpwnam") as account:
                with self.assertRaises(ServiceRefused):
                    observe_service("00000000-0000-4000-8000-000000000001", "a" * 64, cpu_quota_us=cpu, memory_bytes=memory)
                account.assert_not_called()

    def test_manager_reply_cannot_override_a_property_with_a_duplicate(self):
        raw = "\n".join(key + "=" for key in PROPERTIES).encode()
        with self.assertRaises(ServiceRefused):
            parse_properties(raw + b"\nMainPID=123")

    def test_manager_reply_must_be_closed_and_complete(self):
        good = "\n".join(key + "=" for key in PROPERTIES).encode()
        for raw in [good + b"\nEnvironment=private-token", good.replace(b"MainPID=\n", b""), good + b"\0", b"x" * 16385]:
            with self.subTest(raw_length=len(raw)), self.assertRaises(ServiceRefused):
                parse_properties(raw)

    def test_unsupported_host_does_not_invoke_systemctl(self):
        with patch("native_service_scope.platform.system", return_value="Unsupported"), patch("native_service_scope.bounded_command") as command:
            with self.assertRaises(ServiceRefused):
                observe_service("00000000-0000-4000-8000-000000000001", "a" * 64, cpu_quota_us=200000, memory_bytes=268435456)
            command.assert_not_called()


@unittest.skipUnless(sys.platform == "linux", "Bounded native subprocess pipes require Linux")
class BoundedManagerProcessTest(unittest.TestCase):
    def test_caller_credentials_bus_host_and_pager_do_not_reach_the_manager(self):
        with patch.dict(os.environ, {"PRIVATE_TOKEN": "private-value", "DBUS_SYSTEM_BUS_ADDRESS": "foreign-bus", "SYSTEMD_HOST": "foreign-host", "SYSTEMD_PAGER": "foreign-program"}):
            code = "import os;assert not any(k in os.environ for k in ['PRIVATE_TOKEN','DBUS_SYSTEM_BUS_ADDRESS','SYSTEMD_HOST']);assert os.environ['SYSTEMD_PAGER']=='cat';print('ok')"
            self.assertEqual(bounded_command([sys.executable, "-c", code]), b"ok\n")

    def test_oversized_output_refuses_and_reaps_the_owned_child(self):
        with self.assertRaises(ServiceRefused):
            bounded_command([sys.executable, "-c", "import os,time;os.write(1,b'x'*20000);time.sleep(10)"], maximum=1024)

    def test_hung_or_failed_manager_is_not_a_successful_observation(self):
        with self.assertRaises(ServiceRefused):
            bounded_command([sys.executable, "-c", "import time;time.sleep(10)"], timeout=.05)
        with self.assertRaises(ServiceRefused):
            bounded_command([sys.executable, "-c", "raise SystemExit(1)"])


if __name__ == "__main__":
    unittest.main()
