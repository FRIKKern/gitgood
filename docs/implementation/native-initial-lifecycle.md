# Native initial lifecycle

This development dependency joins the private first-install inputs to actual
native installation stages. The journal and anchor share the installation-wide
lock used by upgrades and retirement. An anchor reserves initial responsibility
before the first journal acknowledgement. It binds the request and named shared
lock identity; replacing that lock refuses the current and next controller.

`NativeEnrollmentActions` freshly checks the admitted configuration, private
stores and keys, database identity, five executable identities, five delegated
groups, driver membership, boot and namespaces. The current supported runtime
profile is Ubuntu 24.04 x86-64, Python 3.12, Git 2.43 or later 2.x, Node 22.23.3,
PostgreSQL 18.4 and Caddy 2.11.7. These checks precede archive staging. Candidate
paths, commands and environment are fixed by the operator. Private bootstrap
values travel only in the child's environment, never command arguments or
ordinary output. Generated release configuration stays outside immutable code.

The controller runs inspect, stage, migrate, bootstrap, verify, activate and
enroll. It retains private, digest-bound observations for each completed stage.
Migration runs in the maintenance group. Owner creation runs in the native group
and stops that whole group before normal runtime starts. The separate owner
observer starts no application supervisor or installation runtime lease.

Internal readiness checks matching clean forge/web identities and exact schema.
The public probe uses the configured CA with redirect and ambient proxy refusal,
checks anonymous private API denial, signs in the recorded owner, confirms that
same user and current owner membership, reads authorized repository metadata and
revokes its temporary session. It creates no repository or Git credential. This
is initial access readiness; complete Git transport workflows remain J01/J02.

The first activation pointer names the actual artifact, stage identity, immutable
code inventory, schema and public access observation. Terminal completion then
publishes `initial-baseline-v1.json`, sealing the initial journal, anchor and
activation. Publication and historical reads validate all seven digest-bound
stage observations, the recorded owner, exact schema, pointer and access-probe
digests. Missing or changed observations refuse the handoff and first upgrade.
These are retained observations; reading them does not perform a new live probe.
An exact terminal reopen can finish a lost metadata handoff without
writing another initial claim. The baseline never contains a fictitious upgrade.
The first real upgrade must agree with its candidate, artifact and resource
bindings. Retirement can claim the initial baseline before any upgrade. Status
keeps initial progress separate from upgrade history and reports an unsealed
terminal journal as awaiting handoff.

## Fixed commands and recovery

Run as the installation actor in its original delegated driver group, using
independently prepared private inputs and request seal:

```sh
python3 tools/deployment/native_operator.py enroll \
  --inputs-directory /private/initial-inputs --request-sha256 EXPECTED_REQUEST_SHA256
python3 tools/deployment/native_operator.py enroll-resume \
  --inputs-directory /private/initial-inputs --request-sha256 EXPECTED_REQUEST_SHA256
```

The commands accept no command, role, callback or target override. `enroll` starts
a pending initial request. `enroll-resume` preserves the request, operation,
archive and resource bindings. It stops only the four original runtime groups,
even if the database is unavailable. The driver, boot, namespaces and kernel
identities must still match the admitted scope.

Recovery independently validates a published stage. Unpublished partial bytes
are never executed. A private manifest seals the partial's original identity
before an atomic rename retains it; a fresh stage uses the pinned archive.
Lost rename acknowledgements reconcile the original identity, never a namesake.

Migration recovery observes emptiness or an exact committed migration prefix.
Only the fixed packaged forward migration may repeat; no down migration or
database recreation occurs. Bootstrap uses the packaged read-only observer:
recorded creation advances once, absence permits creation, conflict refuses.
Verification, activation and enrollment restart quiesced groups and require
fresh access probes. An existing initial pointer must match exactly.

Complete initial requests report historical completion without another claim or
readiness assertion. Initial commands refuse after upgrade or retirement
responsibility starts. Use status and the appropriate lifecycle command after
handoff. Enrollment errors return a fixed code without private paths or details.

## Current evidence and limits

The current source operator suite passed 209 tests: 197 Linux checks and 12
expected foreign-platform skips. It includes seven lifecycle custody, eleven
baseline, seven partial-retention and command-refusal privacy checks. Baseline
tests cover metadata-only receipts, missing/changed observations, changed probe
data, handoff loss and first-upgrade/retirement admission.
An additional delegated-host admission exercise passed five checks, including
actual runtime versions, stage refusals, inert archive refusal and whole-group
shutdown of a descendant in a separate process session. Two earlier harness
failures remain retained: a misclassified archive-refusal exception and an exit
status assertion after deliberate child reaping.

A separate fresh fixture ran clean packaged artifact `5960be0`, independently
inspected at 49,968,296 bytes with SHA-256
`3d9006a942faf7e553b02ca96362e02859ed42d5e420e98c4b8d6c727cdb0e69`.
All eight actual checks passed: empty admission, exact 16 migrations, owner
creation, native/web and TLS access, probe-session revocation, initial activation
and baseline, zero-upgrade status and unchanged exact replay, and a real runtime
marker matching the original allocation. The runtime groups remained running
after the controller exited. Its exact original groups were later quiesced;
database, stores, keys, history and artifacts remain retained.

A staging interruption killed the controller during archive writing. Recovery
retained the partial's bytes and inodes, reconciled missing publication and
completed the same operation; six checks passed. A second fixture stopped the
controller while packaged owner creation ran, observed all three owner tables
committed, then killed the controller before acknowledgement. Recovery used the
read-only observer without a second creation stage. All three tables remained
byte-identical; six checks passed.

The second initial baseline admitted its first real upgrade through the existing
CLI, from clean `5960be0` to clean `b4ded4a`. The new inspected archive has
49,966,399 bytes and SHA-256
`f55f2da8a6ac4df290dee4495592138136a9fba31810c6ff1f0386a9a51257f7`.
All seven stages, same-schema compatibility and private API/CA-verified
HTTPS/pinned-key SSH function passed. Its index contains one real upgrade;
initial record bytes and inodes remained unchanged. Six independent later
checks established runtime survival, fresh public identity/function and actual
terminal CLI replay with unchanged responsibility records. Runtime logs may
append during traffic; they are separate from those immutable records.

Each fixture retains its captured operator identities. The original happy path
predates recovery and observation validation; bootstrap recovery and first
upgrade precede the additive enrollment CLI dispatch. A fresh actual CLI staging
interruption passed six checks with all current operator files: the original
partial retained its bytes/inodes, all stages completed and exact CLI replay was
unchanged. This fresh baseline also passed the first distinct-candidate upgrade
and independent later runtime checks with the same current operator bytes.
Final source binding and integration CI remain separate gates. Failed harness
attempts remain retained: wrong configured host, inherited Windows Git working
directory, wrong SSH actor, root-only proof metadata and an incorrect comparison
of live runtime logs with immutable records. A child-source quoting failure
stopped before initial inputs or application effects; its original script and
diagnostics remain retained. No failed run is treated as passing.

An actual fresh first-install export refused before retirement responsibility
or removal: its configuration retained `GITGOOD_INSTALLATION_ID`, which the
recovery configuration validator did not accept. The failed fixture, original
database, stores, history and keys remain retained. Recovery now accepts that
optional UUID only when it equals the enclosing installation identity. Ordinary
restoration preserves it; retirement materialization rebinds it to the separately
allocated target UUID. Legacy configurations without the field remain supported.
A new clean artifact at `4320197` passed independent inspection with all sixteen
migrations. A separate fresh installation passed eight actual CLI enrollment
checks, then independent owner and outsider API, CA-verified HTTPS Git and pinned
SSH witnesses passed six checks each. The outsider is an explicit synthetic actor
created through packaged Accounts functions outside enrollment; this fixture does
not establish customer account provisioning.

The packaged export and checkpoint passed, and the actual `retire` CLI completed
all five stages directly from the initial baseline. No upgrade index or operation
was created. A separately allocated target restored exact data and configuration;
independent actors and real HTTPS/SSH access passed before and after exact source
database/store removal. Original initial record bytes/inodes remained unchanged,
and all nine original/target groups stopped. Six terminal checks passed: status,
unchanged retirement replay, wrong-plan refusal, retired-enrollment refusal,
separate original/target UUIDs and literal credential privacy across 77 retained
logs. Archives, keys, history, packaged code, target data and kernel/provider
resources remain retained. This is same-host evidence, not replacement-host or
managed Cloud acceptance.

A third fresh fixture ran the unchanged enrollment CLI with an explicit
fixture-only maintenance CPU limit. Its exact migration processes were paused
and the controller killed after three of sixteen packaged migrations committed.
Actual `enroll-resume` stopped the surviving owned processes, observed that exact
prefix, reconciled incomplete migration and completed from the same prefix.
Six checks passed through owner/access verification and the complete baseline;
terminal replay preserved responsibility JSON/lock bytes and inodes. This proves
partial migration recovery on the same boot, not reboot or storage power loss.

## Current packaged interruption matrix

Seven independent fixtures now exercise the unchanged shipped CLI and the same
clean `4320197` artifact. Each selected stage interruption and actual
`enroll-resume` passed six checks. Every fixture retained its original request,
operation and completed observations, sealed all seven stages, reported zero
upgrades and preserved responsibility JSON/lock bytes and inodes on exact
terminal replay. The exact original groups were then stopped; database, stores,
configuration, keys, history, packaged code and group directories remain retained.

| Stage | Actual interruption | Observed recovery |
|---|---|---|
| Inspect | Kill the exact running controller before inspection acknowledgement. | Read-only inspection reconciles the same stage as applied. |
| Stage | Kill while the archive contains a nonempty strict prefix of its pinned bytes. | Reconcile missing publication, retain the original partial's bytes/inodes and stage the pinned archive afresh. |
| Migrate | Pause exact maintenance processes and kill the controller after three of sixteen migrations commit. | Stop surviving owned processes, observe that prefix and finish from exactly those three commits. |
| Bootstrap | Stop the controller while packaged owner creation runs; kill after all three owner tables commit. | Observe the recorded owner without another creation stage; all three tables remain byte-identical. |
| Verify | Kill after native processes start, before verification acknowledgement. | Stop original runtime descendants and repeat verification with fresh readiness and access checks. |
| Activate | Kill after the first current-release pointer publishes, before acknowledgement. | Stop original runtime groups, repeat access checks and preserve the existing pointer's bytes/inode. |
| Enroll | Kill the running enrollment stage before its acknowledgement. | Stop original runtime groups and complete enrollment with a fresh access probe. |

A separate eighth fixture lost the controller after all seven observations and
the terminal journal, before baseline publication. Six checks passed: read-only
status reported awaiting handoff; actual terminal resume published the missing
baseline without another claim or epoch. Journal, anchor, observations, pointer
and locks retained their bytes/inodes. Terminal replay established historical
metadata completion, not a new live-readiness observation.

A separate installation used an ordinary PostgreSQL login role with no
superuser, create-database, create-role, replication, bypass-RLS or explicit
role-membership privileges. In that new disposable database only, the harness
removed PUBLIC execution of `pg_control_system()` and granted that specific
function to the application role without grant option. Eight actual CLI
enrollment checks and six privilege/custody checks passed. All sixteen migrations
completed and all 105 public application relations belonged to that role.
Seventeen retained logs excluded the tested literal private credentials. This
loopback trust fixture proves actual privilege boundaries; deployed password/TLS
authentication remains a separate test.

The private archive `initial-stage-recovery-source-5f7386d` contains 53 records
plus its digest index. It binds all 65 operator files, the 37 files used by every
actual fixture and all 257 app files. The archived review SHA-256 is
`bf669aa145fc12312360697885c18a9fb52965a4df1c9c3860de821d54444fdc`;
the digest-index SHA-256 is
`ef63ff5d88ddd67566d0d49891ba1bf33c1988b82d2e92f21c2d613562897682`.
Producer and verifier are the Codex primary agent on `Gitgood-Verify-2404`:
the root harness provisions and signals exact owned fixtures, while UID 1000
runs the unchanged CLI. Private inputs, databases, credentials, TLS/SSH keys and
encrypted archives remain outside the exported metadata archive.

Original failed harness attempts remain retained: a startup process exited
during identity enumeration, the first role fixture assumed PUBLIC function
execution was absent, another compared PostgreSQL OID JSON strings numerically,
and an ordinary-UID log verifier could not read root-private logs. Fresh fixtures
or a separately named verifier resolved each issue. No failed attempt was
relabelled passing, and root-private log ownership remained intact.

[PR 68](https://github.com/FRIKKern/gitgood/pull/68) integrated the first-install
recovery fix and native lifecycle. Every required CI step passed on
`debb4de`; its tested synthetic tree equals merged main `5f7386d`. Five CI
records and 61 artifact files passed private digest readback. Main CI and any
later revision remain independent gates.

Running or failed effects still require stage-specific reconciliation; a
response or receipt alone cannot silently replay them. The matrix proves one
selected owner-loss scenario per stage on the same boot. It does not cover every
failure boundary or storage power loss. Persistent supervision, explicit reboot
resource generations, host allocation/cancellation, managed Cloud and current
complete J01/J02/J14 acceptance remain unfinished. See the
[native host prerequisites](native-host-prerequisites.md). The fixed CLI
provisions no host and establishes no product release.
