# Gitpark agent instructions

Read README.md, PRODUCT.md, QUALITY.md, and the relevant journey before implementation.

- Native Gitpark is accepted. Forgejo is a reference, not a production backend.
- Treat open decisions as open; choose reversible local defaults and record them. Remote visibility, licensing, and publication require resolved ownership decisions.
- Keep forge authorization, merge rules, and recovery in the Elixir backend. Reuse Barkpark through supported APIs.
- Keep one authoritative owner for records. Avoid speculative services or generalized plugin frameworks.
- Use isolated worktrees and test resources. Do not switch or reset a shared main checkout.
- Keep secrets out of source, logs, artifacts, and browser code.
- Update affected specifications and changelog fragments with the change.
- Run npm run generate and npm run check after changing plan/reporting inputs.
- Do not mark planned, merged, or task-closed work verified without current evidence.
- No destructive housekeeping of unmerged work. Preserve release evidence and restore materials.
- No production deployment or public publication is implied by local setup.
- Live implementation status belongs in the configured Barkpark ledger. Until it exists, report it as unconfigured.
