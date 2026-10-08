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

Install the forge's entire `_build/prod/rel/gitgood` directory. Install web `dist/`, `server.mjs`, `package.json` and `package-lock.json`, then run `npm ci --omit=dev --ignore-scripts` there. Application source and Mix are unnecessary on the installed target. Git, Python and Node remain runtime requirements. Keep package installation and artifact storage private; sign/digest validation by a deployment system remains later work.

## Configuration and startup

Provide configuration through the service environment or a secret manager, never command arguments or repository files:

| Service | Configuration |
|---|---|
| Forge | `DATABASE_URL`, `SECRET_KEY_BASE` (at least 64 bytes of entropy), `PHX_HOST`, `GITGOOD_PUBLIC_URL`, `GITGOOD_WEB_ORIGIN`, `GITGOOD_STORAGE`, `GITGOOD_GIT`, `GITGOOD_PYTHON`, `PORT`, `PHX_SERVER=true` |
| Web | `GITGOOD_API_URL=http://127.0.0.1:<forge-port>`, `PORT`, `NODE_ENV=production` |

Public URL and web origin must be the same intended HTTPS origin. The forge and web bind loopback. PostgreSQL and bare Git storage are persistent, mutually dependent stores; neither belongs inside replaceable release directories. Use a dedicated OS identity and database credentials. Do not expose PostgreSQL, forge loopback, internal hook endpoints or service environment.

For SSH, provide GITGOOD_SSH_PORT, GITGOOD_SSH_HOST_KEY_DIRECTORY and the advertised GITGOOD_SSH_PUBLIC_HOST/PORT. Keep the persistent Ed25519 host key outside both release artifacts and Git repository storage. Route raw TCP separately to the loopback SSH listener. The copied-production harness generates isolated host/client fixtures, exercises native SSH and verifies their persistence after restart. See [SSH deployment bounds](../implementation/ssh.md); a real Cloud TCP route and replacement-host restoration still require their own evidence.

Run release migrations before service startup:
`bin/gitgood eval 'Gitgood.Release.migrate()'`.
Bootstrap a local actor once with `GITGOOD_BOOTSTRAP_USERNAME`, `GITGOOD_BOOTSTRAP_TEAM`, `GITGOOD_BOOTSTRAP_ROLE` and `GITGOOD_BOOTSTRAP_PASSWORD`, then `bin/gitgood eval 'Gitgood.Release.bootstrap()'`; remove bootstrap variables afterward. Bootstrap user/membership creation is transactional. There is no production signup or managed identity provider yet.

Start forge with `bin/gitgood start` and web with `npm start`. On Windows use `bin/gitgood.bat`. Use a supervisor that owns the complete process tree and persists logs privately. A production TLS proxy routes `/git/*` directly to the forge, everything else to the web, and denies `/internal/*`. See the Caddy example; validate the deployed proxy separately, including request/time limits and no public backend bypass.

The example uses mutually exclusive path handles so the internal-path denial precedes the fallback, and an exact 33554432-byte body limit (32 MiB). Its response-header timeout allows the bounded upload and Git processing intervals. Syntax/routing guidance comes from [Caddy handle/order](https://caddyserver.com/docs/caddyfile/directives/handle), [body limits](https://caddyserver.com/docs/caddyfile/directives/request_body) and [reverse proxy transport](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy); this source review is separate from deployed proxy verification.

## Readiness and replacement

`/health/live` reports process/build identity. Forge `/health/ready` checks database migrations, writable storage, required executables and clean build identity. Web readiness additionally requires a ready forge with exactly the same candidate. Readiness is a prerequisite for routing traffic, not a complete backup/restore or security proof.

Quiesce writes, drain and stop all old forge instances before migration/replacement. The operation/reconciler protocol currently assumes one deployed version against a repository's stores. Do not use the existing Cloud blue/green overlap without an explicit protocol compatibility proof. Start the matching candidate, reconcile unfinished operations, require both readiness probes, then route traffic. Rollback requires a schema-compatible previous artifact and matching stores; incompatible migrations need a tested recovery procedure.

## Reproduce the disposable artifact proof

After a clean stamped build/release, run `npm run verify:production` in apps/web. Supply a disposable PostgreSQL role able to create fixture databases through `PGHOST`, `PGPORT`, `PGUSER` and `PGPASSWORD` when needed. Defaults are isolated loopback port 55432 and role gitgood. Supply `GITGOOD_CREATEDB`, `GITGOOD_OPENSSL`, `GITGOOD_GIT` and `GITGOOD_PYTHON` when they are absent from PATH; Windows may use `GITGOOD_BROWSER_CHANNEL=msedge`.

The harness copies compiled artifacts to a fresh temporary installation, installs only production web dependencies, migrates a new database and creates synthetic owner/reviewer/reader/outsider actors. It exercises both browser journeys through TLS, real Git with explicit CA verification, process restart with persistent sessions/database/Git refs, unavailable storage and mismatched component identities. Browser TLS bypass is confined to its self-signed disposable certificate; the real Git client must verify the CA.

Retained sanitized results are in ignored `apps/web/test-results-production/`. Private installation logs, fixture database and storage remain available for diagnosis; credentials and TLS keys are not CI artifacts. Process restart on the same host is not replacement-host restore or storage power-loss recovery.

## Required before a private-team release

Managed identity/revocation UX, SSH/import decisions, assets/search/workspace scope, actual TLS/OS/service configuration, resource/storage quotas, private artifact provenance, dependency maintenance, coordinated backups and replacement-host restores, runtime observability, upgrades/rollback and managed Cloud support remain their milestone gates. Consult [D06](../decisions/D06.md) and the run finish record for current evidence.
