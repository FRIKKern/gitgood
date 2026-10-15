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

## Captured executable metadata

The five captured executable digests retain their original initial canonical
resolution on every fingerprint. Each resulting ancestor still receives a fresh
`lstat`, real-directory, Root-owner and non-writable-mode check. Resolving every
already canonical prefix again is redundant with that complete initial resolve
and the subsequent ancestor checks. Only these duplicate prefix resolutions are
removed; no metadata field, alias comparison, byte digest, content read, frozen
contract, before/after check or permanent refusal is removed or cached.

Actual Root cases retain replacement, restored-mtime edits, permission/owner and
hard-link changes, original parent identity, alias retargeting and interrupted
hash refusal. Additional cases substitute an ancestor alias while retaining the
original executable inode, and perform one hundred fresh metadata reads against
the same five originally captured digests. These checks and complete staging
performance require exact hosted evidence; diagnostic counters are not production
deadline acceptance.

## Private binding resources

Private binding directory and file readers now check absolute single-root POSIX
spelling and freshly inspect every ancestor as a real directory. Directory
leaves must still have the expected owner and `0700` mode. File leaves are
explicitly checked as regular before the unchanged `O_NOFOLLOW` open, bounded
content read, before/after descriptor metadata, single-link/owner/`0600` checks
and SHA-256 calculation. No content or identity is newly cached. This avoids
performing a separate canonical resolution walk for each already fixed path.

The persistent binding's root still equals the fixed installation path. Its
ancestors retain fresh real-directory, Root-owner and protected-mode checks;
resolving each prefix again is redundant. Executable alias resolution and
captured executable metadata remain unchanged. Actor, SQL, socket, lifecycle,
history and effect guards, complete archive and deadline are also unchanged.

Five portable cases include the existing admission boundaries and an explicit
POSIX spelling stand-in. Twelve actual Linux filesystem cases cover private
hashes, configuration, bounds, owners, modes, hard links, FIFO refusal, file and
directory aliases, an ancestor alias retaining the original leaf inode, parent
traversal, same-content replacement and restored-mtime edits. Twenty fresh
private metadata/content pairs record only count and elapsed time. Hosted CI
executes the exact seventeen-case module under Root. These checks do not
establish full staging performance, runtime or recovery acceptance.

## Persistent metadata fingerprints

`persistent_fingerprint` still observes previously content-validated resources;
it supplies no content validation, actor admission, database exclusion or effect
authority. Each complete observation now checks canonical single-root POSIX
spelling and freshly inspects the union of resource, machine-id and file
ancestors as real directories. This replaces separate resolution walks for
every path. No ancestor or returned metadata is cached across observations.

All original resource/file identity, owner, mode, size, time, link-count and
executable checks remain. The returned keys and four-field directory/eight-field
file tuples remain exactly the same. Ancestors checked only for alias refusal,
including a machine-id ancestor absent from the old output, do not become new
fingerprint keys. Recorded parents retain the original ownership/mode checks
and identity fields. Executable alias capture, full before/after fingerprints,
original process/service/SQL/socket/history guards and every stage effect and
deadline remain unchanged.

Two portable cases use explicit POSIX grammar stand-ins. Twelve Root filesystem
cases use synthetic ordinary-owned resources under a protected scratch parent;
binding/content admission is an explicit stand-in. They verify the complete
output shape, leaf and ancestor aliases retaining original inodes, parent
traversal, same-content replacement, restored-mtime edits, owner/mode/link changes
and a replaced executable parent retaining every executable inode. Twenty fresh
complete fingerprints record only count and elapsed time. Hosted execution of
these cases and the complete uninstrumented staging/runtime proof remain
required before performance or recovery acceptance.
