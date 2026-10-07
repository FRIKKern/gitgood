# Operational acceptance

Do not host authoritative project history exclusively on Gitpark before recovery and export are proven. Retain independent release artifacts and bootstrap instructions.

## Installation

Document supported OS/CPU, pinned runtime/artifacts, domain and transport endpoints, secret creation, owner bootstrap, database roles, persistent stores, migrations, and functional probes. Repeat on a fresh target.

## Upgrade

Record compatibility before activation. Verify expected artifacts, migrate with controlled ordering, test readiness and a functional probe, then switch routing. If old code cannot use the new schema, do not promise instant rollback. Document maintenance windows and forward repair.

## Backup

Include Git objects/refs, forge metadata, adopted Barkpark stores, assets, configuration, and required recoverable secret material. Define an application-consistent recovery point, initially testing a bounded write pause. Record versions, checksums, retention, and encryption handling.

## Restore exercise

Restore onto another host. Verify identities and access, expected refs/history, pull-request records and artifacts. An authorized clone and new push must succeed; a denied user must remain denied. Record elapsed recovery time and data-loss boundary against agreed targets.

## Archive and removal

Explain retention and export before removal. Verify the archived set is complete, revoke installation credentials where appropriate, and avoid orphaned resources. Apply irreversible lifecycle actions only in explicitly authorized environments.

## Incident readiness

Record symptoms, correlation IDs, known recovery paths, and escalation ownership. Cloud failure must not stop normal installed-product operation. Do not turn an inaccessible health check into a success.
