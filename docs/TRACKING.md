# Tracking and report contract

Barkpark will be the execution ledger. Its Gitpark goal ID is unconfigured. Do not reuse Barkpark Studio's goal or create a second live status list in these documents.

The milestone and journey catalogs are normative planning structure. evidence/status.json is a validated observation snapshot for derived views, not an editable replacement ledger. Source adapters are future S09/S16 work.

The initial snapshot contains no connected sources and no implementation, verification, or release records. Render those states as unverified/unconfigured, not zero completed work confirmed by measurement.

For live integration, map each task to journey IDs, each evidence manifest to criterion IDs and code/spec revisions, and each release to exact artifacts/commit. Closing a task only affects work state. Verification requires valid supporting manifests and acceptance criteria; release requires a published release record.

Fetch updates into a candidate snapshot, validate, then replace atomically. Preserve old observedAt and values after failed reads and record fetch health separately. A source timestamp over 24 hours old is stale. A future timestamp is invalid.

The SVG is generated from catalogs and this snapshot. Branch protection, scheduling, ledger fetch, deduplicated alerts, and automated publishing need remote setup and are not implied by checked-in workflow definitions.
