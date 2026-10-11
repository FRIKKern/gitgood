# Delivery roadmap

The route from a private repository to a complete, recoverable forge. Each milestone describes what you should see, where it appears, and what must pass before we advance.

[Full Gantt](images/roadmap.svg) · [Progress snapshot](STATUS.md) · [What to build next](EXECUTION.md) · [Documentation guide](README.md)

## How to read this plan

Milestones follow dependency order. Their widths in the Gantt do not represent duration, and its bars show planned work rather than completion. There are no calendar promises in this view; re-estimate timing after M2 and M3.

- **M2 — First usable repository:** Gitgood browser · terminal Git client.
- **M4 — Usable private-team forge:** Gitgood pilot installation.
- **M7 — Complete managed release:** Private release artifacts · Cloud · pilot.

## Milestones

### M0 · Scope and ownership

**Where:** GitHub · specifications and decisions

Confirm private-team scope, ownership, identity boundary, and open experiments.

**Ready when:** Recorded bounded execution baseline; delegated agent authority; J01/J02 scenarios and data ownership.

### M1 · Repository ready

**Where:** Local browser · Elixir API · Postgres

Scaffold app/API, isolated Postgres, runtimes, real request contract, local setup, CI.

**Ready when:** Fresh checkout runs; browser reaches API; secrets stay server-side; isolated migrations and tests pass.

### M2 · Private repository slice

**Where:** Gitgood browser · terminal Git client

Complete J01/J02 and minimal J04 with real Git clients and two identities.

**Ready when:** Authorized create/clone/push/browse; unauthorized reads/writes denied; timeouts and cleanup verified.

### M3 · Review and merge foundation

**Where:** Gitgood pull requests · checks · audit

Complete review, check reporting, protected merge, and interruption recovery; start packaging experiment.

**Ready when:** Concurrent and stale-state behavior proven; exact result reconciles after service failure.

### M4 · Usable private forge

**Where:** Gitgood pilot installation

Add SSH, import, fuller browsing, releases, and permission-aware activity.

**Ready when:** Pilot daily workflow works; compatibility limitations and measured performance targets are documented.

### M5 · Connected workspace

**Where:** Gitgood + supported Barkpark APIs

Adopt verified Barkpark capabilities and revision-specific evidence.

**Ready when:** Links preserve both owners' permissions; current/stale verification is clear; scoped agent APIs follow ordinary rules.

### M6 · Managed lifecycle

**Where:** Barkpark Cloud · deployed Gitgood host

Finish Cloud launch, upgrade, restore, export/archive; recovery research starts earlier.

**Ready when:** Clean install, unhealthy-release rejection, real replacement-host restore, supported export and removal.

### M7 · First complete release

**Where:** Private release artifacts · Cloud · pilot

Complete bounded pilot and reconcile all accepted scope, artifact identity, runbooks, and evidence.

**Ready when:** Every required journey has current release-candidate evidence; no blocking correctness gap; agent evaluations pass all evidence gates without human sign-off.

## Work that spans milestones

Research can start early when capacity allows. Its experiment does not complete the later product requirement; full installation and recovery acceptance remains at M6.

| Work | Stages | Where |
|---|---|---|
| Barkpark contract research | M1–M2 | Isolated API fixtures · decision D03 |
| Packaging + restore research | M2–M3 | Disposable hosts · Cloud contracts |
| Quality + repo maintenance | M0–M7 | CI · PRs · evidence · README · changelog |

- **Barkpark contract research:** Proposed early research; verify supported APIs and permissions before adoption at M5. Overlap requires available execution capacity.
- **Packaging + restore research:** Proposed early experiments for D05/D06/D07; managed lifecycle acceptance still belongs to M6. Overlap requires available execution capacity.
- **Quality + repo maintenance:** Checks and upkeep at every stage. Scoped source collectors are configured; complete journey verification and unattended scheduling remain unfinished.

## What counts as complete

Each milestone must meet its own exit conditions. M0, M1 and M7 have requirements beyond journey counts. Code browsing (J04) starts at M2 and reaches its full scope at M4.

Use the [journey specifications](../JOURNEYS.md) and [quality rules](../QUALITY.md) to assess completion. The [progress snapshot](STATUS.md) reports observed evidence separately from this plan.

Generated from [the milestone catalog](milestones.json); edit that source to change this roadmap.
