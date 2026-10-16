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

[CommandPort](../apps/forge/lib/gitgood/command_port.ex) closes captured command
adapter ports for buffered and streaming workers. It tolerates prior closure so
an adapter's normal exit during cleanup cannot erase its completed command result.

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

The native installation code is substantial and still being integrated. `Gitgood.Application` selects development or original native ownership through `InstallationProfile.resolve/3`; normal native release boot uses the fixed runtime root and one-use activation. Read [default native startup](implementation/native-default-startup.md) for its installed proof and remaining gates. Component files and isolated experiments do not mean that the complete Cloud installation works.

## Where to make a change

Put permission, merge and recovery rules in the forge. Keep browser draft state and interaction handling in the web. Add persistent schema changes under [forge migrations](../apps/forge/priv/repo/migrations/). Put external integration behavior behind its existing backend adapter rather than moving authority into the UI.

For backend behavior, start with the corresponding file in [forge tests](../apps/forge/test/gitgood/). HTTP boundaries have [web-layer backend tests](../apps/forge/test/gitgood_web/); real browser workflows live in [web e2e tests](../apps/web/e2e/). Native operator tests live alongside their components in [tools/deployment](../tools/deployment/), with recovery checks under [operation tests](../apps/forge/test/operations/). Choose the checks that exercise the changed behavior; see [development](DEVELOPMENT.md#4-check-your-change) for the entry points.

[native_path_probe.py](../tools/ci/native_path_probe.py) and
[native-path-test.py](../tools/ci/native-path-test.py) retain the rejected pure
lexical SDK diagnostic. [native-descriptor-test.py](../tools/ci/native-descriptor-test.py)
exercises its replacement's C-bound methods, scoped code-input notifications,
restoration and original fallback in [native-metadata-probe.c](../tools/ci/native-metadata-probe.c).
The hosted workflow runs its actual Root cases and original-actor comparison;
portable SDK tests alone do not establish native semantics or production benefit.
Read [artifact controller diagnostics](implementation/native-artifact-controller.md)
before changing the original guard, filesystem observations or staging budget.

## Generated and local files

Native ownership startup is coordinated by [native_ownership_startup.ex](../apps/forge/lib/gitgood/native_ownership_startup.ex)
and [native_ownership_supervisor.ex](../apps/forge/lib/gitgood/native_ownership_supervisor.ex).
[native_lifecycle_action.ex](../apps/forge/lib/gitgood/native_lifecycle_action.ex) matches a requested action
to the guarded Root lifecycle window before lease or worker startup. Read [worker admission](implementation/native-lifecycle-worker-admission.md)
for the distinction between that startup boundary and complete installation effects.
[native_lifecycle_business_inputs.py](../tools/deployment/native_lifecycle_business_inputs.py)
validates private migration/first-owner projections under the original held guard.
Read [business inputs](implementation/native-lifecycle-business-inputs.md) before
connecting these password-bearing values to fixed workers. Transport retains the
original ownership and stage. The attached Python exchange is
[native_monitor_business_inputs.py](../tools/deployment/native_monitor_business_inputs.py),
with closed BEAM decoding in [native_lifecycle_business_inputs.ex](../apps/forge/lib/gitgood/native_lifecycle_business_inputs.ex).
Fixed migration and first-owner effects live in
[native_maintenance.ex](../apps/forge/lib/gitgood/native_maintenance.ex) and
[native_maintenance_worker.ex](../apps/forge/lib/gitgood/native_maintenance_worker.ex).
Read [maintenance effects](implementation/native-maintenance-effects.md) for the
permanent ownership boundary, actual schema prerequisites and evidence limits.
Whole lifecycle dispatch and interruption reconciliation remain unfinished.

The fixed native runtime application and one-use coordinator live in
[native_runtime.ex](../apps/forge/lib/gitgood/native_runtime.ex) and
[native_runtime_worker.ex](../apps/forge/lib/gitgood/native_runtime_worker.ex).
[runtime_workers.ex](../apps/forge/lib/gitgood/runtime_workers.ex) owns the common
product worker/listener list; [native_migration_inventory.ex](../apps/forge/lib/gitgood/native_migration_inventory.ex)
owns protected package inventory for runtime and maintenance. Read
[runtime effects](implementation/native-runtime-effects.md) for actual schema and
ownership prerequisites, internal API/Git evidence and remaining acceptance gates.

[native_public_runtime.py](../tools/deployment/native_public_runtime.py) owns fixed
web/edge launch, protected copied web inventory, current original runtime checks
and bounded original-leaf quiescence. Read [native public runtime](implementation/native-public-runtime.md)
for its TLS/frontend/Git component proof and unfinished activation/recovery gates.

[native_root_controller.py](../tools/deployment/native_root_controller.py) owns
Root's fixed read-only observation of the original ordinary controller. It shares
host/service checks while preserving ordinary caller admission. Read
[Root controller observation](implementation/native-root-controller.md) for the
remaining protected artifact staging and operation-binding requirements.

[native_protected_artifact.py](../tools/deployment/native_protected_artifact.py)
owns the fixed Root staging boundary, allocation budget, descriptor-relative
extraction, read-only code publication and original output metadata checks. Read
[protected artifact staging](implementation/native-protected-artifact.md) for
authority allocation, actual dispatch and interruption verification still needed.

[native_root_lifecycle.py](../tools/deployment/native_root_lifecycle.py) owns the
fixed Root read-only request/history view, with separate original ordinary-file
custody and shared publication/lifecycle format validators. Read
[Root lifecycle observation](implementation/native-root-lifecycle.md) for its
unfinished actual observation, exclusion, allocation and stage-dispatch gates.

[native_root_live_binding.py](../tools/deployment/native_root_live_binding.py)
owns Root's fixed original live resource/database comparison and permanent
refusal. Its private Root admission entry shares persistent validation with the
unchanged ordinary caller gate. Read [Root live resource observation](implementation/native-root-live-binding.md)
for the separate exclusion, allocation, actual dispatch and recovery requirements.

[native_root_controller_request.py](../tools/deployment/native_root_controller_request.py)
owns the closed original-controller socket request and Linux history-descriptor
observation, bracketing peer and kernel checks with the original live view. Read
[original controller requests](implementation/native-root-controller-request.md)
for the database exclusion, effect authority and production dispatch still needed.

[native_root_database_exclusion.py](../tools/deployment/native_root_database_exclusion.py)
owns Root's fixed discovery and retained observation of the original controller
client, socket and database lease/kernel identity. Read [original database
exclusion](implementation/native-root-database-exclusion.md) for its sampled
cooperative scope and the artifact authority/dispatch/recovery still needed.

[native_root_database_reader.py](../tools/deployment/native_root_database_reader.py)
owns one original read-only SQL client only during archive staging. Live identity
and exclusion views share it without removing effect checks or changing ordinary
handoff connection rules. Read [retained staging observations](implementation/native-root-database-reader.md)
for its fixed statements, loss fences and pending actual verification.

[native_ownership_database.py](../tools/deployment/native_ownership_database.py)
owns the shared, fresh fixed-connection kernel socket query behind independent
ordinary and Root admission. Read [targeted TCP observation](implementation/native-tcp-socket-observation.md)
for kernel framing, original process/descriptor checks and pending Linux evidence.

[native_service_scope.py](../tools/deployment/native_service_scope.py) owns the
Root-controlled file reader and retained metadata validation shared by native
observers. Read [Root file path validation](implementation/native-root-file-paths.md)
for canonical spelling, fresh ancestor/leaf checks and actual filesystem cases.

[native_systemd_properties.py](../tools/deployment/native_systemd_properties.py)
owns typed live manager reads. [Selected and Root interface observations](implementation/native-selected-systemd-properties.md)
explain selected live reads and the retained interface-decoder experiment.

[native_root_artifact_policy.py](../tools/deployment/native_root_artifact_policy.py)
owns fixed stage-policy preparation and exclusive Root publication under the
original exclusion and independently provisioned allocation lock. Read
[Root artifact policy allocation](implementation/native-root-artifact-policy.md)
for its original exclusion, allocation flock and retained publication custody.

[native_artifact_controller.py](../tools/deployment/native_artifact_controller.py)
owns ordinary MainPID inspection, fixed Root socket dispatch, independent staged
output validation and controlled journal completion while retaining original
history/writer custody. Its separate reader does not admit application workers.
[native_root_artifact_dispatch.py](../tools/deployment/native_root_artifact_dispatch.py)
owns authenticated request/exclusion observation and retains the Root allocation
flock through protected extraction, closing Root SQL observers before the reply.
Read [the artifact controller](implementation/native-artifact-controller.md) and
[Root dispatch](implementation/native-root-artifact-dispatch.md) for the unverified
live integration, provisioning/listener and recovery requirements.

`JOURNEYS.md`, `docs/ROADMAP.md`, `docs/STATUS.md`, `docs/images/`, `CHANGELOG.md` and the marked README news section have generated views. Change the canonical inputs and run `npm run generate`; see [contribution rules](../CONTRIBUTING.md) for their ownership and validation.

TanStack generates `apps/web/src/routeTree.gen.ts` from the route files. Local `.gitgood/` directories hold ignored development state and may contain private verification or recovery materials. They are not a scratch directory to delete blindly. The [evidence contract](../evidence/README.md) explains what may be published.

Before large Windows allocations, [windows-storage-preflight.ps1](../scripts/windows-storage-preflight.ps1) checks estimated bytes against the fixed local reserve. Its volume resolution and budget calculations live in [windows-storage.psm1](../scripts/windows-storage.psm1); [boundary tests](../scripts/windows-storage.test.ps1) use small reader doubles and actual read-only volume metadata. See the [Windows development prerequisites](DEVELOPMENT.md#windows-notes) for usage and snapshot limitations.
