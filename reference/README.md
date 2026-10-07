# Reference research

Forgejo is a comparison environment and source for implementation research, not a production dependency. Record the pinned version, fixture identity, workflow recording, observed behavior, and limitations before using it as a reference.

Barkpark Studio inspired: journey-driven work, real reference comparisons, one authoritative fact per home, generated roadmap, concise decisions, and a single task ledger. Gitgood adds backend, transport, concurrency, and recovery proof; its quality bar cannot be browser-only.

The roadmap redesign studied Barkpark Studio at commit `c922ce079525b51e4906074b257fbd3028cf7467`: README placement, `docs/images/roadmap.svg`, and `scripts/generate-roadmap.mjs`. Adopted design ideas include journey rows, phase hierarchy, adaptive card heights, summary progress, and light/dark palettes. Gitgood's renderer is independently written in `scripts/roadmap-svg.mjs`; it reads the local catalog and evidence snapshot, keeps implementation/verification/release separate, and never infers milestone completion or current focus from task closure. Status remains unknown until sources are connected. No Studio code or assets were copied.

Local source checkpoints reviewed in this conversation: Barkpark Studio README, QUALITY, JOURNEYS, CONTRIBUTING, roadmap, decisions 0001/0003, API/listen adapter, and reporting scripts. Barkpark checkpoints: Cloud README, template manifest, Site model, deploy driver, Node deployment script, host command allowlist, and restore implementation. Pin their actual commits when repeating research.

Primary technical references:
- [Git receive-pack](https://git-scm.com/docs/git-receive-pack)
- [Git update-ref](https://git-scm.com/docs/git-update-ref)
- [Git HTTP backend](https://git-scm.com/docs/git-http-backend)
- [Postgres backup](https://www.postgresql.org/docs/current/backup.html)
- [Forgejo architecture](https://forgejo.org/docs/latest/contributor/architecture/)

Do not copy code without provenance/license review. Do not present observations of reference software as verification of Gitgood.
