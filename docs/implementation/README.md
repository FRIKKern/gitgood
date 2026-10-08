# Implementation evidence and reproduction

The native implementation is in apps/forge and apps/web. Start with their setup instructions.
It remains a development product with no configured public deployment or Barkpark evidence ledger.

Run mix precommit in apps/forge, npm run check in apps/web and npx playwright test in apps/web with the forge running.
The workflow repeats these against disposable Postgres on Linux. Artifacts are private and contain synthetic fixtures.
On Windows set GITGOOD_BROWSER_CHANNEL=msedge and executable paths for GITGOOD_GIT, GITGOOD_PYTHON and GITGOOD_OPENSSL.

The backend suite covers ownership, durable initialization, retries, invalid/duplicate names, outsider/role denial,
session expiry/revocation, membership removal, CSRF, storage failure, and upgrade of existing managed stores.
Its subprocess tests verify binary stdin/EOF, secret stripping, deadline/caller cancellation of descendants,
concurrency admission, output bounds and child memory limits.

Browser tests cover private creation/reload/sign-out and real Git HTTPS clone, commit, push and fetch.
They check reader/outsider denial, username binding, invalid TLS trust, protected main, interrupted upload/retry,
oversized body rejection, credential revocation and strict fsck.
Credentials are injected through process environment, never Git arguments or trace artifacts.

These checks support parts of J01, J02 and J09. Whole journeys and milestones require their complete criteria;
merging a slice does not satisfy those criteria. D04 is implemented by the native transport decision;
D05 still requires protected merge/restart experiments.
The status source remains unconfigured. evidence/status.json must not be hand-edited to imply otherwise.
