# Supported repository import

Gitgood imports an uploaded full SHA-1 Git version-2 bundle into an empty managed repository. The repository creator must retain current write membership and a valid session. The bundle must include refs/heads/main and may contain up to 64 unique branches and tags. The file limit is 32 MiB.

From a source you can read:

```sh
git bundle create source.bundle --branches --tags
git bundle verify source.bundle
```

Choose the bundle on the empty repository page. The browser shows the waiting/queued/applied/failed/uncertain operation and records the source name, SHA-256, byte count and exact imported refs. Refresh/reload can observe the durable result. Resume a waiting operation with the identical file; cancel it before selecting a different source. A populated repository refuses another import.

## API and authorization

POST /api/repos/:team/:name/imports takes an idempotency-key and exactly source_name, source_sha256 and source_bytes. Fields identifying the actor, credential and repository are assigned by Elixir. Replaying the same request returns its original responsibility, even after a terminal result; a changed body conflicts. Only one unfinished import may exist per repository.

PUT /api/repos/:team/:name/imports/:id/source takes application/octet-stream bytes, a current session and browser CSRF protection. The upload is bounded and hashed server-side; the declared digest and size must match. It stages a complete immutable source then returns 202 while an independent worker performs import. Response loss does not erase responsibility. GET /api/repos/:team/:name/operations/:id and the operation list report it to authorized repository readers.

DELETE /api/repos/:team/:name/imports/:id cancels only a waiting source. Validated/applied/uncertain work cannot be deleted to suppress its responsibility. The source intent remains bound to its original session credential; a queued revoked/expired credential fails before publishing refs. Revocation or membership changes wait for an already admitted bounded lease and deny later admission.

No source URL, client-selected server path, upstream credential or source hook/config is accepted. The BFF streams only the canonical binary-source route, with a 32 MiB bound and fixed upstream. Ordinary JSON keeps its 1 MiB limit. Backend authorization and all byte/digest limits also apply to direct API callers.

## Atomicity and recovery

Gitgood validates the bounded header, verifies the full bundle and streams its pack to explicitly strict/self-contained native index-pack in a private bare validation store. Strict fsck and advertised object-type checks there establish the source independently of any earlier target objects. Malformed sources cannot install objects into the managed target. The validated pack then installs in the target without refs. Gitgood never checks out source code. The complete expected refs commit independently in PostgreSQL before a single Git update-ref transaction creates all refs and refs/gitgood/imports/:operation_id. transfer.hideRefs hides internal markers from normal fetch advertisement.

Pushes, merges and import hold the same repository lock. A competing initialization first leaves the import failed without overwriting that history. An exact hidden marker proves the import event even after a later branch advances. An absent marker proves the atomic import transaction did not commit. Unavailable storage or an inconsistent marker leaves uncertainty visible and blocks mutation.

- Before durable validation, restart resumes queued complete source with current authorization.
- After validation and before refs, restart records failed; a new request key can start a fresh attempt on the still-empty target.
- After atomic refs and before SQL outcome, restart records applied with the original identity.
- Busy native/transport capacity retains queued work for the periodic reconciler.

Two independent import workers share four transport slots and four bounded native processes. Each worker has a 90-second wall-clock ceiling. Native steps use 15- or 60-second deadlines, output/memory/process-group limits and stripped environments. Three durably counted automatic execution attempts prevent repeated interrupted work from cycling indefinitely. After the limit, the stable outcome fails and the creator can explicitly create another attempt on an empty target.

## Retention and compatibility

Waiting responsibilities remain until resumed or explicitly cancelled. Complete staged bundles and validation stores survive unfinished work and are deleted after applied/failed outcomes. Validation directories are removed only when their resolved path is the operation's exact directory inside staging and it is an ordinary directory. Only internal UUID partial files older than one hour are removed during reconciliation. Unknown files, symlinks and unfinished complete sources are preserved. Staging and validation directories use mode 0700 and intake files 0600 where the platform supports them; the entire Git store must be private to its service account. Include unfinished staging in consistent backup/restore.

Import provenance/outcome records are retained. Validated objects installed before failed publication remain unreachable; automatic Git garbage collection is not implemented. Do not delete object files to force an import retry. Header lines are bounded to 2048 bytes and the header to 64 KiB in addition to the ref/file bounds.

Unsupported: version-3/SHA-256, prerequisites/incremental/filtered bundles, missing main, other refs, larger files or more refs. LFS objects, submodule repositories, issues, review records, CI, credentials and forge settings are not imported. LFS pointers and .gitmodules remain source files. Imported tags are retained and fetched; normal tag push remains denied.

Quiesce older forge versions before applying the import migration and activating matching artifacts. The migration's downgrade refuses when import records exist. Preserve responsibility and use compatible rollback artifacts.

## Evidence and reproduction

```sh
cd apps/forge
mix precommit
PGDATABASE=gitgood_recovery GITGOOD_STORAGE=.gitgood/recovery mix ecto.create
PGDATABASE=gitgood_recovery GITGOOD_STORAGE=.gitgood/recovery mix ecto.migrate
# Each failure-point command exits 70 intentionally; reconciliation runs in a new VM.
PGDATABASE=gitgood_recovery GITGOOD_STORAGE=.gitgood/recovery GITGOOD_FAILURE_POINT=before_outcome mix run verification/import_vm_crash.exs
PGDATABASE=gitgood_recovery GITGOOD_STORAGE=.gitgood/recovery GITGOOD_FAILURE_POINT=reconcile mix run verification/import_vm_crash.exs
cd ../web
npx playwright test e2e/import.spec.ts
```

Backend integration tests use real transactions in the disposable test database because an independent durable write cannot be verified in a shared outer sandbox transaction. Fixtures remove only their identified records. They cover refs/history, replay, corrupted source, network/path denial, roles/revocation, partial intake, capacity, competing writes and worker death. Whole-VM checks run before_validation, before_ref, after_ref and before_outcome. Browser/native-client checks preserve historical commits, annotated tags and a binary bundle above the ordinary JSON limit.

Copied production artifacts repeat the browser/client journey and restart persistence. Candidate/spec manifests, actual test results and CI conclusions establish freshness. This document alone does not mark J05 or M4 verified.
