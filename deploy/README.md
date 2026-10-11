# Deploying Gitgood through Barkpark Cloud

[Documentation](../docs/README.md) · [Packaging experiment](../docs/deployment/production.md) · [Operational acceptance](../docs/operations/README.md)

**The managed Cloud integration is unfinished.** The repository contains application packaging and native lifecycle components, but this directory is a design contract, not an installable Cloud package.

## Pilot environment

The [pilot target](pilot-target.md) owns the proposed provider, host profile, location, and budget. A proposal does not establish an allocation or a working installation. Keep the pilot separate from CI and untrusted execution, with independent credentials and storage; CI also needs its own budget.

## Who owns what

| Gitgood | Barkpark Cloud |
|---|---|
| Forge/web release artifacts and matching build identity | Validation, allocation and inventory of the owned installation |
| Application permissions, migrations and functional readiness | Routing and constrained lifecycle orchestration |
| Git repositories, collaboration data and application recovery rules | Reported installation state and access to supported lifecycle actions |

The installed forge must continue ordinary authentication and Git operations during a Cloud outage. Cloud installation ownership does not grant repository access.

## What the workload contract must cover

The descriptor must bind immutable artifact digests, supported CPU/runtime, required binaries, database and Git storage, secret references, HTTP/SSH routes, owner bootstrap, migrations, functional health, backup/restore, and upgrade compatibility. Keep replaceable code separate from mutable application data.

Use fixed, reviewed lifecycle actions and scoped credentials. A descriptor must not grant arbitrary host shell execution. The [controlled native upgrade work](../docs/implementation/installation-upgrade.md) describes the application-side components and their current proof boundaries.

## Existing Cloud features and the missing adapter

The inspected Cloud Node deployment path expects Next.js standalone output. Gitgood's TanStack entry and paired Elixir release require a supported native workload adapter. Existing Barkpark archives cover Barkpark stores; coordinated Gitgood recovery must also include Git repositories and every other authoritative store.

Cloud support-instance provisioning creates a Barkpark instance tied to its parent data and fleet. It does not provide an independently configured Gitgood CI runner or native forge installation. Reusing that route requires a separate supported contract; choosing a different instance name is insufficient.

[Packaging decision D06](../docs/decisions/D06.md) records the source audit and unresolved Cloud boundary. [Backup decision D07](../docs/decisions/D07.md) defines coordinated recovery. Complete installation, upgrade, replacement-host restore, export and removal must pass before this path is called supported.
