# Native lifecycle responsibility

Implementation under [decision 0018](../decisions/0018-native-supervision-generations.md).
This component retains durable responsibility before controller dispatch.
Preserve the original canonical protocol-2 request, input-seal digest, durable
binding, generation and owner. Later claims may reference a successor generation
and continuity receipt; they must not replace that origin or the stage history.

Use the existing installation-wide OS lock through held generation-record custody.
Retain content-addressed immutable snapshots before publishing an atomic operation
head. Bound record count, bytes and stage events. A lost commit acknowledgement
must be distinguishable from an incomplete head publication. Retain partials and
unreferenced snapshots; neither grants permission to repeat a stage.

Starting a fixed stage records responsibility before the caller can perform an
effect. Reopening a recorded running stage makes it uncertain. Only explicit
reconciliation with an observation receipt can decide whether it was applied.
Failure does not imply that a consequential stage had no effect. Exact terminal
replay must preserve the original records and append no duplicate claim.

The store grants no Root authority, current-generation publication, database
exclusion, stage execution or functional readiness. Its caller must separately
establish protected inputs, persistent continuity, current service ownership,
actual OS/database fencing and reconciliation of previous descendants. Existing
generation publication validates and retains explicit snapshot references through
[lifecycle transitions](native-lifecycle-transitions.md). Unknown history still
refuses, and worker admission remains closed until stage-specific integration.

Required verification includes ordered stages, retained original inputs, competing
process refusal, changed/forked ownership, replaced locks/directories, interrupted
snapshot and head publication, lost synchronization acknowledgements, explicit
uncertainty, rebind refusal, bounded history and terminal replay. Component fixtures
do not establish installed controller, actual kernel reboot or complete journeys.

## Store and claims

`NativeLifecycleResponsibility` borrows an already-held `GenerationRecordCustody`.
It never creates or replaces the lifecycle lock, and closing the journal does not
release the caller's custody. The current recorded generation must match the
actual caller's PID, birth, UID, boot and namespaces. Each method rechecks that
original owner, the held directories and unchanged generation registry. Forks
cannot borrow it. Actual systemd scope and publication remain caller obligations.

The fixed `history/lifecycle-responsibility-v2` directory contains only `records`
and `heads`. Directory descriptors keep writes beneath the original directories;
no changed pathname can redirect them. Original snapshot files contain protocol
2, kind `native_lifecycle_snapshot`, immutable `origin`, predecessor digest,
claimed generation, epoch, stage, status, completed stages and the complete bounded
event sequence. Origin contains the canonical request and digest, original input
seal digest, generation, owner and creation time. Events cannot rewrite it.

Records use their canonical SHA-256 as filename. An operation head has protocol
2, kind `native_lifecycle_head`, installation, operation and snapshot digest.
Every snapshot validates its complete event replay, original generation, exact
predecessor, unchanged origin and one-event extension. Histories must have one
root and one tip per operation, without forks, detached heads or unknown partials.
Enumeration is bounded; limits are 128 operations, 1024 snapshots, 128 events per
operation and 128 KiB per snapshot. Starting a stage reserves three event/record
slots for recorded intent, a subsequent claim and its result. Exhaustion refuses
before the stage starts; unlimited retries are not promised.

Normal enrollment follows inspect, stage, migrate, bootstrap, verify, activate
and enroll. Normal upgrade follows inspect, stage, maintenance, migrate, verify,
activate and public verification. A successful stage carries a receipt digest.
A failed stage becomes uncertain, rather than implying no effect. Reconciliation
requires an exact boolean and an observation receipt digest; an applied result
advances the stage, while observed nonapplication permits retry. The store only
records that metadata: it does not validate the actual observation behind a hash.
Upgrade rollback/forward-repair engines remain separate required implementation.

Reclaiming an interrupted running stage changes its recorded state to uncertain.
A successor claim requires an explicit continuity digest and an actual retained
ancestor chain. It may record a newly observed input-seal digest without replacing
the original seal reference or old events. Neither the supplied continuity digest
nor an ancestor chain proves persistent continuity or previous-descendant absence.
The protected controller must establish those facts independently before effects.
An unfinished different operation blocks a new claim. Exact terminal replay adds
no new claim and provides no fresh readiness observation.

## Interrupted publication

Default opening refuses incomplete publication. Explicit `recover_publication`
can promote one complete validated snapshot or head partial, or publish the exact
retained successor of an old head. It resynchronizes the original bytes and
retains the record chain. Complete partials retain their inode through rename;
snapshot publication never overwrites another record. Incomplete, foreign or
branched content refuses and remains untouched. Repair publishes metadata only:
a repaired recorded stage start still becomes uncertain on claim and cannot be
blindly repeated. A lost head acknowledgement reloads the committed outcome,
preserving completed stages. No operation is executed by recovery.

## Current verification

Twenty-five focused ordinary Linux checks pass, including the existing generation
custody checks. They cover fixed ordering, origin retention, successor references,
uncertainty, complete/incomplete partials, interrupted head publication, lost
acknowledgement, terminal replay, forks, replaced directories and capacity refusal.

Two additional process fixtures kill owned writers through original pidfds, after
a recorded stage start and after recorded success. Two competing processes refuse
the actual original OS lock. Replacement writers preserve original snapshot bytes
and inodes, lock identity and origin; both refuse blind repetition. PID, birth,
UID, boot/namespaces and filesystem custody are actual. Systemd/group scopes,
durable and input-seal digests, continuity and stage receipts are synthetic fixture
metadata. No database exclusion, kernel reboot, product stage effect or installed
service admission is established. The first process fixture attempt failed while
parsing combined warnings and JSON output; its source, output and actual files
remain retained separately from the corrected passing fixture.
