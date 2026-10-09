# Journaled Paper return links

Accepted implementation direction, 8 October 2026. Full J10 and M5 acceptance remain pending.

Gitgood owns durable responsibility for a requested source write. Barkpark owns the Paper and its contents. A native attach receipt establishes a native relationship; its source return link is a separate operation.

Use the supported Paper PortableDoc renderer exercised in decision 0009. Append one deterministic hyperlink block whose identity derives from the native link UUID. The URL uses the configured frontend origin and opaque native change UUID, and independently authorizes at Gitgood. Preserve all unrelated source blocks and purpose. Refuse edited/colliding owned blocks and unsupported shapes. Task reverse rendering remains unsupported; no global task schema change is authorized by this decision.

Persist originating native actor/session, selected connection generation, verified API service identity, source scope and link generation before network I/O. Encrypt immutable CAS mutation bytes under the separate installation key with an explicit journal-payload binding namespace. Use the operation UUID for source idempotency, and never regenerate a payload under that key. Source bytes, raw credentials and full source response errors stay out of ordinary records, logs and API receipts.

Two bounded workers use durable attempt leases. A known reply is retained after access changes during an already dispatched request. Unknown outcomes retain responsibility and reconcile actual source state. Observation records the actual observer separately and never invents the original transaction. Connection/session/link/frontend-origin changes stop further writes under old authority.

Five automatic attempts form a bounded round. Exhausted unsent work becomes visibly paused; unknown results remain unknown with automatic retry disabled. An explicit retry retains operation/key/payload and cumulative attempts, and must pass both the current requester and original authority checks. Other authorized readers may observe source presence without taking over writes.

Native removal preserves existing source pointers and operation history. Up to 1000 requests per change bound storage/listing; the full bounded link history remains visible. Terminal encrypted source payloads are cleared when responsibility resolves; provenance, hashes and actual receipts remain. Populated journal migration downgrade refuses rather than deleting responsibility.

This work implements the already scoped first-release connection/recovery behavior and displaces no accepted feature. Source cleanup, task reverse widgets, hosted execution and cross-owner atomic transactions remain outside this slice. Production, restart, live source and complete J10 evidence are independent gates.
