# Private Barkpark accounts

This slice adds backend connection storage and authenticated account APIs. Native link UI, external write journals, reverse navigation and J10 journey acceptance remain pending. The implementation ledger stays unconfigured.

## Connection contract

Each unrestricted native session can read only its own account connection at GET /api/connections/barkpark. POST to that path accepts exactly token, workspace, project, dataset and expected_generation. The initial generation is absent; changes require the current UUID. POST /api/connections/barkpark/disconnect accepts only expected_generation. Both writes require an idempotency-key and the ordinary native bearer or cookie/CSRF rules. Repository-scoped sessions cannot manage account credentials.

The configured source origin belongs to the installation. The client cannot choose a host. Initial support is deliberately limited to a finite-expiry API service token with read, optionally write, no public-read/admin/ops rights, and exactly one membership matching its home workspace. Personal-user attribution and broader credentials need a separate verified contract; an upstream service is not presented as the native user's external human identity.

Four source reads establish the current token ID/kind/label/expiry and workspace membership, full capability metadata, selected project ID and selected dataset ID. No caller-supplied identity is trusted. Missing scope, refusal, unavailable source and unsupported contract fail distinctly. Connection verification does not prove every future document is readable or writable: each owning operation must authorize again.

## Storage and retries

Credentials use versioned AES-256-GCM with a random 96-bit nonce and authenticated actor ID, connection UUID, generation UUID and configured origin. GITGOOD_CONNECTION_KEY is base64 of 32 independently generated random bytes, separate from native session keys. Production refuses to enable a Barkpark origin without it. Ciphertext is redacted from struct inspection. Plain tokens never enter response JSON, request digests, events or ordinary receipts. Phoenix request-parameter logging filters token fields.

One connection row belongs to each native account. Rotation changes its opaque generation and replaces its encrypted credential. Disconnect changes the generation and removes ciphertext. Short transactions validate the actual current session, serialize account changes and compare the expected generation; source I/O runs between transactions without holding database locks. An activation rechecks session authorization, current connection generation and selected installation origin after source verification.

Durable actor-scoped request events retain an HMAC of the complete request and the original sanitized receipt. Exact replay returns that original receipt, including after later rotation/disconnect, and never reactivates an old connection. A different payload under the same key conflicts. Clients must refetch GET for current connection state after reconciling a historical receipt; an operation receipt is not a current-state snapshot.

The encryption key is installation recovery material. Losing or replacing it makes old ciphertext unreadable and changes request HMACs; online key migration and a multi-key keyring are outside this slice. Do not claim rotation compatibility or successful coordinated recovery until the lifecycle implementation establishes it.

## Migration and restart

The migration refuses downgrade while either a connection or original request event remains. Exclusive table locks serialize the refusal with concurrent writers. Empty tables may be rolled back. The isolated verification/barkpark_accounts_upgrade.exs fixture creates a legacy account/session before upgrade, exercises empty rollback/re-upgrade, refuses populated and history-only rollback, then checks the same ciphertext, ownership, connection generation and request identity from a fresh VM using the same privately supplied installation key. Synthetic migration records are explicitly identified as fixtures; they do not pretend to be live source verification or coordinated backup/restore.

## Consumers and privacy

Internal source reads decrypt only the requesting account's credential, check selected origin and generation, then revalidate the current native session and connection generation after I/O. A response arriving after disconnect is discarded. Source denials/unavailability retain their original typed status for an owning link context to interpret. Generic source metadata is not a forge authorization grant; native repository access must be established independently before constructing a link read.

The backend APIs alone do not satisfy complete browser connection flows. Cross-tab invalidation, source-title clearing, outage recovery, deletion semantics, source mutation reconciliation and actual Studio anchors still require implementation and current J10 evidence.
