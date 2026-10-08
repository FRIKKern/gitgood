# Gitgood forge
Native Phoenix API with Postgres records and standard Git bare repositories.

Use the pinned Elixir/OTP versions in the root .tool-versions, Postgres 18.4, Git and Python 3.12+.
Set GITGOOD_GIT and GITGOOD_PYTHON to executable paths when they are absent from PATH.
On Windows, dot-source ../../scripts/windows-runtime.ps1 for isolated Elixir/OTP binaries, then run mix local.hex --force.

Configure PGHOST, PGPORT (default 55432), PGUSER (default gitgood), PGPASSWORD and PGDATABASE.
The development defaults require an isolated loopback database.

```sh
mix deps.get
mix ecto.create
mix ecto.migrate
mix run priv/repo/seeds.exs
mix phx.server
```

Disposable login: owner / synthetic-password. reviewer is a writer; reader and outsider exercise denial paths.
The seed refuses production. Bootstrap a real actor with GITGOOD_BOOTSTRAP_PASSWORD in the environment and
`mix gitgood.bootstrap USER TEAM owner`. Passwords and tokens must never be arguments or saved in remote URLs.

The API listens at http://localhost:47841; /health/ready checks migrations, writable storage and native executables. /health/live reports process/build identity separately.
The web origin defaults to http://localhost:47840. Storage defaults to ignored .gitgood/repos.
Production requires DATABASE_URL, SECRET_KEY_BASE, PHX_HOST, GITGOOD_PUBLIC_URL, GITGOOD_WEB_ORIGIN and GITGOOD_STORAGE.
Public origins require HTTPS; the backend binds loopback behind a TLS proxy. No public deployment is configured.
For compiled releases, transactional bootstrap and copied-artifact verification, see [production instructions](../../docs/deployment/production.md).

Authenticated POST /api/repos/:team/:name/credentials issues a repository-scoped Git token once.
DELETE /api/credentials/:id revokes an owned credential. Git uses HTTP Basic with the account username and this token.
Use a credential helper or an interactive password prompt. Clone URLs are /git/:team/:name.git.
Readers can fetch; writers can push feature branches. The creator may initialize main; subsequent raw main pushes are denied.
Managed stores are upgraded before transport is admitted.

The transport uses native stateless upload-pack and receive-pack. Current limits are 32 MiB input/output, 15 seconds
for body upload, 60 seconds for Git, four concurrent requests, and 64 proposed refs. Forced rewrites, deletes,
LFS and compressed RPC bodies are outside this slice. New tags are supported through the same durable push path;
tag replacement/deletion are denied so released identities cannot be silently reassigned.
See [the transport decision](../../docs/decisions/0003-native-http-transport.md).

Native SSH is opt-in through GITGOOD_SSH_PORT and a persistent GITGOOD_SSH_HOST_KEY_DIRECTORY.
Set GITGOOD_SSH_PUBLIC_HOST/PORT to the verified TCP route. Ed25519 account keys are registered and
revoked in the web interface; the same permissions, protected-main policy and durable push records apply.
See [SSH configuration and verification](../../docs/implementation/ssh.md). OpenSSH ssh-keygen is needed
for disposable test keys, not as the production SSH daemon.

Creator-owned full Git bundle import initializes an empty repository with atomic branches/tags and
durable source/outcome responsibility. See [supported import and recovery](../../docs/implementation/import.md)
for source bounds, explicit limitations, replay, staging retention and whole-VM verification.

Private releases pin tags/commits and actual change ranges, own bounded checksummed assets in Postgres,
and retain corrections/withdrawals. See [release publication and recovery](../../docs/implementation/releases.md).

Run mix precommit against isolated gitgood_test. The suite includes real Git storage, authorization, retry,
reconciliation, process timeout, cancellation, concurrency, memory and output limits.
The web suite additionally exercises trusted HTTPS clone/push/fetch, interrupted upload/retry, revocation,
protected main and Git fsck. These checks establish development evidence, not release acceptance.
