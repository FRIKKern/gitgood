# Ordinary controller artifact inspection

`NativeArtifactInspectionController` executes archive inspection while the
original ordinary systemd controller retains its installation history lock and
database writer session. It records the actual inspection receipt before
beginning `stage`. The fixed Root socket path now connects that request to
serialized policy allocation and protected extraction. The controller validates
actual published code before recording durable stage completion. This source
path remains unverified on a live systemd controller until hosted evidence passes;
production provisioning and the long-lived Root listener remain unfinished.

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
It accepts only running `inspect`, pending inspection completion, running `stage`
and pending stage completion for this original operation. It supplies no worker admission and does not
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

## Serialized staging and completion

`begin_stage()` requires successful actual inspection, begins the durable stage
and retains the same writer session/history custody. It returns the existing
bounded canonical Root controller request with installation/operation and the
original history descriptor. Returning that frame neither sends it nor admits a
Root effect. `stage()` connects only to the independently provisioned
`/run/gitgood/root-artifacts/INSTALLATION.sock`, whose original Root owner, ordinary
group, `0620` mode, inode and protected parents must match. The actual socket peer
must have Root UID/GID. Its bounded canonical response binds this installation,
operation, candidate and stage receipt hash. A refusal or changed peer/path
retains the running stage and every effect.

[The Root dispatcher](native-root-artifact-dispatch.md) authenticates the actual
ordinary MainPID and its original history descriptor, observes its original SQL
writer exclusion, allocates the fixed policy under an actual Root flock, and
brackets every extraction check with that retained original custody. Root SQL
observers close before success is acknowledged; the ordinary controller then
checks its same original writer session again.

The ordinary controller reads only the fixed published Root output. It checks
the response hash against the actual read-only receipt, original request/scope
and running-stage snapshot, archive digest and byte count, inspection-derived
allocation budget, original directory/file identities, exact entry sets, every
regular file's content hash, confined Forge symlinks and the full inventory hash.
Only after those checks and another original-custody check does its owned journal
record `succeed('stage', ...)`. An immutable record and controlled head refresh
then expose pending stage completion. No response alone supplies completion.

Closing or observed loss permanently invalidates the controller and releases only
its owned reader/archive/writer session. Original endpoint, OS lock, journal,
inputs, archive and every retained record remain. Interrupted running stages
still require explicit actual-effect reconciliation.

Thirteen portable admission/window/refresh/transition checks include a real archive
read with explicit controller and journal stand-ins. Four Linux Root output tests
use actual extraction, read-only files, content hashes and original identities,
with explicit controller and fixed-path stand-ins. Ten dispatch boundary/socket
tests keep their authority stand-ins explicit. These checks do not prove live
ordinary systemd custody or complete controller-to-Root dispatch.

The hosted default-release case now selects the complete actual production Forge
and web archive, performs this controller/Root path, records actual inspection and
stage receipts, and launches migration, bootstrap and normal packaged runtime
from the staged code directory. Its public web policy binds the staged web tree.
That expanded case is unverified until its exact source, log and artifact are
reviewed. Production provisioning/listener, interrupted-effect reconciliation,
activation/enrollment and full reboot/replacement recovery remain required before
J14/J15 acceptance or original VM retirement.

The hosted fixture can diagnose a stalled full stage with thirteen fixed method
counters. They record only invocation counts and overlapping cumulative elapsed
milliseconds for the guard, file, SQL, manager and extraction paths. Wrappers
forward the original arguments, return value and exception and restore every
original method on exit, including interruption or partial setup failure. No
profiler hooks, stacks, paths, arguments, SQL or return values enter this output.
The installed production modules, payload, guards and deadlines are unchanged.
These timed runs are diagnostic; production deadline acceptance still requires
an uninstrumented run of the complete stage and subsequent staged runtime.
