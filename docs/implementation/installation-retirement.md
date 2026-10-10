# Native installation retirement

J17 retirement builds on coordinated encrypted export and the exact native
resource inventory. A retained archive must identify the installation as well as
the application candidate: two installations can run the same build. The inspector
now reports the authenticated installation UUID and accepts an independent expected
UUID; a different installation refuses while preserving the archive and stores.
Copied-production verification binds the packaged inspector to its original UUID.
Retirement can now reserve the separately sealed [initial baseline](native-initial-lifecycle.md)
before any real upgrade. It requires that baseline's exact candidate, artifact,
bindings and current-pointer digest; an unfinished or changed initial chain
refuses. This admission has component checks. Actual direct retirement from the
new initial lifecycle remains separate installed evidence. Recovery configuration
accepts a retained `GITGOOD_INSTALLATION_ID` only when it equals the authenticated
installation UUID. Materialization changes both identities to the independent
target UUID; ordinary restoration preserves the original identity. A real export
from the initial CLI exposed the previous validator refusal before any retirement
intent or removal, and that stopped fixture remains retained.
Authenticated inspection also reports normalized Git, SSH and configuration file
inventory hashes. The read-only `snapshotInstallationRoots()` observer uses the
same archive inventory format. A live Git-store change after export changes its
hash while unrelated SSH/configuration hashes remain stable. These hashes cover
file bytes, paths, kinds and normalized private archive modes; installation runtime
markers and the generated recovery descriptor are excluded by the existing format.
Inspection also returns a canonical hash of the authenticated database descriptor
(schema, ordered table data hashes, sequences and locale profile). Comparing it with
the actual live `fingerprintDatabase()` result detects a database-only change after
export while the file hashes remain unchanged. These observations require complete
writer exclusion for a consistent comparison. Descriptor inspection does not
establish that the dump restores to those values or that Gitgood works after restore.

The packaged `Gitgood.Release.retirement_checkpoint()` command acquires the
existing offline backup lease and checks complete runtime/database writer
exclusion before and after comparing the authenticated export with live file and
database inventories. Independent expected installation and ciphertext digests
are required. Archive/key paths must be outside the three live store roots.
Wrong bindings and a database-only change refuse. The lease ends when this command
returns; its receipt cannot authorize later removal without continuous custody
and fresh revalidation. PR48 copied-production verification passed on executed
candidate `da3a1f1b2a25c9e119249aaa1f6d46d1cec36f51`, whose tracked tree equals
the proposed `fe4d835df35b10b63ad16eb4171c911c1cdc1ca3` tree. The merged
`db639601fba10ce9219f84ca5e2caf432219fa7b` pipeline also passed fourteen offline
recovery checks. Both private artifact sets retain matching checkpoint/export
installation, ciphertext, file and database hashes. This proves the checkpoint
scope on those candidates; it does not prove later removal or a product release.

The native lifecycle CLI remains implementation work. The fixed controllers retain an independently
identified archive and external key outside the live resources, establish an
actual usable restoration and the current recovery point, exclude every owned
writer, and journal exact resource identities before consequential actions.
An inspected archive alone does not authorize or establish safe removal.

`tools/deployment/retirement_journal.py` adds durable responsibility for a fixed
retirement sequence: quiesce, archive/restore verification, database removal,
store removal, and retained-resource verification. It records receipts, counts
and booleans, never credentials or commands. The independently hashed plan binds
the installation, current candidate/artifact/pointer, resource plan, archive,
checkpoint, restoration and retention observations. These hashes identify the
operator's retained inputs; journal admission does not execute or validate the
referenced restoration by itself.

The journal acquires the same OS lock as `UpgradeHistory`, requires the previous
upgrade to be complete/recovered, and rejects a different installed release or
current pointer. Its retained marker also prevents a later upgrade from bypassing
an interrupted retirement. A killed owner leaves uncertainty; explicit observed
applied/unapplied reconciliation precedes continuation. Fixed event replay rejects
invented completion, changed intent and missing destructive-action observations.
File/directory sync errors invalidate the current owner until reopening. Read-only
status never acknowledges an action. There is no cancellation or complete retirement
coordinator yet; creating retirement intent is reserved for that future owned executor.

The Linux journal checks use inert receipt fixtures and real competing processes,
SIGKILL, private-file aliases and sync faults. They exercise custody without deleting
resources or proving actual archive/restore functionality. The full Linux operator
suite currently passes 84 checks with eight foreign-platform skips; current
packaged production checks for PR49 passed on executed
`ef6bbe4416d8e5ee8f4a887376cdccdffb73f4bb`, whose entire tracked tree equals
the proposed `cfb07b3cb24beb743a8ae508ff3e146d1f3a7d4d` tree. Integration into
main `23fd7612405f924e2658eefafcb359e9c069d636` is recorded separately.

`retirement_database.py` and `retirement_stores.py` provide the two scoped removal
actions for the future coordinator. Each requires the held journal lock, the exact
independently hashed resource plan, the corresponding running action stage, the
original owned kernel groups and driver membership, and empty runtime groups.
Observation also works during retained-resource verification; it does not authorize
another deletion. The database action checks the original cluster, role, database
OID, owner, encoding and endpoint through the administrative database before an
ordinary `DROP DATABASE`. Existing clients refuse; the action never uses FORCE,
disconnects clients, drops shared roles, or removes the cluster. Configuration
bytes must match the original installation hash, including when recovered from
retained private material after store removal.

The store action removes only the sealed configuration, SSH-host and Git-storage
entries. It pins directory descriptors, checks inode/owner/mode and file hashes,
refuses unexpected entries and aliases before deletion, and syncs each changed
parent. Replacement resources refuse. A partial interrupted removal can resume
only after actual remaining entries match the original plan. Its explicit unapplied
stage reconciliation means the stage remains incomplete; it does not assert that
no individual file was deleted. Lost acknowledgement after complete deletion can
be reconciled from observed absence without repeating the destructive action.

Eight filesystem and five actual PostgreSQL checks cover scoped deletion,
preserved unrelated data/shared roles, changed resources, connected clients,
partial failure and real SIGKILL after deletion before journal acknowledgement.
Their kernel observation boundary is controlled and preceding restore receipts
are inert fixtures. They do not prove real kernel exclusion, usable restoration,
continuous custody across the full retirement, or provider deallocation. All
destructive checks allocate new disposable resources. Managed lifecycle actors
must obey the installation lock and kernel custody; privileged external host or
database administrators remain outside that boundary. No filesystem power-loss
guarantee is established.

`retirement_fence.py` publishes a private, durable same-intent admission fence in
the installation root, outside the three removable stores. New runtime, backup,
migration and restore lease acquisition refuses whenever that fence exists; owner
death, malformed bytes and dangling aliases do not make admission available.
Publication requires the retirement journal's running quiesce stage, exact root
identity, enrolled kernel groups and driver membership. A same-intent retry syncs
the existing fence again; another intent or an alias refuses without replacement.
No automatic fence cancellation is provided. These admission checks apply to
artifacts containing the new guard; a future coordinator must require and verify
that capability before publishing intent against an installed release.

`retirement_quiescence.py` then stops only the four enrolled edge/native/web/
maintenance kernel groups and their descendants. Each stop revalidates the held
journal and fence. Observation requires every original group empty; repeated
same-stage shutdown is harmless and another stage refuses shutdown. Exact child
birth observations limit zombie reaping to the caller's children. Database writers
are a separate observation; empty runtime groups alone do not establish their
absence. The durable admission fence remains after the journal owner dies.

Four fence filesystem cases include lost sync replies, different intent, aliases,
wrong stage and a real killed owner. Two additional backend cases use the actual
PostgreSQL-backed installation lease to refuse runtime and every offline mode.
A separate six-check kernel experiment allocated fresh delegated groups, enrolled
real sleepers including a native descendant, stopped only the four bound groups,
and kept an unplanned owned canary alive. All fixture stores and the fence were
retained. Only the freshly allocated groups were removed after observed emptiness.
Its preceding upgrade and artifact identities are inert fixtures; this experiment
does not establish application restoration or full installed retirement.

Because the fence also refuses ordinary backup admission, the existing packaged
checkpoint cannot simply be called after fencing. The future fixed coordinator
needs a snapshot observer under its continuously held driver/journal/kernel custody,
plus an actual independently bound usable restoration, before admitting either
removal action. Final retained-archive usability remains open.

`retirement_snapshot.py` provides that read-only snapshot step without opening a
new ordinary backup lease. It requires the running archive-verification stage,
retained fence and empty original runtime groups, original database identity and
no connected clients, unchanged current pointer, and the independently pinned
checkpoint and retention inputs. The retention inputs bind the external archive,
32-byte key, private scratch directory and exact PostgreSQL dump/restore tools.
They stay outside the removable roots. The observer comes from the immutable
current artifact; its node/Git executables and the complete staged code are checked.
The controller retains the journal lock and rechecks kernel/fence custody while
its own child runs, then rechecks retained materials, code and database identity.
Private request, result and diagnostic records remain in retained history.

The packaged `retirement-snapshot.mjs` authenticates the independently named
installation/candidate/ciphertext and compares live file and database fingerprints
with that archive. It refuses other database clients at both boundary observations.
Its metadata cannot establish kernel exclusion by itself; the controller supplies
that managed-lifecycle boundary. Privileged unmanaged host/database actors remain
outside the supported boundary. Interrupted read-only children may leave private
scratch material; retention must account for it rather than erase uncertain work.

The controller receipt deliberately has no `restore_function_verified` flag, so
it cannot acknowledge the archive stage or authorize removal without a separate
actual usable-restoration observation. Four controller tests use controlled kernel
and artifact/result boundaries with real filesystem ownership, journal locks,
PostgreSQL identities and node children. Wrong stage, changed key/result, and a
writer appearing during the child read refuse without advancement.

A separate nine-check experiment uses a real bare Git repository, SSH host key,
PostgreSQL18.4 data/dump and authenticated encrypted export. It verifies matching
live fingerprints, independent UUID/ciphertext/request bindings, database-only and
file-only changes, a connected client left alive, a wrong key, and unchanged
original observation on repeat. Its candidate and TLS fields are inert fixtures;
it establishes neither application readiness nor a full installed retirement.
Copied-production acceptance now exercises the shipped observer and its refusals;
the proposed revision still needs its own full required CI and installed acceptance.

The initial local profile must distinguish installation-owned resources from
shared database roles, clusters, service identities and upstream user credentials.
Shared credentials cannot be revoked as installation cleanup. Retention must name
every remaining archive, key, artifact, record and provider resource; an unresolved
provider action stays visible instead of silently becoming completed cleanup.
Retries must reobserve identities, preserve ambiguous results and refuse replacement
resources. Destructive acceptance uses newly allocated disposable fixtures only.

Managed Cloud deallocation requires its own verified provider inventory and action
contract. No live installation, database, key or provider resource has been removed
by the inspector change.

`retirement-restore-data.mjs` verifies recovered contents in a separately allocated
database whose name derives from the independently bound operation UUID. The owner
allocates that target; the helper neither creates nor drops any database. Exact
cluster, original target OID, role/owner, encoding, version and endpoint are required,
and the archived original database name must differ. The original credentials bind
the same local endpoint without appearing in its request or result.

Restore mode requires an empty public schema, no other application schemas or
clients, authenticated archive inspection and the original locale profile before
single-transaction dump import. It then compares the actual schema, ordered row
hashes, sequences and locale with the authenticated descriptor. Observe mode repeats
these reads without import; restore mode refuses a populated target. Replacement
identities and connected clients refuse, and failed or interrupted targets remain
for explicit reconciliation. Only freshly allocated unpack directories are cleaned
after the call. Interrupted child scratch requires retained inventory.

Twelve real PostgreSQL18.4/export checks passed on fresh disposable resources: wrong
installation/ciphertext/request/target identity, actual import and observation,
populated-target refusal, changed data, a connected client left alive and an unchanged
repeat, an actual same-name replacement with a different OID, and preserved
populated replacement data. The first producer run used an incorrect fixture table name after import;
its partial results remain preserved. A corrected producer allocated a new target
and passed all ten initial checks. A third fresh producer added the actual
replacement cases and passed all twelve. These archive candidate/TLS fields are inert. This proves
recovered contents, not installed application startup, authenticated functional
probes, kernel/journal custody or the full retirement flow. No restoration-success
flag for journal acknowledgement is emitted. Copied-production verification adds
the shipped helper and actual dump/target checks; required CI remains pending.

`retirement_restore_data.py` binds that packaged helper to a closed, independently
hashed restoration target plan. The operation-derived target name, original OID,
cluster, role/owner, endpoint and source separation are sealed before admission;
the controller never allocates or deletes a database. The plan occupies the
journal's restoration-input digest and declares its data-verification purpose.
It cannot substitute for a future complete application-restoration plan.

Snapshot and restored-data verification share a fixed packaged-child runner. It
holds the journal lock, rechecks fence/kernel custody during execution, and checks
the retained archive/key/tools, original database identity and entire staged code
before and after. The child's request/result and diagnostics stay private in
retained history. Restore mode imports only into the sealed separate target;
observe mode reads that same target without repeating import. Failure preserves
the target and original stores for explicit reconciliation. Termination stops only
the controller's child; interrupted helper descendants or scratch must remain
visible to reconciliation and cannot be treated as successful restoration.

Five new controller checks and four inherited snapshot checks passed with actual
filesystem/journal locks, PostgreSQL identities and node children with controlled
kernel/artifact/result boundaries. The complete operator suite passed 110 Linux
checks with eight foreign-platform skips. These tests do not prove
an authenticated export import or functional application startup; the separate
twelve-check helper experiment establishes recovered-data behavior. Neither scope
establishes complete installed retirement. The controller emits a recovered-data
receipt without `restore_function_verified`, so archive-stage acknowledgement and
removal still require actual application restoration under continuous custody.

The combined data/custody/operator-status integration passed all 115 Linux
operator checks, with eight foreign-platform skips. The separate component
archives remain scoped: twelve real authenticated-export/database checks, nine
custody/snapshot checks with controlled boundaries, and five read-only status
cases plus historical record observation. Combining these results does not
establish functional restoration or complete installed retirement. PR54 passed
required CI on its exact tree before merging: 176 backend checks, nine database
recovery, 115 Linux operators/eight foreign skips, nine web, 24 operations,
eleven browser with no skips/flaky results, 22 copied-production, sixteen offline
recovery and 33 planning. The copied-production restored-data receipt matches
all six authenticated checkpoint/export fields. This remains component evidence;
full installed retirement and current release acceptance remain open.

The separate verification-runtime mode closes a prerequisite for actually
starting a restored copy: automatic reconciliation is disabled and Barkpark I/O
is refused, while explicit operation-derived local database/origin constraints
and health identity distinguish it from active service. Ordinary activation
probes refuse that mode. [Decision 0011](../decisions/0011-isolated-retirement-verification.md)
defines the remaining fixed controller and independently retained targets;
enabling the mode alone cannot authorize removal.

`retirement-restore-materialize.mjs` materializes the authenticated Git, SSH and
configuration stores into a separately allocated, initially empty private root.
Its name derives from the operation UUID; its original device/inode/owner are
independently bound. The database must already match the authenticated export,
with its exact target identity and no other connected clients. The helper
reobserves those data before and after copying and never imports or deletes a
database.

The retained certificate must currently validate the loopback IP and match its
private key. Five distinct ports must differ from the original profile. Fixed
adaptations preserve session, proxy, connection and SSH secrets while rebinding
the target installation UUID, local origin, database, storage paths, ports and
shipped Git hooks. The external Barkpark origin is omitted from the temporary
configuration; verification-mode flags remain a separate trusted launch input.

Descriptor-anchored publication stays inside the original target directory and
does not overwrite existing files. Every copied path, mode and byte is compared
with the authenticated/adapted stage, synchronized, and checked through actual
Git fsck/refs and final fingerprints. Occupied or replaced targets refuse.
Failures preserve partial targets; only fresh unpack scratch from a normally
completed invocation is cleaned. A killed process leaves its decrypted scratch
private and retained for explicit reconciliation.

Twelve checks passed with actual encrypted archives, PostgreSQL18.4 data, Git
objects and valid TLS keys, including wrong root/database identity, port
collision/original-port refusal, wrong certificate host, request-digest refusal,
occupied/repeated target preservation, actual materialization, same-name root
replacement, changed data and a connected client left alive. A separate four-check
SIGKILL exercise after a nonempty Git-file copy retained the partial target and
scratch, refused retry without changing those bytes, and preserved archive/key
and database contents. An earlier directory-only interruption result is retained;
a subsequent producer watched the wrong `HEAD` path and its failed result remains
separate from the corrected fresh-target run.

These archive candidates are inert fixtures. No application was launched, and
neither experiment establishes continuous retirement journal/kernel custody,
functional access/transport or complete retirement. The helper emits no
`restore_function_verified` flag. Copied-production verification now invokes the
shipped helper and checks original checkpoint bindings, retained secrets and
occupied-target refusal. PR56 required CI passed180 backend,116 Linux operators
with eight foreign skips,10 web,11 browser without skips/flaky results,22 copied
production,17 offline and33 planning checks against the entire head46c0612 tree;
the component is merged in main9689d11. Complete retirement remains unverified.

### Full-restoration input and helper custody boundary

The draft protocol2 `retirement_functional_restore_plan` independently binds the
existing data plan, fixed materialization request, target UUID/root/database,
four operation-specific kernel groups and private actor probe inputs. Parsing
never grants functional success. The existing protocol1 data-only plan retains
its original scope. Fixed archive/data/materialization helpers can execute in
the exact empty target maintenance group while the original driver retains its
journal lock, fence and quiescence observations. Surviving descendants refuse a
new helper launch; private request/result/error files remain in retained history.

The verification groups live beneath the original delegated installation parent
at `retirement-<operation>/<target>/<role>`. A real cross-delegation probe refused;
a fresh nested-layout experiment passed six kernel/process checks including
SIGKILL descendant retention and scoped shutdown with a surviving outside canary.
The original kernel/artifact/archive/result boundaries in that experiment were
controlled. These are helper custody checks, not complete functional retirement.
See [decision0011](../decisions/0011-isolated-retirement-verification.md).

The grouped-helper boundary cannot acknowledge `archive_verify` or authorize
source removal by itself. The fixed controller below adds installed pre-removal
application verification. Interrupted controller recovery, final post-removal
usability, cancellation and native Cloud lifecycle remain unfinished.

### Existing materialized target observation

The fixed materializer accepts a separate closed protocol2 request with
`phase: observe`. It authenticates the original archive and independently bound
restored database again, derives the same adapted private configuration/hooks in
fresh scratch, and compares every existing target name, mode and byte. It copies
or rewrites no target content. Protocol1 still requires an empty target and
refuses repeat publication. Partial roots, unexpected files/runtime markers,
changed configuration, wrong root/database identities and unsupported phases
refuse without repairing or replacing their witnesses.

Twelve actual archive/Git/PostgreSQL/TLS checks passed. An unchanged helper
completed materialization through a controlled caller that held its result before
acknowledgement; SIGKILL of that exact caller lost the acknowledgement. Repeated
existing-target observation then passed with unchanged bytes, device/inode,
owner, modes, links, sizes, mtime and ctime. Wrong identities, digest/phase,
unexpected marker, altered configuration, missing file, same-name replacement
and database change refused while preserving target state. The archive candidate
remains an inert fixture; no application or original kernel/journal custody was
verified in this experiment.

Copied-production recovery now checks the shipped existing-target observer and
its actual receipt, complete target preservation, unexpected-file preservation
and phase refusal. This observer passed required CI on its entire proposed tree
and is merged. The controller below adds post-runtime marker observation and
pre-removal function; final post-removal usability and complete retirement remain
unfinished.

### Fixed application verification controller

`RetirementRestoration` composes original custody with fixed temporary forge, web
and loopback TLS/SSH launches. Full-plan protocol3 adds separately bound outsider
actor inputs and an independent private Git witness. Verification requires exact
recovery-mode readiness/schema, valid independent sessions, recovered private
branches, anonymous/cross-team API refusal and actual permitted/denied HTTPS and
SSH refs. Target processes stop as complete identity-bound groups before
post-runtime materialization/database and original snapshot observations.

A separately observed live runtime marker is retained and validated after stop
through actual owner birth and empty native-group observations. Closed
materializer protocol3 makes that one bound marker explicit; unexpected markers
remain refused. An uncertain archive stage can stop only its sealed target
groups, reobserve the original snapshot through the fixed read-only helper, and
retry existing restored contents. No arbitrary callback or caller-supplied
functional result is accepted by this controller.

Installed pre-removal execution passed against clean artifact
`ea3a2adbc2377138a66ea97fb90247509003fc9e`, SHA256
`ebc5986d76a77a1b273ee3b6deea5a9a66483fc8b3b40651ce746f077db705a0`.
A fresh UUID-owned installation used actual fixed migration, two account
bootstraps, private repository creation/push/key registration, public probes and
durable activation. Its actual encrypted export and checkpoint then fed the
independently sealed target database/root/groups. Ten functional restoration
checks passed through the unchanged packaged helper and controller: actual
recovery-mode readiness/schema, independent valid actors, private branch reads,
anonymous/cross-team API refusal, permitted/denied HTTPS and SSH Git, whole-group
stop, birth-bound stopped-marker observation, unchanged target fingerprints and
unchanged original snapshot. Only then did the owned journal acknowledge
`archive_verify`. At that boundary its original database and stores remained retained.

Twelve additional packaged protocol3 checks passed: repeated complete target
preservation, wrong marker inode/hash/path, wrong native group identity/path,
wrong database, digest/phase, unexpected file and an actual live outside marker
owner all refused without helper repair. All nine original/target groups were
observed empty. The141-file installed evidence archive passed checksum readback
and excludes actual keys, actor credentials, decrypted stores/configuration,
database dumps and environment. Failed cgroup traversal and outside-delegation
fixture attempts are explicitly retained, separately from passing cases.

The current125 Linux operator checks, six grouped-helper kernel checks and
twelve legacy existing-target checks have their own104-file component archive.
Those component cases remain distinct from installed function. Current controller
required CI passed against the complete tracked tree of
`085778c0dde07103342444caad4fc5ac88e55788`:180 backend,9 database recovery,
125 Linux operators/ten foreign skips,10 web,24 operations,11 browser without
skips/flaky results,22 copied production,18 offline and33 planning. The five
run/log records and61 uploaded files passed digest readback. PR59 merged into
`06c0877bd1a796ebd7cd5687e776399c69c7555c`; its own main pipeline passed the
same matrix, with five run/log records and61 uploaded files checked. A second independently installed fixture passed actual
SIGKILL of the ready controller, preserving live target services and an
unacknowledged archive stage. Product status reported dead-owner uncertainty;
the new fixed owner stopped only sealed target groups, reobserved the original
snapshot, reconciled the interrupted history and repeated actual existing-target
function. Ten recovery checks passed, with exactly one database import and all
nine groups empty afterward. Fixed resume took404166ms; this measures resume only,
not complete retirement RTO acceptance. Its101-file archive passed checksum and
credential-exclusion checks. The post-removal continuation below establishes the
fixed five-stage installed disposable case. Cancellation, lifecycle CLI, managed
Cloud and release acceptance remain unfinished. Initial installation uses fixed product libraries
through a private fixture driver; product enrollment CLI is separate work.

### Final retained usability

`retirement_retention.py` introduces a separate fixed final profile, admitted only
after the four prior journal stages are acknowledged. It requires actual original
database and store absence throughout target observations and application probes.
It cannot reimport target data, publish an empty target or run the original live
snapshot helper. The independently hashed original configuration is retained in
private history before database removal so exact absence can be observed after
the configuration store is gone. It is excluded from ordinary evidence.

The existing target's stopped marker/data/materialization and actual independent
actor/API/HTTPS/SSH function must repeat before whole-group stop, unchanged target
fingerprints and unchanged original absence can produce final authority. A failed
or uncertain final stage observes absence and retained identities before retry.
The actual same installed fixture continued from acknowledged pre-removal function:
ordinary exact-OID database removal with zero clients, sealed three-store removal,
and durable private configuration retention. The final profile observed source
absence and authenticated the existing recovered target, then started the actual
loopback verification application. An exact-birth SIGKILL at final readiness left
live target services and an unacknowledged final stage. New-owner status reported
uncertainty; only the sealed target groups stopped before further observation.

Seven adversarial checks passed. Changed archive/key/private configuration, an
actual different-OID replacement source database, a replacement source store and
an unexpected target file refused and were preserved by the product. Fixture
cleanup removed only its own separately observed witnesses. The unexpected target
case produced failed final responsibility; the same fixed retry then reconciled
and repeated actual independent actor/private API/HTTPS/SSH function after source
deletion. Target data/materialization and original absence remained unchanged;
exactly one database import occurred across the complete lifecycle. Only the
combined final receipt acknowledged all five stages as complete.

Eleven installed lifecycle checks and seven refusal checks passed. The final
resume, including adversarial checks, took380209ms; this is not complete
provisioning/retirement RTO acceptance. Two actual operator CLI status observations
reported complete responsibility without changing any of115 private history files.
All nine original/target groups were observed empty. The145-file evidence archive
passed checksum readback and excludes actual keys, actor credentials, private
configuration, stores, database dumps and environment. The initial resume fixture
used inherited read-only PostgreSQL options for witness creation and refused;
its failed driver/log remain retained, separately from corrected v2.

The clean installed application remains `ea3a2adbc2377138a66ea97fb90247509003fc9e`,
artifact SHA256 `ebc5986d76a77a1b273ee3b6deea5a9a66483fc8b3b40651ce746f077db705a0`.
Every executed draft operator file has independent bytes/SHA256 observation and
matches the proposed operator source. All24 executed files match committed Git
blobs in `db3aefed4f37734a79c7441af2c691c68f778da9`. Its required CI passed180
backend,9 database recovery,129 Linux operators/ten foreign skips,10 web,24
operations,11 browser without skips/flaky results,22 copied production,18 offline
and33 planning checks against the entire tracked head tree. Five run/log records
and61 uploaded files passed checksum readback. PR60 merged in
`9b6bf05a2ea40976e40713d3f3918f5b02fe85dd`; that main commit's own full pipeline
passed the same matrix and five-plus61 file archive checks. Same
physical host/kernel and fixture-driven initial enrollment remain explicit limits.
Retained archive/key/probe credentials/private configuration/history/code/target
database and stores/kernel groups/shared roles/provider resources are preserved;
no cancellation, provider deallocation, managed Cloud or complete release follows.
See
[decision0012](../decisions/0012-post-removal-retained-usability.md).

### Fixed native executor under verification

`native_retirement.py` sequences the same fixed controllers and is exposed by
`native_operator.py retire`. It reads five fixed private input files and an
independent canonical plan SHA256. Their full bytes, ownership, single-link
private modes, device/inode/digests and parent identity are observed around each
stage. A changed, aliased or same-byte replacement input refuses. Plan/history
files stay outside the original stores and recovery target. Command and callback
fields are unsupported. The owner must already be in its exact enrolled driver
group through the OS delegation boundary; this command cannot allocate/adopt a
target database, kernel group, original installation or provider resource.

The executor retains the installation lifecycle lock across the whole sequence.
Archive/key/tool/code identities, current pointer and writer exclusion are
reobserved before exact removal. Failed/uncertain database and store stages
observe exact absence or matching remaining resources before fixed applied or
unapplied reconciliation. Quiescence may repeat same-resource stops without
claiming no partial stop occurred. Archive retry proves original snapshot
preservation and uses only the existing target. When that target root is empty,
a fixed data observation precedes any initial import retry; the actual packaged
import helper independently refuses a populated, partial or replaced database.
It never clears a target to make retry possible. Final retry uses the proved
retained-usability controller. Failures retain the corresponding fixed stage code.

A completed same-intent call returns previously recorded responsibility without
opening the journal, mutating retained files or asserting fresh archive usability.
The status command remains a separate read-only observation. Current component
regressions pass135 Linux checks with eleven foreign skips, including real private
inputs/PG identities/OS competing lock/CLI refusals. Their kernel, immutable code,
archive and terminal success boundaries are controlled, so they do not establish
full installed function. Actual CLI continuation passed five checks after prior
fixture-driven archive acknowledgement: exact database/store removal, final
independent actor/API/HTTPS/SSH function, target preservation and whole-group
shutdown. Two same-intent terminal calls left all109 retained history files
unchanged. Its126-file archive passed checksum and credential-exclusion readback.

A third independently enrolled clean installation lost its exact-birth archive
owner before the first import, with an empty target database/root and all four
target groups empty. The actual CLI reclaimed uncertain responsibility, proved
the unchanged original snapshot, refused data observation on the empty target,
and invoked the fixed initial import exactly once. It then verified pre-removal
function, removed the original database/stores and completed final retained
function. Five installed CLI checks and two terminal calls passed; all100
history files were unchanged by the terminal calls and all nine groups were
empty. The122-file archive passed checksum and credential-exclusion checks.
These cases retain their distinct scope: initial enrollment/export/checkpoint,
allocation and the third installation's quiescence used fixed fixture libraries.
A fourth fresh installation passed all five stages through the actual CLI from
absent retirement journal/fence. No fixture driver called retirement stage
controllers. The command published initial responsibility and fence, stopped
original writers, proved actual pre-removal function, removed only the original
database and sealed stores, and repeated final retained actor/API/HTTPS/SSH
function. Exactly one import occurred; all nine original/target groups were empty
and complete responsibility was published. Five CLI checks and two terminal
calls passed. All94 history files stayed unchanged by those repeated calls.
Its117-file archive passed checksum and credential-exclusion readback.
Initial enrollment/export/checkpoint and target/plan allocation remain fixture
driven; those commands, cancellation, managed Cloud and release acceptance remain
unfinished. All three actual CLI cases executed the same25 independently hashed
operator files with the clean application/artifact identified above. Required
CI for the executor remains a separate current-tree integration gate. See
[decision0013](../decisions/0013-fixed-native-retirement-executor.md).

Interruption at an unacknowledged archive stage can require another same-intent
invocation. In particular, loss after unapplied reconciliation but before stage
begin can leave a pending stage with an already restored target. The fixed
initial import refuses that populated target and retains failure; subsequent
failed-stage retry observes the existing target rather than reimporting it.
No single-invocation recovery at every instruction boundary is claimed.
