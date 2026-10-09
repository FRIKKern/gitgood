# Collaboration and recovery verification

Run mix precommit for sandboxed authorization, comment anchoring/retry and provider ordering tests.
The real HTTPS browser fixture opens a pull request, reviews from a second browser identity,
drops a response after a comment has persisted, reloads/retries without duplication, pushes a changed revision,
rejects stale approval/check evidence and performs a protected merge. Ref and hidden-marker advertisements are checked.

Recovery verification deliberately uses a separate real database, outside SQL sandbox transactions:

```sh
export PGDATABASE=gitgood_recovery
export GITGOOD_STORAGE="$PWD/.gitgood/recovery"
mix ecto.create
mix ecto.migrate
mix run verification/merge_recovery.exs
```

Nine scenarios cover one attributable merge/replay, three worker termination boundaries followed by application restart,
concurrent requests, source compare-and-swap interference, target compare-and-swap interference, divergent history, and policy/check/actor/reviewer revocation gates.
Receipts are written to ignored .gitgood/verification/merge-recovery.json.

Whole VM failure uses verification/vm_crash.exs. Set GITGOOD_FAILURE_POINT to before_ref, after_ref or before_outcome,
run it and require the injected exit code 70. Start a fresh VM with GITGOOD_FAILURE_POINT=reconcile.
The saved fixture contains IDs and expected refs, never plaintext credentials.
The resumed VM checks durable state, actual target/marker evidence and strict fsck.

Responsibility commits before Git changes. The Git transaction creates refs/gitgood/operations/OPERATION atomically
with the target update and source verification. Internal refs are hidden from transport.
Recovery never infers success from worker completion: an exact marker plus target ancestry establishes application.
No marker with the unchanged target establishes failure; unavailable or inconsistent evidence remains uncertain and blocks writes.
Replaying a finished operation returns the same result. A failed operation is terminal; a new attempt uses a new key
and must pass current validation again.

Deployment must quiesce older application processes before introducing new operation kinds or schema semantics.
The implementation supports a single configured deployment target; rolling upgrades, power-loss durability,
distributed storage failover and operator repair of uncertain/corrupt stores need additional evidence.
No Cloud deployment or completed milestone is implied by these development checks.

Review browsing captures exact current branch SHAs and binds its diff to those objects. The browser
requires matching metadata and diff revisions before enabling review controls, preserving unsent drafts
when a branch advances between reads. The real Git browser fixture delays the diff request, pushes a new
revision after metadata loads, verifies the explicit refusal to display mismatched context, then refreshes
and resumes the existing stale-approval/protected-merge checks. This changes read composition; merge,
comment and review transactions retain their existing current-ref validation.

The keyboard observer waits for the submit button to become available before tabbing from the comment
field. A disabled button is correctly skipped while matching changes are loading; enabling it later does
not transfer focus back. The retained candidate `6880b2884854b36a4ebe431884e92e87693dc4d2` Linux
production attempt passed ten browser flows and failed that readiness assumption. The repaired observer
still requires keyboard focus, actual submission, lost-reply recovery and the real branch-advance check.
