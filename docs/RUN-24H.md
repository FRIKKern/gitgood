# First 24-hour implementation run

> **Historical plan — 8 October 2026.** This preserves the original time allocation. It is not today's task list or progress report. Start with the [current progress snapshot](STATUS.md) and [execution guide](EXECUTION.md); see the [foundation report](RUN-72H-FINISH.md) for this run's results.

Prepared 8 October 2026. This is a time-boxed execution plan, not a report that implementation has started or passed. Hour zero is the beginning of the implementation run. An active agent execution environment must be available for the run; this document does not create a background runner or schedule.

## Finish target

Deliver the M1 running foundation and aim for the M2 private-repository slice: sign in, create a private repository, clone over authenticated HTTPS, commit and push with a real Git client, then browse the pushed code. Use synthetic owner, read-only member, and outsider identities to verify access boundaries. The goal is a reproducible working slice with current evidence, not a promise that every J01/J02/J04 criterion will pass within 24 hours.

Keep a browser URL, canonical clone URL, reproduction commands, CI results, candidate identity, and criterion-level evidence for the final demonstration. Preserve unverified failure and recovery behavior explicitly.

## Observed starting point

The private repository has specifications, generated diagrams, changelog routines, autonomous progression policy, and planning CI. It has no application implementation. The Barkpark ledger and product evidence sources are unconfigured.

Read-only tooling checks found Node 22.13.1, Elixir 1.11.2 compiled with Erlang/OTP 21, PostgreSQL client 18.4, and Docker client 20.10.20. The Docker daemon was unavailable. A PostgreSQL client does not establish that an isolated database server is running. These observations describe the current machine, not supported runtime selections.

## Time allocation

| Elapsed hours | Work | Observable result and exit check |
|---|---|---|
| 0–3 | Runtime and isolated environment | Verify official runtime compatibility; establish pinned Elixir/OTP, Node, Git and an isolated Postgres server. Prefer an isolated Linux/container environment where available; avoid replacing shared machine runtimes. Record exact setup commands, runtime versions, ports and storage paths. A clean process can start and stop the environment. |
| 3–5 | Identity and transport experiments | Record the first-slice D02/D04 decisions: session/bootstrap ownership, team membership, scoped Git credentials, read/write authorization, HTTP Git subprocess boundary, secret handling, timeouts and cleanup. Test a real Git client against disposable repositories. Keep untested Cloud/Barkpark identity propagation and transport limits open. |
| 5–9 | Running application foundation | Scaffold the modular Phoenix API, Postgres migrations, TanStack web application and minimal request contracts. Implement health/version identity, correlated errors, local fixture setup and relevant CI checks. A browser reaches the real API; production builds are exercised; secrets stay server-side. |
| 9–13 | Identity and private repository creation | Implement real session and credential handling, membership enforcement, repository metadata and isolated bare Git storage. Exercise owner/read-only/outsider access, expired credentials, duplicate names, creation retry and partial-failure reconciliation. Persistence survives a restart; unauthorized discovery/read is refused. |
| 13–17 | Authenticated HTTPS Git | Complete clone/push/fetch through the backend permission boundary. Prove expected refs with a real client, read-only denial, invalid credentials and denied ref updates. Exercise interruption, bounded execution and child cleanup. Only demonstrated limits are called supported. |
| 17–20 | Browser code view | Show the pushed commit, a file tree and safely rendered file contents through stable commit-based URLs. Check direct API denial, unusual filenames, binary content and bounded output. Full history/diff/recovery coverage remains unverified until its detailed J04 checks pass. |
| 20–22 | Integrated verification and repair | Reproduce the full slice from a clean environment. Test revoked access, lost responses, service restart and failed operations; repair correctness gaps. Inspect actual Git and Postgres state. Record criterion-level evidence against the exact candidate and specification revision. |
| 22–24 | Integration, documentation and handoff | Reserve these hours for repair and integration, with no new feature expansion. Verify PR checks on the current revision, merge passing work autonomously, update setup/decisions/changelog, regenerate views, and prepare the working demonstration plus next-run priorities. Report implemented, verified and released states separately. |

## Progress checkpoints

- Hour 3: environment viability and remaining infrastructure blockers.
- Hour 9: running browser/API/database foundation, builds and CI results.
- Hour 17: real Git transport result and access-denial evidence.
- Hour 24: clean-environment demonstration, merged revisions, current evidence, unresolved criteria and revised next-run estimates.

Report meaningful changes and actionable blockers between checkpoints. No human acceptance pause is required. The future Barkpark ledger remains the execution authority when configured; this document is an execution proposal, not a duplicate live task board. Evidence reports must not claim connected sources before source integration is actually established.

## Recovery and scope rules

Budget infrastructure investigation to the first three hours. If the preferred environment remains unavailable, try a reproducible isolated alternative. Continue independent contracts, fixtures and CI work where useful. Record the missing capability and precise recovery step rather than consuming the entire run on setup or claiming the environment works.

When a stage overruns, reduce later feature breadth and retain verification time. Never remove access checks, hide a failure, or weaken the criteria to meet the clock. A working foundation with an evidenced blocker is preferable to an unverified repository-hosting claim.

Keep the run focused on the private repository slice. PR review/merge semantics, SSH, repository import, broader Barkpark adoption and full managed Cloud lifecycle follow their existing milestones. Probe production packaging early enough to expose compatibility gaps; no production customer data is needed for this run.

Use isolated worktrees and disposable fixtures. Preserve explicit user choices and recoverable work. Agents research, implement, evaluate and merge under AUTONOMY.md. Additional agents or background scheduling are separate execution mechanisms and are not enabled by this plan.

## End-of-run record

Record the candidate commit, spec revision, actual environment, clean-start command, web URL, clone URL, synthetic identity roles, reproduction commands, per-criterion results, artifacts, CI links, failures and next dependencies. A merged PR does not substitute for journey evidence. No application release is implied by a first-slice demonstration.

Minimum useful result: a reproducible foundation with demonstrated browser/API/database connectivity, CI and explicit blockers. Target result: the private create/clone/push/browse workflow plus its authorization and recovery evidence. If all targeted criteria pass early, improve reliability and repeatability before expanding to the next milestone.
