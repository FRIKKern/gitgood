# Native ownership and handoff on a disposable hosted runner

This fixture answers a specific unfinished question: can the packaged native
ownership components attach to a real systemd service and PostgreSQL backend,
then stop the original BEAM when that ownership is lost? It replaces large local
VM experiments with a bounded job on a fresh GitHub-hosted Ubuntu 24.04 runner.

**This is an ownership component proof.** A passing receipt does not mean
the native product can be enrolled, upgraded, activated, restarted, or deployed.
The first six cases start a small permanent fixture application from the production
release without product listeners. Later cases exercise actual maintenance,
native product workers and protected web/edge services. The separate
[normal-release case](native-default-startup.md) uses the real `Gitgood.Application`
callback without a fixture runtime substitution. Node/Caddy provenance is part
of the durable binding, and current installed public cases verify their services.

The first four cases require an absent lifecycle worker policy and history.
They never remove a policy or delete an ownership marker. The successor case uses the actual live controller to admit
three owners within one boot and generation. Product lifecycle execution,
controller restart and replacement-host recovery remain separate work.

A fifth `lifecycle-startup-boundary` case installs actual Root operation/worker
seals and private input-file identities, and uses actual journal custody. Its
stage observations are explicitly **fixture metadata** with business effects
unverified. They select migration, bootstrap and runtime windows for testing the
startup API; no product inspection, staging, migration or bootstrap is executed.
The same permanent probe application calls `start_lifecycle_link` in each window.
Before the migration owner, an attempted bootstrap action must exit without a
probe, assignment or publication. Root independently observes the original
exclusion backend and advisory lock still held before authorizing the correct
action under the same reservation. The three valid owners then undergo the same
actual handoff, heartbeat, loss and retained-inode checks as the successor case.
Root finally checks that the original operation/worker seals and exact private
input-file identities remain unchanged, and replays the complete retained journal
chain. Its tip must remain pending after exactly the five fixture observations
through `verify`; activation and enrollment remain unexecuted. The fourth case
still requires lifecycle policy and history to be absent.

`lifecycle_startup_boundary_verified` can become true only after this whole
installed case passes. `business_lifecycle_stages_executed` and complete product
acceptance remain false; synthetic stage receipts cannot establish those gates.

A sixth `private-business-inputs-boundary` case uses a fresh installation with
actual Root/input/journal custody and the same three lifecycle-aware owners. Its
private sealed payload contains deliberately synthetic migration expectations
and a synthetic first-owner password. Migration receives no bootstrap material;
bootstrap receives its original private fields and validates the existing ordered
owner digest. The actual startup calls the original attached monitor and checks
its lease/fence before and after the private reply. The fixture observes redacted
OTP status and records only fixed outcomes; no credentials or their digests enter
the public receipt. Runtime requests no private maintenance payload.

`private_business_input_stream_verified` becomes true only after that complete
installed case and final unit stop pass. The same original loss, kernel/SQL
absence, descendant/sibling and retained-inode checks still apply. Migration
expectations `[1, 2]` are fixture data rather than a verified packaged inventory;
no schema change or first-owner creation is executed. Complete business lifecycle
effects, product startup and recovery stay unverified.

The seventh `maintenance-effects-boundary` case uses the fixed production
maintenance application and actual Repo/worker for migration and bootstrap.
Its sealed target comes from the clean copied release's migration inventory.
The actual role has a conflicting default search path and an empty shadow schema.
The fixed maintenance Repo and migrator must still use public; Root independently
requires the shadow namespace to receive no relations after either action.
The fixture witness waits for Root to capture original SQL/kernel backends, then
requests the fixed action. Root independently observes the complete schema,
durable first-owner receipt and current owner membership in the allocated private
database. After original helper/backend loss, every captured lease and Repo
backend must be absent before another owner can start. Worker status is redacted.
The runtime owner still uses the fixture application, and inspection/staging/
verification journal receipts remain explicitly synthetic metadata.

The `maintenance-schema-refusal` case has one unexpected application table
before an initial migration. The fixed worker must terminate the original BEAM
without creating migration, user or owner-receipt tables. Root observes all
captured backend identities absent and unchanged original lifecycle head/snapshot,
ownership record and marker inodes. The fixture manager does not advance that
failed stage. Both new cases require final owned-unit stop and absent cgroup.

The final `maintenance-inventory-refusal` case deliberately adds one nested
migration to the owned release copy after the earlier cases. The fixed worker
must reject this entry before Ecto's recursive migration discovery. Root requires
zero relations in the private database's public and shadow namespaces, original
BEAM/Repo/lease absence and retained running lifecycle/ownership records. No failed
stage is advanced, and the owned unit/cgroup must stop. The deliberate fixture
addition does not establish complete artifact or native application acceptance.

Before that final destructive fixture addition, `native-runtime-effects` and
`native-runtime-schema-refusal` now exercise the fixed actual product worker tree
and refusal before listeners. They use real maintenance first. The former checks
internal signed login, private-repository creation, HTTP Git push/readback, SSH Git
readback and session revocation before original ownership loss. The latter removes
one expected schema version and requires no product workers/listeners or repository
creation, original backend absence and retained running lifecycle responsibility.
See [native runtime effects](native-runtime-effects.md) for the exact internal
network scope. A separate `native-public-runtime` case adds actual protected
web/edge launch, CA/hostname-verified TLS, frontend identity and packaged assets,
owner cookie/login, HTTPS Git and production component cleanup after original
helper loss. See [native public runtime](native-public-runtime.md) for its current
artifact requirements and limits. The installed suite has twelve cases; the
nested-inventory fault remains last. Complete public activation and journey
acceptance remain unverified. `native-default-release` adds normal packaged boot,
five independent original owner/SQL/kernel/readiness observations and permanent
native failure before public component cleanup. The suite has thirteen cases;
the nested migration fault remains last.

`fixed_migration_and_bootstrap_effects_observed` and
`actual_nonempty_schema_refusal_verified` describe only these component outcomes.
`actual_nested_migration_entry_refusal_verified` describes the final refusal.
They do not establish complete lifecycle dispatch, interruption reconciliation,
native runtime startup, activation, reboot or replacement recovery. See
[maintenance effects](native-maintenance-effects.md) for the execution contract.

## What a passing run observes

Three independent installations exercise three different losses. Each has a
random installation UUID, ordinary Unix account, private database and role, root
seals, actual delegated systemd unit, and original BEAM/backend identities.

1. The ordinary service MainPID creates its delegated workload leaves and uses
   production durable-binding observation. Root independently checks allocated
   directories, configuration/key identities, executable hashes, host identity,
   and a fresh ordinary-role SQL identity before sealing the expected binding.
2. The manager calls the actual generation publisher. That publisher holds its
   real filesystem custody and PostgreSQL writer exclusion; all workload leaves
   must be empty. Its original generation records and receipts remain retained.
3. The built release loads a permanent fixture application. It calls the actual
   `NativeOwnershipSupervisor.start_native_link` and `NativeOwnershipStartup`.
   Clean compiled build identity, protected application configuration, original
   monitor, original database lease, protocol-3 claim, protected publication,
   attachment, and original-helper fence must all succeed without substitutions.
4. The witness observes at least five distinct post-attachment monitor updates.
   Root separately verifies the BEAM/helper/descendant Unix births and cgroup
   membership, the recorded PostgreSQL kernel birth, the precise SQL backend
   birth, and that backend's actual installation advisory lock.
5. Root injects exactly one failure from the table below. It never signals the
   BEAM. The permanent fixture application must terminate the original BEAM,
   and both the original SQL activity and original kernel backend must disappear.
   A zombie still counts as present.
6. A separate-session descendant deliberately survives the BEAM. Only after the
   owner/backend absence check does root authorize the **fixture manager** to
   write the captured native leaf's `cgroup.kill`. The native leaf must become
   empty while a sibling sentinel remains alive. Final unit shutdown removes
   the fixture's remaining processes.

| Case | Injected failure | Retained evidence |
| --- | --- | --- |
| `helper-loss` | Kill the captured monitor helper through a pidfd after checking its original birth, UID, ancestry and cgroup. | Original ownership record and marker keep their bytes and inode. |
| `marker-permission-loss` | Change the captured marker from `0600` to `0640`. | The same marker bytes and inode remain, including the intentionally invalid mode. |
| `original-backend-loss` | Terminate the SQL backend only when both its recorded PID and microsecond SQL birth match. | The original backend's distinct kernel birth must also become absent. |

Descendant cleanup is explicitly attributed to the fixture manager. This does
not verify the production controller's termination or successor reconciliation.
No deletion or empty marker directory is accepted as a replacement for proving
the old owner and backend absent.

## Same-controller successor case

A fourth independent installation retains one actual ordinary systemd MainPID,
protected Unix endpoint, original installation flock and production
`NativeOwnershipController`. It starts three separate packaged BEAMs in
`migrate`, `migrate`, then `runtime` mode. The first two represent migration and
bootstrap ownership boundaries; the fixture executes no business migration or
bootstrap and grants no lifecycle-stage completion.

For each owner, Root first observes the live reservation's exact SQL/kernel
backend and existing writer lock before authorizing that fixture process to
launch. The actual fixed handoff entry authenticates the controller and its
peer, assigns one BEAM birth, releases the captured exclusion, and publishes a
protocol-4 claim backed by that BEAM's new original lease. The witness requires
five distinct attached heartbeat updates. A repeated admission must reach the
actual endpoint and refuse while its completed assignment remains unchanged.

Root independently checks that the original exclusion backend is gone, the
new lease and process births match the retained record, and all claims share
one operation, controller, boot, generation and pointer. Original monitor or
backend loss terminates each BEAM. The fixture manager quiesces its surviving
descendants after Root proves owner/backend absence; Root observes the sibling
alive before authorizing its exact owned reaping. All leaves must then be empty
before the controller's next reservation can succeed.

The immutable ownership records remain at their original inodes. Each previous
marker is archived by the production transition store at the next claim's
`old-marker` path, preserving its bytes and inode. The final runtime marker
remains. No receipt substitutes for the live controller's reservation authority.
An unknown backend after interrupted assignment, controller restart, another
boot/generation and complete startup recovery are outside this case.

Only a passing current hosted receipt with this fourth case establishes these
observations. Its `same_boot_same_generation_successor_handoff_verified` flag
has this component scope. Full product `successor_reconciliation_verified` and
`complete_journey_acceptance` stay false.

## Entry contract

Run after the existing CI job has built a clean production release, pinned
PostgreSQL 18.4 prefix and running private cluster, Node 22.23.3, and Caddy 2.11.7.
The release's compiled clean candidate must match `git rev-parse HEAD`. The
fixture performs no downloads, package installation, cloud provisioning, or VM
creation. Required host tools include systemd 255, Python 3.12, Git, OpenSSL,
`ssh-keygen` and `patchelf`; systemd must actually be PID 1 with the real system
bus available.

The root entry requires these environment variables only:

| Variable | Requirement |
| --- | --- |
| `GITHUB_ACTIONS` | Exactly `true`. |
| `RUNNER_ENVIRONMENT` | Exactly `github-hosted`; self-hosted and local machines are refused. |
| `PGHOST` | Exactly `127.0.0.1`. |
| `PGPORT` | Port of the existing private PostgreSQL 18.4 cluster, between 1024 and 65535. |
| `PGUSER`, `PGPASSWORD` | Synthetic CI administrator credentials for that disposable cluster. They stay in the psql child environment. |

The existing cluster must be a native process in the runner's initial PID/time
namespace, running as a non-root Unix account. The fixture creates separate
least-privilege database owners; the application receives no administrator
credentials. No infrastructure or customer credentials are needed.

Example workflow invocation, after building the clean release:

```bash
sudo -n env \
  GITHUB_ACTIONS="$GITHUB_ACTIONS" RUNNER_ENVIRONMENT="$RUNNER_ENVIRONMENT" \
  PGHOST="$PGHOST" PGPORT="$PGPORT" PGUSER="$PGUSER" PGPASSWORD="$PGPASSWORD" \
  /usr/bin/python3.12 -B tools/ci/native-owned-proof.py \
  --workspace "$GITHUB_WORKSPACE" \
  --release "$GITHUB_WORKSPACE/apps/forge/_build/prod/rel/gitgood" \
  --postgres "$GITHUB_WORKSPACE/.gitgood/postgres-18.4" \
  --node "$(command -v node)" \
  --caddy "$GITGOOD_CADDY" \
  --candidate "$(git rev-parse HEAD)" \
  --output "$GITHUB_WORKSPACE/.gitgood/native-owned-proof"
```

The release, PostgreSQL prefix and Caddy input must resolve inside the checked-out
workspace. Node may come from the pinned Actions tool cache. Input inventories
reject escaping symlinks and special files before copying. The release and
runtimes are copied once into a fresh root-owned `/opt/gitgood-owned-proof/UUID`
tree, with single-link files and verified hashes. The protected production Python
import closure is copied unchanged to `/opt/gitgood/native/v2`; an existing
installation at that path is refused rather than overwritten.

GitHub's [runner image setup](https://github.com/actions/runner-images/blob/main/images/ubuntu/scripts/build/configure-system.sh)
makes `/opt` writable. After checking that this is a disposable hosted runner,
the fixture opens the literal root-owned `/opt` directory without following a
symlink and changes only that directory to `0755`. It checks the same original
device/inode before and after and records the mode change. It does not change
the ownership or permissions of existing children. Production checks still
require every ancestor of the installed private runtimes to be root-controlled.

PostgreSQL's source build embeds its workspace library prefix. The fixture uses
`patchelf` to relocate only the copied psql's RUNPATH to the root-owned copied
library directory. It records the original/relocated psql and copied libpq
hashes, and checks actual dynamic-loader resolution and `psql --version` under
each fresh ordinary account with the same scrubbed environment. A workspace or
system libpq fallback is refused. No `LD_LIBRARY_PATH` exception is added to
production observers.

Fixture source is split by responsibility:

| File | Responsibility |
| --- | --- |
| `tools/ci/native-owned-proof.py` | Root allocation, independent observation, bounded faults, redacted receipt and final owned-unit cleanup. |
| `tools/ci/native-owned-manager.py` | Actual ordinary systemd MainPID, production generation publication, fixture subprocess custody and descendant cleanup. |
| `tools/ci/native-successor-manager.py` | Actual ordinary controller MainPID, original flock and endpoint custody, real protocol-4 reservations, handoff serving and bounded fixture descendant cleanup. |
| `tools/ci/native-owned-worker.exs` | Permanent fixture OTP application around production startup/claim/fence, plus a witness, real descendant and fixed maintenance requests after Root observation. |
| `tools/ci/native-owned-test.py` | Local regressions for bounded copies, original-birth targeting, zombie refusal and failed cleanup exit status. |

## Bounds, receipts and failure handling

- Combined runtime copies are capped at 2 GiB, with a further 1 GiB free-space
  reserve, 30,000 entries per input tree and 256 MiB per regular file. No disk
  images, VM snapshots, repository copies, or source build directories are made.
- Each unit has two CPU cores worth of quota, 512 MiB memory and zero swap.
  BEAM scheduler counts and individual file sizes (64 MiB) are bounded; BEAM
  crash dumps and operating-system core dumps are disabled. The file limit
  includes memory-backed files: OTP 29.1.1 selects a
  [32 MiB JIT block](https://github.com/erlang/otp/blob/OTP-29.1.1/erts/emulator/beam/jit/beam_jit_main.cpp#L188-L205),
  which its [allocator initially doubles](https://github.com/erlang/otp/blob/OTP-29.1.1/erts/emulator/asmjit/core/jitallocator.cpp#L538-L560)
  before [sizing the Linux memfd](https://github.com/erlang/otp/blob/OTP-29.1.1/erts/emulator/asmjit/core/virtmem.cpp#L640-L647).
  The earlier 16 MiB fixture limit killed the original release with `SIGXFSZ`
  before any application code ran. A small hosted regression checks that failure
  and successful JIT startup under the finite 64 MiB limit. Production admission,
  heartbeat, SQL and ownership deadlines remain unchanged.
- Root handshakes, commands, attachment/loss observation and cleanup all have
  finite timeouts. The ordinary manager has a 300-second lifetime even if its
  outer observer disappears. Its bounded failure exit avoids a fixture retry
  over retained responsibility under the required `Restart=on-failure` policy.
- Root always attempts to stop every unit it started. A stop failure makes both
  the receipt and process exit fail. No unrelated service, database, process,
  or path is stopped or deleted. Allocations and retained records are left on
  the disposable runner until that runner is destroyed.
- Upload **only** `.gitgood/native-owned-proof/receipt.json`. The output directory
  is `0755` and the receipt is `0644` so the unprivileged artifact step can read
  it. The receipt contains component scope, exact candidate, installed module
  hashes, observed outcomes and fixed failure phase/type; it contains no SQL,
  private configuration, password, key material, raw process log or stack trace.
  On startup failure, the fixture can include at most 64 fixed startup events
  and the original process's numeric exit code. VM call tracing observes only
  allowlisted startup functions; its arguments, return values and exception
  reasons are never serialized. Only fixed entered/accepted/refused/exception
  tags and witness milestones survive the root reader's closed vocabulary.
  This diagnostic does not substitute for any guard or modify its deadline.
  Private diagnostics remain in each account's `0700` `/run/gitgood-owned-proof`
  directory. Never upload that directory or the `/var/lib` installation roots.

Run local fixture checks with:

```bash
python3 -B tools/ci/native-owned-test.py
```

Local tests cannot establish real systemd delegation, successful protected claim,
BEAM termination, or PostgreSQL kernel absence. Only a fresh hosted execution's
passing receipt establishes those specific observations. The receipt always
keeps `native_application_acceptance`, `complete_journey_acceptance`,
`reboot_verified`, and `successor_reconciliation_verified` false.

Executable local Elixir checks require the version pinned in `.tool-versions`.
An unsupported local installation is reported as skipped; the hosted job must
run these checks with the pinned version and fails if that runtime is absent or
wrong. No local package installation is needed for static checks.
