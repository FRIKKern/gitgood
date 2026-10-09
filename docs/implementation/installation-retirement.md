# Native installation retirement

J17 retirement builds on coordinated encrypted export and the exact native
resource inventory. A retained archive must identify the installation as well as
the application candidate: two installations can run the same build. The inspector
now reports the authenticated installation UUID and accepts an independent expected
UUID; a different installation refuses while preserving the archive and stores.
Copied-production verification binds the packaged inspector to its original UUID.
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

Removal remains implementation work. The executor must retain an independently
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
