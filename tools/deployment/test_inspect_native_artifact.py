import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from inspect_native_artifact import inspect_native_artifact


class ArtifactInspectionTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.path = Path(self.scratch.name) / "native.tar.gz"
        self.candidate = "a" * 40
        self.identity = {"schema": 1, "candidate": self.candidate, "dirty": False,
                         "locks": {name: "b" * 64 for name in ["forge", "web", "toolchain"]},
                         "requirements": {f"J{i:02}": "c" * 64 for i in range(1, 18)},
                         "migrations": ["20261008072524"]}

    def archive(self, *, native=None, web=None, extra=(), executable=True, machine=62):
        header = bytearray(20)
        header[:6] = b"\x7fELF\x02\x01"
        header[18:20] = machine.to_bytes(2, "little")
        files = {
            "forge/bin/gitgood": b"synthetic test entry point; never executed",
            "forge/lib/gitgood-0.1.0/priv/build-identity.json": json.dumps(native or self.identity).encode(),
            "forge/erts-17.1/bin/beam.smp": bytes(header),
            "web/dist/build-identity.json": json.dumps(web or self.identity).encode(),
            "web/server.mjs": b"synthetic test module; never executed",
            "web/package.json": b"{}",
        }
        directories = set()
        for name in files:
            parent = Path(name).parent
            while str(parent) != ".":
                directories.add(parent.as_posix())
                parent = parent.parent
        with tarfile.open(self.path, "w:gz") as archive:
            for name in sorted(directories, key=lambda value: (value.count("/"), value)):
                member = tarfile.TarInfo(name)
                member.type = tarfile.DIRTYPE
                member.mode = 0o755
                archive.addfile(member)
            for name, data in files.items():
                member = tarfile.TarInfo(name)
                member.size = len(data)
                member.mode = 0o755 if executable else 0o644
                archive.addfile(member, io.BytesIO(data))
            for member, data in extra:
                archive.addfile(member, io.BytesIO(data) if data is not None else None)
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def refuses(self, digest, candidate=None):
        before = self.path.read_bytes()
        with self.assertRaises((ValueError, tarfile.TarError, EOFError)):
            inspect_native_artifact(self.path, digest, candidate or self.candidate)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual([value.name for value in self.path.parent.iterdir()], [self.path.name])

    def test_inspection_changes_no_files_and_claims_no_activation(self):
        digest = self.archive()
        before = self.path.read_bytes()
        result = inspect_native_artifact(self.path, digest, self.candidate)
        self.assertEqual(result["status"], "inspected")
        self.assertEqual(len(result["checks"]), 8)
        self.assertIn("does not establish readiness", result["limitations"][0])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(len(list(self.path.parent.iterdir())), 1)

    def test_foreign_digest_and_candidate_refuse(self):
        digest = self.archive()
        self.refuses("0" * 64)
        self.refuses(digest, "d" * 40)

    def test_split_web_identity_and_dirty_artifact_refuse(self):
        self.refuses(self.archive(web={**self.identity, "candidate": "d" * 40}))
        dirty = {**self.identity, "dirty": True}
        self.refuses(self.archive(native=dirty, web=dirty))

    def test_missing_requirement_and_duplicate_migration_refuse(self):
        requirements = dict(self.identity["requirements"])
        requirements.pop("J17")
        missing = {**self.identity, "requirements": requirements}
        self.refuses(self.archive(native=missing, web=missing))
        duplicate = {**self.identity, "migrations": self.identity["migrations"] * 2}
        self.refuses(self.archive(native=duplicate, web=duplicate))

    def test_boolean_schema_refuses(self):
        invalid = {**self.identity, "schema": True}
        self.refuses(self.archive(native=invalid, web=invalid))

    def test_duplicate_and_traversing_members_refuse(self):
        for name in ["web/package.json", "forge/../../outside", "/forge/outside", "web\\outside"]:
            with self.subTest(name=name):
                member = tarfile.TarInfo(name)
                member.size = 1
                self.refuses(self.archive(extra=[(member, b"x")]))

    def test_links_special_files_and_setuid_refuse(self):
        for kind, target, mode in [(tarfile.SYMTYPE, "../../outside", 0o777),
                                   (tarfile.SYMTYPE, "/outside", 0o777),
                                   (tarfile.LNKTYPE, "web/package.json", 0o644),
                                   (tarfile.FIFOTYPE, "", 0o644),
                                   (tarfile.REGTYPE, "", 0o4755)]:
            with self.subTest(kind=kind, target=target):
                member = tarfile.TarInfo("web/unsafe")
                member.type, member.linkname, member.mode = kind, target, mode
                self.refuses(self.archive(extra=[(member, b"" if member.isfile() else None)]))

    def test_runtime_platform_and_execution_modes_refuse(self):
        self.refuses(self.archive(machine=183))
        self.refuses(self.archive(executable=False))

    def test_truncated_archive_refuses_even_with_its_own_digest(self):
        self.archive()
        self.path.write_bytes(self.path.read_bytes()[:50])
        self.refuses(hashlib.sha256(self.path.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
