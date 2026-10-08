# First 72-hour implementation run

Prepared 8 October 2026. Hour zero is the beginning of an implementation run. This proposal includes the first 24-hour plan; it is not an additional 72 hours afterward. No implementation result, active background runner, or scheduled execution is established by this document.

## Outcome

Target a reproducible private repository slice (M1/M2) and a working pull-request/check/merge foundation. Aim to prove M3 only if every required J06–J09 criterion passes against the current candidate. If foundational work takes longer, spend the remaining time completing its evidence and recovery paths before adding dependent features.

The final demonstration should show owner and reviewer identities collaborating: create a private repository, HTTPS clone/push, browse a commit, open a same-repository pull request, view the diff, comment/review, receive an authenticated external check, and request a policy-controlled merge. An outsider cannot read or act on the repository. A source/target change, failed check, revoked membership, or interrupted operation cannot produce a false merge success.

These are targets to verify, not promised completed journeys. See [QUALITY.md](../QUALITY.md), [AUTONOMY.md](../AUTONOMY.md), and the canonical [milestone catalog](milestones.json).

## Allocation and demonstrations

| Elapsed hours | Work | Observable result |
|---|---|---|
| 0–24 | Execute [the first 24-hour plan](RUN-24H.md): isolated runtime/Postgres, identity and transport experiments, API/web/CI foundation, private repository creation, HTTPS clone/push and minimal commit browsing. | First browser and clone URLs, repeatable setup, real Git-client results, authorization/recovery evidence and explicit remaining criteria. |
| 24–30 | Repair first-slice gaps. Resolve D08's initial merge strategy, revision/check identity and approval invalidation rules. Begin D05 with a disposable Git/Postgres operation experiment before integrating merge UI. | Recorded policy/operation contracts and failure-injection findings; no dependent merge feature claims while the repository slice is blocked. |
| 30–40 | Build same-repository pull requests, bounded diffs, exact commit/line comments, review state and authenticated external-check ingestion. Exercise outsider denial, stale checks, duplicate/out-of-order delivery and comment retries. | A second synthetic collaborator can inspect a change and provide review/check results tied to its revision. Old comments retain their original context. |
| 40–48 | Implement one documented merge strategy with backend authorization, current branch policy, expected source/target refs, approval/check evaluation, durable responsibility and exact outcomes. | A permitted candidate merges; changed refs, conflicts, revoked access and failed checks are refused or re-evaluated explicitly. First working change-to-merge demonstration. |
| 48–58 | Prove concurrency and restart recovery. Inject termination before/after Git ref updates and before database outcome persistence; restart, reconcile and retry. Exercise competing pushes/merges and policy mutations. | Actual Git refs and durable operation/audit records agree; retry does not apply twice or overwrite another writer; pending operations do not remain unexplained. |
| 58–64 | Build/start real production artifacts on a clean disposable target with persistent stores and explicit configuration. Record D06 findings and validate the basic readiness/version probes. If core gates passed early, audit one Barkpark capability and tracking/evidence source contract. | Reproducible production-build/start instructions and concrete Cloud packaging gaps. Barkpark adoption is optional and remains blocked on verified supported contracts. |
| 64–72 | Reserve the final eight hours for clean-environment end-to-end reproduction, adversarial checks, fixes, current PR verification and integration. Update canonical decisions/specs, changelog, generated views, evidence and the next-run plan. | Candidate commit and environment, working demonstration, CI links, criterion-level results, actual milestone status, unresolved blockers and measured estimates. |

## Daily expectations

**By hour 24:** aim for the private create/clone/push/browse slice. The result appears in a local Gitgood browser and a real terminal Git client. Re-estimate the remaining work using actual setup and implementation effort.

**By hour 48:** aim for the first policy-controlled change-to-merge loop. The result appears in Gitgood pull requests, review/check views and operation results. This demonstration does not establish recovery acceptance until the interruption tests pass.

**By hour 72:** aim for a hardened foundation whose high-risk behavior has reproducible evidence, with real production packaging exercised on a disposable host. Mark M3 passed only when all required criteria pass; record partial progress otherwise. A complete private-team release still requires M4–M7.

## Working rules

Use isolated worktrees and synthetic owner, reviewer/read-only member and outsider identities. Agents resolve technical decisions, implement, evaluate evidence and merge passing changes without human acceptance pauses. The implementation environment must remain available for execution. This plan assumes one active agent stream; additional agents and persistent scheduling are separate mechanisms, not assumed capacity.

Follow the environment time budget and recovery rules in RUN-24H.md. The observed old Elixir/OTP installation and unavailable Docker daemon must be rechecked at execution start. Prefer reproducible isolated runtimes over changes to shared installations.

Preserve the final verification reserve. Overruns reduce optional integration and feature breadth. Correctness gaps in authorization, transport, merge or recovery take priority over UI polish. Do not weaken criteria or modify the evidence snapshot to produce a green roadmap. Prove the relevant failure paths before marking a journey verified.

Treat external-check integration as an authenticated provider contract; accepting an arbitrary successful payload is not verification. Validate actual commit identity and ordering semantics. Keep Gitgood's product review-policy functionality distinct from this project's autonomous progression policy.

Keep scope to the native forge foundation. SSH, imports, releases/assets, broader search/activity, adopted Barkpark workspace features and managed Cloud lifecycle follow their existing milestones. Production packaging here is an experiment and reproducibility result; no managed installation, restore capability or release is implied.

## Oversight and continuity

Checkpoints: hours 3, 9, 17, 24, 36, 48, 60 and 72. Report working behavior, current evidence, relevant merged revisions, failures and next dependencies. Provide updates on meaningful findings between checkpoints; no human approval queue is created.

Record enough state to resume after an agent or tool interruption: worktree/branch, last commit, remaining criterion, reproduction command and next action. Use the Barkpark execution ledger when configured; this document remains a static proposal and does not become a second live task board. Source integration and unattended reconciliation remain explicit setup work until demonstrated.

## Finish record

Include web/clone URLs, clean-start commands, runtime/dependency versions, candidate/spec identities, synthetic roles, commands and retained artifacts for each tested criterion, CI links, exact outcomes, known limitations and next-run estimates. Separate implemented, verified and released states.

Minimum useful outcome: a reproducible repository foundation with its access/transport behavior evidenced and blockers stated. Target outcome: the repository slice plus a working review/check/merge foundation. Stretch outcome: complete M3 evidence and clean-target production packaging. Full Cloud deployment and a first complete product release require later gates.
