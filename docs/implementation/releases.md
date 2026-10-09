# Private release workflow

Release metadata/events/assets belong to Postgres; code and tags belong to the managed Git repository. Runtime packaging remains in Gitgood.Release; forge release records use Gitgood.Releases/ReleaseRecord.

## Supported interface

All paths are under /api/repos/:team/:name and require a current authenticated session and team membership. Cookie mutations require CSRF. Repository visibility is checked before identifiers are read, then every context call locks/rechecks the actual credential and membership. Owner/writer may mutate; reader may inspect records and download published assets. Caller identity, credential IDs and storage paths are never accepted from request data.

- GET /tags returns lightweight/annotated commit tags and exact object/commit identity.
- GET /releases lists the latest 100; GET /releases/:id returns one record and latest 100 retained events.
- POST /releases takes tag, commit_sha, optional base_sha, title and notes with Idempotency-Key. The backend verifies tag/commit and derives the bounded actual included commit range. A tag is reserved by one record, including after withdrawal.
- POST /releases/:id/assets takes name, size and lowercase sha256 with Idempotency-Key. This creates waiting responsibility. The same actor/key/body returns the same asset; changed body conflicts. Names are 1–120 ASCII characters beginning with a letter/digit and containing letters/digits/dot/dash/underscore.
- PUT /releases/:id/assets/:asset/source takes application/octet-stream, at most 16 MiB, 64 KiB read chunks, 15-second total/5-second read limits. Exact bytes/digest are verified before ready state. The body and event commit atomically. Partial/wrong content retains waiting responsibility; retry the same immutable asset. A matching waiting asset can be resumed in the browser after reload.
- DELETE /releases/:id/assets/:asset cancels a waiting draft asset with a retained event. Ready bytes are immutable. At most eight active assets exist.
- POST /releases/:id/actions takes kind/version and an Idempotency-Key. Publish additionally requires current notes_digest; revise/correct take title/notes; correct and withdraw require reason. Every transition increments version and appends attributed snapshot history. Stale versions, changed tag/commit, wrong reviewed notes, pending/no assets, unknown fields and revoked authority fail.
- GET /releases/:id/assets/:asset/download only serves a currently published ready asset after current authorization and byte/digest revalidation. It is a private attachment with no-store/nosniff and X-Gitgood-SHA256. Withdrawn/draft bytes are unavailable. Existing downloaded copies cannot be revoked.

The browser uses stable #release-UUID links, displays draft/published/withdrawn explicitly and keeps the original request key/body when a reply is lost. Retries query/apply the same consequence. Included commits come from Git, not from arbitrary notes. Plain text is escaped.

## Publication and recovery

The repository/credential/membership lease serializes publication with native writes. Native HTTPS/SSH accept new tag refs and deny their replacement/deletion; ordinary branches retain existing main protection. No Git ref changes are made by publication itself. SQL commits the release state, verified assets and event together, so there is no dual-store release outcome to infer.

Worker interruption before commit rolls all publication claims back to draft; after commit, one published event remains. New VMs retry the original key and read the same outcome. Concurrent identical publication retries converge; competing corrections at one version yield one success and one stale-version refusal. A withdrawn release remains withdrawn when an old publication request is replayed; its original event is returned alongside the current state.

The migration refuses downgrade once any release record exists. Keep a compatible backup and forward recovery path; do not delete recorded claims/assets to force rollback. Independent installation and replacement-host restore still need complete M6 evidence, including database asset capacity.

## Reproduction and scope

Use mix precommit and the release/tag/recovery backend tests, then the full Playwright suite with synthetic owner/reviewer/reader/outsider fixtures. The native HTTPS and SSH tests push tags and try replacement/deletion. The release browser flow tests lost draft/upload/publication replies, partial intake/resume, exact >1 MiB BFF downloads, readers/outsiders, safe notes, actual changes, corrections, withdrawal and desktop/mobile layout.

With an isolated recovery database, verification/release_vm_crash.exs halts the complete VM at before_commit/after_commit and re-enters with reconcile. The copied-production harness repeats all browser/client flows, restarts source-free artifacts and verifies published identity/change range/asset bytes through both API and BFF, plus withdrawn history/download refusal.

These are development slices. Basic forge releases do not publish Gitgood itself, attest arbitrary artifact builds, create a deployment, enable public assets, or satisfy the whole product/Cloud/pilot gate. Current candidate/specification and environment must accompany evidence.
