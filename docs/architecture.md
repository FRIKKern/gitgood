# Architecture and ownership

## Boundaries

The initial shape is one modular Elixir backend plus a React/TanStack web application. Additional processes do not automatically require additional deployed services.

| Component | Owns |
|---|---|
| Browser | Interaction state, drafts, navigation, rendering |
| TanStack server | Browser sessions and backend request composition |
| Gitpark API | Forge authorization, reviews, policies, checks, operation records, APIs/events |
| Git boundary | Validated command arguments, transport hooks, timeouts, resource limits, expected-ref checks |
| Git repositories | Code objects and refs |
| Gitpark Postgres | Forge metadata, durable jobs, audit/operation records, relationship mappings |
| Barkpark | Adopted document/task/media responsibility through verified contracts |
| Artifact storage | Assets and evidence with explicit access rules |
| Cloud | Installation administration, desired releases, lifecycle orchestration |
| Host runtime | Actual release, storage bindings, service execution |

## Identity decision

Cloud billing/installation ownership and repository authorization are distinct. A Cloud owner must not silently bypass repository rules. Decide local identity versus supported identity-provider integration, initial-owner bootstrap, service identity, revocation, and recovery in D02 before authenticated writes.

The product must continue normal authentication and Git operations during Cloud control-plane outages.

## Durable operations

Git and Postgres do not share a transaction. Plan a durable record with expected refs, actor, policy context, idempotency key, attempt history, observed result, and reconciliation state.

Persist responsibility before performing the Git side effect. Use conditional updates and repository-level coordination as required. Verify behavior under concurrent pushes and service termination. Never claim exactly-once execution merely because a queue retries.

## Data lifecycle

Keep immutable release artifacts separate from repository volumes and databases. A restore point must coordinate every adopted authoritative store. Initial write-pause backup is an experiment, not a guaranteed implementation.

## API discipline

Begin with the endpoints and events needed by J01/J02. Version public contracts, validate inputs, correlate requests, and make errors actionable. Do not add a generic adapter framework before a second proven need.

## Compatibility

Pin Barkpark/runtime versions and validate real APIs. Record supported Git operations and known exclusions. Use an explicit upgrade path for shared schemas and store-format changes.
