# Serialized Root artifact policy allocation

`NativeRootArtifactPolicyAllocation` prepares the fixed stage seal consumed by
the protected stager. It derives the policy from an authenticated original
controller's live database exclusion, sealed artifact declaration and actual
archive inspection. The allocator is an implementation in progress: production
provisioning, ordinary inspection/stage dispatch and interruption reconciliation
remain unfinished.

## Original operation and archive

The Root-only constructor takes custody of an exact
`NativeRootDatabaseExclusionObservation`. Its current original snapshot must be
running `stage` with only `inspect` completed. The sealed original `inputs.json`
for enrollment or `plan.json` for upgrade must contain a protocol-2 `artifact`
declaration with kind `native_artifact_declaration`, installation/operation UUIDs,
candidate, SHA-256 and bounded archive bytes. There are no caller paths, programs,
environments, policies or callbacks.

The independently provisioned Root-controlled paths are fixed:

- Input: `/var/lib/gitgood/artifact-inputs/INSTALLATION/OPERATION/archive.tar.gz`.
- Output parent: `/opt/gitgood/artifacts/INSTALLATION`.
- Policy parent: `/etc/gitgood/installations/INSTALLATION/artifacts`.
- Original allocation lock: `allocation-lock-v1` beneath that policy parent.

Missing parents or the original lock refuse. This allocator does not create a
replacement lock or upload/copy an archive. Original directory descriptors and
named paths, Root UID/GID, permissions, file metadata and the held exclusive
kernel `FLOCK` remain checked. A competing allocator refuses without replacing
that inode. Input must be an unchanged, single-link, read-only Root file of the
declared size.

## Inspection and publication

Before policy publication, bound gzip/tar header parsing and inventory with the
existing protected stager's limits, then independently verify the declared digest
and candidate using the shared native inspector. The actual canonical inspection
receipt must match the completed `inspect` event in the original complete history.
A recorded fixture receipt alone cannot satisfy that check. Read-only inspection
is bracketed by original exclusion and resource checks.

The policy records the original controller scope, request, running snapshot,
archive metadata/digest and actual destination/history directory identities. It
must pass the protected stage seal parser. Both the system and policy volumes
must retain at least 20 GiB plus bounded metadata allocation.

Publication creates one exclusive operation partial, writes and fsyncs it under
Root read-only ownership, checks its original descriptor/named identity, then
uses `renameat2(RENAME_NOREPLACE)` beneath the held policy parent descriptor and
fsyncs that directory. After rename, only its expected `ctime` change is accepted on
the retained descriptor and matching named inode; all other metadata and exact
policy bytes remain checked, then the published fingerprint freezes again.
Foreign final files, pre-existing partials and uncertain effects remain; no
overwrite, adoption or cleanup occurs. Repeated allocation
and observed original-resource or lock loss permanently refuse. Closing releases
only owned descriptors and Root observation views.

## Verification limits

Portable declaration/admission tests use explicit account/guard stand-ins.
Root-only filesystem tests use actual descriptors, locks, inspection and
publication, with explicit admitted-controller, capacity and scratch-ancestor
stand-ins. Those Root tests and the actual live ordinary-controller stage flow
remain unverified until current hosted evidence passes.

This seal allocation does not execute extraction, mark a lifecycle stage
successful, establish a production Root listener, prove interrupted-effect
reconciliation or run the application from staged code. Artifact staging,
activation/enrollment, public readiness, unhealthy-candidate preservation and
reboot/replacement recovery remain required. Status keeps stage effect authority
and complete journey acceptance false. Every original VM/recovery material
remains protected.
