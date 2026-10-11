# Native ownership on a disposable hosted runner

This fixture answers a specific unfinished question: can the packaged native
ownership components attach to a real systemd service and PostgreSQL backend,
then stop the original BEAM when that ownership is lost? It replaces large local
VM experiments with a bounded job on a fresh GitHub-hosted Ubuntu 24.04 runner.

**This is a publication-only component proof.** A passing receipt does not mean
the native product can be enrolled, upgraded, activated, restarted, or deployed.
It starts a small permanent fixture application from the production release;
the product's `Gitgood.Application` native-startup refusal stays in place. There
are no forge HTTP, SSH, web, or edge listeners. The private Node and Caddy binaries
are checked as part of the durable binding, rather than started as services.

The fixture requires an absent lifecycle worker policy and lifecycle history.
It never removes a policy, fabricates successful lifecycle stages, deletes an
ownership marker, or admits a replacement owner. Integrating real lifecycle
stages and reconciling retained predecessors remain separate work.

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
| `tools/ci/native-owned-worker.exs` | Permanent fixture OTP application around actual production startup/claim/fence, plus a read-only witness and real descendant. |
| `tools/ci/native-owned-test.py` | Local regressions for bounded copies, original-birth targeting, zombie refusal and failed cleanup exit status. |

## Bounds, receipts and failure handling

- Combined runtime copies are capped at 2 GiB, with a further 1 GiB free-space
  reserve, 30,000 entries per input tree and 256 MiB per regular file. No disk
  images, VM snapshots, repository copies, or source build directories are made.
- Each unit has two CPU cores worth of quota, 512 MiB memory and zero swap.
  BEAM scheduler counts and individual file sizes (16 MiB) are bounded; BEAM
  crash dumps are disabled. Production admission, heartbeat, SQL and ownership
  deadlines remain unchanged.
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
