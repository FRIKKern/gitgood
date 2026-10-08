"""Pass a bounded, full v2 bundle's pack to strict native Git without buffering it."""
import os
import sys

git, repository, bundle = sys.argv[1:]
with open(bundle, "rb", buffering=0) as source:
    if source.read(16) != b"# v2 git bundle\n":
        raise SystemExit("full_v2_bundle_required")
    size = 16
    for _ in range(65):
        line = source.readline(2049)
        size += len(line)
        if size > 65536 or len(line) > 2048:
            raise SystemExit("bundle_header_limit")
        if line == b"\n":
            os.dup2(source.fileno(), 0)
            # The existing process adapter owns the entire group/job and its limits.
            os.execv(git, [git, "--git-dir", repository, "index-pack", "--stdin",
                          "--strict", "--fix-thin", "--check-self-contained-and-connected",
                          "--max-input-size=33554432"])
        if not line or not line.endswith(b"\n") or line.startswith((b"-", b"@")):
            raise SystemExit("full_bundle_required")
raise SystemExit("bundle_ref_limit")
