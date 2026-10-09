# Controlled native installation upgrades

Implementation work for J15. The existing populated migration experiment proves
specific data-preservation refusals; it does not activate an installed release.
This work keeps the single-runtime installation lease and independent recovery
custody as operating constraints. Managed Cloud execution remains a separate J14
integration dependency.

## Initial operating profile

Support the measured Ubuntu 24.04 x86-64 installation, PostgreSQL 18.4, one forge
runtime, its TanStack web server and an owned edge route. Use a maintenance window:
two forge versions cannot hold the same installation lease concurrently. Stage
immutable code separately from the mutable database, Git stores, assets, private
configuration and external recovery key. Never downgrade a schema automatically.

Production migration admission requires an existing runtime marker's complete
cgroup to be empty, as backup already requires. Linux replacement-runtime
admission refuses every process outside its own current startup lineage. The
wrapper requires an empty group before joining; after exec, the backend validates
the new BEAM and its descendants by kernel PID/parent/birth identity and UID,
including nested cgroups and a stable membership snapshot. It permits those
startup processes without admitting an unrelated survivor. A dead BEAM owner or released database
lease does not establish that its Git descendants stopped. First installation
migration still permits an absent runtime marker; a present unbound or nonempty
group refuses. The copied-production interruption experiment exercises refusal
with a real prepared Git transaction and retained schema/lock bytes, then migration
permission after the entire owned group stops. This admission safeguard does not
establish a complete installed upgrade or automatic schema compatibility.
Bootstrap also starts the native application, so Linux setup must run it within
the installation's dedicated runtime cgroup and stop that whole group before the
next bootstrap/runtime admission. The copied-production verifier follows this
boundary rather than writing a marker for its still-running parent harness.

The first component is implemented as
`python3 tools/deployment/inspect_native_artifact.py ARCHIVE SHA256 CANDIDATE`.
It opens the archive without following a file symlink on supported Linux, verifies
the independently supplied digest, checks bounded member metadata and matching
build identities, and reads the native ELF platform header. It extracts nothing
and executes nothing. The emitted `inspected` receipt is separate from readiness
or activation. Its structural tests use synthetic inert fixtures; the retained
9392a31 real artifact also passed inspection. No full J15 result follows from this.

The private Linux journal in `tools/deployment/upgrade_journal.py` persists the
fixed inspect/stage/maintenance/migrate/verify/activate/public-verify sequence
under a nonblocking OS lock. It binds one operation UUID and immutable installation,
artifact, candidate, resource-binding digest and rollback policy. Concurrent owners
refuse. Reclaiming an interrupted stage records uncertainty and requires explicit
reconciliation with an observation receipt before continuing. Recovery completion
requires receipts for the previous identity and public functional probe. These
receipts are obligations on the supervisor; the journal does not perform probes.

Journal files use private ownership, reject symlinks/hardlinks/shared permissions,
and persist by atomic replacement plus file/directory fsync. Loaded histories are
replayed against the fixed protocol before their reported state is trusted.
Read-only status polling does not claim the operation or append events. A lost
owner is exposed as uncertain even before reclaiming its journal; PID, birth tick,
boot identity and zombie state distinguish it from a current live owner. A lost
write acknowledgement disables that owner's in-memory continuation; a new owner
must inspect the durable state. Evidence fields admit bounded counts, booleans and
digests rather than payloads or environment. Linux tests include a genuinely
killed owner, process contention, altered history, lost acknowledgement and
interrupted recovery. Windows tests only establish early platform refusal; they
do not establish Windows upgrade support. Full installed activation, resource
inventory and supervised execution remain implementation work.

`UpgradeHistory` in `tools/deployment/upgrade_history.py` coordinates successive
operations in a dedicated private directory. Its installation lock spans the
whole claimed journal. A new operation requires the previous one to be complete
or recovered, keeps its exact terminal journal bytes and digest, and binds the
next previous artifact to the actually recorded outcome. Installation and resource
bindings cannot change between operations. Reusing an older operation UUID or
starting another operation while responsibility remains pending, failed or uncertain
refuses. This component records probe obligations; it does not perform activation
or establish that a declared recovery receipt reflects a healthy running release.

History reserves the immutable intent durably before creating or claiming its
operation journal. After a lost reservation acknowledgement, read-only inspection
shows `reserved`; only the same intent can continue. It does not infer an applied
stage. Interrupted journal stages still require explicit observation and reconciliation.
Read-only history preserves ownership and events. Sealed journal tampering,
symlinks, hardlinks, shared permissions and orphan operation directories refuse.
The bounded initial profile retains up to 128 operations; exceeding that bound
requires an explicit future retention design, rather than deleting evidence.

`stage_native_artifact.py ARCHIVE SHA256 CANDIDATE PRIVATE_DIRECTORY OPERATION_UUID`
implements private staging. It copies a bounded archive into a fresh request
directory, verifies the digest and unchanged source metadata, and runs the inspector
on that retained snapshot. It creates real directories/files before safe internal
symlinks, records each file's hash and executable mode, and fsyncs the inventory
and code tree before Linux atomic publication with no replacement. Existing targets
and interrupted partial directories refuse; failed partial custody is retained for
reconciliation. No installation stores or public route are changed. The real
retained 9392a31 package staged successfully: 8667 files and 14 links passed
independent inventory readback, with its original archive digest unchanged.
This is staging proof for that historical artifact, not an installed upgrade.

The supervisor receives only fixed lifecycle actions and exact owned resources.
A user-supplied descriptor cannot introduce arbitrary host commands. Runtime
processes are identified by PID and creation identity; the dedicated native cgroup
must include all descendants before maintenance. Preserve the previous artifact,
configuration and recovery bundle through activation and subsequent verification.

## Implementation sequence

1. Inspect an immutable native artifact against its independently supplied digest
   and candidate. Verify the forge/web build identities agree, required files and
   Linux x86-64 runtime exist, declared migrations and dependency/requirement
   identities are well formed, and archive paths cannot escape staging. Inspection
   executes no candidate code and changes no installation stores. Tampered,
   duplicate, truncated, foreign-platform and mismatched artifacts must refuse.
2. Introduce a private installation inventory and durable upgrade journal binding
   the installation UUID, old/new artifact identities, database, owned stores,
   supervisor/cgroups, routing and compatibility decision. Persist stages before
   consequential actions. Concurrent requests refuse; retry reconciles the same
   intent and never silently switches candidate or targets. Unknown state remains
   visible. No secrets or expanded environment enter ordinary receipts.
3. Stage and preflight the candidate before stopping the old runtime. Enter
   maintenance, stop its complete owned cgroup and obtain the existing offline
   migration lease. Record the actual schema before/after migration. Start the
   candidate under its own supervisor; require exact identity, all readiness checks
   and authenticated functional probes before changing the public route. Verify
   both the public web/API versions and native HTTPS/SSH operation after routing.
4. Exercise unhealthy artifacts, migration failure, killed stage owners and lost
   activation receipts against populated disposable installations. If schema
   compatibility and actual probes establish that previous code still works,
   restart that artifact with the retained stores; otherwise keep maintenance and
   expose the supported forward-repair or matching-artifact restore path. Retain
   failed candidates and their stage evidence. Do not report rollback from a
   successful process spawn or readiness endpoint alone.

## Evidence gate

J15-A requires an actual old-to-new installed release transition, controlled
migration, identity/readiness/function checks and route activation. J15-B requires
an unhealthy candidate that does not become the working public release, plus an
explicit schema/code compatibility result. J15-C requires failure-stage visibility,
supported retry or recovery, and fresh public/native probes of the final version.

Archive raw stage observations, exact artifact digests, process birth identities,
schema results and public probe receipts privately with digest readback. Record
the producer and evaluator honestly. Inspector tests, populated migration checks,
or the supporting same-host recovery profile alone cannot close J15 or establish
managed Cloud lifecycle or a product release.
