# Execution plan

## Immediate sequence

1. Remote owner and private visibility are recorded in D01. Resolve the project license and first-release scope; private repository work can proceed.
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
| S01 | Repository governance | D01 | Owner/private visibility recorded; license and scope remain open before public publication or release baseline acceptance |
| S02 | Product and journey baseline | S01 | Owners accept scope, invariants, J01/J02 |
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

Frikk owns product decisions. Assign engineering delivery, independent quality review, and Cloud operations owners before accepting their gates. Do not imply staffing or approval that has not been provided.

## Reporting

At meaningful changes and milestone boundaries, report what is implemented, what is verified, what is shipped, blockers, evidence age, and the next acceptance condition. Re-estimate after M2 and M3. Do not manufacture a calendar schedule before those experiments.

## Completion

Use milestone and journey definitions, not task counts. A release needs current evidence, compatible artifacts, operational procedures, and pilot acceptance.
