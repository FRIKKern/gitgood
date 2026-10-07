# Contributing and maintaining Gitgood

## Work

Use a worktree per scoped change; keep the shared main checkout on main. Branches use `codex/` by default. One primary journey per implementation PR keeps acceptance reviewable. Follow docs/EXECUTION.md.

Follow [AUTONOMY.md](AUTONOMY.md). Agent verification satisfies project review requirements; do not add human approval or acceptance requirements. After current checks and the relevant evidence pass, agents merge and take the next ready task. Product features that support repository review policies still enforce the configured users' rules.

Live assignments and blockers belong in the Barkpark ledger once configured. The execution plan is dependency guidance, not a competing live checklist.

A PR describes behavior, relevant journey/decision, verification, compatibility, and documentation impact. Keep intended behavior and implementation in agreement; investigate disagreements rather than automatically changing the spec.

## Commands

- `npm run generate`: regenerate journey index, roadmap, SVG, and changelog views.
- `npm run check`: validate links/IDs/evidence, generated drift, and reporting behavior.
- `npm run status`: print progress and source freshness.
- `npm run release:check`: require release-candidate evidence; fails before implementation.

Generated outputs must come from the checked-in canonical inputs. Never hand-edit counts or generated sections. No dependencies are required by these planning scripts.

## Maintenance cadence

| Trigger | Action |
|---|---|
| Every PR | Update affected specs; validate IDs, links, evidence references, and changelog classification. |
| Relevant merge or evidence/release change | Generate reviewed derived files and publish through protected-branch-compatible PRs. |
| Daily after integration is enabled | Reconcile missed source events and inspect freshness. Initial maximum age: 24 hours. |
| Weekly | Review dependencies, idle work, merged branches, worktrees, old decisions, and evidence retention. |
| Milestone/release | Reconcile required journeys, actual artifacts, current evidence, runbooks, and release notes. |

The maintenance workflow is opt-in through `GITGOOD_MAINTENANCE_ENABLED`. Agents enable it once ledger/evidence integrations and a responsible agent execution path are configured and verified; no human enablement approval is needed. Local CI cannot claim remote branch protection is enabled.

Record the maintenance agent and retry/fallback execution path in the ledger. Failed maintenance creates one deduplicated actionable record; repeated unchanged failures should not create spam. That integration is setup task S16, not implemented by this planning skeleton.

## Safe hygiene

Delete only remote branches proven merged under the actual merge policy. Flag unmerged work idle more than seven days; do not auto-close or delete it. Inspect worktree ownership and uncommitted changes before cleanup. Preserve recoverable work and never reset a shared checkout as housekeeping.

Review dependency upgrades with compatibility checks. Retain provenance. Archive duplicate documents after repairing incoming links; retain decision history and release evidence. Do not purge artifacts still needed to prove a supported release or restore it.

## Generated publication

Deterministic inputs produce identical output. Do not create timestamp-only commits on every reconciliation. Preserve last-known values and observation timestamps on fetch failure; never replace unknown values with zero.

Use a constrained bot PR with checks that run on the proposed revision. Demonstrate event behavior and prevent commit loops before enabling unattended publication. Do not weaken protection for a bot.

A static SVG cannot change if its workflow stops. Display snapshot/freshness context and inspect successful publication separately after integration. No system can guarantee detection when its only monitoring provider is also down.

## Changelog

Follow changelog/ROUTINE.md. Weekly summaries are development updates; release notes describe actual published artifacts.
