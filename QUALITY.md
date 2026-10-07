# Quality and acceptance

## Invariants

| ID | Required property |
|---|---|
| I01 | Private data stays private across Git, APIs, events, search, assets, and caches. |
| I02 | Backend authorization governs every operation; UI controls are not enforcement. |
| I03 | A protected merge applies only the source/target state validated under current policy. Changes require re-evaluation. |
| I04 | Retries cannot silently apply a consequential operation twice. |
| I05 | Restarts preserve durable responsibility for unfinished work. |
| I06 | Partial success is reconciled against actual Git and database state; uncertainty stays visible. |
| I07 | Every authoritative record has one owner. |
| I08 | Consequential actions identify the actual user or service actor. |
| I09 | Activation verifies expected artifact identity and functional readiness. |
| I10 | Backup readiness requires successful restoration of code, collaboration data, and access rules. |
| I11 | Secrets do not enter browser bundles, logs, fixtures, or ordinary evidence. |
| I12 | Untrusted execution is outside application credentials and storage. |

## Proof

Use browser checks for interactions, real Git-client tests for transport, backend tests for rules, and interruption/restore exercises for recovery. Unit tests do not substitute for a complete journey. A browser clip does not prove invisible authorization properties.

Record every detailed criterion in its journey specification and every result in an evidence manifest. A task closing or a PR merging does not establish verification.

A changed requirement or relevant implementation requires evidence reassessment. Cross-commit evidence needs an explicit applicability decision; this planning reporter conservatively treats different commits as stale.

## Measurements

Before M4 acceptance, specify representative repository sizes, file counts, diff size, concurrent sessions/jobs, hardware, network, cache state, latency percentiles, and capacity targets. Measure browser interaction, browse/diff latency, event freshness, and bounded background resource use.

Before M6 acceptance, set maximum tolerated data loss and restoration time, then measure both. These targets are deliberately not invented before the workload experiments.

## Review

Assign an engineering lead, quality reviewer, and operations owner before their acceptance gates. The implementer cannot unilaterally accept a high-risk journey. Frikk accepts product scope; technical reviewers accept technical evidence. CI supports those decisions.

## Release gate

All required journeys need current verification for the candidate, documented compatibility, and no open blocking access, data-loss, merge, or recovery defects. Installation and replacement-host restore must pass. Publish immutable artifacts and exact release identity.

Run `npm run release:check` for the report-level gate. It intentionally fails with the initial unconfigured evidence. It is not a substitute for artifact inspection, review sign-off, or the actual release workflow.
