# Production artifact experiment

Gitgood currently packages an Elixir OTP release and a TanStack SSR web service. This is an experimental deployment contract, not a managed Cloud release. Build and deployment must use one clean candidate. Do not reuse the development seed in production.

## Build

Use Elixir 1.20.4 / OTP 29.1.1, Node 22.23.3, PostgreSQL 18.4, Git with atomic update-ref transactions, and Python 3.12. The Windows proof uses Git 2.53.0.windows.3 and Python 3.12.14; Linux CI records its actual versions. Build releases on the target OS and architecture: Windows artifacts do not establish Linux compatibility.

From a clean checkout:

```sh
cd apps/web
npm ci
npm run check
npm run build
cd ../..
node scripts/stamp-build.mjs
cd apps/forge
mix deps.get --check-locked
MIX_ENV=prod mix release
```

Stamp after the web build, which clears dist. The stamp records the commit, dirty state, lockfiles, journey specifications and required migrations. The forge compiles that identity into its release; the web reads the matching artifact at startup. Keep both outputs together. A dirty artifact or mismatched component fails readiness.

Install the forge's entire `_build/prod/rel/gitgood` directory. Install web `dist/`, `server.mjs`, `client-address.mjs`, `package.json` and `package-lock.json`, then run `npm ci --omit=dev --ignore-scripts` there. Application source and Mix are unnecessary on the installed target. Git, Python and Node remain runtime requirements. Keep package installation and artifact storage private; sign/digest validation by a deployment system remains later work.

## Configuration and startup

The initial operator entry point reads retained local custody without claiming a
job or changing a file:

```sh
python3 tools/deployment/native_operator.py status \
  --history-directory /absolute/private/installation-history \
  --installation <expected-installation-uuid>
```

Run as the installation owner on Linux. It verifies private records, reads the
upgrade history, optional activation pointer and retirement journal, and refuses
if their identities or bytes change during observation. A dead recorded owner
produces an uncertain observation without rewriting or reconciling the journal.
An activation record reports retained metadata; it does not establish current
readiness, actual artifact/store identity, archive usability or Cloud/provider
inventory. The entry point currently exposes status only. Installation enrollment
and lifecycle commands remain separate implementation work. Private-invalid,
inconsistent or wrong-installation inputs refuse with a fixed error and no input
or exception details.

Four Linux checks passed, including a real killed journal owner, live-owner reads
that leave every retained file unchanged, concurrent record changes and private
input refusal. The complete operator suite passed 109 Linux checks with eight
foreign-platform skips. A separate observation reads the retained historical
installed upgrade and matches its independent configuration UUID without changing
configuration. The first supporting producer used an incorrect full candidate
suffix; its failed assertion and source remain retained. The corrected producer
checks the independently known short prefix and reports the full validated record
identity. It does not independently verify the historical artifact or current
readiness, and required CI on this new entry point remains pending.

Provide configuration through the service environment or a secret manager, never command arguments or repository files:

| Service | Configuration |
|---|---|
| Forge | `DATABASE_URL`, `SECRET_KEY_BASE` (at least 64 bytes of entropy), `PHX_HOST`, `GITGOOD_PUBLIC_URL`, `GITGOOD_WEB_ORIGIN`, `GITGOOD_STORAGE`, `GITGOOD_GIT`, `GITGOOD_PYTHON`, `GITGOOD_PROXY_KEY`, `PORT`, `PHX_SERVER=true` |
| Web | `GITGOOD_API_URL=http://127.0.0.1:<forge-port>`, `PORT`, `GITGOOD_PROXY_KEY`, `NODE_ENV=production` |

Public URL and web origin must be the same intended HTTPS origin. Provision the direct TLS edge, web and forge with the same separately managed 32-byte GITGOOD_PROXY_KEY. The edge overwrites its socket client address, the web authenticates and signs it, and the forge verifies it before login limiting. Unsigned or invalid production login context refuses; see [login origin bounds](../implementation/client-address.md). Extra proxies/CDNs need their own verified address contract. The forge and web bind loopback. PostgreSQL and bare Git storage are persistent, mutually dependent stores; neither belongs inside replaceable release directories. Use a dedicated OS identity and database credentials. Do not expose PostgreSQL, forge loopback, internal hook endpoints or service environment.

For SSH, provide GITGOOD_SSH_PORT, GITGOOD_SSH_HOST_KEY_DIRECTORY and the advertised GITGOOD_SSH_PUBLIC_HOST/PORT. Keep the persistent Ed25519 host key outside both release artifacts and Git repository storage. Route raw TCP separately to the loopback SSH listener. The copied-production harness generates isolated host/client fixtures, exercises native SSH and verifies their persistence after restart. See [SSH deployment bounds](../implementation/ssh.md); a real Cloud TCP route and replacement-host restoration still require their own evidence.

Run release migrations before service startup:
`bin/gitgood eval 'Gitgood.Release.migrate()'`.
Bootstrap a local actor once with `GITGOOD_BOOTSTRAP_USERNAME`, `GITGOOD_BOOTSTRAP_TEAM`, `GITGOOD_BOOTSTRAP_ROLE` and `GITGOOD_BOOTSTRAP_PASSWORD`, then `bin/gitgood eval 'Gitgood.Release.bootstrap()'`; remove bootstrap variables afterward. Bootstrap user/membership creation is transactional. There is no production signup or managed identity provider yet.

On Linux, bootstrap starts the native application and must use the installation's
pre-provisioned dedicated runtime cgroup through its supervisor or the packaged
`priv/operations/runtime_cgroup.py` helper. Stop the complete group before another
bootstrap or runtime admission and retain the empty group for marker verification.
Do not run bootstrap in the operator's still-populated parent group. Production
migration refuses when a previous runtime group is unbound, unavailable or still
contains descendants. Linux replacement-runtime admission additionally validates
that any processes present are exclusively its own new BEAM startup lineage,
using kernel process identities and group membership. Unrelated survivors refuse even after their BEAM
owner and database lease are gone. A first migration with no previous runtime
marker remains supported.

The packaged forge runs without automatic distributed Erlang registration; see [single-host releases](../decisions/0010-single-host-releases.md). Use the OS supervisor for stop/restart and release eval for offline maintenance. Remote/rpc commands are outside this profile.

For Barkpark account connections, select GITGOOD_BARKPARK_ORIGIN and provision GITGOOD_CONNECTION_KEY as a separate secret. Preserve the key with coordinated recovery materials; a database copy alone cannot recover encrypted source credentials. See [account connection bounds](../implementation/barkpark-accounts.md). An optional GITGOOD_BARKPARK_CA PEM path provides explicit source-issuer trust while certificate-chain and hostname checks remain enabled; default operation uses normal platform trust. Keep this trust configuration outside replaceable artifacts.

Start forge with `bin/gitgood start` and web with `npm start`. On Windows use `bin/gitgood.bat`. Use a supervisor that owns the complete process tree and persists logs privately. A production TLS proxy routes `/git/*` directly to the forge, everything else to the web, and denies `/internal/*`. See the direct-edge Caddy example; validate the deployed proxy separately, including request/time limits and no public backend bypass.

The example uses mutually exclusive path handles so the internal-path denial precedes the fallback, and an exact 33554432-byte body limit (32 MiB). Its response-header timeout allows the bounded upload and Git processing intervals. Syntax/routing guidance comes from [Caddy handle/order](https://caddyserver.com/docs/caddyfile/directives/handle), [body limits](https://caddyserver.com/docs/caddyfile/directives/request_body) and [reverse proxy transport](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy); this source review is separate from deployed proxy verification.

The example disables expanded config persistence and filters request/response header objects from the default runtime logger. Access-log filtering alone does not cover reverse-proxy errors or cancelled-stream warnings, which can include the private edge header. Keep the runtime filter when adding operator log destinations; separately configured access loggers need the same filter. Route, status, time and failure diagnostics remain available. See [Caddy global logging](https://caddyserver.com/docs/caddyfile/options#log) and [field filtering](https://caddyserver.com/docs/caddyfile/directives/log#filter).

## Readiness and replacement

`/health/live` reports process/build identity. Forge `/health/ready` checks database migrations, writable storage, required executables and clean build identity. Web readiness additionally requires a ready forge with exactly the same candidate. Readiness is a prerequisite for routing traffic, not a complete backup/restore or security proof.

Quiesce writes, drain and stop all old forge instances before migration/replacement. The operation/reconciler protocol currently assumes one deployed version against a repository's stores. Do not use the existing Cloud blue/green overlap without an explicit protocol compatibility proof. Start the matching candidate, reconcile unfinished operations, require both readiness probes, then route traffic. Rollback requires a schema-compatible previous artifact and matching stores; incompatible migrations need a tested recovery procedure.

## Reproduce the disposable artifact proof

After a clean stamped build/release, run `npm run verify:production` in apps/web. Supply GITGOOD_CADDY pointing to the pinned Caddy 2.11.7 binary; the harness validates and runs the committed direct-edge example with disposable TLS and private configuration. The workflow downloads the exact Linux release and verifies its published SHA-512 checksum before use. Supply a disposable PostgreSQL role able to create fixture databases through `PGHOST`, `PGPORT`, `PGUSER` and `PGPASSWORD` when needed. Defaults are isolated loopback port 55432 and role gitgood. Supply `GITGOOD_CREATEDB`, `GITGOOD_OPENSSL`, `GITGOOD_GIT` and `GITGOOD_PYTHON` when they are absent from PATH; Windows may use `GITGOOD_BROWSER_CHANNEL=msedge`.

The harness copies compiled artifacts to a fresh temporary installation, installs only production web dependencies, migrates a new database and creates synthetic owner/reviewer/reader/outsider actors. It proves independent login buckets through actual TLS client sockets from two addresses, the unchanged 20/21 attempt boundary despite spoofed forwarding fields, and unsigned direct web/forge refusal. It then exercises nine browser/client flows through the actual Caddy edge with TLS, real Git with explicit CA verification, native SSH, full-bundle import, private discovery and access changes, process restart with persistent sessions/database/Git refs/import provenance, published release identities/change ranges/asset bytes, withdrawn/corrected history and download refusal, unavailable storage and mismatched component identities. Native activity links/timestamps and membership audit UUIDs must survive restart; removed members must remain denied in search. Browser TLS bypass is confined to its self-signed disposable certificate; the real Git client must verify the CA. The separate owned source HTTPS wire has synthetic service credentials, explicit issuer trust and normal backend TLS verification. Its linked-record workflow uses the actual encrypted connection and native link APIs, then retains link lifecycle, original attach receipts and decrypted per-viewer source access after release restart. The criterion-evidence workflow additionally exercises real native Git, source-bound task criteria, lost-reply retry, checksummed private downloads, changed requirements and retained reassessment/unavailable-artifact history. Original provenance and download refusals must survive release restart through both the native API and web proxy. A browser account-settings fixture still uses intercepted synthetic responses. Neither source wire nor prototype navigation is complete live J10 or managed Cloud acceptance.

Retained sanitized results are in ignored `apps/web/test-results-production/`. Private installation logs, fixture database and storage remain available for diagnosis; Caddy access evidence excludes all request/response headers and runtime logs are checked for the edge secret. Expanded configuration stays private and the harness disables global config persistence; credentials and TLS keys are not CI artifacts. Process restart on the same host is not replacement-host restore or storage power-loss recovery.

The production run also requires an actual pinned-Caddy privacy exercise: verified TLS, edge identity replacement, direct Git header stripping, internal-route denial, an upstream socket failure and a cancelled stream. Their runtime diagnostics must omit private headers. The completed main Caddy log is checked again after browser/restart work; a check before those requests cannot establish later log hygiene.

## Required before a private-team release

Managed identity integration, verified Cloud SSH routing and broader Git compatibility, measured release-asset capacity and permission-aware activity, actual TLS/OS/service configuration, resource/storage quotas, private artifact provenance, dependency maintenance, coordinated backups and replacement-host restores, runtime observability, upgrades/rollback and managed Cloud support remain their milestone gates. Consult [D06](../decisions/D06.md) and the run finish record for current evidence.
