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
| Reading a bounded set of actual service properties | [Selected systemd properties](native-selected-systemd-properties.md) |
| Checking the original application and database owner | [Ownership observation](native-ownership-observation.md) |
| Publishing retained ownership without replacing prior responsibility | [Ownership publication](native-ownership-publication.md) |
| Detecting changed or missing ownership markers | [Ownership marker guard](native-ownership-marker-guard.md) |
| Keeping the original owner attached to its generation monitor | [Monitor attachment](native-ownership-monitor-attachment.md) |
| Binding a claim to the captured generation, owner and database session | [Ownership record construction](native-ownership-record-construction.md) |
| Publishing and attaching ownership before application startup | [Ownership handoff](native-ownership-claim.md) |
| Resolving lease checks against trusted PostgreSQL catalogs | [Ownership SQL namespace](native-database-namespace.md) |
| Distinguishing original backend activity absence from a reused PID | [Prior backend observation](native-prior-backend-observation.md) |

## Verification environment

| Read about… | Document |
|---|---|
| The isolated Linux environment used by CI | [Development CI](isolated-ci.md) |
| Measuring a realistic private-team workload | [Pilot workload](pilot-workload.md) |

Start ordinary development checks through the [development guide](../DEVELOPMENT.md). Detailed fixtures may need dedicated databases, private inputs or disposable hosts; use each document's stated environment and preserve candidate identities when interpreting its results.
