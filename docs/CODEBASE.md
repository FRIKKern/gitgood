# Find your way around the code

[Docs home](README.md) · [Run locally](DEVELOPMENT.md) · [Architecture](architecture.md)

Gitgood has two applications. **The forge owns the rules and durable state. The web application presents them.** Postgres stores accounts, collaboration records and operation outcomes; standard Git stores repository objects and refs. Barkpark remains an external system reached through supported APIs.

This map describes code in this checkout. It is not a release checklist. Use [current status](STATUS.md) for the distinction between implemented behavior, current verification, and remaining product work.

## The repository at a glance

| Location | What belongs here | Start with |
|---|---|---|
| `apps/forge/` | Phoenix API, authorization, Git operations, durable workflows | [Forge guide](../apps/forge/README.md) |
| `apps/web/` | React/TanStack pages, interaction state, server-side API proxy | [Web guide](../apps/web/README.md) |
| `tools/deployment/` | Native installation, upgrade, recovery and retirement components | [Deployment instructions](deployment/production.md) and [implementation index](implementation/README.md) |
| `scripts/` | Generated docs, status reporting, build identity and verification harnesses | [Root commands](../package.json) |
| `docs/journeys/` | Required end-to-end behavior and acceptance criteria | [Journey index](../JOURNEYS.md) |
| `docs/decisions/` | Why a consequential design was chosen | [Decision index](decisions/README.md) |
| `evidence/` | Reporting contracts and checked-in status inputs | [Evidence contract](../evidence/README.md) |
| `changelog/` | Individual change fragments and publication rules | [Changelog routine](../changelog/ROUTINE.md) |
| `.github/workflows/` | Required checks and opt-in maintenance | [Product checks](../.github/workflows/product.yml), [planning checks](../.github/workflows/verify.yml) |

## Follow a request

1. A route in [web routes](../apps/web/src/routes/) renders a page and calls the API through [api.ts](../apps/web/src/lib/api.ts).
2. The [server-only proxy](../apps/web/src/server/forge.ts) forwards the request to the configured forge. The browser cannot choose an upstream or obtain service credentials.
3. The [Phoenix router](../apps/forge/lib/gitgood_web/router.ex) selects a controller. [Auth](../apps/forge/lib/gitgood_web/auth.ex) and [Access](../apps/forge/lib/gitgood/access.ex) apply the current actor's access rules.
4. A domain module under `apps/forge/lib/gitgood/` performs the operation. Consequential Git writes have workers and durable records so retries and restarts can be reconciled.
5. The web renders the result or an explicit retry/unavailable state. Browser visibility is never the authorization boundary.

Git transport has separate HTTP and SSH entries but uses the same backend access and write rules. Read [architecture](architecture.md) for ownership boundaries and [QUALITY.md](../QUALITY.md) for the invariants every path must preserve.

## Find a feature

| Working on… | Backend entry points | Interface or contract |
|---|---|---|
| Sign-in, membership, access changes | [Accounts](../apps/forge/lib/gitgood/accounts.ex), [Access](../apps/forge/lib/gitgood/access.ex), [Teams](../apps/forge/lib/gitgood/teams.ex) | [Access boundary](../apps/web/src/lib/access-boundary.tsx), [team controls](../apps/web/src/lib/team-members.tsx) |
| Repository creation and Git transfer | [Repositories](../apps/forge/lib/gitgood/repositories.ex), [Git](../apps/forge/lib/gitgood/git.ex), [Pushes](../apps/forge/lib/gitgood/pushes.ex), [SSH transport](../apps/forge/lib/gitgood/ssh_transport.ex) | [HTTP decision](decisions/0003-native-http-transport.md), [SSH guide](implementation/ssh.md) |
| Files, history and diffs | [Browse](../apps/forge/lib/gitgood/browse.ex), [BrowseSlots](../apps/forge/lib/gitgood/browse_slots.ex) | [Browsing contract](implementation/browsing.md) |
| Pull requests, reviews, checks and merge | [Pulls](../apps/forge/lib/gitgood/pulls.ex), [Checks](../apps/forge/lib/gitgood/checks.ex), [Merges](../apps/forge/lib/gitgood/merges.ex) | [Collaboration components](../apps/web/src/lib/collaboration.tsx), [workflow contract](implementation/collaboration.md) |
| Import and releases | [Imports](../apps/forge/lib/gitgood/imports.ex), [Releases](../apps/forge/lib/gitgood/releases.ex) | [Import UI](../apps/web/src/lib/repository-import.tsx), [release UI](../apps/web/src/lib/releases.tsx) |
| Barkpark links and criterion evidence | [BarkparkConnections](../apps/forge/lib/gitgood/barkpark_connections.ex), [SourceLinks](../apps/forge/lib/gitgood/source_links.ex), [Evidence](../apps/forge/lib/gitgood/evidence.ex), [EvidenceIntents](../apps/forge/lib/gitgood/evidence_intents.ex) | [Source links](../apps/web/src/lib/source-links.tsx), [criterion evidence](../apps/web/src/lib/criterion-evidence.tsx), [integration guide](implementation/barkpark.md) |
| Search and recent activity | [Discovery](../apps/forge/lib/gitgood/discovery.ex) | [Discovery UI](../apps/web/src/lib/discovery.tsx), [activity contract](implementation/activity.md) |
| Startup, readiness and recovery | [Application](../apps/forge/lib/gitgood/application.ex), [Readiness](../apps/forge/lib/gitgood/readiness.ex), [OfflineRecovery](../apps/forge/lib/gitgood/offline_recovery.ex) | [Native supervision](implementation/native-supervision-profile.md), [backup and restore](implementation/offline-backup.md) |

The native installation code is substantial and still being integrated. In this checkout, `Gitgood.Application` starts through `InstallationProfile.ensure_development/3`; it refuses the managed native startup path. Component files and their isolated experiments do not mean that the complete Cloud installation works.

## Where to make a change

Put permission, merge and recovery rules in the forge. Keep browser draft state and interaction handling in the web. Add persistent schema changes under [forge migrations](../apps/forge/priv/repo/migrations/). Put external integration behavior behind its existing backend adapter rather than moving authority into the UI.

For backend behavior, start with the corresponding file in [forge tests](../apps/forge/test/gitgood/). HTTP boundaries have [web-layer backend tests](../apps/forge/test/gitgood_web/); real browser workflows live in [web e2e tests](../apps/web/e2e/). Native operator tests live alongside their components in [tools/deployment](../tools/deployment/), with recovery checks under [operation tests](../apps/forge/test/operations/). Choose the checks that exercise the changed behavior; see [development](DEVELOPMENT.md#4-check-your-change) for the entry points.

## Generated and local files

`JOURNEYS.md`, `docs/ROADMAP.md`, `docs/STATUS.md`, `docs/images/`, `CHANGELOG.md` and the marked README news section have generated views. Change the canonical inputs and run `npm run generate`; see [contribution rules](../CONTRIBUTING.md) for their ownership and validation.

TanStack generates `apps/web/src/routeTree.gen.ts` from the route files. Local `.gitgood/` directories hold ignored development state and may contain private verification or recovery materials. They are not a scratch directory to delete blindly. The [evidence contract](../evidence/README.md) explains what may be published.
