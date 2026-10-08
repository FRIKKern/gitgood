# Gitgood forge
Native Phoenix JSON API with Postgres collaboration records and standard Git bare repositories.

Use the pinned versions in the root .tool-versions. Postgres 18.4 is the initial development target. Standard Git must be on PATH; compatibility breadth remains an explicit transport experiment.
On Windows, dot-source `../../scripts/windows-runtime.ps1` in your PowerShell process for checksum-pinned isolated Elixir/OTP binaries. This does not replace the system installation. Then run `mix local.hex --force` once in that process.
Configure PGHOST, PGPORT (default 55432), PGUSER (default gitgood), PGPASSWORD and PGDATABASE.
These development defaults assume an isolated loopback database, never a shared or exposed trust-authenticated database.

```sh
mix deps.get
mix ecto.create
mix ecto.migrate
mix run priv/repo/seeds.exs
mix phx.server
```

The disposable fixture login is owner / synthetic-password. Other roles are reviewer (writer), reader and outsider.
These accounts are development fixtures; the seed refuses production.
For an installation actor, provide GITGOOD_BOOTSTRAP_PASSWORD in the process environment and run
`mix gitgood.bootstrap USER TEAM owner`. Do not pass passwords as arguments.

The API is http://localhost:47841; readiness is /health/ready. Repository storage defaults to the ignored .gitgood/repos directory.
The web interface runs separately; GITGOOD_WEB_ORIGIN defaults to http://localhost:47840.
A production release requires DATABASE_URL, SECRET_KEY_BASE, PHX_HOST, GITGOOD_PUBLIC_URL, GITGOOD_WEB_ORIGIN and GITGOOD_STORAGE.
Production public origins must use HTTPS. The backend binds loopback for a TLS reverse proxy.
There is no configured public deployment.

Run `mix precommit` against the isolated gitgood_test database (or explicitly configured PGDATABASE).
Tests cover real bare repository creation, privacy, credential revocation/expiry, CSRF, retry and storage-failure reconciliation.
This slice does not yet provide Git transport, browsing, pull requests or release acceptance.
