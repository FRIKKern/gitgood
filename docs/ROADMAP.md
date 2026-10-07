# Delivery roadmap

Generated from docs/milestones.json. Definitions are not execution status; view the README SVG and npm run status for evidence freshness.

| Milestone | Work | Exit evidence |
|---|---|---|
| M0 Scope and ownership | Confirm private-team scope, ownership, identity boundary, and open experiments. | Recorded bounded execution baseline; delegated agent authority; J01/J02 scenarios and data ownership. |
| M1 Repository ready | Scaffold app/API, isolated Postgres, runtimes, real request contract, local setup, CI. | Fresh checkout runs; browser reaches API; secrets stay server-side; isolated migrations and tests pass. |
| M2 Private repository slice | Complete J01/J02 and minimal J04 with real Git clients and two identities. | Authorized create/clone/push/browse; unauthorized reads/writes denied; timeouts and cleanup verified. |
| M3 Review and merge foundation | Complete review, check reporting, protected merge, and interruption recovery; start packaging experiment. | Concurrent and stale-state behavior proven; exact result reconciles after service failure. |
| M4 Usable private forge | Add SSH, import, fuller browsing, releases, and permission-aware activity. | Pilot daily workflow works; compatibility limitations and measured performance targets are documented. |
| M5 Connected workspace | Adopt verified Barkpark capabilities and revision-specific evidence. | Links preserve both owners' permissions; current/stale verification is clear; scoped agent APIs follow ordinary rules. |
| M6 Managed lifecycle | Finish Cloud launch, upgrade, restore, export/archive; recovery research starts earlier. | Clean install, unhealthy-release rejection, real replacement-host restore, supported export and removal. |
| M7 First complete release | Complete bounded pilot and reconcile all accepted scope, artifact identity, runbooks, and evidence. | Every required journey has current release-candidate evidence; no blocking correctness gap; agent evaluations pass all evidence gates without human sign-off. |

M0/M1 and M7 have their own exit gates; an empty journey set never marks them complete. J04 begins in M2 but its full browsing scope is required by M4. Recovery and Cloud packaging research start before the final lifecycle phase.

Follow [execution order](EXECUTION.md), [journey index](../JOURNEYS.md), and [quality rules](../QUALITY.md). Re-estimate after M2 and M3. No milestone is accepted by this generated diagram alone.
