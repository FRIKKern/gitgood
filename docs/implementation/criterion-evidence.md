# Criterion evidence

## Implementation contract

The first native evidence profile attaches an immutable result to one acceptance criterion of a linked Barkpark **task**, its exact source document revision, and the current pull request's source and target Git commits. Barkpark remains the requirement owner. Paper links remain supported context; automatic extraction of criteria from arbitrary Paper prose is outside this profile.

Read requirement criteria through the current viewer's connection. Only the task's bounded `acceptance_criteria[].criterion` text is eligible; task closure, `met` flags and upstream evidence strings cannot establish a native result. Preserve a criterion digest and index in each native record. Any source document revision change, criterion change, source-link generation change or source/target commit change makes prior results stale. No automatic applicability transfer is provided.

Evidence is a producer's declared passed, failed or inconclusive result with bounded commands, environment, producer label and observation time. The authenticated attaching actor and receipt time are assigned by Gitgood. An attached result is not an independent verification pass, trusted external check or merge-policy approval.

Keep the artifact in native Postgres custody as immutable UTF-8 text, at most 64 KiB, with its name, exact byte size and SHA256. The digest supplied by the producer must match the received bytes. Larger or binary evidence and external artifact-provider fetching require separate profiles. This bound is a refusal rule rather than measured platform capacity.

The production web proxy preserves protected evidence download bytes and attachment/checksum headers only on the canonical evidence route and a successful native response. Denial remains a structured response without artifact headers. Offline recovery includes evidence and its event history in the database fingerprint; the narrow PostgreSQL dump/reparse normalization for its observed criterion-bound parentheses retains every bound, name and operator. Functional recovery still requires its complete production exercise.

Native repository permission and current source permission are both required to read artifact/provenance. Never borrow the creator's source credential or return a stored requirement snapshot after source denial. An unavailable source hides source-bound evidence without deleting native history. Download is an attachment, never executable HTML. Marking an artifact unavailable adds a retained event and prevents its result from satisfying current evidence; reassessment creates another record. Refresh only observes state and cannot rewrite history.

Within one criterion, the newest attached record governs the displayed result. A failed, inconclusive, stale or unavailable newer record cannot fall back to an older pass. An untested criterion is absent. Idempotent retries preserve the original receipt and cannot create another record or edit its provenance.

Creation-profile validation applies to new records. An exact actor/link/key/body match first resolves the original opaque receipt under current native writer permission, even if a later profile would refuse those original bytes or current source access is unavailable. A changed body remains an idempotency conflict. Older protected bytes retain their checksum and current native/source download permissions; tightening new-input rules never rewrites them or transfers source permission. NUL text is an explicit new-creation refusal, not a migration of existing byte custody.

The [bounded history contract](evidence-history.md) keeps the entire history while paging record and event reads. A selected older page does not change which result governs a criterion. Pagination is a resource boundary, not measured capacity.

The open browser evidence panel freezes a consequential request's destination, exact body and idempotency key until a valid native receipt confirms it. A lost reply, malformed success receipt or later Source revision cannot turn retry into a new assessment. The explicit original-request retry uses that frozen intent; new attachments and withdrawals remain disabled while its outcome is unknown. A structured invalid-evidence refusal allows correction. Synchronous guards exclude overlapping writes and artifact preparation. A failed read after a confirmed receipt does not undo confirmation.

This panel intent exists only in memory. Reload, navigation or Source-panel unmount can lose its body; private artifacts are not copied into browser storage. The native original receipt remains durable and actor-bound, but recovery across those browser lifecycle boundaries still needs a separate contract and proof. This profile does not establish complete browser retry recovery or full J11 acceptance.

## Acceptance still pending

Implementation, database constraints, API permission/race checks, source and code revision fixtures, durable retry, unavailable-artifact handling, browser distinction of states and copied production verification must all be demonstrated before claiming J11 complete. These paragraphs define the intended behavior; they are not evidence that it works.
