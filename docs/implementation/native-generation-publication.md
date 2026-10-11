# Native stopped generation publication

`tools/deployment/generation_publication.py` combines persistent installation
observation, the existing independently bound lifecycle lock, an actual ordinary
PostgreSQL writer lease, immutable generation/transition records and an atomic
current pointer. Publication establishes resource continuity while native, web,
edge and maintenance groups are empty. It does not establish application readiness.

The host allocator must independently seal the expected durable binding digest,
existing history and lock identities, unit digest, executable paths and limits.
The publisher cannot allocate or replace those authorities. Its actual caller
must be the admitted systemd MainPID in the driver leaf, with the ordinary account,
empty capability sets and NoNewPrivileges required by service admission.

## Retained state and recovery

The history contains the original lifecycle lock, content-addressed generation
records, an immutable durable binding, immutable operation-specific transitions
and completion receipts, and `current-generation-v2.json`. Writes synchronize
the file and directory and read back canonical private bytes. Interrupted partial
files remain retained. Transition and receipt directory identities remain bound
while the lock is held. Unknown or legacy lifecycle history refuses publication;
there is no implicit conversion or inference that unfinished responsibility ended.

Each transition retains the full previous pointer, its digest, the exact generation
predecessor and whether the previous publication had a completion receipt. A pointer
without its separately retained receipt remains uncertain. Exact retry reobserves
persistent facts, stopped groups and the held database lease before completing it.
It preserves original generation, transition and receipt bytes and identities.

A new kernel boot cannot contain an old process and authorizes no signal. A same-boot
restart additionally requires a replaced root-controlled service parent and the
actual absence of the original manager birth. This publisher sends no signals.
Stopped publication can retain a successor before replacing the pointer. Recovery
follows the unique retained generation tip and separately references the old
published pointer; it cannot create another branch around that retained successor.
Reusing an original operation with changed inputs refuses before retaining another
generation. [Lifecycle transition integration](native-lifecycle-transitions.md)
now retains exact original snapshot references when the explicit protocol-2
journal exists. Publication preserves unfinished responsibility; it neither
reconciles effects nor admits a worker. Earlier publication-only transitions
retain their original empty reference lists.

History is bounded to 128 generation records and bounded directory inventories.
Capacity exhaustion refuses further publication while retaining existing custody;
there is no automatic history deletion or compaction. Database loss, changed
persistent identity, replaced custody, connected clients, corrupted records or
uncertain lifecycle history leave publication unavailable and runtime stopped.

## Verification and remaining scope

Fifteen boundary tests exercise ordinary-Linux filesystem replay, lost
acknowledgements at binding/transition/pointer/receipt retention, reboot with an
unacknowledged pointer or staged successor, lease loss, competing publishers,
changed binding, unknown legacy history, replaced directories, tampered receipts
and changed request/scope refusal, plus stopped-descendant checks and old-manager
absence/PID reuse, corruption in older receipts and unknown canonical operations.
Every retained operation is validated even when it is outside the current pointer.
These tests isolate host and database admission
with boundary stand-ins; they do not substitute for an actual service experiment.

An owned offline VM passed twenty checks with independently allocated fixture
inputs, real systemd and PostgreSQL 18.4. The Root fixture killed only the bound
first manager through a pidfd after pointer publication, while its database lease
was held and its completion receipt was absent. The actual same-boot restart
replaced the service parent and manager and published a successor referencing
that original uncertain pointer. It preserved the original missing receipt.
Lost pointer acknowledgement resumed exactly, and a competing publisher refused
the existing lifecycle owner.

An actual kernel reboot then published a third generation referencing its exact
predecessor. The persistent binding, original database row and ordinary relation
owner, retained record/transition/receipt bytes and inodes, machine identity and
unit definition survived. Explicit guest boot readiness and complete bounded
message writes make the fixture channel observe the full reboot result. The
guest powered off normally. Four independent custody checks bind forty-four
current operator sources and confirm all nine booted fixture groups are empty;
original failed and superseded disks, logs, requests and diagnostics remain retained.
Four additional checks inspected eleven installed files on a private read-only
copy of the powered-off disk. All seven product modules, the fixture manager,
observer, bootstrap and installation unit match their exact expected bytes,
Root ownership and single-link file identities. The original disk remained unchanged;
no physical, loop or mounted device was used for this inspection.

These observations establish stopped resource publication. Product allocation,
deployed database authentication, generation-aware application markers, lifecycle
stage reconciliation, artifact and functional readiness, managed Cloud and complete
journey acceptance remain open. Current required CI and integration are separate
gates. The boundary stand-ins alone do not establish the VM result.
The [accepted supervision decision](../decisions/0018-native-supervision-generations.md)
defines the remaining integration order.
