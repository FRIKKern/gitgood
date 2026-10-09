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
and fresh revalidation. Copied-production acceptance for this new command is
pending on the proposed revision.

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
status never acknowledges an action. There is no cancellation or removal executor
yet; creating retirement intent is reserved for that future owned executor.

The Linux journal checks use inert receipt fixtures and real competing processes,
SIGKILL, private-file aliases and sync faults. They exercise custody without deleting
resources or proving actual archive/restore functionality. The full Linux operator
suite currently passes 83 checks with eight foreign-platform skips; current
packaged production checks for this separate journal integration remain pending.

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
