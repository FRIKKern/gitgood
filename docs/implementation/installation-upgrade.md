# Controlled native installation upgrades

Implementation work for J15. The existing populated migration experiment proves
specific data-preservation refusals; it does not activate an installed release.
This work keeps the single-runtime installation lease and independent recovery
custody as operating constraints. Managed Cloud execution remains a separate J14
integration dependency.

The first executing library is `tools/deployment/native_upgrade.py`. It requires
an independently pinned private plan and resource inventory, a previously enrolled
artifact and current-release digest, and scoped probe credentials. Its fixed stage
sequence verifies the working public baseline, stages before maintenance, stops
whole owned groups, records actual schema before/after migration, verifies internal
function while public routes remain closed, activates routing, and records the
release pointer only after fresh public API/HTTPS/SSH probes. Plans contain fixed
identities and paths; they cannot supply commands. The frozen aa79679 coordinator
executed a populated installation transition from authentic clean 95f8dee to
1b0fe04 artifacts. The actual schema advanced from thirteen migrations to fifteen;
internal and public authenticated API/CA-verified HTTPS/pinned-key SSH probes
preserved the private branch and commit. The release pointer and terminal journal
identify the new artifact. Thirteen actual checks and a thirty-file private archive
passed digest readback. The original older archive omitted its web parent entry
and refused before enrollment; that artifact and failure remain retained. Current
structural checks passed 69 Linux and 27 Windows checks, with eight and fifty
foreign-profile skips respectively, plus 23 planning tests; thirteen proof files
passed digest readback. Failure and interruption paths still require current
experiments, so this positive transition does not establish complete J15 acceptance.

Explicit previous-code recovery reclaims the same failed or uncertain operation,
stops its complete owned groups before database-dependent observation, and requires
the actual schema to equal the previous artifact's migration list. Incompatible or
unavailable schema remains closed or in maintenance with a failed recovery stage;
no down migration occurs. Automatic continuation of partially applied forward
migrations and matching-artifact restoration remain unfinished in this library.

The frozen `fd9b909` installed supporting experiment exercised the fixed product
probe and current-release libraries on the historical `1b0fe04` artifact. Thirteen
actual checks passed, including schema identity, internal function behind
maintenance, public authenticated API/HTTPS/SSH reads, exact pointer readback and
repeat, immutable code, and empty owned groups after cleanup. Forty private files
passed digest readback. It recovered the same operation after two retained actual
failures: `e33a2c1` omitted read-only maintenance observation during candidate
verification; `34fdd46` exposed repeated edge launch paths within one recovery
stage. Distinct private attempts now preserve each edge launch. Separate current
structural checks passed 66 Linux checks and 26 Windows checks, with seven and
47 foreign-profile skips, plus 23 planning tests; eleven proof files passed digest
readback. This experiment used the same artifact and schema before and after;
it is not an old-to-new transition or a complete coordinator proof.

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
do not establish Windows upgrade support. Full installed version transitions and
the executing coordinator remain implementation work.

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

`native_probes.py` fixes the coordinator's probe contract to a private, independently
hash-bound actor manifest, pinned SSH client/key custody, installation identity and
one expected repository branch/commit. Reads do not follow HTTP redirects or inherit
proxy/environment credentials. Schema observation uses the bound PostgreSQL client
with the existing fixed read-only environment. Native/web readiness must identify
the intended clean candidate and checks; functional probes require authenticated
branch state, anonymous refusal and exact Git refs through actual HTTPS/SSH clients.
Git probe descendants enter the separately owned maintenance group and that whole
group stops after each client command. Distinct private command logs permit multiple
fixed probes in one durable stage without replacing prior diagnostics. Inspection
may stop only that client group, never the working native/web/edge groups. Ordinary
receipts contain candidate/ref/check observations and digests, not credentials.
Probe execution against installed artifacts and the complete coordinator remain
under verification.

`native_activation.py` supplies private current-release observation custody for
the forthcoming coordinator. The installation history lock and its current owned
public-verification/recovery journal govern the write. Candidate, archive digest,
staged code inventory/directory identity, exact expected schema and a public probe
receipt bind the record. Compare-and-swap against the independent previous record
digest refuses stale or foreign responsibility. An exact repeated write is
idempotent; file/directory fsync acknowledgement loss disables continuation from
that in-memory owner while preserving the landed observation for reconciliation.
Pointer files reject aliases, hardlinks and shared modes. The pointer does not
perform probes, switch routing or complete the journal; its producer must supply
actual observations. Structural custody checks use inert staged artifacts and
receipts and establish no installed upgrade or live activation.

`native_edge.py` adds a fixed guardian for the installation-owned edge group.
The initial TLS profile uses retained certificate/key custody and distinct public
HTTPS/SSH and loopback native/web/SSH ports. Maintenance returns HTTP 503 with a
retry hint and closes SSH without opening its upstream. Active routing uses the
existing private-header filter and fixed forge/web paths; only the actual current
journal owner may request it during activation or recovery. A closed environment,
exact configuration/binary/module identities and driver membership precede entry
into the empty owned edge group. No supplied command or arbitrary upstream exists.
SSH forwarding admits at most 32 connections, bounds buffers, connect time and
connection lifetime, and closes live sockets before waiting for server closure.
That ordering fixes an observed Python 3.12 shutdown deadlock. Guardian failure
stops its Caddy child too. Socket checks establish binary forwarding, maintenance
refusal and live-connection shutdown. The actual operator `b015370` experiment used
the copied historical `1b0fe04` native/web artifact in a fresh private installation.
Twelve checks passed: TLS maintenance and SSH closure held through internal
candidate function checks, then public readiness, authenticated branch reads,
anonymous refusal and real CA-verified HTTPS/strict-host-key SSH clients identified
the same retained commit. Immutable code stayed unchanged and logs excluded
edge/session/Git credentials. The disposable fixture was stopped while the
public-verification stage remained owned, then its completed history was sealed;
all five groups were empty after the driver exited. Fifteen private proof files
passed digest readback.

Retained attempts include a private-file creation refusal before edge startup and
a fixture SSH request with the wrong account name. The latter's lost owner remained
visible at public verification; explicit recovery using its exact previous artifact
and the returned owner-account URL passed eleven public function/history checks.
Twenty-five private files passed digest readback. A separate earlier `8c99172`
operator experiment held the SSH port with an owned fixture listener: guardian
refusal stopped Caddy, left its exact group empty, removed TLS and retained a failed
maintenance stage. Five checks and eleven private files passed readback. These
older proofs retain their actual operator identities. The current route experiment
uses the same artifact and existing schema before/after; version-changing pending
migrations, the product coordinator and durable current-release pointer remain
unfinished. No complete J15 acceptance follows from these supporting experiments.

`native_actions.py` supplies fixed migration and native/web launch actions for
the forthcoming executor. Actions require the current process to own a running
journal stage in the bound driver group. Launch re-observes installation bindings,
uses a closed configuration-key set and a fresh environment, and joins the exact
empty component cgroup before executing the release. No descriptor supplies a
shell command. Migration is the fixed `Gitgood.Release.migrate()` entry point.
The release's generated runtime configuration stays in a private mutable directory
outside staged code, with a private child-process umask; runtime secrets are not
added to immutable code inventories or their evidence.

Before execution, the action layer rechecks every staged file, link and executable
mode against the independently pinned retained archive. Updating a private
manifest cannot substitute changed code under the original artifact digest.
Missing web runtime dependencies refuse before launch. Whole-group stopping uses
the exact recorded kernel identity and remains available when the database is
unavailable; it never discovers or kills unrelated host processes. Structural and
artifact-refusal checks pass. The retained operator `9f51885` experiment staged a
clean historical `1b0fe04` native/web package and ran its fixed migration command,
native and production web processes under the owned journal. Both actual readiness
responses matched the artifact; whole-group stopping removed the live native
runtime and an independent owned descendant. All immutable code was rechecked
after execution, and generated runtime configuration remained outside it. Nine
process-action checks passed, all five groups were empty after the driver exited,
and thirteen private proof files passed digest readback. Fifty Linux operator
checks and seventeen Windows checks passed in separate platform profiles, with
four and thirty-seven foreign-profile skips respectively; planning checks passed.
The same native artifact and existing schema were used before and after. This
earlier journal remains pending activation. The subsequent route experiments are
separately identified above; a version-changing pending migration and the complete
executing coordinator remain unfinished. This earlier action experiment does not
establish an installed upgrade.

The read-only `native_inventory.py` component binds the initial local operator
profile to an owned private installation root, exact configuration and Ed25519
host-key digests, store directory device/inode identities, pinned runtime binary
identities, and dedicated `gitgood-installation-UUID` native/web/edge/maintenance
cgroups, with its supervisor in a separate driver group under the same delegated
parent. The parent process-control file must be delegated too, so lifecycle children
can move from the driver into their exact sibling group. Collection requires that
actual driver membership. It also observes the PostgreSQL 18.4 cluster system identifier, database
OID and database-owner role through one fixed read-only query. Re-observation
must match the independently retained bindings digest. A copied directory with
the same name or another database cannot silently replace the recorded target.

This initial enrollment requires the configured database role to own the database
and have permission to read `pg_control_system()`. PostgreSQL permits a specific
EXECUTE grant; broad administrative access is not inferred or granted by the
collector. See the official [control data functions](https://www.postgresql.org/docs/18/functions-info.html#FUNCTIONS-PG-CONTROL-DATA).
The collector never logs connection credentials or expands the environment into
receipts. It performs no migration, shutdown, routing or deletion. Observed
resource identity is distinct from readiness, an active public release and
replacement-host enrollment. The retained operator `2eb9d15` experiment used a
fresh dedicated database and the copied `1b0fe04` native release: migration,
bootstrap and native readiness passed before eight inventory/refusal checks.
Changing the configured store refused; replacing the stopped storage directory
changed its inode and refused the retained digest. The original directory and
bindings were restored exactly. All five owned groups were empty after the
driver exited, and fourteen private proof files passed digest readback. Earlier
controller/delegation/address-format failures remain retained. This does not
establish an active web/edge route or a full installed upgrade.

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
