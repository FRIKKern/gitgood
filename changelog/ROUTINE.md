# Changelog routine

## Per change

Add a JSON fragment in changelog/fragments for user-visible behavior, APIs, operations, compatibility, or security changes. Internal-only work can omit it with a reviewed PR explanation. A fragment has a unique id, category, user-facing summary, release impact, source references, and optional journey IDs.

Keep merged work in Unreleased. No release version is inferred from commit titles or task closure. Source references for the planning baseline point to local deliverables; real implementation entries require the actual PR/commit.

## Weekly

Produce a short development digest only when meaningful changes exist. Separate published work, merged-unreleased work, and remaining limits. Skip empty editions. A future Barkpark Paper can hold the digest; record its canonical link rather than maintaining conflicting histories.

## Release

Select fragments from the actual included revisions, including backports and cherry-picks. Use changelog/releases.json as the publication manifest. An agent acting as release editor verifies claims, migration requirements, compatibility, and rollback limitations before publication. Record that evaluation; no human editorial acceptance is required.

The local generator derives CHANGELOG.md and README highlights from fragments and release manifests. It does not publish a release. Retain each fragment's version mapping; duplicate IDs or multiple assignments fail checks. Never label an unreleased claim shipped.

Before the first release, README shows the number and categories of pending
entries with a link to the complete Unreleased changelog. It does not concatenate
the development history into a growing paragraph. Published releases retain their
three-entry summary; CHANGELOG keeps every included entry and source reference.

Cloud shows the release actually running, not the latest available release.

## Corrections and sensitive changes

Withdraw reverted Unreleased entries. Consolidate related changes and keep traceability. Add dated corrections to published claims through a reviewed change; preserve the original release identity. Coordinate security disclosure under SECURITY.md, excluding unpatched exploit details from public fragments.

## Automation and acceptance

Publish generated changes through the same checked PR route as roadmap updates. Agents merge when current checks and verification pass, without a human approval step. An unattended merge service or external posting integration is not configured by this planning skeleton. Retry publication without duplication, preserve prior content on failure, and alert once per actionable failure.

Before S17 closes, demonstrate a user-visible fragment, an internal-only exemption, withdrawal/revert, release-specific selection, migration notices, duplicate-safe reruns, README updates, and publication-failure recovery. Local generator tests cover only the reporting portion.
