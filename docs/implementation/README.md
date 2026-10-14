# Implementation reference

[Documentation home](../README.md) · [Development guide](../DEVELOPMENT.md) · [Codebase guide](../CODEBASE.md) · [Progress snapshot](../STATUS.md)

Use this index when you need the design, limitations or reproduction steps for a particular behavior. These documents include scoped experiments and retained results from different candidates. A passing component check does not accept a whole journey or release; use the [journey specifications](../../JOURNEYS.md), [quality rules](../../QUALITY.md) and [reporting contract](../TRACKING.md) for that distinction.

## Repositories and collaboration

| Read about… | Document |
|---|---|
| Files, trees, history and diffs | [Commit browsing](browsing.md) |
| Pull requests, reviews, checks and interrupted merges | [Collaboration and recovery](collaboration.md) |
| SSH keys and Git transport | [Native SSH](ssh.md) |
| Bringing an existing repository into Gitgood | [Supported import](import.md) |
| Supported Git formats and client behavior | [Git compatibility](git-compatibility.md) |
| Tags, release records and private assets | [Release workflow](releases.md) |
| Permission-aware search and activity | [Private discovery](activity.md) |
| Login requests through the web proxy | [Client address and proxy boundary](client-address.md) |

## Barkpark links and evidence

| Read about… | Document |
|---|---|
| Calling supported Barkpark APIs | [Connection boundary](barkpark.md) |
| Connecting an individual Gitgood account | [Private Barkpark accounts](barkpark-accounts.md) |
| Keeping native and source permissions separate | [Native link records](barkpark-records.md) |
| Showing linked work on a change page | [Linked changes](barkpark-linked-changes.md) |
| Linking a Paper back to Gitgood | [Journaled return links](barkpark-return-pointers.md) |
| Attaching a result to a specific requirement | [Criterion evidence](criterion-evidence.md) |
| Browsing retained evidence and reassessments | [Evidence history](evidence-history.md) |
| Reading protected verification results for reporting | [Delivery evaluations](delivery-evaluations.md) |

## Installation and recovery

These are operational implementation references. Begin with the [packaging experiment](../deployment/production.md) and [operational acceptance requirements](../operations/README.md) before following an individual procedure.

| Read about… | Document |
|---|---|
| Checking an already allocated empty host | [Initial allocation admission](initial-allocation-admission.md) |
| Preserving responsibility during a first installation | [Initial enrollment journal](initial-enrollment-journal.md) |
| Validating private first-install inputs | [Enrollment input custody](native-enrollment-inputs.md) |
| Creating the first installation owner safely | [Owner bootstrap](installation-owner-bootstrap.md) |
| Executing and resuming initial installation | [Initial lifecycle](native-initial-lifecycle.md) |
| Recording unfinished installation steps and their original inputs | [Lifecycle responsibility](native-lifecycle-responsibility.md) |
| Retaining that responsibility when service generations change | [Lifecycle transitions](native-lifecycle-transitions.md) |
| Starting workers only during their recorded lifecycle stages | [Lifecycle worker admission](native-lifecycle-worker-admission.md) |
| Reading original private migration and first-owner inputs | [Lifecycle business inputs](native-lifecycle-business-inputs.md) |
| Applying fixed migrations and creating the first owner | [Native maintenance effects](native-maintenance-effects.md) |
| Starting actual product workers under native ownership | [Native runtime effects](native-runtime-effects.md) |
| Running the fixed frontend and TLS edge under the original controller | [Native public runtime](native-public-runtime.md) |
| Booting the ordinary packaged release under native ownership | [Default native startup](native-default-startup.md) |
| Installing an upgrade and recovering a failure | [Controlled upgrades](installation-upgrade.md) |
| Coordinating Git, Postgres and configuration backups | [Offline backup and recovery](offline-backup.md) |
| Exporting and removing an installation | [Installation retirement](installation-retirement.md) |

## Native service supervision

This work connects application processes to their actual host, database and service ownership. The documents describe individual prerequisites and checks; their presence does not establish a supported managed deployment.

| Read about… | Document |
|---|---|
| Required Linux host capabilities | [Host prerequisites](native-host-prerequisites.md) |
| The systemd service experiment | [Supervision profile](native-supervision-profile.md) |
| Checking the actual service before use | [Service admission](native-service-admission.md) |
| Separating installation identity from process lifetimes | [Persistent installation bindings](native-durable-bindings.md) |
| Excluding competing database writers | [Writer exclusion](native-writer-exclusion.md) |
| Recording a particular set of host resources | [Resource-generation records](native-generation-records.md) |
| Preserving protected records during use | [Generation custody](native-generation-custody.md) |
| Publishing a stopped resource generation | [Generation publication](native-generation-publication.md) |
| Reading published generation identity | [Generation reader](native-generation-reader.md) |
| Checking ownership throughout an operation | [Periodic generation guard](native-generation-lease-guard.md) |
| Admitting runtime and maintenance workers | [Worker admission](native-worker-admission.md) |
| Checking generation and database identity from Elixir | [Elixir admission](native-elixir-generation-admission.md) |
| Connecting these checks to application startup | [Application ownership](native-application-ownership.md) |
| Matching actual application settings to protected installation inputs | [Native application configuration](native-application-configuration.md) |
| Reading a bounded set of actual service properties | [Selected systemd properties](native-selected-systemd-properties.md) |
| Checking the original application and database owner | [Ownership observation](native-ownership-observation.md) |
| Publishing retained ownership without replacing prior responsibility | [Ownership publication](native-ownership-publication.md) |
| Detecting changed or missing ownership markers | [Ownership marker guard](native-ownership-marker-guard.md) |
| Keeping the original owner attached to its generation monitor | [Monitor attachment](native-ownership-monitor-attachment.md) |
| Binding a claim to the captured generation, owner and database session | [Ownership record construction](native-ownership-record-construction.md) |
| Publishing and attaching ownership before application startup | [Ownership handoff](native-ownership-claim.md) |
| Resolving lease checks against trusted PostgreSQL catalogs | [Ownership SQL namespace](native-database-namespace.md) |
| Distinguishing original backend activity absence from a reused PID | [Prior backend observation](native-prior-backend-observation.md) |
| Requiring the original PostgreSQL process to disappear under the same host scope | [Kernel backend identity and absence](native-kernel-backend.md) |
| Reading fixed local commands from the admitted Linux account | [Controller command framing](native-command-wire.md) |
| Binding the original database lease to its protected kernel observation | [Backend observation bridge](native-backend-observation.md) |
| Retaining and monitoring the original backend process with ownership | [Kernel identity in ownership](native-kernel-ownership.md) |
| Claiming ownership before workers and aborting when an original helper exits | [Native startup boundary](native-ownership-startup.md) |
| Keeping the original local controller listener under protected service custody | [Controller endpoint ownership](native-command-endpoint.md) |
| Root observing the original controller before protected artifact staging | [Root controller observation](native-root-controller.md) |
| Copying inspected artifacts into bounded, read-only Root-controlled code | [Protected native artifact staging](native-protected-artifact.md) |
| Root reading the original request, complete generation and lifecycle history | [Root lifecycle observation](native-root-lifecycle.md) |
| Root comparing live files, binaries and database with the original sealed binding | [Root live resource observation](native-root-live-binding.md) |
| Root authenticating the original controller and its held history descriptor | [Original controller requests](native-root-controller-request.md) |
| Root observing the original controller's actual database lease, client and backend | [Original database exclusion](native-root-database-exclusion.md) |
| Binding enrollment and upgrade commands to their original protected inputs | [Operation input custody](native-operation-inputs.md) |

## Verification environment

| Read about… | Document |
|---|---|
| The isolated Linux environment used by CI | [Development CI](isolated-ci.md) |
| Attaching real systemd ownership and observing original owner loss on disposable CI | [Hosted ownership component proof](native-hosted-ownership.md) |
| Measuring a realistic private-team workload | [Pilot workload](pilot-workload.md) |
| Cleaning disposable retirement test databases within separate time bounds | [Retirement fixture cleanup](native-retirement-fixture-cleanup.md) |

Start ordinary development checks through the [development guide](../DEVELOPMENT.md). Detailed fixtures may need dedicated databases, private inputs or disposable hosts; use each document's stated environment and preserve candidate identities when interpreting its results.
