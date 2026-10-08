# Commit browsing
The browser opens /repos/TEAM/NAME?sha=COMMIT&path=PATH&view=code (or diff).
Branch selection resolves its current tip once; refreshing branches preserves the viewed SHA.
Files, history entries, breadcrumbs and commit diffs have shareable commit URLs.

The backend checks team membership before any Git access. Requested commits must be reachable from a current
branch or commit tag; deleted/unreachable commits are refused. Tag-only release commits can be navigated without
exposing internal recovery refs. Git receives separate arguments, and filenames are resolved
through tree entries. Text renders in React pre elements. Symlinks are previewed as blob text, never followed.
Binary files and submodules have explicit states. Preview/tree/diff output is bounded to 256 KiB, history to
50 commits, and branch listings to 256 entries. Invalid filename encodings are displayed with an explicit
unsupported-encoding label and cannot be navigated. Unavailable loads offer retry while retaining URL context.

Evidence: backend fixtures cover literal shell-like names, binary/large output, deleted refs, unreachable objects,
outsider denial and malformed revisions/paths. The real Git browser fixture checks stable reload, script text,
branch refresh and explicit selection after a real push. Current scope supports J04 development criteria;
full product acceptance still requires the evidence ledger and wider interaction coverage.
