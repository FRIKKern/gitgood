# Delivery roadmap

Generated from docs/milestones.json. The [Gantt](images/roadmap.svg) shows milestone order and delivery surfaces; the [journey evidence map](images/journey-evidence.svg) shows detailed implementation, verification, and release states.

Equal columns do not imply equal durations. Gantt bars show planned delivery gates, not completion or a calendar forecast. The milestone catalog is ordered by dependencies.

| Milestone | Where it appears | Work | Exit evidence |
|---|---|---|---|
| M0 Scope and ownership | GitHub · specifications and decisions | Confirm private-team scope, ownership, identity boundary, and open experiments. | Recorded bounded execution baseline; delegated agent authority; J01/J02 scenarios and data ownership. |
| M1 Repository ready | Local browser · Elixir API · Postgres | Scaffold app/API, isolated Postgres, runtimes, real request contract, local setup, CI. | Fresh checkout runs; browser reaches API; secrets stay server-side; isolated migrations and tests pass. |
| M2 Private repository slice | Gitgood browser · terminal Git client | Complete J01/J02 and minimal J04 with real Git clients and two identities. | Authorized create/clone/push/browse; unauthorized reads/writes denied; timeouts and cleanup verified. |
| M3 Review and merge foundation | Gitgood pull requests · checks · audit | Complete review, check reporting, protected merge, and interruption recovery; start packaging experiment. | Concurrent and stale-state behavior proven; exact result reconciles after service failure. |
| M4 Usable private forge | Gitgood pilot installation | Add SSH, import, fuller browsing, releases, and permission-aware activity. | Pilot daily workflow works; compatibility limitations and measured performance targets are documented. |
| M5 Connected workspace | Gitgood + supported Barkpark APIs | Adopt verified Barkpark capabilities and revision-specific evidence. | Links preserve both owners' permissions; current/stale verification is clear; scoped agent APIs follow ordinary rules. |
| M6 Managed lifecycle | Barkpark Cloud · deployed Gitgood host | Finish Cloud launch, upgrade, restore, export/archive; recovery research starts earlier. | Clean install, unhealthy-release rejection, real replacement-host restore, supported export and removal. |
| M7 First complete release | Private release artifacts · Cloud · pilot | Complete bounded pilot and reconcile all accepted scope, artifact identity, runbooks, and evidence. | Every required journey has current release-candidate evidence; no blocking correctness gap; agent evaluations pass all evidence gates without human sign-off. |

## Supporting work

Research spans are proposed early experiments and require execution capacity for overlap. Full lifecycle acceptance remains at M6.

| Work | Stages, inclusive | Where | Conditions |
|---|---|---|---|
| Barkpark contract research | M1–M2 | Isolated API fixtures · decision D03 | Proposed early research; verify supported APIs and permissions before adoption at M5. Overlap requires available execution capacity. |
| Packaging + restore research | M2–M3 | Disposable hosts · Cloud contracts | Proposed early experiments for D05/D06/D07; managed lifecycle acceptance still belongs to M6. Overlap requires available execution capacity. |
| Quality + repo maintenance | M0–M7 | CI · PRs · evidence · README · changelog | Checks and upkeep at every stage. Live evidence collection and unattended scheduling remain implementation work. |

M0/M1 and M7 have their own exit gates; an empty journey set never marks them complete. J04 begins in M2 but its full browsing scope is required by M4.

Follow [execution order](EXECUTION.md), [journey index](../JOURNEYS.md), and [quality rules](../QUALITY.md). Re-estimate calendar timing after M2 and M3. No milestone is accepted by a generated diagram alone.
