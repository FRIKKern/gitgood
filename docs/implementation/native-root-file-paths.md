# Root file path validation

Native observations must keep checking the original Root-controlled files and
ancestors before staging effects. The content reader and metadata fingerprint
now validate canonical POSIX spelling directly, then retain their existing
fresh ancestor and leaf checks. This avoids a second filesystem walk that only
resolves the same already checked path. Installed performance and full staging
remain unverified until the exact hosted proof passes.

The private `_root_file_path` helper requires an absolute path with a single
POSIX root and rejects parent traversal components. Existing `Path` normalization
of `.` and repeated interior separators is unchanged. Both callers still inspect
every ancestor with `lstat`, require a real Root-owned directory without group or
world write permission, and reject symlink ancestors. Metadata fingerprints
still require a regular Root-owned single-link leaf and retain every original
device/inode/size/time/UID/mode/link-count and parent identity field.

The content reader still opens the leaf with `O_NOFOLLOW`, checks the opened file
before and after its complete bounded read, and computes the same byte digest.
Original metadata/parent replacement or mutation still poisons retained content
views. No file identity, parent observation or live manager response is newly
cached. Bounds, read-only behavior, effect guards and response deadlines are
unchanged; the helper alone grants no actor or staging authority.

Two portable spelling tests use an explicit POSIX syntax stand-in. Fourteen
Linux filesystem cases retain the existing installed file/version checks and
exercise original-file replacement, restored-mtime mutation, permissions,
symlink leaf and ancestor substitution, parent replacement, hard links, aliased
paths and changed read contracts. Twenty repeated actual metadata/content pairs
record only their count and wall time. These cases require actual Linux Root
filesystem execution in hosted CI; portable mocks do not establish their result,
full guard timing, complete production staging or recovery acceptance.
