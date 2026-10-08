# Basic private releases and transactional assets

Status: experimental design; current candidate verification is required before integration.

J12 uses an explicit release record owned by Gitgood. It pins an existing tag object and peeled commit, a chosen ancestor boundary, bounded server-derived commit subjects, author-written plain notes and checksummed immutable assets. A draft is not published. A release is not a deployment or proof that its uploaded files were produced by a particular compiler.

Publication requires the current session/membership lease, the current draft revision, a SHA-256 acknowledgment of the notes being reviewed, an unchanged tag identity, at least one asset, and every reserved asset ready with its declared size/digest. The lease serializes with receive-pack and protected merges. Native HTTPS and SSH now accept creation of valid tags through their existing durable push responsibility; tag replacement/deletion remain denied. Imported lightweight and annotated commit tags can also be used. Branch names and blob/tree tags cannot substitute for a release identity.

For the initial bounded team product, each asset is 1 byte to 16 MiB, at most eight active assets per release. Postgres bytea owns its bytes, identity and state in the same transaction. This deliberately adds assets to database backup/capacity requirements and avoids a second filesystem commit/reconciliation boundary. The proxy streams intake with backpressure; the forge buffers one bounded body under the four-slot admission limit. Larger assets/object storage need a separate measured lifecycle contract.

Draft intent, immutable upload and publication retries converge. Concurrent updates require the exact current revision. Published notes may be corrected with an explicit reason; an immutable event retains the prior claims. Withdrawal is terminal, retains attribution/identity/assets/history and stops further downloads. It cannot retract copies already downloaded.

No user content executes or renders as HTML. Download responses use attachment/octet-stream, no-store and nosniff, and require current membership on every fetch. The proxy avoids forwarding compressed wire lengths after Fetch decoding. Asset data is excluded from default Ecto queries, metadata and event snapshots.

There are at most 500 release records per repository, 200 included commits per range, 256 eligible tags in a listing, 16 KiB notes, 200-byte titles and 2 KiB correction reasons. The current interface lists the latest 100 releases/events; an older release remains accessible by its stable UUID link, and all events remain stored. Capacity targets and pilot workload measurements are still M4 work.

Primary references: [Git revision peeling](https://git-scm.com/docs/git-rev-parse), [Postgres binary values](https://www.postgresql.org/docs/18/datatype-binary.html), [Plug response/body boundaries](https://plug.hexdocs.pm/Plug.Conn.html). Existing command/lease/transport design remains authoritative.

Evidence needs context rules, real browser/private downloads and ordinary Git tag push tests, concurrent/stale edits, worker and VM interruption before/after SQL commit, and copied-production restart proof. An explicit agent review records the candidate and J12 hash. GitHub Actions infrastructure unavailability remains unavailable, even when local and independent Linux proof pass.
