[![Gitgood milestone Gantt: delivery order, where capabilities appear, and proposed overlapping research; columns are stages, not dates](docs/images/roadmap.svg)](docs/ROADMAP.md)

# Gitgood

A native forge connecting requirements, tasks, code review, evidence, and releases.

[Full-size Gantt](docs/images/roadmap.svg) · [Journey evidence map](docs/images/journey-evidence.svg) · [Milestone exit criteria](docs/ROADMAP.md) · [Journey specifications](JOURNEYS.md)

**Native development is underway.** This checkout contains a Phoenix/Postgres private repository foundation, a TanStack web interface, specifications and reporting checks. See [forge setup](apps/forge/README.md) and [web setup](apps/web/README.md). Native HTTPS/SSH Git, supported bundle import, commit browsing, pull requests, reviews, checks, protected merges and [basic private releases/assets](docs/implementation/releases.md) are implemented with development verification. The [private Gitgood delivery ledger](https://guerrilla.barkpark.cloud/w/gitgood/p/delivery/studio) owns live implementation status and protected delivery assessments. Complete native J11 acceptance, release ingestion and managed deployment remain unfinished; no Gitgood product release is established. See the [tracking contract](docs/TRACKING.md) for refresh and freshness limits.

**Autonomous progression.** Agents resolve decisions, implement, verify, merge, and advance milestones without human acceptance. Current evidence governs each transition. See [AUTONOMY.md](AUTONOMY.md) for the operating policy and the distinction between active agent work and future unattended automation.

**Foundation run delivered.** The [run finish record](docs/RUN-72H-FINISH.md) maps implemented behavior to tests, candidate identities and remaining scope. [Production artifact instructions](docs/deployment/production.md) reproduce the copied Elixir/TanStack installation and readiness experiment.

<!-- whats-new:start -->
## What's new

**Unreleased — development.** 131 pending changelog entries (90 added, 14 changed, 26 fixed, 1 security). See the [full development changelog](CHANGELOG.md#unreleased). No Gitgood application release has been published.
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

`apps/forge/` owns the Phoenix API, access rules, durable operations and Git storage. `apps/web/` owns the TanStack interface and its server-side request composition. The root retains specifications, reporting scripts and CI definitions.

The upstream design discussion is preserved in the [initial reference Page](https://chatgpt.com/space/page_fd72d3f936c88191b2f83ed1217f7f82); access to that Page is separate. These repository files are the normative implementation baseline.

The upstream repository is [FRIKKern/gitgood](https://github.com/FRIKKern/gitgood), created as private on 7 October 2026. Planning checks run on pushes to `main` and pull requests. The scheduled freshness job remains disabled until its sources and alerts are configured. Agents resolve remaining licensing and technical decisions through [decision records](docs/decisions/README.md); human release staffing is not required.
