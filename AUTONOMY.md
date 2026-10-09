# Autonomous progression

Frikk delegates Gitgood development decisions and progression to agents, with full trust, as of 7 October 2026. Human approval, staffing, milestone acceptance, and release sign-off are not prerequisites. Agents carry work through implementation, verification, integration, and the next ready task within the project scope.

## Authority and scope

Use PRODUCT.md as the execution baseline. Resolve open technical decisions through research and experiments, record the result, and proceed without a confirmation round. Record scope changes and their impact before implementing them. Preserve explicit user choices: native architecture, private repository, and the bounded first-release direction. Full trust does not turn failed or missing evidence into success.

Agents may select dependencies, resolve architecture decisions, implement, test, review, merge passing changes, maintain documentation, and progress milestones. Release and deployment progression uses the same evidence-based process once the target, credentials, artifacts, and recovery path exist. Missing infrastructure is an implementation dependency, not a human acceptance gate.

## Progression loop

1. Read current scope, dependencies, decisions, and evidence. Select the next ready work package; do not wait for a person to assign it.
2. Record the intended result and criteria, then implement in an isolated worktree.
3. Run the relevant checks and reproduce the affected journey, including its failure and recovery paths.
4. Perform an explicit agent verification pass against the specification and artifacts. For authorization, merge correctness, migrations, and recovery, include adversarial and interruption checks. A separate agent can perform this pass when available; absence of another agent must not create a staffing gate. Record the actual verifier and limitations.
5. Update specifications, decision records, evidence references, and changelog. Open a PR, verify checks on its current revision, resolve findings, and merge without requesting human review. Revalidate after any change invalidating the checked candidate.
6. Reconcile the merged result and recorded evidence. Advance the journey or milestone only when every required exit condition passes, then take the next ready task.

Agent review and CI serve different purposes. A prose assertion, a merged PR, or passing planning tests alone cannot verify a product journey. Never change a requirement merely to hide a failing implementation.

## Evidence gates

Acceptance means a recorded passing evaluation of explicit criteria, not a human signature. Keep implementation, verification, and release state separate. Unknown, stale, unavailable, and failed evidence block the dependent transition while agents investigate or work on independent tasks.

Record producer/verifier identities, candidate commit, specification revision, commands, environment, outcomes, artifacts, and gate rationale. Release progression additionally requires artifact identity, current required-journey evidence, compatibility, installation, and replacement-host restoration. Publish only the candidate that passed those checks and retain its recovery materials.

## Blockers and communication

Attempt reasonable recovery and alternatives. Record unresolved blockers precisely and continue independent work. Ask the user only for information or access the agent cannot obtain, conflicting user requirements, or a decision outside the delegated project scope. No routine approval requests or human acceptance checklists.

Report meaningful completed work, changed decisions, failures, and blockers concisely. Reporting is for oversight and can happen after successful autonomous progression; it is not a waiting point.

## Current implementation status

This policy governs agents working in the repository now. It does not install a persistent agent runner. The repository has planning CI and scoped live collectors for implementation status and explicit protected delivery assessments. Complete native journey acceptance, release ingestion, unattended scheduling, and release/deployment automation remain implementation work. An active agent can execute the loop with the available tools, but no background progression is claimed when no agent is running. See [the tracking contract](docs/TRACKING.md) for observation and freshness limits.
