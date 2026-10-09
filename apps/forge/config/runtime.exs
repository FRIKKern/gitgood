import Config

recovery_verification =
  case System.get_env("GITGOOD_RECOVERY_VERIFY_ONLY") do
    value when value in [nil, "false"] -> false
    "true" -> true
    _ -> raise("Recovery verification startup refused")
  end

verification_operation = System.get_env("GITGOOD_RECOVERY_VERIFY_OPERATION")

if recovery_verification do
  operation_valid =
    is_binary(verification_operation) and
      Regex.match?(
        ~r/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
        verification_operation
      )

  parse_verification_uri = fn value ->
    try do
      URI.parse(value)
    rescue
      ArgumentError -> raise("Recovery verification startup refused")
    end
  end

  database = parse_verification_uri.(System.get_env("DATABASE_URL", ""))
  origin = parse_verification_uri.(System.get_env("GITGOOD_PUBLIC_URL", ""))

  target =
    if operation_valid,
      do: "/gitgood_retirement_restore_" <> String.replace(verification_operation, "-", ""),
      else: nil

  unless operation_valid and database.scheme in ["postgres", "postgresql"] and
           database.host in ["127.0.0.1", "localhost"] and database.path == target and
           is_integer(database.port) and database.port >= 1024 and database.port <= 65535 and
           database.query == nil and database.fragment == nil and
           origin.scheme == "https" and origin.host == "127.0.0.1" and
           is_integer(origin.port) and origin.port >= 1024 and origin.port <= 65535 and
           origin.userinfo == nil and origin.query == nil and origin.fragment == nil and
           origin.path in [nil, "", "/"] and
           System.get_env("GITGOOD_WEB_ORIGIN") == System.get_env("GITGOOD_PUBLIC_URL") and
           System.get_env("PHX_HOST") == "127.0.0.1" and
           System.get_env("GITGOOD_BARKPARK_ORIGIN") == nil,
         do: raise("Recovery verification startup refused")

  config :gitgood, :reconcile, false
else
  if verification_operation != nil, do: raise("Recovery verification startup refused")
end

config :gitgood, :recovery_verification, recovery_verification

connection_key =
  case System.get_env("GITGOOD_CONNECTION_KEY") do
    nil ->
      nil

    encoded ->
      case Base.decode64(encoded) do
        {:ok, key} when byte_size(key) == 32 -> key
        _ -> raise("GITGOOD_CONNECTION_KEY must be base64 encoding of 32 random bytes")
      end
  end

config :gitgood, :connection_key, connection_key

proxy_key =
  case System.get_env("GITGOOD_PROXY_KEY") do
    nil ->
      nil

    encoded ->
      case Base.decode64(encoded) do
        {:ok, key} when byte_size(key) == 32 ->
          if Base.encode64(key) == encoded,
            do: key,
            else: raise("GITGOOD_PROXY_KEY must encode 32 random bytes")

        _ ->
          raise("GITGOOD_PROXY_KEY must encode 32 random bytes")
      end
  end

config :gitgood, :proxy_key, proxy_key

if System.get_env("GITGOOD_SSH_PORT") do
  config :gitgood,
    ssh_port: String.to_integer(System.fetch_env!("GITGOOD_SSH_PORT")),
    ssh_host_key_directory: System.fetch_env!("GITGOOD_SSH_HOST_KEY_DIRECTORY"),
    ssh_public_host: System.get_env("GITGOOD_SSH_PUBLIC_HOST", "localhost"),
    ssh_public_port:
      String.to_integer(
        System.get_env("GITGOOD_SSH_PUBLIC_PORT", System.fetch_env!("GITGOOD_SSH_PORT"))
      )
end

config :gitgood,
  barkpark_origin: System.get_env("GITGOOD_BARKPARK_ORIGIN"),
  barkpark_ca_file: System.get_env("GITGOOD_BARKPARK_CA"),
  storage_root:
    System.get_env(
      "GITGOOD_STORAGE",
      Application.get_env(
        :gitgood,
        :storage_root,
        Path.expand("../../../.gitgood/repos", __DIR__)
      )
    )
    |> Path.expand(),
  web_origin: System.get_env("GITGOOD_WEB_ORIGIN", "http://localhost:47840"),
  public_url: System.get_env("GITGOOD_PUBLIC_URL", "http://localhost:47841"),
  git_executable: System.get_env("GITGOOD_GIT", "git"),
  python_executable: System.get_env("GITGOOD_PYTHON", "python3"),
  internal_url: "http://127.0.0.1:" <> System.get_env("PORT", "47841")

config :gitgood, GitgoodWeb.Endpoint,
  http: [port: String.to_integer(System.get_env("PORT", "47841"))]

if System.get_env("PHX_SERVER") == "true", do: config(:gitgood, GitgoodWeb.Endpoint, server: true)

if config_env() == :prod do
  if is_nil(proxy_key), do: raise("Production login origin requires GITGOOD_PROXY_KEY")

  if System.get_env("GITGOOD_BARKPARK_ORIGIN") && is_nil(connection_key),
    do: raise("Production Barkpark connections require GITGOOD_CONNECTION_KEY")

  case System.get_env("GITGOOD_BARKPARK_ORIGIN") do
    nil -> :ok
    "https://" <> _ -> :ok
    _ -> raise("Production Barkpark origin must use HTTPS")
  end

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
