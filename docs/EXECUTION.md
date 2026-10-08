# Execution plan

## Immediate sequence

The [first 24-hour run plan](RUN-24H.md) time-boxes the environment, experiments, running foundation and private-repository slice. Its hours are allocations for an implementation run, not milestone delivery-date promises or completed tasks.

The [72-hour run plan](RUN-72H.md) includes that first day, then targets review/check/merge foundations, concurrency/restart proof and clean-target packaging, with an eight-hour final verification reserve. Completion remains criterion-based.

1. Follow [autonomous progression](../AUTONOMY.md). Owner/private visibility and delegated agent authority are recorded in D01. Use PRODUCT.md as the execution baseline; resolve remaining decisions with evidence while private development proceeds.
2. Resolve identity/data ownership and write the first permission scenarios.
3. Scaffold app/API and isolated Postgres with pinned runtimes.
4. Establish the real request boundary, local setup, CI, and evidence contracts.
5. Implement private repository create, HTTPS clone/push, and commit browsing for two users.
6. Repeat from a clean environment; then estimate review/merge work from observed effort.
7. Prove review, protected merge, and interruption recovery.
8. Complete scoped Git/Barkpark workflows.
9. Prove Cloud lifecycle and enter a bounded pilot.

No task below is automatically complete because its planning document or script exists. Assignments and work status belong in the future Barkpark ledger.

## Setup work packages

| ID | Deliverable | Depends on | Acceptance |
|---|---|---|---|
| S01 | Repository governance | D01 | Owner/private visibility and autonomous authority recorded; unresolved licensing does not block private development |
| S02 | Product and journey baseline | S01 | Agent evaluation records scope consistency, invariants, and J01/J02 criteria; no human sign-off |
| S03 | Development skeleton | Local planning may start before S01 | Runtime pins, isolated worktree convention, ignore/lock rules |
| S04 | API/Postgres | S03 | Clean migration, version identity, backend checks |
| S05 | Web/server boundary | S03 | Production build and secret isolation |
| S06 | Real browser/API request | S04/S05 | Success, structured failure, correlation |
| S07 | Local fixtures | S04/S05 | Isolated ports, stores, cleanup boundaries |
| S08 | CI/review | S06/S07 | Required checks demonstrated on remote proposed revisions |
| S09 | Tracking/evidence/SVG | S02/S08 | Real ledger and evidence connected; unknown states preserved |
| S10 | Identity | D02/S06 | Two users with enforced distinct access |
| S11 | Native Git transport | D04/S10 | Real client push/pull; denial and timeout cleanup |
| S12 | Browsing | S11 | Authorized access to pushed content |
| S13 | Barkpark capability | D03/S06 | One supported API with attribution and failure behavior |
| S14 | Reference environment | S07 | Pinned Forgejo plus repeatable synthetic repository |
| S15 | Clean acceptance | S08/S09/S12/S16/S17 | Fresh environment reproduces private-repository slice |
| S16 | Maintenance | S08/S09 | Named owner; source integration, stale-input and refresh-failure handling demonstrated |
| S17 | Changelog | S08/S09 | Reviewed fragments, digest/release selection, README, publication/retry behavior |

## Roles

Agents take engineering delivery, verification, and Cloud operations responsibilities as work becomes ready. Record the acting agent and evidence for each gate. Missing human staffing is not a blocker; progress follows AUTONOMY.md and QUALITY.md. User updates provide oversight without creating an approval queue.

## Reporting

At meaningful changes and milestone boundaries, report what is implemented, what is verified, what is shipped, blockers, evidence age, and the next acceptance condition. Re-estimate after M2 and M3. Do not manufacture a calendar schedule before those experiments.

## Completion

Use milestone and journey definitions, not task counts. A release needs current evidence, compatible artifacts, operational procedures, and verified pilot workflows. Agents evaluate these criteria and continue without human sign-off.
