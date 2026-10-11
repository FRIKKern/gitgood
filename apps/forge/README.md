# Gitgood forge

The Phoenix/Elixir backend owns authorization, collaboration records, Git storage and recovery. It uses Postgres for durable records and standard Git bare repositories for code.

**New here? Follow [Run Gitgood locally](../../docs/DEVELOPMENT.md)** for the complete database → API → web sequence, disposable accounts, and separate test resources. This page is the backend configuration and behavior reference. The [code map](../../docs/CODEBASE.md) points to the modules for each feature.

## Development configuration

Use the Elixir/OTP pins in [.tool-versions](../../.tool-versions), PostgreSQL 18.4, Git and Python 3.12 or later. Run backend commands from `apps/forge`.

| Setting | Development default | Purpose |
|---|---|---|
| `PGHOST`, `PGPORT` | `127.0.0.1`, `55432` | Isolated local Postgres server |
| `PGUSER`, `PGPASSWORD` | `gitgood`, empty password | Local database authentication |
| `PGDATABASE` | `gitgood_dev`; `gitgood_test` in tests | Database name; an explicit value overrides both defaults |
| `PORT` | `47841` | API listener, bound to loopback |
| `GITGOOD_PUBLIC_URL` | `http://localhost:47841` | Advertised API/Git origin |
| `GITGOOD_WEB_ORIGIN` | `http://localhost:47840` | Allowed browser origin |
| `GITGOOD_STORAGE` | Repository-root `.gitgood/repos` | Git storage; use an absolute, session-specific path |
| `GITGOOD_GIT`, `GITGOOD_PYTHON` | `git`, `python3` | Native executables or explicit executable paths |

The source of truth is [dev.exs](config/dev.exs), [test.exs](config/test.exs) and [runtime.exs](config/runtime.exs). The local walkthrough sets a unique database and storage so two worktrees do not share state.

`/health/ready` checks database migrations, writable storage, executables and any configured SSH listener. `/health/live` reports process/build identity separately. A live process is not automatically ready.

## Accounts and credentials

[Development seeds](priv/repo/seeds.exs) create `owner`, `reviewer`, `reader` and `outsider`, all with the disposable password `synthetic-password`. Seeding refuses production. For a real actor, the bootstrap task is `mix gitgood.bootstrap USER TEAM owner`, with `GITGOOD_BOOTSTRAP_PASSWORD` supplied through the environment. See [production instructions](../../docs/deployment/production.md) for the complete installation context.

Git credentials are separate from login passwords. Authenticated `POST /api/repos/:team/:name/credentials` issues a repository-scoped token once; `DELETE /api/credentials/:id` revokes an owned credential. Use the account username and token through a credential helper or interactive password prompt. Never store the token in a remote URL.

## Git over HTTP and SSH

HTTP clone URLs are `/git/:team/:name.git`. Readers can fetch; writers can push feature branches. The creator can initialize `main`, and subsequent raw pushes to `main` are denied. New tags use the durable push path; tag replacement and deletion are denied.

The native stateless `upload-pack` and `receive-pack` path currently admits 32 MiB input/output, 15 seconds for body upload, 60 seconds for Git, four concurrent requests, and 64 proposed refs. Managed packing uses two threads to stay within the worker memory ceiling. Forced rewrites, deletes, LFS and compressed RPC bodies are outside this slice. Read the [HTTP transport decision](../../docs/decisions/0003-native-http-transport.md) and [client compatibility matrix](../../docs/implementation/git-compatibility.md) before claiming support for another client feature.

SSH is opt-in. Set `GITGOOD_SSH_PORT` and a persistent `GITGOOD_SSH_HOST_KEY_DIRECTORY`; set `GITGOOD_SSH_PUBLIC_HOST` and `GITGOOD_SSH_PUBLIC_PORT` to the actual TCP route. The interface registers and revokes Ed25519 account keys. SSH applies the same permissions, main-branch protection and durable push rules. [SSH configuration and verification](../../docs/implementation/ssh.md) covers the full setup. OpenSSH `ssh-keygen` creates disposable test keys; it is not the application's SSH daemon.

## Feature contracts

| Feature | What the guide explains |
|---|---|
| [Browsing](../../docs/implementation/browsing.md) | Commit-bound trees, previews, history and bounded diffs |
| [Collaboration](../../docs/implementation/collaboration.md) | Same-repository pull requests, line reviews, checks and protected merge |
| [Import](../../docs/implementation/import.md) | Creator-owned full Git bundles, bounds, retries and interrupted import recovery |
| [Releases](../../docs/implementation/releases.md) | Tags/commits, actual change ranges, checksummed assets and retained corrections |
| [Barkpark](../../docs/implementation/barkpark.md) | Private account connections and supported external source contracts |
| [Criterion evidence](../../docs/implementation/criterion-evidence.md) | Evidence tied to criteria, source revisions and Git revisions |

## Verification and deployment

Run `mix precommit` and `mix format --check-formatted` with an isolated test database and storage; the [local guide](../../docs/DEVELOPMENT.md#4-check-your-change) provides the exact command. Backend tests cover actual Git storage, access rules, retries, reconciliation and bounded process behavior. Browser and interruption exercises establish additional properties.

Production has additional requirements, including `DATABASE_URL`, `SECRET_KEY_BASE`, `PHX_HOST`, HTTPS public/web origins, `GITGOOD_STORAGE` and `GITGOOD_PROXY_KEY`. The backend binds loopback behind the TLS edge. Configured production Barkpark connections also require their separate `GITGOOD_CONNECTION_KEY`. Use the [production guide](../../docs/deployment/production.md) for copied artifacts, migration/bootstrap, and verification; this configuration summary is not an installation procedure.

Development checks do not establish release acceptance. The [status guide](../../docs/STATUS.md) separates the implemented application from unfinished managed native startup and Cloud lifecycle work.
