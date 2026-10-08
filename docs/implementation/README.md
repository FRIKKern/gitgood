# Implementation evidence and reproduction
Native code is in apps/forge and apps/web. Start with their setup instructions.
No public deployment, managed Cloud lifecycle or Barkpark evidence ledger is configured.

Run mix precommit in apps/forge, npm run check in apps/web and npx playwright test in apps/web with the forge running.
On Windows set GITGOOD_BROWSER_CHANNEL=msedge and executable paths for GITGOOD_GIT, GITGOOD_PYTHON and GITGOOD_OPENSSL.
The workflow repeats checks on Linux with disposable Postgres, plus real-database and VM interruption tests.
Private artifacts include screenshots, JSON results, recovery receipts and candidate/requirement identities.
Synthetic fixtures must never be seeded into an exposed installation.

Backend checks cover private creation/ownership, authorization, session expiry/revocation, CSRF, retries,
storage failure/upgrade, process limits/cleanup, exact comment context and provider ordering/rotation.
The browser flow uses real HTTPS Git and two identities to create, clone, push, browse, comment, review, update,
receive provider checks and merge. It also exercises outsider/reader denial, trust failure, interruption/retry,
lost comment response and stale approval/check refusal.

See [browsing](browsing.md) and [collaboration/recovery](collaboration.md) for scope and reproduction.
See [private releases](releases.md) for tag/commit identity, bounded private assets, retry/withdrawal history and interruption proof.
These results support J01/J02/J04/J06–J09 development behavior. Whole journeys and milestones require all current criteria;
a merged slice or manifest alone does not establish release acceptance.
The live status source remains unconfigured; evidence/status.json must not be edited to imply otherwise.
