# Contributing to Gitgood

[Documentation](docs/README.md) · [Development setup](docs/DEVELOPMENT.md) · [Code map](docs/CODEBASE.md)

Work in an isolated worktree and keep the shared main checkout on its branch. Use `codex/` for new branches. A change should have a clear outcome, a relevant journey or contract, and verification that demonstrates the result.

Agents choose work, verify it, and merge passing revisions under [AUTONOMY.md](AUTONOMY.md). Product review policies still enforce the configured users' rules. Live assignments and blockers belong in the [delivery ledger](docs/TRACKING.md).

## Make a change easy to review

1. Read the relevant [scope](PRODUCT.md), [journey](JOURNEYS.md), and [quality criteria](QUALITY.md).
2. Describe the behavior that will change and the evidence it needs.
3. Implement and run the affected checks from [the development guide](docs/DEVELOPMENT.md). Preserve failed results and relevant recovery materials.
4. Update the user-facing explanation, affected specifications, and [changelog fragment](changelog/ROUTINE.md).
5. Open a PR explaining the result, verification, compatibility, and remaining limits. Pass the required checks on the proposed revision; then reassess the integrated result.

Passing a planning check, closing a task, or merging a PR does not establish journey acceptance. Never change a requirement just to hide a failure.

## Keep the reading path clear

The README is the front door. Keep it short: product, maturity, navigation, and a compact generated news summary. Put setup in the development guide, code responsibilities in the code map, and detailed engineering evidence in implementation references.

When adding a document, give it a descriptive title and link it from its directory index. `npm run check` requires every direct guide, implementation reference, and decision record to appear in its index. Explain unfamiliar terms before using them. Keep old run reports visibly historical, and keep existing paths stable when reorganizing navigation.

State limitations next to the claim they qualify. Use ordinary language for the outcome before naming internal processes or proof artifacts. Avoid copying live task counts, blockers, or acceptance status into multiple hand-maintained pages.

Keep the [visual web tour](docs/WEB-TOUR.md) aligned with the interface. After frontend or capture-fixture changes, run `npm run tour` in `apps/web`, inspect the screenshots and recordings, and commit their manifest together. Root checks detect stale source hashes and missing or altered media. Use synthetic data and label it; a visual tour is not backend verification.

## Edit the source, then generate

| Generated view | Edit this source |
|---|---|
| [Journey index](JOURNEYS.md) | [Journey catalog](docs/journeys/catalog.json); each linked spec owns its criteria |
| [Roadmap](docs/ROADMAP.md) and full Gantt | [Milestone catalog](docs/milestones.json) and its renderer |
| Compact README illustration | [Overview renderer](scripts/overview-svg.mjs) |
| [Progress snapshot](docs/STATUS.md) and journey evidence map | Authenticated source refresh into [status.json](evidence/status.json); see [tracking](docs/TRACKING.md) |
| [Changelog](CHANGELOG.md) and README news | Reviewed [fragments](changelog/fragments) and [release manifest](changelog/releases.json) |

From the root, with Node 22 and the OpenSSL CLI on `PATH` (used by the reporting tests' local TLS fixture):

```sh
npm run generate
npm run check
npm run status
```

These reporting scripts need no npm dependencies. Generated files are checked in and checked for drift. Never hand-edit a generated count or change an observation timestamp to make old evidence look current. A failed source refresh retains last-known values and their original time. See [the tracking contract](docs/TRACKING.md) for authenticated refresh commands.

## Maintain the repository

| When | Action |
|---|---|
| Every PR | Check explanations, navigation, contracts, changelog classification, and relevant tests. |
| Meaningful source or evidence change | Refresh and publish derived views through a checked PR. Skip timestamp-only or empty updates. |
| Daily, once unattended maintenance is established | Reconcile missed events and investigate stale sources; the initial age limit is 24 hours. |
| Weekly | Review dependencies, idle work, obsolete guidance, worktree ownership, and evidence retention. |
| Milestone or release | Reconcile all required journeys, immutable artifacts, operations procedures, and release notes. |

Unattended collection and publication are not established by a workflow file. Keep `GITGOOD_MAINTENANCE_ENABLED` disabled until source integration, actual execution, retry behavior, and deduplicated failure reporting are verified. An inaccessible monitoring provider cannot prove that publication is healthy.

## Preserve work and recovery

Delete remote branches only after proving they merged under the actual merge policy. Flag unmerged work idle more than seven days; do not automatically close or delete it. Inspect ownership and uncommitted changes before worktree cleanup. Preserve required release evidence and restore materials.

Repair incoming links before archiving duplicate documents. Retain decision history, failed experiments, and supported-release provenance. Review dependency changes against the supported runtime and compatibility profile. Keep secrets and private artifacts outside tracked source and ordinary logs.
