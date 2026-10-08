# Initial review, checks and merge semantics
Accepted implementation direction, 8 October 2026.

The first strategy is fast-forward only into main from a same-repository feature branch.
Merge commits and squash were considered; each adds another generated commit and conflict-resolution surface.
Fast-forward keeps the merged object identical to the reviewed source and makes recovery evidence smaller.
A divergent source must be updated by its author. There is no override endpoint.

An owner configures 1–10 independent approvals and up to 16 required provider/check pairs.
The default is one independent approval with no external check requirement.
An author cannot approve their own request. A current changes-requested review blocks merging.
For each actor only their latest review counts. Its source and target SHAs must both match current refs,
and the reviewer must retain a writer/owner membership. Comments retain original SHAs, side, line and a server-derived
excerpt. Comments outside the bounded diff are refused. Source or target changes invalidate approvals and mark
comments outdated. Historical excerpts remain readable. A merged request retains its reviewed source/target and the policy/check/review snapshot used by its operation.

A check provider receives a repository-scoped, revocable credential bound to its issuing actor.
A report identifies a reachable commit, check name, positive attempt and positive sequence.
Within an attempt, lower sequences are acknowledged without changing state; identical replay is stable,
conflicting same-sequence reports are refused, states cannot regress, and final results cannot change.
A retry uses a higher attempt. Provider token rotation revokes the prior credential and invalidates its results; new reports require a new attempt under the new credential. Only the highest attempt for the exact current source SHA can satisfy policy.
A provider's credential and issuing membership must remain valid. Session/Git credentials cannot report checks.

All collaboration mutations acquire the same repository lease as Git pushes. Merges re-evaluate session,
membership, current policy version, exact refs, approvals and checks inside that lease.
Git then atomically verifies the source ref, conditionally advances the target, and creates an operation marker.
A client cannot choose a different target, strategy, actor, policy snapshot or bypass.

Browser comment drafts live in session storage under actor/repository/request/source/target identity.
A lost response retains the submitted idempotency key; reload/retry deduplicates the already-persisted comment.
A changed revision opens a distinct draft context. Draft storage contains user comment text, never credentials.

Evidence commands are documented in implementation/collaboration.md.
Development tests establish the implemented contract; broader forge interoperability and release acceptance remain separate.
