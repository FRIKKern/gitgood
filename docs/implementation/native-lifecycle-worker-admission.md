# Native lifecycle worker admission

The native and maintenance leaves can now observe a recorded enrollment or
upgrade window through the fixed generation admission and monitor entries. This
implements part of [decision 0018](../decisions/0018-native-supervision-generations.md).
It does not execute a lifecycle stage, acquire database exclusion or establish
functional readiness. The complete native application and controller remain
integration work.

## Independent protected inputs

The fixed Root-owned `/etc/gitgood/installations/<installation-UUID>/lifecycle-worker-admission-v2.json`
selects this reader. A caller supplies neither a policy path nor permitted stages.
The closed protocol-2 policy binds installation, operation, enrollment/upgrade
purpose, clean candidate, durable binding, original operation-seal digest,
request digest and ordinary UID/GID. The fixed ownership seal must agree with
that candidate, operation and binding.

The reader independently checks the original Root operation seal and its private
input directory. Full file identities, nanosecond timestamps, canonical bytes,
bounded exact names, held descriptors, private permissions and byte digests
remain required. Even a fresh reader refuses a same-byte replacement or rewrite
against the original seal. Payloads remain private; the result returns only the
closed request and its pinned candidate/seal/request digests. These checks do
not impersonate the controller MainPID or provide allocator authority.

## Fixed stage windows

| Purpose | Maintenance leaf | Native leaf |
|---|---|---|
| Enrollment | `migrate`, `bootstrap` | `verify`, `activate`, `enroll` |
| Upgrade | `migrate` | `verify`, `activate`, `public_verify` |
| Completed operation | Refused | Recorded runtime admission, subject to all current scope checks |

Pending, uncertain and other running stages refuse. Running responsibility must
name the current published generation and match the original protected request
and input seal. Every other retained operation must be complete. A completed
operation from an older generation requires its exact terminal snapshot reference
in the current transition and retained ancestry; an old running operation cannot
provide current worker admission.

Admission and the monitor's initial reply retain an optional closed
`lifecycle_observation` when this explicit Root policy is present. It contains
the original operation, purpose, candidate, request/origin/snapshot digests,
recorded generation, epoch, stage, status and worker. A terminal ancestor keeps
its original generation; it is never relabelled as the current one. The Elixir
consumer checks the closed schema, typed identities and fixed stage/role windows.
Running observations must name the current pointer's generation. Unknown,
pending and uncertain observations refuse. No caller request can supply this
field, and the publication-only path omits it.

The monitor's original history digest already binds this observation. Returning
or editing a caller's copy grants no lifecycle effect authority and changes no
captured guard. Stage advancement still poisons that guard. Business startup must
also match its requested action to this original observation before effects;
that application/controller integration remains unfinished. Writer exclusion,
lifecycle responsibility and readiness flags remain false in this read-only reply.

## Action-specific startup

The explicit `NativeOwnershipSupervisor.start_lifecycle_link(root, action, children)`
path makes ownership startup the first child. Its fixed actions are `:runtime`,
`:migrate` and `:bootstrap`; child options accept only `root` and `action`.
Migration and bootstrap share the maintenance leaf, but cannot exchange their
recorded stage. Bootstrap requires enrollment purpose, and both maintenance
actions require their exact running stage. A completed operation permits runtime
without replaying a maintenance action.

`NativeLifecycleAction` checks the decoded original observation against the
independently read Root operation, candidate and durable binding. Missing policy,
changed authority, uncertain history and action/role mismatch refuse before
controller handoff or opening the SQL lease. The existing controller publication
and fence still finish before any supplied worker starts. This API never executes
an action from a receipt and does not accept a command or mode override.

The packaged application callback remains unwired and refuses native startup.
Actual business effects, fixed lifecycle dispatch and interruption recovery still
require implementation and installed verification. Matching fixture metadata is
not proof of a migration, bootstrap or complete installation.

The [hosted startup-boundary case](native-hosted-ownership.md) tests the actual
Root seals, protected inputs, journal transport, live controller and three
explicit startup actions. Its prior-stage receipts are declared fixture metadata;
they establish no business stage effects. The installed boundary stays unverified
until a current receipt passes both wrong-action refusal before handoff and the
three actual admitted owners.

The reader admits only complete, bounded, canonical history. It performs no
partial recovery, journal claim, write or effect reconciliation. The default
publication-only reader continues to refuse lifecycle history and also refuses
the explicit lifecycle policy. It cannot silently bypass this integration.

## Original guard and installed dependencies

The guard retains the original scope, generation files, lifecycle snapshot and
Root/private input identities. A stage advance, file replacement or rewrite,
controller loss, fork or role change invalidates that guard permanently.
Restoring bytes or moving to another allowed stage cannot revive it. A new leaf
needs fresh admission. Closing it releases only its read descriptors, never the
controller's existing lifecycle lock.

Heartbeats check the captured metadata and bounded names without reparsing the
journal or opening database identity sessions. The installed entry checks all
41 required Python peers for Root ownership, regular single-link files and
nonwritable modes before importing protected admission code. Existing bounds and
wire fields remain unchanged. `lifecycle_responsibility_admitted` remains false:
worker observation grants no lifecycle write or effect authority.

## Verification and remaining work

The component suite passed 82 focused checks and 604 operator tests, including
29 documented skips. A separate ordinary-UID fixture used actual Root seals,
private input files and all 41 protected module peers: 14 constructor checks,
two missing/writable peer refusals and three live guard losses passed. The live
cases observed recorded stage advancement, same-byte Root policy replacement
and an actual kill of the fixture's original controller. Original actors, files,
logs and exact tested source are retained privately.

Actual filesystem custody and owned process termination are distinct from the
fixture's service/cgroup and database admission stand-ins. These cases do not
prove systemd admission, database exclusion, a protected installed application,
controller dispatch, reboot recovery or J14/J15 acceptance. Stage engines,
previous-owner/backend fencing, allocator integration and complete journeys
remain required before deployment.
