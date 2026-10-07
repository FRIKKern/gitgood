# Gitpark

A native forge connecting requirements, tasks, code review, evidence, and releases.

[![Gitpark roadmap with separate implementation, verification, and release states](docs/images/roadmap.svg)](docs/ROADMAP.md)

**Planning repository.** Native Gitpark is the agreed direction. This checkout contains the product plan and runnable reporting checks; it does not host repositories or deploy an application yet. Product progress is unverified until real sources are connected.

<!-- whats-new:start -->
## What's new

**Unreleased — planning foundation.** Product scope, 17 journey specifications, delivery milestones, repository routines, and a generated roadmap are available. Private GitHub repository FRIKKern/gitpark established with planning verification on pushes and pull requests, current pinned GitHub Actions, and an explicit Ubuntu 24.04 runner. No Gitpark application release has been published.
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
| Assignments and blockers | Future Gitpark goal in the Barkpark ledger; [tracking contract](docs/TRACKING.md) |
| Setup sequence | [Execution plan](docs/EXECUTION.md) |
| Repository care | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Release history and routine | [CHANGELOG.md](CHANGELOG.md), [changelog routine](changelog/ROUTINE.md) |
| Cloud and recovery | [Cloud contract](deploy/README.md), [operations acceptance](docs/operations/README.md) |
| Provenance | [THIRD-PARTY.md](THIRD-PARTY.md), [references](reference/README.md) |
| Reporting inputs | [Status snapshot](evidence/status.json); schema and validation in scripts |
| Security reporting | [SECURITY.md](SECURITY.md) |

## Repository shape

`app/` and `api/` are created when implementation begins. The current repository contains specifications, fixtures, reporting scripts, and CI definitions. Do not create empty service frameworks.

The upstream design discussion is preserved in the [initial reference Page](https://chatgpt.com/space/page_fd72d3f936c88191b2f83ed1217f7f82); access to that Page is separate. These repository files are the normative implementation baseline.

The upstream repository is [FRIKKern/gitpark](https://github.com/FRIKKern/gitpark), created as private on 7 October 2026. Planning checks run on pushes to `main` and pull requests. The scheduled freshness job remains disabled until its sources and alerts are configured. License, identity bootstrap, and release staffing remain open in [decisions](docs/decisions/README.md).
