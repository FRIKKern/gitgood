# Gitgood agent instructions

Read README.md, PRODUCT.md, QUALITY.md, and the relevant journey before implementation.

Read [AUTONOMY.md](AUTONOMY.md). Agents have full delegated authority to progress within scope. Resolve decisions, implement, verify, merge passing work, and select the next task without human acceptance or routine confirmation. Gate progress on current evidence; record decisions and report meaningful results.

- Native Gitgood is accepted. Forgejo is a reference, not a production backend.
- Resolve open technical decisions through evidence and record their rationale. Preserve the public source repository authorized on 11 October 2026 and other explicit user choices; keep operational secrets, customer data and private recovery material out of it. Do not treat missing human sign-off as a blocker.
- Keep forge authorization, merge rules, and recovery in the Elixir backend. Reuse Barkpark through supported APIs.
- Keep one authoritative owner for records. Avoid speculative services or generalized plugin frameworks.
- Use isolated worktrees and test resources. Do not switch or reset a shared main checkout.
- Keep local storage bounded. Use hosted Linux CI for heavy verification. Before local dependency installs, large builds, image creation, exports, or runtime copies, check both the system volume and every output volume; include temporary copies in the estimate and leave at least 20 GiB free on each after the operation. Below that reserve, continue source work and hosted checks without new local VM or build payloads. Reclaim only confirmed inactive, reproducible caches; never follow a cache link into source, and preserve retained evidence, databases, VM images, and recovery materials.
- Keep secrets out of source, logs, artifacts, and browser code.
- Update affected specifications and changelog fragments with the change.
- Keep the human reading path current: README for orientation, docs/README.md for navigation, docs/DEVELOPMENT.md for setup, and docs/CODEBASE.md for code responsibilities. Index new guides, implementation references, and decisions; explain the user outcome before internal proof details. Label historical reports and avoid copying live status into competing summaries.
- Run npm run generate and npm run check after changing plan/reporting inputs.
- Do not mark planned, merged, or task-closed work verified without current evidence.
- No destructive housekeeping of unmerged work. Preserve release evidence and restore materials.
- Follow the autonomous release/deployment evidence gates when targets and credentials are configured. Keep private material private and preserve recovery paths.
- Live implementation status belongs in the configured Barkpark ledger. Until it exists, report it as unconfigured.
