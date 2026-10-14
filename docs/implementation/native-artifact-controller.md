# Ordinary controller artifact inspection

`NativeArtifactInspectionController` executes archive inspection while the
original ordinary systemd controller retains its installation history lock and
database writer session. It records the actual inspection receipt before
beginning `stage`. Root policy allocation, protected extraction and a production
listener still need to be connected to this controller path.

## Original controller custody

The constructor accepts an installation UUID and exact existing
`GenerationRecordCustody`, `NativeCommandEndpoint` and
`NativeLifecycleResponsibility` objects. They must belong to the original
ordinary MainPID, installation and journal. The caller must have matching ordinary
UID/GID; Root and caller authority maps refuse before resource reads.

The fixed protected generation and operation policies supply original runtime,
inputs, candidate, request, publication, directory/lock identities and limits.
Actual persistent binding, private configuration, controller endpoint and history
remain checked. The controller borrows the original OS custody/endpoint/journal
and owns only its inspection reader, archive descriptor and `psql` writer session.
Application worker groups must remain stopped.

## Controller windows and real inspection

A separate private reader reuses the complete generation/lifecycle validators.
It accepts only running `inspect`, pending inspection completion and running
`stage` for this original operation. It supplies no worker admission and does not
expand the maintenance/runtime worker stage lists. Other incomplete operations,
changed inputs, generation/publication or journal state refuse.

The original sealed artifact declaration selects the fixed Root-controlled
`/var/lib/gitgood/artifact-inputs/INSTALLATION/OPERATION/archive.tar.gz` by
candidate, SHA-256 and bounded bytes. The ordinary controller needs read access;
the archive and every parent must remain Root-owned and unwritable by ordinary
accounts. Original parent identities and archive descriptor/named metadata remain
checked. There are no caller paths, programs, environments or callbacks.

While holding the original writer exclusion, inspection bounds gzip/tar headers
and inventory before the shared native inspector validates digest, build identity
and candidate. The canonical actual inspection receipt is published through the
owned journal's `succeed('inspect', ...)`. Inspection executes no application code
and establishes no readiness or stage extraction.

Reader refresh admits only the journal's one newly published event and head. All
generation/publication/input metadata, prior lifecycle record identities and
directory inodes must remain unchanged. This permits the controller's actual
transition without adopting a replacement generation, input or old record.

## Stage request and pending integration

`begin_stage()` requires successful actual inspection, begins the durable stage
and retains the same writer session/history custody. It returns the existing
bounded canonical Root controller request with installation/operation and the
original history descriptor. Returning that frame neither sends it nor admits a
Root effect. The production listener, response validation, protected stage
dispatch and durable stage completion remain unfinished.

Closing or observed loss permanently invalidates the controller and releases only
its owned reader/archive/writer session. Original endpoint, OS lock, journal,
inputs, archive and every retained record remain. Interrupted running stages
still require explicit actual-effect reconciliation.

Twelve local admission/window/refresh/transition checks include a real archive
read with explicit controller and journal stand-ins. They do not prove live
ordinary systemd custody or controller-to-Root dispatch. Those observations,
normal runtime from staged code, activation/enrollment, public readiness and full
reboot/replacement recovery remain required before J14/J15 acceptance or original
VM retirement.
