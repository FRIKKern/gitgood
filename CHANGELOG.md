# Changelog

Development changes and published releases, grouped by the kind of change. Unreleased work has not been published as a Gitgood application release.

[Project overview](README.md) · [Progress snapshot](docs/STATUS.md) · [Changelog routine](changelog/ROUTINE.md)

Generated from reviewed fragments and [the release manifest](changelog/releases.json). This file does not publish a release.

## Unreleased

### Security

- Filter private headers from Caddy runtime errors and cancelled-stream warnings as well as access evidence. Disable expanded config persistence and require actual failure-path privacy checks in copied-production verification.
  Sources: [details 1](docs/deployment/production.md), [details 2](docs/deployment/Caddyfile.example)

### Added

- Added a time-boxed first implementation run targeting the running foundation and private create/clone/push/browse slice, with observed environment constraints, verification checkpoints, and recovery rules.
  Sources: [details 1](docs/RUN-24H.md)

- Added a 72-hour implementation proposal covering the private repository slice, review/check/merge foundations, interruption recovery, and clean-target packaging, with evidence-based daily targets.
  Sources: [details 1](docs/RUN-72H.md)

- Added private per-account Barkpark connection APIs with source-verified scoped service identities, separate-key authenticated credential encryption, generation-safe rotation/disconnect and durable request receipts; complete linked-workspace workflows remain pending.
  Sources: [details 1](docs/implementation/barkpark-accounts.md), [details 2](docs/decisions/0009-supported-barkpark-links.md)

- Added private Barkpark account settings with credential-input clearing, current-state reconciliation after historical receipts, unavailable-read hiding and old-account completion guards.
  Sources: [details 1](docs/implementation/barkpark-accounts.md)

- Added an origin-pinned, bounded Barkpark HTTP adapter with separate request capacity, TLS and wire checks, plus real private-source permission and idempotency experiments; linked-workspace journeys remain pending.
  Sources: [details 1](docs/implementation/barkpark.md), [details 2](docs/decisions/0009-supported-barkpark-links.md)

- Added durable Paper return-link responsibility with encrypted immutable source requests, bounded attempts, visible pause/retry, actual write receipts and separately attributed source observation.
  Sources: [details 1](docs/implementation/barkpark-return-pointers.md)

- Added private tag/commit releases with transactional checksummed assets, actual commit ranges, reviewed-note publication, safe retries, retained corrections/withdrawals and native immutable tag pushes.
  Sources: [details 1](docs/implementation/releases.md), [details 2](docs/decisions/0007-basic-private-releases.md)

- Added private commit browsing with stable URLs, branch selection, file tree, safe text previews, history and bounded diffs.
  Sources: [details 1](docs/implementation/browsing.md), [source 2](https://github.com/FRIKKern/gitgood/pull/9)

- Read explicit delivery evaluations from the scoped Source with criterion identities, protected text proof checksums, retained provenance, latest-result selection and proof-age checks; actual protected publication and denied-refresh preservation retain an inconclusive supporting assessment.
  Sources: [details 1](scripts/verification-source.mjs), [details 2](scripts/refresh-verification.mjs), [details 3](docs/implementation/delivery-evaluations.md)

- Bind authenticated native export inspection to an independently expected installation UUID and comparable file/database hashes, and add a lease-bound retirement checkpoint that refuses changed snapshots; removal remains unfinished.
  Sources: [details 1](apps/forge/priv/operations/installation-export.mjs), [details 2](docs/implementation/installation-retirement.md), [details 3](docs/operations/export.md)

- Added a real-client compatibility experiment for Git protocols, shallow ancestry, separate submodule credentials, signed object preservation and explicit LFS/partial-clone/SHA256 hosting limits; production verification includes exact ref/gitlink persistence.
  Sources: [details 1](docs/implementation/git-compatibility.md)

- Observe an already allocated empty native host with supported OS/database checks, exact private resources, empty stores and process groups, database-object refusal and boot/namespace binding; allocation and installation remain separate responsibilities.
  Sources: [details 1](docs/implementation/initial-allocation-admission.md), [details 2](docs/decisions/0016-native-initial-enrollment.md)

- Add a private first-install responsibility journal with fixed stages, namespace-aware ownership, sealed requests, interrupted-effect reconciliation and unchanged terminal replay; allocation, installation commands and managed Cloud enrollment remain unfinished.
  Sources: [details 1](docs/implementation/initial-enrollment-journal.md), [details 2](docs/decisions/0016-native-initial-enrollment.md)

- Expose coordinated encrypted native installation export and inspect its authenticated Git/configuration/database inventory without connecting to the live database; removal remains unfinished.
  Sources: [details 1](docs/operations/export.md)

- Add a digest-bound first-install owner bootstrap with atomic user/membership/receipt creation, serialized admission and exact historical replay that cannot reset credentials or restore changed access; complete installation and Cloud enrollment remain unfinished.
  Sources: [details 1](docs/implementation/installation-owner-bootstrap.md), [details 2](docs/decisions/0015-installation-owner-bootstrap.md)

- Add a fixed read-only first-owner observation entry that distinguishes committed absence from exact recorded creation under the creation lock, preserves current access and starts only the temporary database repository; packaged enrollment remains under verification.
  Sources: [details 1](docs/implementation/installation-owner-bootstrap.md), [details 2](docs/decisions/0015-installation-owner-bootstrap.md)

- Define isolated functional retirement verification with a separate bound target, continuous original custody, private listeners and disabled external Source effects; implementation and installed acceptance remain open.
  Sources: [details 1](docs/decisions/0011-isolated-retirement-verification.md)

- Connected the private Gitgood delivery ledger to a scoped authenticated implementation-status collector with requirement binding, retained observation history and failed-read preservation; evidence/release ingestion and unattended publishing remain pending.
  Sources: [details 1](docs/TRACKING.md)

- Persist exact native current-release observations under the installation history lock, with artifact/schema/probe binding and explicit lost-write uncertainty.
  Sources: [details 1](tools/deployment/native_activation.py), [details 2](tools/deployment/test_native_activation.py), [details 3](docs/implementation/installation-upgrade.md)

- Check actual native application credentials, stores, listeners and executable paths against protected installation configuration before lease acquisition or ownership publication.
  Sources: [details 1](docs/implementation/native-application-configuration.md), [details 2](apps/forge/lib/gitgood/native_application_configuration.ex)

- Gate application startup, direct lease initialization and offline maintenance before storage or database actions. Reject unsupported profiles and implicit native downgrade. Add immutable private ownership-record custody with synchronized publication, unchanged retries and retained partial responsibility. Add root supervision without child restarts and a single-session native database lease keeper; actual standalone processes exit on held backend or connection loss. Application integration, live markers and complete native startup remain unfinished.
  Sources: [details 1](docs/implementation/native-application-ownership.md), [details 2](apps/forge/lib/gitgood/installation_profile.ex), [details 3](tools/deployment/native_ownership_records.py), [details 4](apps/forge/lib/gitgood/native_ownership_supervisor.ex), [details 5](apps/forge/lib/gitgood/native_database_lease.ex)

- Inspect digest-pinned Linux native artifacts without extraction or execution, checking bounded paths, matching build identities, migrations and runtime platform before installation staging.
  Sources: [details 1](tools/deployment/inspect_native_artifact.py), [details 2](docs/implementation/installation-upgrade.md)

- Stage inspected native code under private custody with independent file hashes, retained interrupted requests and atomic publication that cannot replace existing targets.
  Sources: [details 1](tools/deployment/stage_native_artifact.py), [details 2](tools/deployment/test_stage_native_artifact.py), [details 3](docs/implementation/installation-upgrade.md)

- Add a bounded protected bridge for observing the original held Postgres session's kernel identity under an independently sealed server scope; installed enrollment, ownership retention and native application admission remain unfinished.
  Sources: [details 1](docs/implementation/native-backend-observation.md), [details 2](tools/deployment/native_backend_observation.py), [details 3](apps/forge/lib/gitgood/native_ownership_publication.ex)

- Added durable native links to Barkpark tasks and Paper specifications, per-viewer source reads, private change-page context, and original operation receipts that survive removal and replay.
  Sources: [details 1](docs/implementation/barkpark-records.md)

- Document the measured native rootless CI boundary and a pinned runner build recipe, preserving failed emulated/minimal-image results and requiring actual job conclusions.
  Sources: [details 1](docs/implementation/isolated-ci.md), [details 2](tools/ci/native-runner.Containerfile)

- Add fixed Root-sealed controller scope and private command-listener custody. Installed service admission, restart cleanup and lifecycle dispatch remain required.
  Sources: [details 1](docs/implementation/native-command-endpoint.md), [details 2](tools/deployment/native_controller_scope.py), [details 3](tools/deployment/native_command_endpoint.py)

- Add bounded canonical local controller request framing and actual Linux peer-account checks; sealed operation admission, lifecycle dispatch and installed controller remain required.
  Sources: [details 1](docs/implementation/native-command-wire.md), [details 2](tools/deployment/native_command_wire.py)

- Added immutable native evidence attached to linked task criteria and exact source/Git revisions, checksummed private text artifacts, explicit reassessment history and unavailable-artifact events; full J11 acceptance remains under verification.
  Sources: [details 1](docs/implementation/criterion-evidence.md)

- Observe native persistent installation identity separately from kernel resource generations. Bind private directory, configuration/key, host and root-controlled executable identities to an actual ordinary PostgreSQL owner; reject administrative role privileges, memberships and changed observations. Writer exclusion, publication and lifecycle recovery remain unfinished.
  Sources: [details 1](docs/implementation/native-durable-bindings.md), [details 2](tools/deployment/native_durable_binding.py), [details 3](tools/deployment/native_durable_database.py)

- Add bounded Elixir admission through a fixed Root-installed generation observer and read-only identity checks on an already held Postgrex installation lease. Application leases and generation-aware markers remain separate integration work.
  Sources: [details 1](docs/implementation/native-elixir-generation-admission.md), [details 2](apps/forge/lib/gitgood/installation_generation_admission.ex), [details 3](apps/forge/lib/gitgood/installation_database_session.ex)

- Bind private first-install request, allocation and bootstrap/plan inputs to independent seals and exact retained file/directory identities, refusing command/role extensions and replaced custody without claiming a journal or executing installation actions.
  Sources: [details 1](docs/implementation/native-enrollment-inputs.md), [details 2](docs/decisions/0016-native-initial-enrollment.md)

- Execute fixed native upgrade stages from pinned private plans, with a working public baseline, actual migration schema checks, authenticated probes, durable activation and schema-bound previous-code recovery.
  Sources: [details 1](tools/deployment/native_upgrade.py), [details 2](tools/deployment/test_native_upgrade.py), [details 3](docs/implementation/installation-upgrade.md)

- Add explicit same-intent native forward repair with observed schema compatibility, preserved failed events, repeated migration and public probes, scoped child reaping and private crash-dump custody. Permit owned read-only maintenance observation during controlled forward migration.
  Sources: [details 1](tools/deployment/native_upgrade.py), [details 2](tools/deployment/upgrade_journal.py), [details 3](tools/deployment/native_actions.py), [details 4](docs/implementation/installation-upgrade.md)

- Added a runnable Phoenix/Postgres private repository foundation and TanStack web interface with local identities, revocable sessions, backend membership checks, durable idempotent creation and recovery tests.
  Sources: [details 1](apps/forge/README.md), [details 2](apps/web/README.md), [details 3](docs/decisions/0002-local-identity.md), [source 4](https://github.com/FRIKKern/gitgood/pull/7)

- Retain exact native generation records under the independently bound installation lifecycle lock. Preserve interrupted temporary files and original records across retries; reject replaced custody, foreign chains and generation-ID reuse. Active publication, database writer exclusion and lifecycle reconciliation remain unfinished.
  Sources: [details 1](docs/implementation/native-generation-custody.md), [details 2](tools/deployment/generation_custody.py)

- Add a poisoning read-only generation guard, fixed bounded observation stream and linked Elixir monitor with a freshness-bound ownership context. Periodic checks preserve the captured owner, scope, publication and persistent file identity without acquiring another database lease; application wiring and generation-aware markers remain unfinished.
  Sources: [details 1](docs/implementation/native-generation-lease-guard.md), [details 2](apps/forge/lib/gitgood/installation_generation_monitor.ex), [details 3](tools/deployment/native_generation_lease_guard.py)

- Publish stopped native resource generations under independently bound lifecycle custody and an actual database writer lease, with immutable transitions, atomic pointers, lost-acknowledgement recovery and exact predecessor preservation. Application lifecycle reconciliation, allocation and Cloud acceptance remain unfinished.
  Sources: [details 1](docs/implementation/native-generation-publication.md), [details 2](tools/deployment/generation_publication.py)

- Admit actual native and maintenance owners against completed resource generations through read-only custody and repeated persistent observations. Refuse unresolved, staged or changed history without granting a writer lease, lifecycle or readiness authority.
  Sources: [details 1](docs/implementation/native-generation-reader.md), [details 2](tools/deployment/native_generation_reader.py)

- Define closed native resource-generation records with exact predecessor digests, unchanged durable identity and validated ordinary service scope. Reject foreign or reused links, privileged state, aliased groups and malformed payloads. Durable continuity, publication and lifecycle recovery remain unfinished.
  Sources: [details 1](docs/implementation/native-generation-records.md), [details 2](tools/deployment/resource_generations.py)

- Added scoped and revocable Git credentials, authenticated native smart HTTP clone/push/fetch, protected main enforcement, durable push records and bounded subprocess supervision.
  Sources: [details 1](docs/decisions/0003-native-http-transport.md), [details 2](apps/forge/README.md), [source 3](https://github.com/FRIKKern/gitgood/pull/8)

- Added a bounded disposable hosted-runner proof for actual systemd native ownership attachment and original helper, marker and PostgreSQL backend loss, with retained records, closed startup diagnostics and explicit component-only receipts.
  Sources: [details 1](docs/implementation/native-hosted-ownership.md), [details 2](tools/ci/native-owned-proof.py)

- Added fixed native enrollment/resume commands with installation-wide custody, actual resource/runtime checks, retained partial staging, packaged migration and owner observation, access probes and an initial baseline bound to every stage observation. Actual CLI staging and partial migration recovery, committed owner recovery, a first upgrade between distinct artifacts and direct initial retirement passed; current integration, other interrupted stages, supervision, allocation, Cloud and full journeys remain pending.
  Sources: [details 1](docs/implementation/native-initial-lifecycle.md), [details 2](docs/decisions/0017-native-initial-lifecycle.md)

- Observe exact private native installation resources and PostgreSQL cluster/database identity under a retained bindings digest before supervised upgrade actions.
  Sources: [details 1](tools/deployment/native_inventory.py), [details 2](tools/deployment/test_native_inventory.py), [details 3](docs/implementation/installation-upgrade.md)

- Capture the original held native database lease's Linux process identity and combine same-boot kernel/SQL absence observations without signals or replacement authority; complete native recovery remains required.
  Sources: [details 1](docs/implementation/native-kernel-backend.md), [details 2](tools/deployment/native_kernel_backend.py)

- Retain original protocol-2 lifecycle responsibility through immutable stage snapshots, explicit uncertainty and bounded publication recovery under the original OS lock.
  Sources: [details 1](docs/implementation/native-lifecycle-responsibility.md), [details 2](tools/deployment/native_lifecycle_responsibility.py)

- Retain exact lifecycle snapshot references across native generation transitions without treating unfinished stages as reconciled or admitting workers.
  Sources: [details 1](docs/implementation/native-lifecycle-transitions.md), [details 2](tools/deployment/native_lifecycle_history.py)

- Admit native and maintenance workers only in fixed recorded lifecycle windows with original protected inputs and permanently fenced guards.
  Sources: [details 1](docs/implementation/native-lifecycle-worker-admission.md), [details 2](tools/deployment/native_lifecycle_generation_reader.py)

- Introduce fixed TLS maintenance and bounded SSH routing under the installation-owned edge group; complete upgrade activation remains under verification.
  Sources: [details 1](tools/deployment/native_edge.py), [details 2](tools/deployment/test_native_edge.py), [details 3](docs/implementation/installation-upgrade.md)

- Bind native enrollment and upgrade input reads to fixed Root-sealed operations, original private file identities and digests; retain files and refuse replacements without granting lifecycle dispatch.
  Sources: [details 1](docs/implementation/native-operation-inputs.md), [details 2](tools/deployment/native_operation_inputs.py)

- Expose a read-only native operator status command for retained upgrade, activation and retirement responsibility, preserving dead-owner uncertainty and refusing mixed or private-invalid records; live readiness and Cloud inventory remain separate checks.
  Sources: [details 1](tools/deployment/native_operator.py), [details 2](docs/deployment/production.md)

- Connect captured native generation and original database lease to bounded record construction, protected publication and monitor attachment in one non-retrying application handoff. Helper loss or refusal prevents success; complete installed startup and controller reconciliation remain required.
  Sources: [details 1](docs/implementation/native-ownership-claim.md), [details 2](apps/forge/lib/gitgood/native_ownership_claim.ex)

- Inspect retained native application ownership through read-only custody, preserving uncertain files and refusing replaced storage, directories or records. Inspection grants no replacement, live ownership or readiness authority; controller reconciliation remains required.
  Sources: [details 1](docs/implementation/native-application-ownership.md), [details 2](tools/deployment/native_ownership_records.py)

- Observe original ownership record and marker custody through retained descriptors and immutable fingerprints; poison the guard after loss without repair or recapture. Protected helper linkage and complete native startup remain unfinished.
  Sources: [details 1](docs/implementation/native-ownership-marker-guard.md), [details 2](tools/deployment/native_ownership_marker_guard.py)

- Attach ownership custody and the original held session to the existing generation monitor; require immutable ownership heartbeats and terminal acknowledgement deadlines. Protected service loss and complete application startup remain unverified.
  Sources: [details 1](docs/implementation/native-ownership-monitor-attachment.md), [details 2](tools/deployment/native_monitor_ownership_attachment.py)

- Combine original generation, held database session and retained marker observations without replacement authority; batch live typed systemd properties while retaining strict bounds and permanent refusal. Protected helper attachment and current native VM timing remain unverified.
  Sources: [details 1](docs/implementation/native-ownership-observation.md), [details 2](tools/deployment/native_ownership_observation.py)

- Add durable non-replacing ownership markers, original held-backend and owner-socket observations, a protected fixed publication entry and a bounded Elixir caller with independently sealed candidate/operation admission. Interrupted effects remain retained; prior-owner reconciliation and complete native application integration remain unfinished.
  Sources: [details 1](docs/implementation/native-ownership-publication.md), [details 2](tools/deployment/native_ownership_markers.py), [details 3](tools/deployment/native_ownership_publication_entry.py)

- Construct bounded native ownership records in the Elixir application from matching captured generation, original database-session and controller-seal values. Verify all four mode outputs against the Python record grammar. Construction grants no live authority; protected publication and complete native startup integration remain required.
  Sources: [details 1](docs/implementation/native-ownership-record-construction.md), [details 2](apps/forge/lib/gitgood/native_ownership_record.ex)

- Add a native ownership startup child, fixed-path private input reader, root factory and original-helper fence before claim publication. Native application wiring and installed startup acceptance remain required.
  Sources: [details 1](docs/implementation/native-ownership-startup.md), [details 2](apps/forge/lib/gitgood/native_ownership_startup.ex), [details 3](apps/forge/lib/gitgood/native_ownership_inputs.ex), [details 4](apps/forge/lib/gitgood/native_ownership_fence.ex)

- Observe the exact original native PostgreSQL backend's absence without signalling reused PIDs, adopting a new holder or granting replacement authority; complete controller reconciliation remains required.
  Sources: [details 1](docs/implementation/native-prior-backend-observation.md), [details 2](tools/deployment/native_prior_backend.py), [details 3](tools/deployment/native_ownership_database.py)

- Remove exactly inventoried native databases and stores under retirement custody, refuse replacement resources and connected clients, and reconcile partial deletion or lost acknowledgements; complete installed retirement remains unfinished.
  Sources: [details 1](tools/deployment/retirement_database.py), [details 2](tools/deployment/retirement_stores.py), [details 3](docs/implementation/installation-retirement.md)

- Verify an installed recovery application through independently bound actors, loopback routing, private API and HTTPS/SSH Git probes, whole-group shutdown and stopped-marker observation; final removal and interruption recovery remain separate work.
  Sources: [details 1](tools/deployment/retirement_restoration.py), [details 2](docs/implementation/installation-retirement.md)

- Add a fixed native retirement operator command with independently bound private inputs, exact destructive-stage reconciliation and metadata-only terminal repeat; actual five-stage execution and pre-import owner-loss recovery passed on disposable installations.
  Sources: [details 1](tools/deployment/native_retirement.py), [details 2](docs/decisions/0013-fixed-native-retirement-executor.md)

- Retain retirement admission outside removable stores, refuse new runtime and offline leases after owner loss, and stop only enrolled kernel groups behind the held fence; complete installed retirement remains unfinished.
  Sources: [details 1](tools/deployment/retirement_fence.py), [details 2](tools/deployment/retirement_quiescence.py), [details 3](docs/implementation/installation-retirement.md)

- Retain fixed native retirement responsibility under the installation upgrade lock, with pinned intent, interrupted-owner reconciliation and explicit retained-resource observations; removal execution remains unfinished.
  Sources: [details 1](tools/deployment/retirement_journal.py), [details 2](docs/implementation/installation-retirement.md)

- Observe an existing retirement target against its authenticated archive, adapted configuration and restored database without copying or rewriting target contents; partial, changed or replaced targets remain preserved and refuse continuation.
  Sources: [details 1](apps/forge/priv/operations/retirement-restore-materialize.mjs), [details 2](docs/implementation/installation-retirement.md)

- Materialize authenticated retirement Git, SSH and configuration into a separately sealed private target with retained TLS/key checks and fixed operational adaptations, preserving partial or replaced targets; functional restoration remains unfinished.
  Sources: [details 1](apps/forge/priv/operations/retirement-restore-materialize.mjs), [details 2](docs/implementation/installation-retirement.md)

- Bind full retirement restoration inputs and fixed helpers to operation-specific delegated process groups while preserving original custody; surviving descendants refuse retry and functional restoration remains unfinished.
  Sources: [details 1](tools/deployment/retirement_restore_plan.py), [details 2](docs/implementation/installation-retirement.md)

- Bind restored-data verification to a separately sealed target and retain original retirement custody while the pinned packaged helper runs; functional application restoration and complete installed retirement remain separate work.
  Sources: [details 1](tools/deployment/retirement_restore_data.py), [details 2](docs/implementation/installation-retirement.md)

- Verify retained export contents through actual dump import into a separately identified disposable database, with matching schema, rows, sequences and locale and repeat-import refusal; complete installed retirement remains unfinished.
  Sources: [details 1](apps/forge/priv/operations/retirement-restore-data.mjs), [details 2](scripts/verify-offline-recovery.mjs), [details 3](docs/implementation/installation-retirement.md)

- Add fixed post-removal retained usability with exact source absence, private configuration custody and repeated authenticated recovery checks; actual five-stage installed removal, controller interruption, seven refusal cases and repeated status passed, while lifecycle CLI and managed Cloud remain unfinished.
  Sources: [details 1](tools/deployment/retirement_retention.py), [details 2](docs/decisions/0012-post-removal-retained-usability.md)

- Compare authenticated retained exports with live file/database fingerprints under continuously owned retirement custody, with independently bound materials and changed-writer refusals; usable restoration and complete installed retirement remain separate work.
  Sources: [details 1](tools/deployment/retirement_snapshot.py), [details 2](apps/forge/priv/operations/retirement-snapshot.mjs), [details 3](docs/implementation/installation-retirement.md)

- Recorded the completed native foundation run with criterion-level observations, exact candidate/runtime evidence, clean-start instructions, integration references and remaining private-forge/Cloud milestones.
  Sources: [details 1](docs/RUN-72H-FINISH.md)

- Add read-only admission for a separately allocated ordinary-user systemd service, with pinned unit identity, actual manager and delegated cgroups, bounded resource checks and a credential-free manager query. Require empty capability sets, no extra groups and NoNewPrivileges. Durable generations, product supervision and full lifecycle or Cloud acceptance remain unfinished.
  Sources: [details 1](docs/implementation/native-service-admission.md), [details 2](tools/deployment/native_service_scope.py)

- Added PostgreSQL-owned Ed25519 account keys, browser registration/revocation, native OTP SSH Git transport, host fingerprints and clone URLs, with shared authorization/push recovery and real-client interruption checks.
  Sources: [details 1](docs/implementation/ssh.md), [details 2](docs/decisions/0005-native-ssh.md)

- Bind fixed native migration and runtime launch actions to owned journal stages, rechecking code against its pinned archive and preserving exact whole-process shutdown without database availability.
  Sources: [details 1](tools/deployment/native_actions.py), [details 2](tools/deployment/test_native_actions.py), [details 3](docs/implementation/installation-upgrade.md)

- Retain successive native upgrade journals under one installation lock, requiring terminal recovery or completion and preserving interrupted reservations without claiming activation.
  Sources: [details 1](tools/deployment/upgrade_history.py), [details 2](tools/deployment/test_upgrade_history.py), [details 3](docs/implementation/installation-upgrade.md)

- Persist private native upgrade responsibility with fixed stages, process ownership, explicit interrupted-action reconciliation and read-only status without claiming activation.
  Sources: [details 1](tools/deployment/upgrade_journal.py), [details 2](tools/deployment/test_upgrade_journal.py), [details 3](docs/implementation/installation-upgrade.md)

- Add fixed native upgrade, previous-code recovery and forward-repair commands with independently pinned private inputs, session-independent supervised runtimes and metadata-only terminal repeat; actual seven-stage execution, bad-artifact refusal and migration-owner recovery passed on a disposable installation.
  Sources: [details 1](tools/deployment/native_upgrade_command.py), [details 2](docs/decisions/0014-fixed-native-upgrade-commands.md)

- Bind fixed authenticated upgrade probes to private actor credentials, exact schema/candidate identity and real HTTPS/SSH Git refs with redirect refusal and owned client-process exclusion.
  Sources: [details 1](tools/deployment/native_probes.py), [details 2](tools/deployment/test_native_probes.py), [details 3](docs/implementation/installation-upgrade.md)

- Observe actual native and maintenance owners within independently sealed systemd service leaves, binding helper ancestry and process births without changing controller publication authority. Generation-aware application integration remains unfinished.
  Sources: [details 1](docs/implementation/native-worker-admission.md), [details 2](tools/deployment/native_worker_scope.py)

- Hold fixed ordinary PostgreSQL writer exclusion under the native application's existing advisory key. Recheck exact backend birth, owner identity and granted lock; refuse unexpected clients or lost sessions and reap only the owned query child. Active generation publication and lifecycle reconciliation remain unfinished.
  Sources: [details 1](docs/implementation/native-writer-exclusion.md), [details 2](tools/deployment/native_writer_exclusion.py)

- Implemented coordinated encrypted offline recovery with complete-process exclusion, database locale compatibility, exact restore retry and preserved interrupted Git locks; supported recovery acceptance remains under verification.
  Sources: [details 1](docs/implementation/offline-backup.md)

- Added opaque native change landing addresses with permission-bound resolution and validated sign-in return targets, preparing source links without exposing repository names in their URLs.
  Sources: [details 1](docs/implementation/barkpark-linked-changes.md)

- Add a checksum-bound warm-read observer with independent actors, retained failures and concurrent outsider checks; actual capacity measurements remain pending.
  Sources: [details 1](scripts/pilot-read-samples.mjs), [details 2](scripts/pilot-read-samples.test.mjs), [details 3](docs/implementation/pilot-workload.md)

- Define the initial bounded pilot repository, independent concurrent actors, cache and network phases, and performance targets before measurement.
  Sources: [details 1](docs/implementation/pilot-workload.md), [details 2](QUALITY.md)

- Product scope, 17 journey specifications, delivery milestones, repository routines, and a generated roadmap are available.
  Sources: [details 1](PRODUCT.md), [details 2](JOURNEYS.md), [details 3](docs/EXECUTION.md)

- Private GitHub repository FRIKKern/gitgood established with planning verification on pushes and pull requests, current pinned GitHub Actions, and an explicit Ubuntu 24.04 runner.
  Sources: [details 1](docs/decisions/D01.md)

- Added copied production Elixir/TanStack artifacts, clean commit/spec build identity, migration/bootstrap entry points, dependency/storage readiness and an isolated full-workflow persistence experiment.
  Sources: [details 1](docs/deployment/production.md), [details 2](docs/decisions/D06.md), [source 3](https://github.com/FRIKKern/gitgood/pull/11)

- Added same-repository pull requests, exact-line comments and reviews, scoped check providers, current branch policy and atomic protected fast-forward merges with durable recovery markers.
  Sources: [details 1](docs/decisions/0004-review-check-merge-semantics.md), [details 2](docs/implementation/collaboration.md), [source 3](https://github.com/FRIKKern/gitgood/pull/10)

- Isolate temporary retirement recovery runtimes from external Barkpark effects and ordinary activation evidence, with operation-bound local startup constraints and explicit health identity; complete functional retirement remains unfinished.
  Sources: [details 1](docs/deployment/production.md), [details 2](docs/decisions/0011-isolated-retirement-verification.md)

- Added creator-owned full Git bundle import with bounded streaming intake, durable replay/provenance, atomic branches and tags, recovery markers and browser/native-client verification.
  Sources: [details 1](docs/implementation/import.md), [details 2](docs/decisions/0006-offline-bundle-import.md)

- Added an in-repository tour of the actual web interface: five screenshots, an animated README preview, browser video and ASCII companion, captured with clearly labelled synthetic API data. Added a reproducible capture command and source/media freshness checks.
  Sources: [details 1](README.md), [details 2](docs/WEB-TOUR.md), [details 3](apps/web/tour/capture.mjs), [details 4](scripts/web-tour.mjs)

### Changed

- Delegated project progression to agents and replaced human acceptance gates with recorded evidence-based verification across decisions, milestones, merges, and releases.
  Sources: [details 1](AUTONOMY.md), [details 2](QUALITY.md)

- Bounded evidence history to 20 records and 25 events per record per response, with authorized navigation and whole-history latest-result state. NUL-containing evidence text now refuses before database storage; retained records and artifact custody are unchanged.
  Sources: [details 1](docs/implementation/evidence-history.md)

- Prefer a separate EU Hetzner CCX23 project with dedicated CPU for the Gitgood pilot and a EUR 120 planning budget, while preserving measured workload and deployment gates.
  Sources: [details 1](deploy/pilot-target.md)

- Converted the top README roadmap to a milestone Gantt showing delivery surfaces and proposed research overlap; retained the detailed journey evidence map as a separate generated view.
  Sources: [details 1](docs/ROADMAP.md), [details 2](docs/images/journey-evidence.svg)

- Renamed the project from Gitpark to Gitgood, including the private GitHub repository, documentation, package metadata, roadmap SVG, and maintenance variable.
  Sources: [details 1](docs/decisions/D01.md)

- Reorganized the repository around a short README, a readable delivery overview, local setup, a code map, and grouped documentation. Added a dated progress view and navigation checks; historical reports and detailed evidence remain accessible without dominating the front page.
  Sources: [details 1](README.md), [details 2](docs/README.md), [details 3](docs/DEVELOPMENT.md), [details 4](docs/CODEBASE.md), [details 5](docs/STATUS.md), [details 6](CONTRIBUTING.md), [details 7](deploy/README.md), [details 8](docs/decisions/D06.md), [details 9](scripts/render.mjs)

- Route required planning and forge jobs to the measured isolated ephemeral Linux runner after real GitHub dispatch proof, verifying the build platform and installer image identity while preserving tests and full production recovery.
  Sources: [details 1](docs/implementation/isolated-ci.md)

- Require a local disk-space reserve before large development allocations and prefer hosted verification while preserving source, recovery material and retained evidence during cache cleanup.
  Sources: [details 1](AGENTS.md), [details 2](docs/DEVELOPMENT.md)

- Hash the five Root-controlled executables once per generation-guard capture, with repeated original file custody checks and both configuration/database observations retained; actual service timing remains unverified.
  Sources: [details 1](docs/implementation/native-generation-lease-guard.md), [details 2](docs/implementation/native-durable-bindings.md), [details 3](tools/deployment/native_durable_binding.py)

- Record actual current-CLI recovery after selected owner loss in all seven initial installation stages, lost terminal baseline handoff, and packaged installation with an ordinary database-owner role. Preserve failed harness attempts and private recovery materials; identify systemd delegation and explicit reboot resource generations as the next host dependencies. These same-boot fixtures do not establish managed Cloud or complete journey/release acceptance.
  Sources: [details 1](docs/implementation/native-initial-lifecycle.md), [details 2](docs/implementation/native-host-prerequisites.md)

- Require original SQL and kernel backend identity in new native ownership claims and monitoring; preserve older records as history and refuse their live readmission. Installed startup and controller recovery remain unfinished.
  Sources: [details 1](docs/implementation/native-kernel-ownership.md), [details 2](apps/forge/lib/gitgood/native_ownership_claim.ex), [details 3](tools/deployment/native_ownership_records.py)

- Record the retained native ownership attachment failure after fresh generation admission and a publication receipt; preserve the failed VM materials and native startup refusal while investigating under unchanged limits.
  Sources: [details 1](docs/implementation/native-ownership-monitor-attachment.md), [details 2](docs/implementation/native-selected-systemd-properties.md)

- Read the fifteen required systemd properties in a bounded live batch with original library custody before and after the batch; preserve typed replies, permanent refusal and existing freshness limits. Installed timing and full native acceptance remain unverified.
  Sources: [details 1](docs/implementation/native-selected-systemd-properties.md), [details 2](tools/deployment/native_systemd_properties.py)

- Record actual ordinary-user systemd delegation, whole-unit descendant cleanup and bounded manager-loss restart. Select a distinct resource-generation profile with immutable original lifecycle history and explicit continuity. The product supervisor, generation protocol, actual reboot, allocation and Cloud acceptance remain unfinished.
  Sources: [details 1](docs/decisions/0018-native-supervision-generations.md), [details 2](docs/implementation/native-supervision-profile.md)

- Added permission-filtered native search and activity, opaque collaboration links, shared browser access invalidation and audited owner controls for team membership; corrected merge crash proof to bind the clean source candidate and requirement.
  Sources: [details 1](docs/implementation/activity.md), [details 2](docs/decisions/0008-private-discovery.md)

- Authorize public source development and move planning and forge verification to disposable GitHub-hosted Ubuntu 24.04 runners. Preserve pinned native dependencies, non-root workspace ownership, cgroup exclusion and recovery checks; prepare an identical job-owned Node binary with native-safe permissions, retire the local dispatch probe and document private vulnerability reporting without adding a software license.
  Sources: [details 1](docs/decisions/D01.md), [details 2](docs/implementation/isolated-ci.md), [details 3](.github/workflows/product.yml), [details 4](.github/workflows/verify.yml), [details 5](SECURITY.md)

- Keep the pre-release README summary compact with pending changelog counts and category totals, while preserving every detailed entry and source reference in CHANGELOG.
  Sources: [details 1](changelog/ROUTINE.md), [details 2](scripts/render.mjs)

- Redesigned the README roadmap with journey-level status, milestone dependencies and exit criteria, separate progress summaries, and light/dark palettes.
  Sources: [details 1](docs/ROADMAP.md), [details 2](scripts/roadmap-svg.mjs)

### Fixed

- Wait for the successful activity baseline and observe the actual failed refresh before evaluating source-unavailable browser behavior, preserving the failed main-run evidence.
  Sources: [details 1](apps/web/e2e/activity.spec.ts), [details 2](docs/decisions/0008-private-discovery.md)

- Bound managed Git packing to two threads so many-core hosts retain functional HTTPS/SSH transfer within the existing worker memory ceiling.
  Sources: [details 1](docs/implementation/ssh.md), [details 2](apps/forge/README.md)

- Bound concurrent browse requests with four active readers, eight waiting callers and a five-second admission deadline; temporary Git capacity failures return retryable service errors.
  Sources: [details 1](docs/implementation/browsing.md)

- Sequence repository branch and selected commit reads, and admit pull-request revision reads through the same bounded queue; preserve retryable capacity refusals without raising resource limits.
  Sources: [details 1](docs/implementation/browsing.md)

- Align each isolated CI worker's private cgroup namespace with its delegated mount and make owned job directories traversable, preserving actual backup writer-exclusion checks.
  Sources: [details 1](.github/workflows/product.yml), [details 2](docs/implementation/isolated-ci.md)

- Declare and verify the native Python and Git executable paths required by copied-production interrupted-writer recovery in Linux CI.
  Sources: [details 1](.github/workflows/product.yml), [details 2](docs/implementation/isolated-ci.md)

- Install and verify OpenSSH client tools in required Linux CI instead of assuming a prepopulated runner image; retain actual SSH authorization and transport checks.
  Sources: [details 1](.github/workflows/product.yml)

- Replaced the shared production proxy login bucket with authenticated edge/socket client addresses, preserving per-address limits and rejecting forged forwarding assertions.
  Sources: [details 1](docs/implementation/client-address.md)

- Navigate repository cards, files, history and pull-request lists through the web router while retaining shareable URLs and disabling speculative reads.
  Sources: [details 1](docs/implementation/browsing.md)

- Preserve exact evidence requests in encrypted native custody across reload, navigation and panel unmount, with actor-only recovery, separate receipt acknowledgement and safe retirement.
  Sources: [details 1](docs/implementation/criterion-evidence.md)

- Preserve the original connection-generation refusal when retrying a saved evidence draft, retaining its responsibility without poisoning the surrounding database transaction or creating a new assessment.
  Sources: [details 1](docs/implementation/criterion-evidence.md)

- Preserve the original browser evidence request across lost responses and Source revision changes, with explicit retry and native receipt validation.
  Sources: [details 1](docs/implementation/criterion-evidence.md)

- Resolve exact actor-bound evidence receipts before validating new creation inputs. Legacy protected bytes keep their checksum; changed bodies conflict and revoked native writers cannot replay receipts.
  Sources: [details 1](docs/implementation/criterion-evidence.md)

- Accept and preserve the exact first-install UUID in encrypted export and recovery configuration, reject mismatched identity before publication, and rebind it only for an independently allocated retirement verification target. Fresh packaged enrollment and direct five-stage retirement passed without any prior upgrade; terminal/refusal checks and 77-log credential checks passed. Actual partial migration recovery resumed after three of sixteen commits; current integration CI and broader lifecycle/Cloud acceptance remain separate.
  Sources: [details 1](docs/implementation/native-initial-lifecycle.md), [details 2](docs/implementation/installation-retirement.md)

- Pin native ownership database observations and the held lease connection to the PostgreSQL catalog search path and read-only statements.
  Sources: [details 1](docs/implementation/native-database-namespace.md), [details 2](apps/forge/lib/gitgood/native_database_lease.ex), [details 3](tools/deployment/native_ownership_database.py)

- Reject native ownership acknowledgements after their absolute attachment deadline even when the timer message is delayed; retain the three-second limit and native startup refusal pending installed proof.
  Sources: [details 1](apps/forge/lib/gitgood/installation_generation_monitor.ex), [details 2](docs/implementation/native-ownership-monitor-attachment.md)

- Use one complete generation/session/marker bracket for initial ownership attachment and consume its result once; retain fresh checks on later heartbeats and all original deadlines, refusal and authority limits. Installed proof remains pending.
  Sources: [details 1](docs/implementation/native-ownership-monitor-attachment.md), [details 2](tools/deployment/native_ownership_observation.py), [details 3](tools/deployment/native_monitor_ownership_attachment.py)

- Build digest-pinned PostgreSQL 18.4 server and recovery clients in the isolated Ubuntu runner, preserving exact recovery versions and the same-OS database locale profile.
  Sources: [details 1](tools/ci/install-postgres-18.4.sh), [details 2](.github/workflows/product.yml)

- Bound disposable retirement input-fixture cleanup with the existing production database-removal limits while preserving identity checks, no-force behavior and product deadlines.
  Sources: [details 1](docs/implementation/native-retirement-fixture-cleanup.md), [details 2](tools/deployment/test_native_retirement.py)

- Require native ownership startup to match its clean compiled build candidate to the Root seal before database lease acquisition and publication.
  Sources: [details 1](docs/implementation/native-ownership-startup.md), [details 2](apps/forge/lib/gitgood/native_ownership_startup.ex)

- Exercise unsupported native root startup in a bounded separate BEAM so the running development supervisor cannot mask the expected refusal; preserve the parent application and production ownership guards.
  Sources: [details 1](apps/forge/test/gitgood/native_ownership_startup_test.exs), [details 2](docs/implementation/native-ownership-startup.md)

- Install the Ubuntu systemd runtime in isolated CI so native root-file custody and installed-version tests execute against actual protected executables instead of failing on missing files.
  Sources: [details 1](.github/workflows/product.yml), [details 2](docs/implementation/native-generation-lease-guard.md)

- Exclude surviving runtime writers from production migration and Linux replacement admission, validating the new startup lineage while retaining first-install migration support.
  Sources: [details 1](apps/forge/lib/gitgood/installation_lease.ex), [details 2](apps/forge/priv/operations/process_status.py), [details 3](apps/forge/test/gitgood/installation_lease_test.exs), [details 4](scripts/verify-offline-recovery.mjs), [details 5](scripts/verify-production.mjs), [details 6](docs/implementation/installation-upgrade.md)

- Select distinct available copied-production fixture TCP ports below the observed outbound ephemeral range, preserving explicit targets and unrelated listeners after a real web bind collision.
  Sources: [details 1](scripts/verification-component-ports.mjs), [details 2](scripts/verification-component-ports.test.mjs), [details 3](scripts/verify-production.mjs)

- Capture current pull-request branch revisions in bounded Git reads, bind diffs to their immutable objects and require matching browser context before review actions.
  Sources: [details 1](docs/implementation/browsing.md), [details 2](docs/implementation/collaboration.md)

- Disabled automatic distributed Erlang registration for single-host releases after a real concurrent Windows/Linux node collision; added populated/history-only Barkpark migration refusal and a fresh-VM encrypted-account retention fixture.
  Sources: [details 1](docs/decisions/0010-single-host-releases.md), [details 2](docs/deployment/production.md), [details 3](docs/implementation/barkpark-accounts.md)

- Target the protected membership migration in populated downgrade verification, check complete audit retention and restore the current schema before a fresh-process check.
  Sources: [details 1](apps/forge/verification/discovery_upgrade.exs), [details 2](docs/implementation/activity.md)

- Select copied-production Caddy fixture ports only after both TCP and UDP bind successfully. Bounded retries preserve unrelated listeners and retain the HTTP/3 listener instead of dropping its protocol.
  Sources: [details 1](scripts/verification-edge-port.mjs)
