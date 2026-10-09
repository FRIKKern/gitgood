# Offline full-bundle import

Status: bounded implementation under verification, 8 October 2026. Owner: Codex under delegated authority.

The first allowed source for J05 is a self-contained SHA-1 version-2 Git bundle supplied by the repository creator through an authenticated session. Require main and accept up to 64 unique branches and tags in a file no larger than 32 MiB. The target must be an empty managed repository. Existing creator-only initial-main semantics apply.

This establishes supported repository import within PRODUCT.md; universal importer parity remains excluded. It does not remove another release requirement. HTTPS and SSH source access can be used by the user to obtain their source locally. Gitgood does not fetch URLs, accept server filesystem paths, retain upstream credentials or promise preservation of external forge metadata. A bundle does not establish the uploader's ownership of an external forge account.

Validate the source in its own private bare store: bounded header, native bundle verification, streamed native index-pack with strict/self-contained checks, strict fsck and advertised object-type checks. This prevents malformed objects entering the managed store and prevents a source borrowing missing advertised history from earlier target objects. Only the validated pack is then installed, without advertising refs. One update-ref transaction creates all accepted branches/tags and a hidden marker. PostgreSQL commits the exact expected ref set on an independent connection first. The creator/session/membership/repository lease serializes import with pushes, merges and revocation.

Intake creates one replayable durable responsibility per repository. Truncated uploads retain that waiting identity, complete uploads stage privately and queue independent bounded workers, and lost responses query/reuse the same operation. A process death before durable validation can resume queued source. After validation, an absent marker proves no import transaction committed; an exact marker proves the atomic event, including after later legitimate branch changes. Missing storage or an inconsistent marker stays uncertain and blocks writes.

Automatic execution is capped at three durably recorded attempts, two import workers, four shared transport slots and four shared native command processes. Workers have a 90-second wall-clock ceiling; source upload has a 15-second deadline. Busy work remains queued. Terminal source files and their internal validation directories are removed; abandoned UUID partial files age out after one hour. Durable provenance and outcome records are retained, as are validated unreachable Git objects pending a separately verified storage-maintenance policy.

Alternatives: a server URL importer adds credential custody, DNS/IP revalidation, redirect and network egress policy, and remote-protocol compatibility before the initial import can be supported. Adopting Forgejo as importer authority would introduce a second repository/permission owner. Neither is needed for the bounded bundle contract.

Compatibility: version-3/SHA-256, prerequisite/incremental/filtered bundles, missing main, arbitrary refs and more than 64 refs are rejected. Tags are retained and readable; ordinary tag push is still denied. LFS objects and submodule repositories are not downloaded. Issues, reviews, CI, source credentials and forge settings are not imported. Source pointers and .gitmodules are preserved as ordinary Git files.

This adds an operation kind and migration invariant. Quiesce older forge processes before migrating and activating the matching artifacts; overlapping old/new mutation services are unverified. Downgrade refuses when import responsibility exists. Roll back using compatible artifacts while preserving records.

Evidence: real-transaction backend/recovery tests, whole-VM failure-point harness and browser/native-client import are required on the current candidate. The initial offline atomic-ref experiment informed the design; it does not by itself establish J05. See [implementation and reproduction](../implementation/import.md).

Primary references: [git bundle](https://git-scm.com/docs/git-bundle), [git update-ref](https://git-scm.com/docs/git-update-ref).

Strict-pack boundary review: Git 2.55.0's [bundle CLI](https://github.com/git/git/blob/v2.55.0/builtin/bundle.c) passes default unbundle options; [bundle implementation](https://github.com/git/git/blob/v2.55.0/bundle.c) enables pack object checks only when its explicit fsck flag is set. Do not infer strict validation from unbundle or transfer configuration. The trusted Python adapter forwards only the bundle pack's file descriptor to explicitly strict native index-pack under the existing process group/job boundary. It does not buffer the whole file or run source-supplied programs.
