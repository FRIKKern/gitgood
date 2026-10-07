# Product contract

## Purpose

Gitgood is a native private-team forge that makes the relationship between intended behavior, implementation, review, verification, and release understandable. Normal small changes should remain easy; a formal specification is not mandatory for every edit.

## Settled direction

- Own the forge backend in Elixir using standard Git, rather than Forgejo as the production backend.
- Use Postgres for collaboration and operation records, and Git for code objects and refs.
- Follow the proposed React/TypeScript/TanStack interface direction and validate actual production packaging early.
- Reuse Barkpark only through verified contracts.
- Make Barkpark Cloud the managed deployment path while preserving independent installation operation.

## Proposed first release

Serve our own small development team, then selected private teams. Support private repositories, team membership, scoped credentials, HTTPS and SSH clone/push, supported repository import, browsing, same-repository pull requests, line discussions, protected merge, trusted external checks, connected tasks/specifications, evidence, basic releases/assets, and permission-aware activity.

Include reproducible self-hosted packaging plus Cloud installation, upgrades, backup, replacement-host restore, export, and archive/removal. A recovery procedure is part of the product.

Begin with one documented merge strategy. Forks and additional strategies need separate scope decisions. Decide Git LFS, submodules, signed commits, shallow/partial clones, and repository-format compatibility before claiming support. SSH follows HTTPS during development but is included in the proposed release.

## Explicit exclusions

Public hosting, federation, hosted CI execution, hosted agent execution, package registries, multi-region replication, plugin marketplaces, complex merge queues, and universal importer parity are outside the first release. Agents may submit changes through scoped APIs and ordinary Git under the same rules as people.

Evidence can link to acceptance criteria in the first release. Making arbitrary document criteria mandatory merge gates is deferred until its enforcement semantics are proven.

## Success

A pilot team completes its agreed daily workflow without hidden manual database edits or unexplained status. Every scoped journey has current evidence against the release candidate. Permissions, merge correctness, and restoration meet QUALITY.md. Scope acceptance and ownership are recorded before a release is called complete.

## Scope control

Frikk is the product decision owner. Record each scope change, rationale, affected journeys, displaced work, and estimate impact through a PR. Deferred requirements are not counted as passed. Product scope is a proposed baseline until confirmed; the native architecture direction is accepted.

Do not promise offline editing, lossless migration from every forge, or zero-downtime upgrades without evidence.
