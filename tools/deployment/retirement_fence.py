"""Durable admission fence outside the stores selected for retirement."""
import hashlib
import os
from pathlib import Path

from native_inventory import cgroup_identity, directory_identity, private_bytes
from retirement_stores import RetirementStores
from upgrade_journal import canonical, require


class RetirementFence:
    def __init__(self, journal, resource_plan):
        stores = RetirementStores(journal, resource_plan)
        self.root, self.bindings, self.journal = stores.root, stores.bindings, journal
        self.path = self.root / ".gitgood-retirement-v1.json"
        self.bytes = canonical({"protocol": 1, "installation": journal.plan["installation"],
                                "operation": journal.operation, "candidate": journal.plan["candidate"],
                                "plan_sha256": journal.plan_sha256,
                                "resource_plan_sha256": journal.plan["resource_plan_sha256"]}) + b"\n"

    def _custody(self, *, installing=False):
        self.journal._owned()
        require(self.journal.record["status"] in {"pending", "running", "failed", "uncertain"})
        if installing:
            require(self.journal.record["stage"] == "quiesce" and self.journal.record["status"] == "running")
        require(directory_identity(self.root, private=True) == self.bindings["resources"]["root"])
        for name in ["native", "web", "edge", "maintenance", "driver"]:
            group = self.bindings["cgroups"][name]
            require(cgroup_identity(self.bindings["installation"], name) == group)
            if name == "driver":
                require(Path("/proc/self/cgroup").read_text().splitlines() == ["0::" + group["kernel_path"]])

    def observe(self):
        self._custody()
        require(private_bytes(self.path, 4096) == self.bytes)
        self._custody()
        value = {"retirement_fence_verified": True,
                 "fence_sha256": hashlib.sha256(self.bytes).hexdigest(),
                 "plan_sha256": self.journal.plan_sha256}
        return {**value, "receipt_sha256": hashlib.sha256(canonical(value)).hexdigest()}

    def install(self):
        self._custody(installing=True)
        if not self.path.exists() and not self.path.is_symlink():
            descriptor = self.journal._private_open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            with os.fdopen(descriptor, "wb") as output:
                output.write(self.bytes)
                output.flush()
                os.fsync(output.fileno())
        # Same-intent retry also reestablishes durability after a lost sync reply.
        # Malformed/aliased/different intent is retained and refuses; never unlink
        # an admission fence in order to retry publication.
        require(private_bytes(self.path, 4096) == self.bytes)
        descriptor = self.journal._private_open(self.path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        descriptor = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            require(directory_identity(self.root, private=True) == self.bindings["resources"]["root"])
            info = os.fstat(descriptor)
            require({"device": info.st_dev, "inode": info.st_ino, "uid": info.st_uid} ==
                    {key: self.bindings["resources"]["root"][key] for key in ["device", "inode", "uid"]})
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return self.observe()
