# Delivery sequence

[Documentation](README.md) · [Progress snapshot](STATUS.md) · [Roadmap](ROADMAP.md)

This page explains the route to a complete first release. Live assignments, blockers, and task state belong in the [private delivery ledger](https://guerrilla.barkpark.cloud/w/gitgood/p/delivery/studio). Use the [progress snapshot](STATUS.md) to inspect its last recorded assessment; this sequence is not a second task board.

## What we are building on

The repository contains the local forge, web interface, Git transports, collaboration workflows, and deployment/recovery components. Their [implementation references](implementation/README.md) explain what each component does and how it has been exercised. The presence of code or a passing component check does not establish a complete installation or an accepted user journey.

`main` is the integrated baseline. Read an open PR as proposed work until it merges and its required checks pass. A result recorded for another candidate must be reassessed before it can support the current one.

## The remaining delivery path

| Step | Outcome a person should be able to observe | What proves it |
|---|---|---|
| Complete native installation and recovery | Start a clean host, run the packaged forge, resume interrupted work, and restore onto a replacement host. | Real installed services, interruption tests, artifact identity, and full lifecycle evidence. See [native lifecycle](implementation/native-initial-lifecycle.md) and [operations](operations/README.md). |
| Close the whole product workflows | A team creates a repository, pushes code, reviews and merges a change, connects its work, and publishes a release. | Every criterion in the [required journeys](../JOURNEYS.md), including permission denial and failure paths, against the candidate. |
| Finish evidence and release reporting | Readers can distinguish current, failed, missing, and outdated proof, and see which artifact was released. | Complete evidence attachment/access/reassessment and publication-source integration. See [tracking limits](TRACKING.md). |
| Connect Barkpark Cloud | Install and operate Gitgood through a supported Cloud contract with independently owned resources. | Clean deployment, upgrade refusal and recovery, coordinated backup, export, and removal through the [Cloud boundary](../deploy/README.md). |
| Run the bounded pilot and release | A small private team can do its daily work and recover its data using documented procedures. | The [pilot workload](implementation/pilot-workload.md), all required journey evidence, compatible immutable artifacts, and [release criteria](../QUALITY.md#release-gate). |

These are connected outcomes, not five new milestones. [M0–M7](ROADMAP.md) remain the canonical milestone order. Independent implementation and experiments may overlap; acceptance still follows each milestone's dependencies and exit criteria. No elapsed-hour estimate establishes completion.

## How work progresses

1. Choose a ready outcome from the ledger and identify the affected journey.
2. Implement it in an isolated worktree; update the relevant contract and human explanation.
3. Verify normal use, permission boundaries, and relevant interruption/recovery behavior.
4. Record the candidate, result, limitations, and supporting evidence; pass the required checks on the proposed revision.
5. Merge, reassess the integrated result, and advance only the criteria that the evidence establishes.

Agents carry this loop forward under [AUTONOMY.md](../AUTONOMY.md), without a human acceptance queue. Reports should say what changed for a user, what is proven, what remains blocked, and the next observable result.

## Earlier planning records

The [24-hour plan](RUN-24H.md), [72-hour plan](RUN-72H.md), and [foundation run report](RUN-72H-FINISH.md) preserve the original run's assumptions and results. Their elapsed-hour allocations and then-current limitations are historical; use the ledger and current specifications to direct new work.

## Original setup work packages

These baseline IDs are retained for the reporting, maintenance, and changelog contracts that reference them. They define acceptance conditions; they are not a live completion checklist.

<details>
<summary>Show S01–S17 foundation criteria</summary>

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

</details>
