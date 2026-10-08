[![Gitgood milestone Gantt: delivery order, where capabilities appear, and proposed overlapping research; columns are stages, not dates](docs/images/roadmap.svg)](docs/ROADMAP.md)

# Gitgood

A native forge connecting requirements, tasks, code review, evidence, and releases.

[Full-size Gantt](docs/images/roadmap.svg) · [Journey evidence map](docs/images/journey-evidence.svg) · [Milestone exit criteria](docs/ROADMAP.md) · [Journey specifications](JOURNEYS.md)

**Planning repository.** Native Gitgood is the agreed direction. This checkout contains the product plan and runnable reporting checks; it does not host repositories or deploy an application yet. Product progress is unverified until real sources are connected.

**Autonomous progression.** Agents resolve decisions, implement, verify, merge, and advance milestones without human acceptance. Current evidence governs each transition. See [AUTONOMY.md](AUTONOMY.md) for the operating policy and the distinction between active agent work and future unattended automation.

<!-- whats-new:start -->
## What's new

**Unreleased — planning foundation.** Added a time-boxed first implementation run targeting the running foundation and private create/clone/push/browse slice, with observed environment constraints, verification checkpoints, and recovery rules. Delegated project progression to agents and replaced human acceptance gates with recorded evidence-based verification across decisions, milestones, merges, and releases. Converted the top README roadmap to a milestone Gantt showing delivery surfaces and proposed research overlap; retained the detailed journey evidence map as a separate generated view. Renamed the project from Gitpark to Gitgood, including the private GitHub repository, documentation, package metadata, roadmap SVG, and maintenance variable. Product scope, 17 journey specifications, delivery milestones, repository routines, and a generated roadmap are available. Private GitHub repository FRIKKern/gitgood established with planning verification on pushes and pull requests, current pinned GitHub Actions, and an explicit Ubuntu 24.04 runner. Redesigned the README roadmap with journey-level status, milestone dependencies and exit criteria, separate progress summaries, and light/dark palettes. No Gitgood application release has been published.
<!-- whats-new:end -->

## Start here

1. Read [Product scope](PRODUCT.md) and [Architecture](docs/architecture.md).
2. Follow [Execution order](docs/EXECUTION.md); open decisions are explicit.
3. Use [Journeys](JOURNEYS.md) and [Quality rules](QUALITY.md) to judge completion.
4. Run the planning checks below before changing the baseline.

```sh
npm run generate
npm run check
npm run status
```

Requires Node 22.13.1 or a compatible Node 22 runtime. No npm dependencies are needed. Generated files are checked in and verified for drift.

## One fact, one home

| Information | Home |
|---|---|
| Users, scope, exclusions | [PRODUCT.md](PRODUCT.md) |
| Journey IDs and phase membership | [Journey catalog](docs/journeys/catalog.json) |
| Required behavior | [Journey specifications](docs/journeys/J01.md), indexed in [JOURNEYS.md](JOURNEYS.md) |
| Milestone definitions | [Milestone catalog](docs/milestones.json); [rendered roadmap](docs/ROADMAP.md) |
| Quality and evidence | [QUALITY.md](QUALITY.md), [evidence contract](evidence/README.md) |
| Architecture and decisions | [Architecture](docs/architecture.md), [decision index](docs/decisions/README.md) |
| Assignments and blockers | Future Gitgood goal in the Barkpark ledger; [tracking contract](docs/TRACKING.md) |
| Setup sequence | [Execution plan](docs/EXECUTION.md) |
| Agent authority and progression | [AUTONOMY.md](AUTONOMY.md) |
| Repository care | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Release history and routine | [CHANGELOG.md](CHANGELOG.md), [changelog routine](changelog/ROUTINE.md) |
| Cloud and recovery | [Cloud contract](deploy/README.md), [operations acceptance](docs/operations/README.md) |
| Provenance | [THIRD-PARTY.md](THIRD-PARTY.md), [references](reference/README.md) |
| Reporting inputs | [Status snapshot](evidence/status.json); schema and validation in scripts |
| Security reporting | [SECURITY.md](SECURITY.md) |

## Repository shape

`app/` and `api/` are created when implementation begins. The current repository contains specifications, fixtures, reporting scripts, and CI definitions. Do not create empty service frameworks.

The upstream design discussion is preserved in the [initial reference Page](https://chatgpt.com/space/page_fd72d3f936c88191b2f83ed1217f7f82); access to that Page is separate. These repository files are the normative implementation baseline.

The upstream repository is [FRIKKern/gitgood](https://github.com/FRIKKern/gitgood), created as private on 7 October 2026. Planning checks run on pushes to `main` and pull requests. The scheduled freshness job remains disabled until its sources and alerts are configured. Agents resolve remaining licensing and technical decisions through [decision records](docs/decisions/README.md); human release staffing is not required.
