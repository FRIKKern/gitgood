import Config

config :gitgood,
  storage_root:
    System.get_env(
      "GITGOOD_STORAGE",
      Application.get_env(
        :gitgood,
        :storage_root,
        Path.expand("../../../.gitgood/repos", __DIR__)
      )
    ),
  web_origin: System.get_env("GITGOOD_WEB_ORIGIN", "http://localhost:47840"),
  public_url: System.get_env("GITGOOD_PUBLIC_URL", "http://localhost:47841"),
  git_executable: System.get_env("GITGOOD_GIT", "git"),
  python_executable: System.get_env("GITGOOD_PYTHON", "python3"),
  internal_url: "http://127.0.0.1:" <> System.get_env("PORT", "47841")

config :gitgood, GitgoodWeb.Endpoint,
  http: [port: String.to_integer(System.get_env("PORT", "47841"))]

if System.get_env("PHX_SERVER") == "true", do: config(:gitgood, GitgoodWeb.Endpoint, server: true)

if config_env() == :prod do
  config :gitgood, Gitgood.Repo,
    url: System.fetch_env!("DATABASE_URL"),
    pool_size: String.to_integer(System.get_env("POOL_SIZE", "10"))

  host = System.fetch_env!("PHX_HOST")
  public_url = System.fetch_env!("GITGOOD_PUBLIC_URL")
  web_origin = System.fetch_env!("GITGOOD_WEB_ORIGIN")

  unless String.starts_with?(public_url, "https://") and
           String.starts_with?(web_origin, "https://"),
         do: raise("Production origins must use HTTPS")

  config :gitgood, :storage_root, System.fetch_env!("GITGOOD_STORAGE")

  config :gitgood, GitgoodWeb.Endpoint,
    url: [host: host, port: 443, scheme: "https"],
    http: [ip: {127, 0, 0, 1}],
    secret_key_base: System.fetch_env!("SECRET_KEY_BASE")
end
