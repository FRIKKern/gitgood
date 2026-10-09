"""Inspect a digest-pinned native archive without extraction or code execution."""
import argparse
import hashlib
import json
import os
import posixpath
import re
import stat
import tarfile


def require(condition):
    if not condition:
        raise ValueError("Native artifact refused")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def inspect_native_artifact(path, digest, candidate):
    require(re.fullmatch(r"[0-9a-f]{64}", digest) is not None)
    require(re.fullmatch(r"[0-9a-f]{40}", candidate) is not None)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as source:
        before = os.fstat(source.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= 1_073_741_824)
        observed = hashlib.file_digest(source, "sha256").hexdigest()
        require(observed == digest)
        source.seek(0)
        with tarfile.open(fileobj=source, mode="r:gz") as archive:
            members, total = {}, 0
            for member in archive:
                name = member.name.rstrip("/") if member.isdir() else member.name
                require(name and len(name) <= 4096 and "\\" not in name and "\0" not in name)
                require(not name.startswith("/") and posixpath.normpath(name) == name)
                require(all(part not in ("", ".", "..") for part in name.split("/")))
                require(name.split("/")[0] in ("forge", "web") and name not in members)
                require(member.isfile() or member.isdir() or member.issym())
                require(not (member.mode & 0o7000) and member.size >= 0)
                if member.issym():
                    target = member.linkname
                    require(target and not target.startswith("/") and "\\" not in target)
                    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
                    require(resolved.split("/")[0] == name.split("/")[0])
                members[name] = member
                total += member.size
                require(len(members) <= 100_000 and total <= 4_294_967_296)

            # Even safe-looking child paths refuse beneath a symlink or non-directory.
            for name, member in members.items():
                parent = posixpath.dirname(name)
                while parent:
                    require(parent in members and members[parent].isdir())
                    parent = posixpath.dirname(parent)
                if member.issym():
                    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), member.linkname))
                    require(resolved in members and not members[resolved].issym())

            def content(name, limit):
                require(name in members and members[name].isfile() and members[name].size <= limit)
                with archive.extractfile(members[name]) as value:
                    data = value.read(limit + 1)
                require(len(data) == members[name].size and len(data) <= limit)
                return data

            identities = [name for name in members if re.fullmatch(
                r"forge/lib/gitgood-[0-9]+\.[0-9]+\.[0-9]+/priv/build-identity\.json", name)]
            require(len(identities) == 1)
            native = json.loads(content(identities[0], 131_072), object_pairs_hook=unique_object)
            web = json.loads(content("web/dist/build-identity.json", 131_072), object_pairs_hook=unique_object)
            require(isinstance(native, dict) and native == web)
            require(type(native.get("schema")) is int and native["schema"] == 1)
            require(native.get("candidate") == candidate and native.get("dirty") is False)
            require(set(native.get("locks", {})) == {"forge", "web", "toolchain"})
            require(set(native.get("requirements", {})) == {f"J{i:02}" for i in range(1, 18)})
            require(all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
                        for field in ("locks", "requirements") for value in native[field].values()))
            migrations = native.get("migrations")
            require(isinstance(migrations, list) and migrations)
            require(all(isinstance(value, str) and re.fullmatch(r"[0-9]{14}", value)
                        for value in migrations))
            require(migrations == sorted(set(migrations)))
            for name in ("forge/bin/gitgood", "web/server.mjs", "web/package.json"):
                require(name in members and members[name].isfile() and members[name].size > 0)
            require(members["forge/bin/gitgood"].mode & 0o111)
            beams = [name for name in members if re.fullmatch(r"forge/erts-[0-9.]+/bin/beam\.smp", name)]
            require(len(beams) == 1 and members[beams[0]].isfile())
            require(members[beams[0]].mode & 0o111)
            with archive.extractfile(members[beams[0]]) as binary:
                header = binary.read(20)
            require(len(header) == 20 and header[:6] == b"\x7fELF\x02\x01")
            require(int.from_bytes(header[18:20], "little") == 62)
        after = os.fstat(source.fileno())
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns))
    return {"schema": 1, "status": "inspected", "candidate": candidate,
            "artifact_sha256": observed, "artifact_bytes": before.st_size,
            "platform": "linux-x86_64", "members": len(members), "declared_bytes": total,
            "migrations": migrations,
            "checks": ["independent_digest", "bounded_safe_inventory", "matching_build_identities",
                       "clean_expected_candidate", "requirement_dependency_bindings",
                       "ordered_migrations", "native_web_entry_points", "linux_x86_64_runtime"],
            "limitations": ["Inspection executes no code and does not establish readiness, compatibility, activation or J15 acceptance."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("archive")
    parser.add_argument("sha256")
    parser.add_argument("candidate")
    args = parser.parse_args()
    try:
        print(json.dumps(inspect_native_artifact(args.archive, args.sha256, args.candidate)))
    except Exception:
        print(json.dumps({"status": "refused", "error": "Native artifact inspection failed"}))
        raise SystemExit(1)
