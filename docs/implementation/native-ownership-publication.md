# Native ownership publication

Implementation under [decision 0018](../decisions/0018-native-supervision-generations.md).
Complete native application startup, prior-owner reconciliation, lifecycle dispatch
and journey acceptance remain unfinished. The application profile still refuses
native startup before mutation.

## Marker custody

`NativeOwnershipMarkers` publishes a runtime or maintenance marker referencing an
already retained immutable ownership record. The marker binds protocol, kind,
installation, operation, exact mode and record digest. It grants no replacement,
writer, lifecycle or readiness authority.

An exclusive nonblocking lock on the original ownership-directory inode serializes
the two marker modes. Storage and record-directory descriptors retain their admitted
identities. Complete record names and all eight record-file metadata fields are
bracketed throughout publication. An identical completed retry preserves marker
bytes and inode. A different marker or the other mode refuses without repair.

Publication uses an exclusive private partial in the ownership directory, file and
directory synchronization, and atomic link publication without replacement into
storage. Synchronizing storage precedes removal of the partial. A failed link,
unlink or synchronization retains observable responsibility; partials and hard
links refuse later publication. Nothing removes an unknown marker or partial.

Fourteen ordinary Linux filesystem tests pass, including kernel lock contention,
mode competition, symlink/hard-link/permission refusal, storage replacement,
identical-byte record/marker inode replacement, and interrupted synchronization.
Their service and database values are synthetic; these tests establish custody.

## Original database session and owner connection

`observe_held_session` uses bounded read-only queries against an independently
admitted psql executable and private configuration. It compares the original
backend PID, microsecond birth, ordinary database identity and existing advisory
lease. It never acquires a lease or adopts a new backend holding the same key.
Credentials stay in the child environment; queries and refusals expose no password.

When an owner is supplied, its UID and process birth must match current kernel
observations. Its network namespace must match the observer. The PostgreSQL
client port must identify one established loopback TCP connection whose socket
inode is present in that exact owner's descriptor table. Repeated observations
bind its descriptor, inode, endpoints and namespace. This prevents a different
process from borrowing another owner's held backend as publication authority.

Ten actual PostgreSQL/kernel checks pass against private ordinary-role sessions:
original held identity, changed birth, absent PID, changed cluster, unchanged
original session after refusals, actual backend closure, a new holder refusing the
old snapshot, actual holder/socket linkage, another ordinary process's refusal,
and changed owner birth. Both holder processes exited normally. These checks use
psql owners, not a protected native BEAM or full application artifact.

## Fixed entry and admission

The installed entry is fixed at
`/opt/gitgood/native/v2/native_ownership_publication_entry.py`. Isolated Python
must load only its protected Root-controlled directory. The entry validates all
installed module custody before importing publication code. Its canonical,
bounded request has only protocol and the complete closed ownership record.
It accepts no executable, shell, environment, database URL, seal path or SQL.

A separate Root-controlled `ownership-admission-v2.json` must contain exactly
protocol, kind, installation, ownership operation, candidate and durable binding
digest. The kind is `native_application_ownership_seal`; the operation and candidate
must match the request. Creating this seal belongs to the forthcoming constrained
controller; a stored application record cannot create its own authority.

The writer independently captures current generation/service/owner admission and
matches the complete scope, owner, publication and guard digests. The fixed generation
seal supplies executable and database expectations. Independently admitted private
configuration supplies the connection URL. Original owner/socket/session observations,
generation checks and both Root seal identities bracket record retention and marker
publication. Refusal after an effect retains that effect and reports no completion.

Nine boundary/order tests pass with explicit service/database stand-ins. They verify
closed requests, candidate/operation mismatch, changed owner, prior responsibility,
borrowed backend refusal, and preserved effects after session loss. Actual protected
entry execution, Root controller seal creation and native BEAM linkage remain required.

`Gitgood.NativeOwnershipPublication` calls only the fixed protected entry through
isolated Python with bytecode writes disabled. It clears inherited environment
variables, bounds the request to 32 KiB, the response to 4 KiB and execution to
60 seconds, and rechecks protected executable/entry custody after completion.
It binds the request to the actual BEAM PID and accepts only a closed canonical
response with the same operation and SHA-256 of the canonical record. Six focused
Elixir tests cover Python-compatible sorted ASCII JSON (including surrogate pairs),
malformed or oversized requests, owner binding, changed response identities and
rejection of additional authority. These tests do not execute an installed entry.

The current fixed admission allows an initial ownership claim or its identical live
retry. Any other retained ownership record refuses. This is an incomplete integration
stage, not the final replacement policy. Controller reconciliation must independently
establish original-owner, backend and descendant absence before replacement; it must
preserve their records, uncertain effects and transition evidence. Marker monitoring,
whole-BEAM loss behavior, packaged functional access and lifecycle interruption proofs
remain required before native startup can be enabled.
