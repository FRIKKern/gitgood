# Journaled Paper return links

A native link does not prove that Barkpark has a return link. A writer can separately request a return link using their current source connection. Gitgood must persist that responsibility before source I/O and expose the actual outcome.

The supported reverse renderer is a Barkpark Paper. Append a single deterministic owned hyperlink block to the current Paper under its revision comparison; preserve purpose and unrelated blocks. Task reverse rendering remains unsupported. A collision or edited owned block requires visible conflict rather than overwrite.

Bind the operation to its originating native actor/session, native link generation, selected source connection generation, exact source scope and verified API service identity. A replacement connection or another actor cannot silently continue its writes. Encrypt any immutable mutation payload containing source blocks; retain hashes, revisions and actual transaction attribution without mirroring editable source contents.

Use the operation UUID as the source idempotency identity. Persist immutable CAS bytes before sending. Unknown outcomes must reconcile actual source state or retry those same bytes; no new source revision or payload may reuse the key. A read-only observation can prove the exact pointer exists, while write transaction identity stays unknown.

Process restarts retain queued, prepared, sending and uncertain responsibility. Bounded workers use durable attempt leases and current authorization. A known reply is recorded even when access is revoked during I/O; every response and later read independently rechecks current native access.

Native removal stops future activation by generation change. It does not delete an already written source pointer. Applied and uncertain source responsibility remains visible. Source cleanup would be a separate owning operation.

A draft native implementation and focused checks exist; full J10 verification remains pending. Required proof includes concurrency, source outage/denial/revision conflict, lost replies, connection/native permission changes and fresh-process recovery, plus actual deployed Paper navigation under the intended candidate.


## API and visibility

Use /api/repos/:team/:name/pulls/:id/links/:link/return-pointers. GET lists the complete bounded native history; POST accepts exactly generation and connection_generation with a native idempotency key. The operation UUID is the stable source key. POST /:operation/observe accepts the viewer connection generation and performs only a source read. POST /:operation/retry retains original authority and immutable bytes.

Status is separate from native attach success: queued, prepared, sending, unknown, paused, applied, observed, denied, conflict, unsupported or stopped. Five automatic attempts pause unsent work explicitly; uncertain writes retain their state and disable automatic retry after the round. Retry adds another bounded round without resetting cumulative attempts. A current actor cannot replace a revoked originating session or connection. Unknown/pending responsibility stays visible.

The configured GITGOOD_WEB_ORIGIN supplies the frontend destination; GITGOOD_PUBLIC_URL still supplies Git transport addresses. A queued operation cannot write an old frontend address after configuration changes. A supported existing pointer is observed instead of rewritten. Source unlink/cleanup is never implied by native removal.

## Evidence boundaries

Focused rule tests and the actual native browser/Git workflow use an owned synthetic HTTPS source with normal chain/hostname checks and an explicit issuer. They exercise lost replies, immutable idempotency replay, owner revision changes, held disconnect/revocation, interruption, distinct source actors, encrypted binding and paused retry. These are supporting checks, not live Barkpark or complete J10 acceptance.

verification/source_returns_upgrade.exs requires a clean candidate, an ordinary owned Postgres database and a separately running synthetic HTTPS source. It upgrades retained native/source link identity, checks empty and populated journal downgrade behavior, runs eight concurrent same-key requests, retains an actual interrupted source request, and uses a separate VM to replay its exact sealed bytes/key and obtain the real fixture transaction while preserving one owned pointer. Metadata fixtures do not establish actual Git or coordinated backup/restoration.
