# Implementation evidence and reproduction

The first native slice is in apps/forge and apps/web. Start with their setup instructions.
This is a reproducible development foundation, not a released product.

The backend verification suite uses a real isolated Postgres database and standard Git.
It exercises repository ownership, durable initialization, response retry, duplicate/invalid names,
outsider denial, role denial, session expiry/revocation, membership removal, CSRF and storage failure/reconciliation.
The browser suite uses development fixtures and a real server pair to create/reload a private repository,
deny outsiders and cookie writes without CSRF, and revoke a session through sign-out.

Run `mix precommit` in apps/forge, `npm run check` in apps/web and `npx playwright test` in apps/web with the development forge running.
The CI workflow repeats these on Linux with disposable Postgres. Browser screenshots and JSON results are private test artifacts.
Do not use synthetic fixtures on an exposed installation.

These checks support parts of J01. No completed milestone or verified whole journey is claimed by merging this slice.
D02 standalone identity is recorded; its Cloud/Barkpark actor-boundary work remains open.
D04 transport and D05 general Git/DB operations follow in the current run.
The configured Barkpark status source remains unconfigured; evidence/status.json must not be hand-edited to imply it exists.
