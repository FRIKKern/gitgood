# Run Gitgood locally

[Docs home](README.md) · [Code map](CODEBASE.md) · [Current status](STATUS.md)

This guide runs the development interface and API against your own local Postgres database. You will be able to sign in, create a private repository, and explore the implemented workflow. Managed installation and release verification have their own [production guide](deployment/production.md).

The commands below were checked against the repository's configuration and workflows. They were not freshly executed as part of this documentation change. See [implementation evidence](implementation/README.md) for recorded experiments and their limits.

## Before you start

Use a separate checkout or worktree for your change. The shell examples use Bash on Linux or WSL; Ubuntu 24.04 on x86_64 is the production build target.

| Dependency | Repository baseline | Why it is needed |
|---|---|---|
| Erlang/OTP | 29.1.1 | Elixir runtime |
| Elixir | 1.20.4, built for OTP 29 | Phoenix API and backend checks |
| Node.js | 22.23.3 | Web application and repository checks |
| PostgreSQL server and clients | 18.4 | Collaboration data; exact client versions also matter for recovery |
| Git | Available on `PATH` | Actual repository storage and transport |
| Python | 3.12 or later, as `python3` | Bounded subprocess and recovery helpers |
| OpenSSL CLI | Available as `openssl` on `PATH` | Local TLS fixtures in reporting and application checks |

Runtime pins live in [.tool-versions](../.tool-versions) and [.node-version](../.node-version). The root planning scripts accept Node `>=22.13.1 <23` and have no package dependencies.

You need an **existing, isolated PostgreSQL 18.4 server on loopback**, with a development role that can create its own databases. The steps below create a new database; they do not install or start PostgreSQL. Use your local server's actual port and credentials. The example port is `55432` and role is `gitgood`, matching the development defaults. Keep this server separate from installations and retained recovery fixtures.

## 1. Prepare the API and database

Start in the repository root in a fresh development shell. Supply the password through `PGPASSWORD`: the API reads that environment variable directly. The prompt below keeps it out of shell history and command-line arguments.

```bash
export PGHOST=127.0.0.1
export PGPORT=55432
export PGUSER=gitgood
read -r -s -p 'Local database password: ' PGPASSWORD
printf '\n'
export PGPASSWORD
psql -d postgres -Atc 'SHOW server_version'

# Keep the printed name: use these same values when returning to this session.
export GITGOOD_DEV_ID="$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
export PGDATABASE="gitgood_dev_${GITGOOD_DEV_ID}"
export GITGOOD_STORAGE="$PWD/.gitgood/dev-${GITGOOD_DEV_ID}/repos"
printf 'Development database: %s\nStorage: %s\n' "$PGDATABASE" "$GITGOOD_STORAGE"

export MIX_ENV=dev
export PORT=47841
export GITGOOD_PUBLIC_URL=http://localhost:47841
export GITGOOD_WEB_ORIGIN=http://localhost:47840
export GITGOOD_GIT="$(command -v git)"
export GITGOOD_PYTHON="$(command -v python3)"

cd apps/forge
mix local.hex --force
mix deps.get --check-locked
mix ecto.create
mix ecto.migrate
mix run priv/repo/seeds.exs
mix phx.server
```

Check that the server reports `18.4` before creating the database. Run the Mix commands in order and stop at any failure. Use development environment settings only; leave native supervision, retirement verification, production proxy keys, and optional SSH settings unset for this walkthrough.

The API binds `127.0.0.1:47841`. In another terminal, `curl --fail http://127.0.0.1:47841/health/ready` should return HTTP 200 with `"status":"ready"` and passing `checks`. Readiness checks the database, storage and native executable availability. `/health/live` reports the process and build separately; it does not establish readiness.

## 2. Start the web interface

Open a second terminal at the same repository root:

```bash
cd apps/web
export GITGOOD_API_URL=http://127.0.0.1:47841
npm ci
npm run dev
```

Open **http://localhost:47840**. Use that hostname consistently: the API checks the configured web origin. The web server listens on loopback and forwards `/api/` requests to the fixed server-side `GITGOOD_API_URL`.

Ports `47840` and `47841` must be free. If another checkout owns them, select a different pair: change the API's `PORT`, `GITGOOD_PUBLIC_URL` and `GITGOOD_WEB_ORIGIN`, update the web's `GITGOOD_API_URL`, then start Vite with `npm exec vite -- --host 127.0.0.1 --port YOUR_WEB_PORT --strictPort`. Keep all four addresses consistent; do not stop an unrelated listener to reclaim its port.

## 3. Try the first workflow

All four disposable accounts use the password **`synthetic-password`**:

| Account | Membership | Useful for |
|---|---|---|
| `owner` | Owner of `team` | Creating repositories and managing team access |
| `reviewer` | Writer in `team` | Review and ordinary write access |
| `reader` | Reader in `team` | Checking read-only behavior |
| `outsider` | Owner of `elsewhere` | Checking that another team's private data stays hidden |

Sign in as `owner`, create a repository under `team`, and open it. For Git operations, create a repository-scoped Git credential in the interface and use the shown clone URL. Git uses your account name and that token through a credential helper or password prompt. The login password is not a Git token.

An empty repository needs its first commit before there is code to browse. The creator can initialize `main`; later direct pushes to `main` are protected. Use feature branches and a pull request for subsequent changes. See the [Git transport contract](decisions/0003-native-http-transport.md), [review workflow](implementation/collaboration.md), and [compatibility limits](implementation/git-compatibility.md).

These seeds are for isolated development and refuse `MIX_ENV=prod`. They do not provision a production installation. Optional SSH and Barkpark connections require additional configuration described in the [forge guide](../apps/forge/README.md).

## 4. Check your change

Choose checks for the part you changed. The root scripts validate documentation and reporting; they do not run the application suites.

| Change | Run from | Commands |
|---|---|---|
| Documentation, scope, reporting or changelog | Repository root | `npm run generate`, then `npm run check` |
| Backend behavior | `apps/forge` | `mix precommit`, then `mix format --check-formatted`, using a separate test database and storage below |
| Web behavior | `apps/web` | `npm run check` for the production build, TypeScript, and proxy/runtime checks |
| User workflow, Git protocol or recovery | Dedicated verification environment | Follow the relevant [implementation guide](implementation/README.md) and [required product workflow](../.github/workflows/product.yml) |

**Do not run backend tests with the development database still selected.** `PGDATABASE` overrides the default database in both development and test configuration. This subshell uses the same isolated PostgreSQL server credentials but gives the test run its own database and storage:

```bash
# Run from the repository root, with PGHOST/PGPORT/PGUSER and credentials set.
(
  cd apps/forge
  test_id="$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
  export PGDATABASE="gitgood_test_${test_id}"
  export GITGOOD_STORAGE="$PWD/.gitgood/test-${test_id}"
  unset MIX_ENV
  mix precommit && mix format --check-formatted
)
```

`mix precommit` selects the test environment, compiles with warnings as errors, removes unused dependency locks, formats Elixir, and runs the test alias that creates/migrates the selected database. Review resulting source changes. Keep tests sequential within one checkout; individual tests also manage their own fixtures.

Browser tests require seeded identities, real Git tools, and feature-specific fixtures. Copied-production verification additionally needs pinned PostgreSQL recovery clients, OpenSSH, Chromium, Caddy, clean build identity, and the Linux process-isolation setup. The [CI workflow](../.github/workflows/product.yml) defines the full sequence; the [isolated CI guide](implementation/isolated-ci.md) explains its host boundary. A local build or green unit suite alone does not certify a complete journey or release.

## Returning to your work

Stop the API and web processes you started with `Ctrl+C`. Your database and Git storage persist. Restart with the same `PGDATABASE` and `GITGOOD_STORAGE` values to keep your work; generating another ID starts a separate session. This guide intentionally does not delete databases or retained storage.

If the page reports that the forge is unavailable, check `/health/ready`, the API terminal, and `GITGOOD_API_URL` first. If sign-in returns `origin_denied`, compare the browser's full origin with `GITGOOD_WEB_ORIGIN`. If the API cannot start, check PostgreSQL connectivity and that the selected listener is free before changing configuration.

## Windows notes

The Bash sequence above is intended to run entirely inside Linux or WSL. Keep that checkout, toolchain, database and processes in the same environment.

For native PowerShell development, [scripts/windows-runtime.ps1](../scripts/windows-runtime.ps1) downloads and checksum-verifies the pinned Windows OTP, Elixir and Node archives. From the repository root, dot-source `. ./scripts/windows-runtime.ps1` in the shell that will run Mix. The helper sets that process's `PATH`, `MIX_HOME` and `HEX_HOME`; it does not install PostgreSQL, Git or Python. Set variables using PowerShell's `$env:NAME = 'value'` syntax and supply real executable paths for `GITGOOD_GIT` and `GITGOOD_PYTHON`.

Windows development is distinct from native deployment proof. Production packaging, process ownership and replacement-host recovery are verified against the Linux target described in the [production instructions](deployment/production.md).

The root reporting tests call `openssl` directly. Check `Get-Command openssl` before running them. If you use Git for Windows' bundled OpenSSL, add that installation's `usr/bin` directory to this shell's `PATH`; setting `GITGOOD_OPENSSL` alone does not configure these root tests.
