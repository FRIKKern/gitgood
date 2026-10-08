[![Gitgood milestone Gantt: delivery order, where capabilities appear, and proposed overlapping research; columns are stages, not dates](docs/images/roadmap.svg)](docs/ROADMAP.md)

# Gitgood

A native forge connecting requirements, tasks, code review, evidence, and releases.

[Full-size Gantt](docs/images/roadmap.svg) · [Journey evidence map](docs/images/journey-evidence.svg) · [Milestone exit criteria](docs/ROADMAP.md) · [Journey specifications](JOURNEYS.md)

**Native development is underway.** This checkout contains a Phoenix/Postgres private repository foundation, a TanStack web interface, specifications and reporting checks. See [forge setup](apps/forge/README.md) and [web setup](apps/web/README.md). Native HTTPS/SSH Git, supported bundle import, commit browsing, pull requests, reviews, checks, protected merges and [basic private releases/assets](docs/implementation/releases.md) are implemented with development verification. No Gitgood product release or managed deployment is established; the live evidence sources remain unconfigured.

**Autonomous progression.** Agents resolve decisions, implement, verify, merge, and advance milestones without human acceptance. Current evidence governs each transition. See [AUTONOMY.md](AUTONOMY.md) for the operating policy and the distinction between active agent work and future unattended automation.

**Foundation run delivered.** The [run finish record](docs/RUN-72H-FINISH.md) maps implemented behavior to tests, candidate identities and remaining scope. [Production artifact instructions](docs/deployment/production.md) reproduce the copied Elixir/TanStack installation and readiness experiment.

<!-- whats-new:start -->
## What's new

**Unreleased — development.** Added a time-boxed first implementation run targeting the running foundation and private create/clone/push/browse slice, with observed environment constraints, verification checkpoints, and recovery rules. Added a 72-hour implementation proposal covering the private repository slice, review/check/merge foundations, interruption recovery, and clean-target packaging, with evidence-based daily targets. Delegated project progression to agents and replaced human acceptance gates with recorded evidence-based verification across decisions, milestones, merges, and releases. Added private per-account Barkpark connection APIs with source-verified scoped service identities, separate-key authenticated credential encryption, generation-safe rotation/disconnect and durable request receipts; complete linked-workspace workflows remain pending. Added private Barkpark account settings with credential-input clearing, current-state reconciliation after historical receipts, unavailable-read hiding and old-account completion guards. Added an origin-pinned, bounded Barkpark HTTP adapter with separate request capacity, TLS and wire checks, plus real private-source permission and idempotency experiments; linked-workspace journeys remain pending. Added private tag/commit releases with transactional checksummed assets, actual commit ranges, reviewed-note publication, safe retries, retained corrections/withdrawals and native immutable tag pushes. Added private commit browsing with stable URLs, branch selection, file tree, safe text previews, history and bounded diffs. Converted the top README roadmap to a milestone Gantt showing delivery surfaces and proposed research overlap; retained the detailed journey evidence map as a separate generated view. Renamed the project from Gitpark to Gitgood, including the private GitHub repository, documentation, package metadata, roadmap SVG, and maintenance variable. Added a runnable Phoenix/Postgres private repository foundation and TanStack web interface with local identities, revocable sessions, backend membership checks, durable idempotent creation and recovery tests. Added scoped and revocable Git credentials, authenticated native smart HTTP clone/push/fetch, protected main enforcement, durable push records and bounded subprocess supervision. Recorded the completed native foundation run with criterion-level observations, exact candidate/runtime evidence, clean-start instructions, integration references and remaining private-forge/Cloud milestones. Added PostgreSQL-owned Ed25519 account keys, browser registration/revocation, native OTP SSH Git transport, host fingerprints and clone URLs, with shared authorization/push recovery and real-client interruption checks. Product scope, 17 journey specifications, delivery milestones, repository routines, and a generated roadmap are available. Added permission-filtered native search and activity, opaque collaboration links, shared browser access invalidation and audited owner controls for team membership; corrected merge crash proof to bind the clean source candidate and requirement. Private GitHub repository FRIKKern/gitgood established with planning verification on pushes and pull requests, current pinned GitHub Actions, and an explicit Ubuntu 24.04 runner. Added copied production Elixir/TanStack artifacts, clean commit/spec build identity, migration/bootstrap entry points, dependency/storage readiness and an isolated full-workflow persistence experiment. Added same-repository pull requests, exact-line comments and reviews, scoped check providers, current branch policy and atomic protected fast-forward merges with durable recovery markers. Added creator-owned full Git bundle import with bounded streaming intake, durable replay/provenance, atomic branches and tags, recovery markers and browser/native-client verification. Redesigned the README roadmap with journey-level status, milestone dependencies and exit criteria, separate progress summaries, and light/dark palettes. Disabled automatic distributed Erlang registration for single-host releases after a real concurrent Windows/Linux node collision; added populated/history-only Barkpark migration refusal and a fresh-VM encrypted-account retention fixture. No Gitgood application release has been published.
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
