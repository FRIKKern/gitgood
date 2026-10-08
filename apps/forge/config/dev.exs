import Config

config :gitgood, Gitgood.Repo,
  username: System.get_env("PGUSER", "gitgood"),
  password: System.get_env("PGPASSWORD", ""),
  hostname: System.get_env("PGHOST", "127.0.0.1"),
  port: String.to_integer(System.get_env("PGPORT", "55432")),
  database: System.get_env("PGDATABASE", "gitgood_dev"),
  pool_size: 10

config :gitgood, GitgoodWeb.Endpoint,
  http: [ip: {127, 0, 0, 1}],
  check_origin: true,
  code_reloader: true,
  debug_errors: false,
  secret_key_base: String.duplicate("development-only-", 8)

config :logger, level: :info
config :phoenix, :plug_init_mode, :runtime
