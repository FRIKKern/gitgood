# Protected native artifact staging

Native runtime code must be controlled by Root. The existing ordinary-user
stager cannot supply that custody. `NativeProtectedArtifactStage` copies an
independently pinned archive, inspects its actual build identity, and publishes
read-only Root-owned code without replacement. Root policy allocation, ordinary
controller dispatch and complete installation/recovery remain unfinished.

## Original authority and input custody

The Root-only constructor accepts only an installation UUID and operation UUID.
Its fixed policy is `/etc/gitgood/installations/INSTALLATION/artifacts/OPERATION.json`.
Canonical protocol 2, unique fields, the original request/hash, original observed
controller scope/hash, candidate, running-stage snapshot hash, original directory
identities and original archive metadata/digest are mandatory. There are no caller
paths, programs, environments, callbacks or authority maps.

The archive is fixed at
`/var/lib/gitgood/artifact-inputs/INSTALLATION/OPERATION/archive.tar.gz` and the
destination parent at `/opt/gitgood/artifacts/INSTALLATION`. Protected Root parents
and original destination device/inode are required. The archive is an original
single-link Root-owned read-only file; original descriptor/path metadata is
rechecked around streaming. The independently sealed lifecycle request and exact
ordinary-owned current head/snapshot must remain running at `stage` after
`inspect`. Their directory and file identities, canonical bytes and hashes remain
fixed. This component does not replay journal history or allocate that policy.
The future allocator must independently validate original request/history and
stage admission before issuing it; a snapshot receipt alone grants no effects.

Directory and private-file admission validate canonical POSIX spelling, freshly
check every named ancestor as a directory and refuse a symlink leaf. The lexical
walk reuses bounded immutable paths from the existing parent plan and retains no
metadata, content or validation result. The original leaf UID/mode predicates,
private-file UID/GID, link/size limits, no-follow open, before/after descriptor
metadata and named identity comparison remain required. Owned Root filesystem
tests include alias/ancestor changes, directory replacement, private hardlinks,
mutation during a read and twenty repeated observation sets. Component checks
do not establish the full archive's deadline or subsequent staged runtime.

## Bounded extraction and publication

Inspection requires the expected clean candidate, independent digest, safe closed
archive paths, matching native/web identities, ordered migrations, required entry
points and Linux x86-64 runtime. Staging additionally caps the archive at 1 GiB,
declared content at 4 GiB, entries at 30,000, paths at 1024 characters and individual
members at 128 MiB. A held-input preflight caps parser header reads at 8 KiB and
decompressed offsets at declared content plus bounded header overhead before the
shared inspector reads gzip/PAX metadata. Web links refuse; inspected internal
forge links may remain. The opened destination descriptor must match the policy,
including when its pathname changes between observation and opening.

Preflight only parses the held archive; it creates no staging output. Full live
custody checks bracket that read-only pass, and every member checks the original
opened and named archive fingerprint. This matches policy allocation's read-only
inspection window while avoiding a complete recursive observation for each
header. A lost controller, exclusion or history observed after parsing refuses
before inspection or extraction. Every subsequent guard around allocation,
archive copying, entry writes, metadata changes and publication remains intact.
All original member/parser bounds and response deadlines remain unchanged.

Before any large allocation, the system and output filesystems must each have
20 GiB free after the complete estimated archive copy, extraction, block/metadata
overhead and receipt allocations. The private archive copy is included.

An exclusive `.native-OPERATION.partial` remains private during extraction.
Files, directories, links and receipts are created relative to held original
work/code descriptors; traversed directories must match the created original
inode. Candidate code is never executed by staging. Regular files become 0444 or
0555, directories 0555, and the retained archive copy 0444, all under Root custody.
Content inventory and metadata capture are synced before descriptor-relative
`renameat2(RENAME_NOREPLACE)` publication as `native-OPERATION`. Existing targets
and partials refuse; no original or foreign entry is deleted or replaced.

Before metadata is frozen and synced, the owned archive copy, inventory, receipt
and regular code files receive explicit `0444` modes; executable code receives
`0555`. These final modes do not depend on the Root process's umask. The published
archive contains the same code-only payload already available through the sealed
input, so the ordinary controller can independently read its digest and complete
output while no ordinary account can write it. The operation partial remains
private until publication.

Published-output checks require exact directory entries and original file
metadata. Same-content replacement, permission restoration, changed files or
added entries cannot revive a poisoned original instance. Controller, policy,
stage, source or custody failure closes observation descriptors and retains every
input and incomplete/published effect. Explicit observed interruption
reconciliation remains required; retained output is not automatic retry authority.

## Verification boundaries

Local closed-format, reserve and descriptor-traversal tests use explicit account
and syscall stand-ins where the host lacks Linux facilities.
Read-only parsing tests use actual bounded archive reads with explicit authority
stand-ins. On Windows, pathname change-time metadata is also an explicit stand-in
for Linux semantics; held descriptors and byte reads remain actual. They check
loss before/after parsing and refuse a changed named archive before any write.
Root-only hosted
tests exercise actual descriptors, archive copy/extraction, read-only modes,
no-replace publication and original output metadata with explicit authority and
budget stand-ins. Concurrent destination creation preserves both the foreign
target and completed partial; an injected interruption preserves the original
input and incomplete copy while closing owned descriptors. These retention checks
do not establish reconciliation or safe retry. They do not prove Root allocation,
lifecycle dispatch or complete
stage authority. Actual installed inspection/staging effects, interrupted-effect
reconciliation and runtime use of the inspected output remain mandatory before
those components or full J14/J15 can be accepted.
