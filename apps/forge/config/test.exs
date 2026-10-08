import Config

config :gitgood, Gitgood.Repo,
  username: System.get_env("PGUSER", "gitgood"),
  password: System.get_env("PGPASSWORD", ""),
  hostname: System.get_env("PGHOST", "127.0.0.1"),
  port: String.to_integer(System.get_env("PGPORT", "55432")),
  database: System.get_env("PGDATABASE", "gitgood_test"),
  pool: Ecto.Adapters.SQL.Sandbox,
  pool_size: 10

config :gitgood, :storage_root, Path.expand("../../../.gitgood/test", __DIR__)
config :gitgood, :reconcile, false

config :gitgood, GitgoodWeb.Endpoint,
  http: [ip: {127, 0, 0, 1}, port: 4002],
  secret_key_base: String.duplicate("test-only-", 16),
  server: false

config :logger, level: :warning
config :phoenix, :plug_init_mode, :runtime
