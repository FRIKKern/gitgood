"""Stop only the enrolled native installation groups behind a retained fence."""
import hashlib
from pathlib import Path
import time

from native_actions import NativeActions
from native_inventory import cgroup_identity
from retirement_fence import RetirementFence
from upgrade_journal import canonical, require

GROUPS = ("edge", "native", "web", "maintenance")


class RetirementQuiescence:
    def __init__(self, journal, resource_plan):
        self.fence = RetirementFence(journal, resource_plan)
        self.journal, self.bindings = journal, resource_plan["bindings"]

    def _custody(self, *, stopping=False):
        self.fence.observe()
        if stopping:
            require(self.journal.record["stage"] == "quiesce" and self.journal.record["status"] == "running")

    def observe(self):
        self._custody()
        identities = {}
        for name in GROUPS:
            group = cgroup_identity(self.bindings["installation"], name)
            require(group == self.bindings["cgroups"][name])
            path = Path(group["path"])
            require(dict(line.split() for line in (path / "cgroup.events").read_text().splitlines()).get("populated") == "0")
            require(not (path / "cgroup.procs").read_text().strip())
            identities[name] = group
        self._custody()
        value = {"owned_runtime_groups_empty": True, "retirement_fence_verified": True,
                 "groups_sha256": hashlib.sha256(canonical(identities)).hexdigest(),
                 "plan_sha256": self.journal.plan_sha256}
        return {**value, "receipt_sha256": hashlib.sha256(canonical(value)).hexdigest()}

    def stop(self):
        self._custody(stopping=True)
        for name in GROUPS:
            self._custody(stopping=True)
            group = cgroup_identity(self.bindings["installation"], name)
            require(group == self.bindings["cgroups"][name])
            path = Path(group["path"])
            descendants = [path, *[child for child in path.rglob("*") if child.is_dir()]]
            require(len(descendants) <= 256)
            pids = {int(pid) for child in descendants for pid in (child / "cgroup.procs").read_text().split()}
            require(len(pids) <= 4096)
            members = [member for pid in sorted(pids) if (member := NativeActions._process_birth(pid)) is not None]
            (path / "cgroup.kill").write_text("1")
            deadline = time.monotonic() + 15
            while dict(line.split() for line in (path / "cgroup.events").read_text().splitlines()).get("populated") != "0":
                require(time.monotonic() < deadline)
                self._custody(stopping=True)
                time.sleep(.05)
            require(not (path / "cgroup.procs").read_text().strip())
            NativeActions._reap_owned(members)
        return self.observe()
