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

Browse admission allows four active requests and eight FIFO waiting callers, with a five-second admission
deadline. Waiting work runs in the requesting process, so abandoned callers cannot start detached reads.
Cancellation releases capacity. Excess or expired admissions return `503 browse_busy_retry`; temporary
Git-command failure returns `503 git_unavailable`, including during commit reachability checks. Actual
unreachable commits retain their explicit refusal. Native team authorization precedes admission. The existing
four-command subprocess limit remains in effect; other operations can consume that capacity.

The first reference-guest pilot at candidate `9149a25b864da6e5713c54a5fde2ba5348176565` failed its concurrent
read targets. Its QEMU TCG guest had four virtual CPUs and 4 GiB on a shared physical host. Sequential
warmups passed, but eight independent readers observed 503 responses, misleading 422 responses from
reachability failures, and request timeouts. Warm P95 ranged from 5267 to 10053 ms against 1500 ms;
the ten process-cold directory reads were correct but had a 5781 ms P95 against 5000 ms. Five imports,
five verified TLS clones and thirty fetches passed their separate targets. This admission change requires
fresh measurement; the original failed samples remain private evidence and do not establish M4 acceptance.

Evidence: backend fixtures cover literal shell-like names, binary/large output, deleted refs, unreachable objects,
outsider denial and malformed revisions/paths. The real Git browser fixture checks stable reload, script text,
branch refresh and explicit selection after a real push. Current scope supports J04 development criteria;
full product acceptance still requires the evidence ledger and wider interaction coverage.
