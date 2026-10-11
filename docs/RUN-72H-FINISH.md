# Native foundation run — 8 October 2026

> **Historical evidence — 8 October 2026.** Results, remaining scope, source-configuration statements and estimates below describe the candidates from this run. Later work may supersede those limitations. Use the [current progress snapshot](STATUS.md), [implementation index](implementation/README.md) and [live delivery ledger](https://guerrilla.barkpark.cloud/w/gitgood/p/delivery/studio) for present context; do not apply these receipts to a newer candidate.

The bounded [72-hour plan](RUN-72H.md), including the first-day slice, produced the private create/clone/push/browse and review/check/protected-merge foundation, deterministic concurrency/recovery proof and a copied production-artifact experiment. Delivery finished ahead of the allocation; elapsed time is not an acceptance criterion. This is an implementation/evidence record, not a product release or replacement live task board.

## Delivered and integrated

| Change | Integration |
|---|---|
| Phoenix/Postgres identity, membership, private repository creation and React/TanStack interface | [PR 7](https://github.com/FRIKKern/gitgood/pull/7), merge 233b324 |
| Bounded native HTTPS Git, trusted hooks, scoped credentials and durable pushes | [PR 8](https://github.com/FRIKKern/gitgood/pull/8), merge 8189792 |
| Commit-pinned trees, text/binary/large-file states, branches/history and bounded diffs | [PR 9](https://github.com/FRIKKern/gitgood/pull/9), merge 9ffa8b9 |
| Same-repository pull requests, exact-line comments/reviews, scoped check providers, policy and atomic fast-forward merge/reconciliation | [PR 10](https://github.com/FRIKKern/gitgood/pull/10), merge 66621fe |
| Copied production releases, matched clean build identity, migration/bootstrap, readiness and persistent restart proof | [PR 11](https://github.com/FRIKKern/gitgood/pull/11), merge 0419f6facab8a23425a9cdf4a623257f36c1f824 |

Native Elixir owns authorization, review/check/merge policy and recovery. Standard Git owns objects and refs. PostgreSQL owns metadata, credentials, policy and durable operation responsibility. The React/TypeScript interface follows Barkpark Studio's separation of UI and authoritative APIs. Forgejo is a reference, not a production backend.

## Candidate and environment

The local clean artifact candidate is **0c21ae7a6b97119977d94ac2d7ecf3829dc3a8d0**. The passing PR 11 Linux CI checkout is **eef8b00367a667915e1e3338d503cd0f7addf4c7**. Production identity records every journey SHA-256, lockfile hashes, toolchain hash and required migration versions. CI checks its own actual checkout; the manifest and production receipt identify that revision explicitly. Integration creates another commit, whose main CI produces a new identity. Do not relabel an old receipt as proof of a new revision.

Pinned runtimes: Elixir 1.20.4 / OTP 29.1.1, Node 22.23.3 and PostgreSQL 18.4. Local Git is 2.53.0.windows.3; Python is 3.12.14. Dependencies include Phoenix 1.8.15, Ecto 3.14.2, Ecto SQL 3.14.0, Postgrex 0.22.4, React 19.3.0 and srvx 1.0.5. Lockfiles are authoritative for the complete graph. Linux CI used Git 2.55.0 / Python 3.12.3 and built native Linux artifacts.

The isolated Windows runtime avoids changing the shared Elixir 1.11/OTP 21 installation. PostgreSQL runs only on loopback port 55432, with separate development, sandbox-test, recovery and unique production-fixture databases. Local trust authentication is confined to this disposable loopback cluster; deployed databases require dedicated credentials and restricted access. Docker was unavailable locally; GitHub CI uses its own PostgreSQL service.

Actual synthetic actors: owner (team owner), reviewer (team writer), reader (team read-only), outsider (owner of another team). Fixture login is owner / synthetic-password. These accounts are never production seeds for an exposed service.

## Commands and retained proof

Results: **21 backend checks**, **16 reporting checks**, **9 real-database recovery scenarios**, **3 whole-VM crash/reconciliation boundaries**, **2 development browser journeys**, and **2 browser journeys against copied production artifacts**. Linux CI passed the complete pipeline in 3 minutes 33 seconds. The production harness additionally verifies persistent sessions/repository IDs/exact refs after process restart, readiness failure for missing storage and readiness failure for mismatched component identity. Remote results and exact checkout identity are retained in [the native forge CI run](https://github.com/FRIKKern/gitgood/actions/runs/37757511256) and its private artifact.

| Verification | Command / evidence |
|---|---|
| Backend authorization, storage, process boundaries, browsing, collaboration and readiness | apps/forge: `mix precommit`; `mix format --check-formatted` |
| Web production build and strict types | apps/web: `npm ci && npm run check` |
| Reporting/spec/link/changelog/SVG integrity | root: `npm run generate && npm run check` |
| Real HTTPS browser/Git workflow and keyboard/focus checks | apps/web: `npx playwright test`; screenshots, results.json and git-receipt.json under ignored test-results |
| Real PostgreSQL merge recovery | [reproduction](implementation/collaboration.md); verification/merge_recovery.exs; merge-recovery.json |
| Complete VM termination | verification/vm_crash.exs at before_ref, after_ref and before_outcome; exit 70, then a new VM with reconcile; vm-crash-POINT.json |
| Installed production artifact proof | [build/start instructions](deployment/production.md); `npm run verify:production`; production-receipt.json and browser results under test-results-production |
| Candidate/spec/runtime association | scripts/verification-manifest.mjs; scripts/stamp-build.mjs; verification-manifest.json and both build identities |

Private CI artifacts are named native-forge-verification-CHECKOUT_SHA and retained for seven days. They include sanitized results/screenshots and identity manifests, not secrets, environment dumps, installation logs or fixture TLS keys. Download evidence needed for longer retention before expiry. The scripts and assertions remain reproducible after artifacts expire.

Previous integration checkpoints: [PR 7 CI](https://github.com/FRIKKern/gitgood/actions/runs/37745161144), [PR 8 CI](https://github.com/FRIKKern/gitgood/actions/runs/37750731213), [PR 9 CI](https://github.com/FRIKKern/gitgood/actions/runs/37751605785), [PR 10 CI](https://github.com/FRIKKern/gitgood/actions/runs/37754845501). These establish their own candidates; the final pipeline repeats all relevant checks.

## Criterion-level observations

These observations apply to the bounded implementation and fixture environment above. A receipt must still match the candidate/spec and current source freshness before formal release acceptance.

| Criteria | Observed result and proof |
|---|---|
| J01-A | Browser creation/reload and backend ownership/bare-store assertions preserve canonical repository and actor. |
| J01-B | Outsider list/direct-content denial, duplicate-name conflict, expired/revoked sessions and membership removal. Search/events are not implemented; no future endpoint is implicitly accepted. |
| J01-C | Stable creation key resolves to the original operation; unavailable-store responsibility remains queryable and reconciles without another repository. Backend foundation tests. |
| J02-A | A real Git client clones an empty repository over trusted HTTPS, commits/pushes/fetches and checks actual refs. Browser/Git receipt. |
| J02-B | Reader write, wrong username, revoked token and subsequent raw main push are denied; protected main stays unchanged. Tokens use scoped environment headers, never remote URLs or arguments. |
| J02-C | Interrupted real upload leaves refs unchanged, retry succeeds, strict fsck passes; 32 MiB limit and subprocess EOF/output/timeout/concurrency/memory/cancellation/descendant cleanup checks pass. |
| J04-A | Commit URLs navigate branches/tree/files/history/diff and survive reload. Backend and browser checks. |
| J04-B | Literal shell-like names, untrusted script text, binary/large output, deleted refs and unreachable objects have explicit safe outcomes. Backend fixtures plus browser rendering. |
| J04-C | A real branch push/refresh preserves the viewed SHA until explicit branch selection. Retry retains URL context in the interface; automated browser coverage of every failed-load interaction remains an M4 task. This run proves minimal browsing, not full M4. |
| J06-A | Two browser identities open/review an actual pushed change; exact-line comment retains its source/target SHA, excerpt and original context after a push. |
| J06-B | Reader/self approval and stale-revision review denial; source changes invalidate previous approval/check evidence. Both source and target bind reviews; target/source interference is tested by recovery fixtures. |
| J06-C | Drop a response after the server persisted the comment, reload the preserved draft/key and retry; exactly one comment exists. Keyboard focus/submission is exercised. Draft persistence is session-scoped to actor/repository/PR/both SHAs. |
| J07-A | Repository/provider/scoped credential/SHA/check/attempt/sequence are durable and attributable. API tests and actual provider-to-merge browser workflow. |
| J07-B | Wrong credential kind/revoked epoch denial, current-SHA policy evaluation, immutable final state and defined pending/running/final ordering. |
| J07-C | Duplicate acknowledgements/out-of-order older sequence converge; conflicting same-sequence payload is refused; new attempt and provider rotation rules preserve attribution. API responses are bounded and retry semantics documented. |
| J08-A | Actor/current membership/policy/refs/independent approvals/required checks authorize one atomic fast-forward strategy. Git main equals the reviewed SHA; operation and PR outcome agree. |
| J08-B | Changed policy, failed/latest-attempt checks, revoked author/reviewer, divergent history and competing merges are refused. Source/target CAS interference cannot overwrite another writer. No override is supported. |
| J08-C | Stale expectations return explicit errors; an operation is marked applied only from actual Git transaction evidence. Inconsistent target evidence is uncertain and blocks further writes. |
| J09-A | Responsibility commits before Git; source verification, target update and hidden operation marker are one Git transaction. Durable operation state remains queryable. |
| J09-B | Terminate worker/application and the whole VM before refs, after refs and before DB outcome. Real database/refs/marker assertions, not job completion flags. |
| J09-C | A fresh application/VM reconciles actual refs/markers; completed retry returns the same operation, failed retry stays failed and concurrent attempts apply once. An uncertain store blocks instead of reporting success or spinning indefinitely. |

## Demonstration and clean start

Development web: **http://localhost:47840**. Forge API: **http://127.0.0.1:47841**. Canonical clone shape: **http://localhost:47841/git/team/NAME.git** in loopback development. The production fixture uses an ephemeral HTTPS origin and the actual returned HTTPS clone URL; it verifies the exact persisted main SHA after restart. No public Gitgood URL exists.

Start from a clean checkout using [forge setup](../apps/forge/README.md) and [web setup](../apps/web/README.md). Create the isolated database, install locked dependencies, migrate, seed only development fixtures, start the forge and then web. On Windows dot-source scripts/windows-runtime.ps1; provide Git/Python/OpenSSL executable paths and GITGOOD_BROWSER_CHANNEL=msedge when needed. Root tests require no application services.

For copied production artifacts follow [production.md](deployment/production.md). That experiment starts/stops its own process trees and keeps its unique database/stores for diagnosis. A process restart on the same machine is distinct from restoration onto a replacement host.

## Actual scope and remaining gates

M0 has the bounded baseline and delegated authority. M1's running foundation and M2's private HTTPS/minimal-browse slice have concrete development evidence. M3's J06–J09 foundation has review/check/policy/concurrency/restart evidence, plus experimental packaging. M4–M7 remain future scope. The Barkpark execution/evidence/release sources are still **unconfigured**; the generated SVG deliberately does not turn these engineering observations into synthetic live verification or release state.

Important current limits: local bootstrap identity; one deployment version against shared stores; HTTPS only; SHA-1 Git repositories; protected main and fast-forward-only merges; bounded previews; no force/delete/tag/LFS transport; no SSH/imports/releases/assets/search/activity product scope; no supported Cloud adapter, managed installation, power-loss proof or replacement-host restore.

[D06](decisions/D06.md) records a read-only Barkpark Cloud audit at 68412eff4a0eb5a22cdc8e755e437c8dc66ceed3. Its existing Node runtime expects Next.js standalone artifacts and does not establish this paired TanStack/Elixir workload. No Barkpark deployment was modified or invented. Supported workspace/evidence API adoption remains D03/M5 work.

Correctness discoveries fixed during the run include real stdin EOF/child cleanup, migration version ordering, provider/check-name route collisions, provider rotation epochs, reconciler filtering of operation kinds, archived merged-review diff snapshots, missing proxy PUT and unbounded proxy body buffering. Initial failures are retained as development findings rather than relabeled as passing evidence.

## Next-run estimates

Observed feedback cycles are about one minute for local browser verification, roughly one minute for backend verification, and several minutes for a cold production build/full remote pipeline. Scope and security boundaries dominate work estimates; the 72-hour allocation is not evidence that later milestones can be completed on the same clock.

| Next work | Planning estimate and acceptance |
|---|---|
| M4 SSH credential/transport and revocation | 1–2 focused implementation runs; real SSH client, current authorization, resource cleanup and revoked-key refusal before acceptance. |
| M4 bounded import, fuller browsing/retries, release assets and permission-aware activity | 2–4 focused runs; separate import/resource/archive safety, asset isolation and interaction evidence. Re-estimate after import prototype. |
| D03/M5 supported Barkpark workspace/evidence integration | 1 research run plus 1–2 integration runs if contracts exist; permission/scoping/version fixtures and one real authoritative ledger before enabling live status. |
| D07 consistent backup/replacement-host restore | 1–2 experiments before operational implementation; pause writes, restore PostgreSQL and Git elsewhere, verify actors/permissions/clone/push and recovery point. |
| M6 Cloud adapter/upgrade/rollback | 2–4 runs after supported workload contract and restore proof; actual clean host, TLS, artifact provenance, persistent stores and unhealthy-release rejection. |
| M7 complete release | Bound a private-team pilot after M4–M6; estimate from measured workload/recovery evidence and remaining criteria. No release-date promise yet. |

A focused run means an explicit implementation-and-verification workstream, not a fixed calendar day. Unattended scheduling, a persistent runner and new parallel capacity are not implied by this completed interactive execution.
