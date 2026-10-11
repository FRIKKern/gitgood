# Native ownership publication

Implementation under [decision 0018](../decisions/0018-native-supervision-generations.md).
The controller handoff can retain successive native worker claims within one
lifecycle operation, after proving the previous owner and database backend absent.
This is a component path for the installed proof. Product application startup,
lifecycle dispatch, controller-restart recovery and journey acceptance remain
unfinished. The application profile still refuses native startup before mutation.

## Successive workers in one operation

A migration worker, bootstrap worker and runtime worker have different BEAMs and
database connections. Protocol 4 therefore keeps the lifecycle `operation` stable
and gives each worker a distinct `claim`. Each claim references the exact preceding
record and its controller reservation. Protocol-3 record bytes, filenames and entry
behavior stay unchanged. Protocol-2 histories without original backend kernel
identity cannot be converted or used to authorize a successor.

The currently supported boundary is one boot, generation, candidate and actual
controller process. The controller keeps its original `GenerationRecordCustody`
and protected `NativeCommandEndpoint` open. It borrows that custody into readers;
reader refusal cannot release the controller's flock. A lifecycle caller must stop
and reap its captured workers before advancing stage history. Every stage change
invalidates the previous worker guard, so the next worker captures the new stage.

The explicit controller path is:

1. `NativeOwnershipController.reserve(mode)` checks the Root seals, durable binding,
   generation and lifecycle window. All four captured worker groups must be empty,
   including descendants. Every retained original BEAM must be absent; an original
   zombie or unreadable identity refuses. Original PostgreSQL PID, microsecond birth
   and kernel birth must independently be absent. A fresh original writer-exclusion
   session then brackets retention of the immutable reservation.
2. `NativeOwnershipSupervisor.start_controller_link/3` starts the worker with the
   explicit controller startup child. Before opening its database lease, the child
   calls the fixed `native_ownership_handoff_entry.py`. The helper sends one closed,
   canonical request over the existing protected Unix endpoint. The live controller
   independently checks the kernel peer UID, GID, PID, birth, helper-to-BEAM ancestry
   and selected cgroup. The first exact BEAM birth is assigned once. Only then does
   the controller release its exclusion and prove that original exclusion backend
   absent. The unfinished handoff has an absolute 120-second deadline. Fully
   verified publication retires that deadline; the live controller can keep serving
   for the runtime's lifetime. A later successor receives a fresh finite deadline.
3. The worker opens its own original held database lease and publishes its protocol-4
   record through the same fixed entry. `serve_once(controller)` handles the bounded
   request and reply. The publisher rechecks the live reservation, exact assigned
   BEAM, current generation, prior owners and backends, and the new BEAM's original
   SQL/kernel session and socket ownership. It never accepts a stored receipt or
   supplied hash as admission authority.

Both peers authenticate the other side. The client binds the actual controller
MainPID and birth to its independently observed service scope. Requests accept no
caller-supplied path, executable, command, environment, URL or SQL. The Root endpoint
seal contains the two configurable limits; the observed service must also retain
the fixed CPU period and zero swap allowance. The protected module manifest includes
the handoff entry, transport, controller and transition store. Installing only the
entry script does not satisfy module custody.

## Retention and interrupted handoffs

The `.gitgood-ownership-v2` directory keeps all original records. A separate bounded
`.gitgood-successors-v4` directory keeps each immutable reservation, assignment,
marker-transition intent and completion receipt. The original marker inode moves
without replacement into that claim's `old-marker` archive. The new marker also moves
without replacement. The temporary gap has retained intent and grants no runtime
authority. There is no deletion, overwrite, reset or legacy conversion shortcut.

Reopening complete history validates every closed receipt schema, predecessor link,
original marker identity and byte sequence. A substituted inode with identical bytes
refuses. Admission stops before a 129th retained ownership record. Each receipt and
record is size-bounded before publication; an oversized reservation never reaches
assignment or database handoff.

| Interruption | Current outcome |
| --- | --- |
| Request refused before assignment, while the original reservation and exclusion remain live | The same controller may accept the first valid request within the original deadline after fresh checks. |
| Reservation write or acknowledgement fails before `reserve` completes | Retain the exact files and release that controller's exclusion; refuse automatic reassignment. |
| Assignment retained, but admission reply is lost or the worker exits before its new original backend identity is captured | Retain reservation and assignment; refuse a second owner, new reservation or reopened-controller adoption. Unknown backend identity is never treated as absence. |
| Publication file sync or marker rename acknowledgement fails | The same live object may retry the exact record and original partial inodes, within its deadline and after fresh owner, predecessor-absence, lease and custody checks. |
| Completed owner later disappears | A same-controller successor may reserve only after all original owner, descendant and SQL/kernel absence checks plus fresh writer exclusion pass again. |
| Controller restarts, boot or generation changes, deadline expires, or history contains an unknown/incomplete transition | Refuse; retain responsibility. Separate recovery or Root continuity is still required. |

This implements completed-owner replacement and bounded same-controller publication
retry. It does **not** provide complete startup-interruption recovery. In particular,
the unknown-backend case after assignment remains an explicit operational boundary.
The component never signals processes itself: lifecycle stop/reap orchestration is
still separate, and all four workload leaves must be empty before reservation.

Ordinary Linux tests exercise real directory custody, locking, peer credentials,
original-inode preservation, all six publication renames and every file/directory
sync interruption. Controller order tests use explicit service/database stand-ins;
they cover migration, bootstrap and runtime claims, lost admission replies, deadlines,
capacity refusal and borrowed-flock preservation. Elixir tests cover record construction,
closed handoff replies, the existing startup refusal and monitor attachment deadline.
These checks do not establish actual protected systemd/BEAM/database integration or
installed journey acceptance. The hosted installed proof must establish that path
before enabling native product startup.

## Marker custody

`NativeOwnershipMarkers` publishes a runtime or maintenance marker referencing an
already retained immutable ownership record. The marker binds protocol, kind,
installation, operation, exact mode and record digest. It grants no replacement,
writer, lifecycle or readiness authority.

An exclusive nonblocking lock on the original ownership-directory inode serializes
the two marker modes. Storage and record-directory descriptors retain their admitted
identities. Complete record names and all eight record-file metadata fields are
bracketed throughout publication. An identical completed retry preserves marker
bytes and inode. A different marker or the other mode refuses without repair.

Publication uses an exclusive private partial in the ownership directory, file and
directory synchronization, and atomic link publication without replacement into
storage. Synchronizing storage precedes removal of the partial. A failed link,
unlink or synchronization retains observable responsibility; partials and hard
links refuse later publication. Nothing removes an unknown marker or partial.

Fourteen ordinary Linux filesystem tests pass, including kernel lock contention,
mode competition, symlink/hard-link/permission refusal, storage replacement,
identical-byte record/marker inode replacement, and interrupted synchronization.
Their service and database values are synthetic; these tests establish custody.

## Original database session and owner connection

`observe_held_session` uses bounded read-only queries against an independently
admitted psql executable and private configuration. It compares the original
backend PID, microsecond birth, ordinary database identity and existing advisory
lease. It never acquires a lease or adopts a new backend holding the same key.
Credentials stay in the child environment; queries and refusals expose no password.

When an owner is supplied, its UID and process birth must match current kernel
observations. Its network namespace must match the observer. The PostgreSQL
client port must identify one established loopback TCP connection whose socket
inode is present in that exact owner's descriptor table. Repeated observations
bind its descriptor, inode, endpoints and namespace. This prevents a different
process from borrowing another owner's held backend as publication authority.

Ten actual PostgreSQL/kernel checks pass against private ordinary-role sessions:
original held identity, changed birth, absent PID, changed cluster, unchanged
original session after refusals, actual backend closure, a new holder refusing the
old snapshot, actual holder/socket linkage, another ordinary process's refusal,
and changed owner birth. Both holder processes exited normally. These checks use
psql owners, not a protected native BEAM or full application artifact.

## Fixed entry and admission

The installed entry is fixed at
`/opt/gitgood/native/v2/native_ownership_publication_entry.py`. Isolated Python
must load only its protected Root-controlled directory. The entry validates all
installed module custody before importing publication code. Its canonical,
bounded request has only protocol and the complete closed ownership record.
It accepts no executable, shell, environment, database URL, seal path or SQL.

A separate Root-controlled protocol-3 `ownership-admission-v3.json` must contain exactly
protocol, kind, installation, ownership operation, candidate and durable binding
digest. The kind is `native_application_ownership_seal`; the operation and candidate
must match the request. Creating this seal belongs to the forthcoming constrained
controller; a stored application record cannot create its own authority.

The writer independently captures current generation/service/owner admission and
matches the complete scope, owner, publication and guard digests. The fixed generation
seal supplies executable and database expectations. Independently admitted private
configuration supplies the connection URL. Original owner/socket/session observations,
generation checks and both Root seal identities bracket record retention and marker
publication. Refusal after an effect retains that effect and reports no completion.

The protocol-3 record also retains the original backend kernel identity. A
separately Root-controlled per-boot scope and original process-birth checks
bracket SQL/socket observation and every effect. No current birth can replace
the retained one. The [current kernel ownership contract](native-kernel-ownership.md)
defines versions, legacy preservation and current component verification.

Earlier SQL-only boundary/order tests passed with explicit service/database stand-ins. They verified
closed requests, candidate/operation mismatch, changed owner, prior responsibility,
borrowed backend refusal, and preserved effects after session loss. Actual protected
entry execution, Root controller seal creation and native BEAM linkage remain required.

`Gitgood.NativeOwnershipPublication` calls only the fixed protected entry through
isolated Python with bytecode writes disabled. It clears inherited environment
variables, bounds the request to 32 KiB, the response to 4 KiB and execution to
60 seconds, and rechecks protected executable/entry custody after completion.
It binds the request to the actual BEAM PID and accepts only a closed canonical
response with the same operation and SHA-256 of the canonical record. Six focused
Elixir tests cover Python-compatible sorted ASCII JSON (including surrogate pairs),
malformed or oversized requests, owner binding, changed response identities and
rejection of additional authority. These tests do not execute an installed entry.

The original protocol-3 fixed admission allows an initial ownership claim or its
identical live retry; another retained ownership record still refuses through that
entry. Protocol 4 uses only the separately authenticated controller handoff described
above. Marker monitoring, whole-BEAM loss behavior, packaged functional access and
installed lifecycle interruption proofs remain required before native startup can be
enabled.
