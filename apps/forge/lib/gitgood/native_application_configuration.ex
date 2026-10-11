defmodule Gitgood.NativeApplicationConfiguration do
  @moduledoc "Match actual native application settings to protected inputs before any SQL lease."

  @forge_required ~w(DATABASE_URL SECRET_KEY_BASE PHX_HOST GITGOOD_PUBLIC_URL GITGOOD_WEB_ORIGIN GITGOOD_PROXY_KEY GITGOOD_STORAGE PORT GITGOOD_SSH_PORT GITGOOD_SSH_HOST_KEY_DIRECTORY GITGOOD_SSH_PUBLIC_HOST GITGOOD_SSH_PUBLIC_PORT GITGOOD_INSTALLATION_ID)
  @forge_optional ~w(GITGOOD_CONNECTION_KEY GITGOOD_BARKPARK_ORIGIN GITGOOD_BARKPARK_CA)
  @controls ~w(GITGOOD_GIT GITGOOD_PYTHON GITGOOD_SUPERVISION_PROFILE PHX_SERVER POOL_SIZE GITGOOD_RECOVERY_VERIFY_ONLY GITGOOD_RECOVERY_VERIFY_OPERATION)
  @app_keys ~w(environment supervision_profile storage_root public_url web_origin internal_url proxy_key connection_key barkpark_origin barkpark_ca_file git_executable python_executable ssh_port ssh_host_key_directory ssh_public_host ssh_public_port recovery_verification reconcile ecto_repos)a
  @endpoint_keys ~w(url http secret_key_base server adapter render_errors pubsub_server live_view force_ssl)a
  @failure {:error, :native_application_configuration_unavailable}

  def check(inputs, admission, mode) do
    actual = %{
      app:
        Map.new(@app_keys, fn key ->
          {key, Application.get_env(:gitgood, key, if(key == :reconcile, do: true, else: nil))}
        end),
      repo: Application.get_env(:gitgood, Gitgood.Repo),
      endpoint: Application.get_env(:gitgood, GitgoodWeb.Endpoint),
      env: Map.take(System.get_env(), @forge_required ++ @forge_optional ++ @controls)
    }

    validate(inputs, admission, mode, actual)
  rescue
    _ -> @failure
  catch
    _, _ -> @failure
  end

  @doc false
  def validate(inputs, admission, mode, actual) do
    configuration = inputs.configuration
    forge = configuration["forge"]
    web = configuration["web"]
    installation = admission["installation"]
    root = "/var/lib/gitgood/installations/" <> installation
    storage = root <> "/storage"

    with true <- mode in [:runtime, :migrate, :backup, :restore],
         true <- exact?(configuration, ~w(protocol installation forge web edge)),
         true <- configuration["protocol"] === 1 and configuration["installation"] == installation,
         true <-
           is_map(forge) and
             MapSet.subset?(MapSet.new(@forge_required), MapSet.new(Map.keys(forge))),
         true <-
           MapSet.subset?(
             MapSet.new(Map.keys(forge)),
             MapSet.new(@forge_required ++ @forge_optional)
           ),
         true <- Enum.all?(Map.values(forge), &text?/1),
         true <-
           forge["GITGOOD_INSTALLATION_ID"] == installation and
             forge["GITGOOD_STORAGE"] == storage,
         true <- forge["GITGOOD_SSH_HOST_KEY_DIRECTORY"] == root <> "/ssh-host",
         {:ok, native_port} <- port(forge["PORT"]),
         {:ok, ssh_port} <- port(forge["GITGOOD_SSH_PORT"]),
         {:ok, public_ssh_port} <- port(forge["GITGOOD_SSH_PUBLIC_PORT"], 1),
         {:ok, public} <- origin(forge["GITGOOD_PUBLIC_URL"]),
         {:ok, _} <- origin(forge["GITGOOD_WEB_ORIGIN"]),
         true <- public.host == forge["PHX_HOST"] and host?(forge["GITGOOD_SSH_PUBLIC_HOST"]),
         true <- byte_size(forge["SECRET_KEY_BASE"]) >= 64,
         {:ok, proxy} <- key(forge["GITGOOD_PROXY_KEY"]),
         {:ok, connection} <- optional_key(forge["GITGOOD_CONNECTION_KEY"]),
         :ok <- source(forge, connection, root),
         true <- exact?(web, ~w(PORT GITGOOD_API_URL GITGOOD_PROXY_KEY NODE_ENV)),
         {:ok, web_port} <- port(web["PORT"]),
         true <- length(Enum.uniq([native_port, ssh_port, web_port])) == 3,
         internal <- "http://127.0.0.1:" <> forge["PORT"],
         true <-
           web["NODE_ENV"] == "production" and web["GITGOOD_API_URL"] == internal and
             web["GITGOOD_PROXY_KEY"] == forge["GITGOOD_PROXY_KEY"],
         true <- configuration["edge"] == edge(forge),
         true <- exact?(inputs.executables, ~w(python node git psql caddy)),
         true <- Enum.all?(Map.values(inputs.executables), &executable?/1),
         true <- length(Enum.uniq(Map.values(inputs.executables))) == 5,
         true <- exact?(actual, [:app, :repo, :endpoint, :env]),
         true <- exact?(actual.app, @app_keys),
         true <-
           Enum.all?(@forge_required ++ @forge_optional, fn name ->
             actual.env[name] == forge[name]
           end),
         true <- actual.env["GITGOOD_SUPERVISION_PROFILE"] == "systemd-v2",
         true <-
           actual.env["GITGOOD_GIT"] == inputs.executables["git"] and
             actual.env["GITGOOD_PYTHON"] == inputs.executables["python"],
         true <-
           actual.env["POOL_SIZE"] in [nil, "10"] and
             actual.env["GITGOOD_RECOVERY_VERIFY_ONLY"] in [nil, "false"] and
             actual.env["GITGOOD_RECOVERY_VERIFY_OPERATION"] == nil,
         true <-
           if(mode == :runtime,
             do: actual.env["PHX_SERVER"] == "true",
             else: actual.env["PHX_SERVER"] in [nil, "false"]
           ),
         expected <- %{
           environment: :prod,
           supervision_profile: "systemd-v2",
           storage_root: storage,
           public_url: forge["GITGOOD_PUBLIC_URL"],
           web_origin: forge["GITGOOD_WEB_ORIGIN"],
           internal_url: internal,
           proxy_key: proxy,
           connection_key: connection,
           barkpark_origin: forge["GITGOOD_BARKPARK_ORIGIN"],
           barkpark_ca_file: forge["GITGOOD_BARKPARK_CA"],
           git_executable: inputs.executables["git"],
           python_executable: inputs.executables["python"],
           ssh_port: ssh_port,
           ssh_host_key_directory: root <> "/ssh-host",
           ssh_public_host: forge["GITGOOD_SSH_PUBLIC_HOST"],
           ssh_public_port: public_ssh_port,
           recovery_verification: false,
           reconcile: true,
           ecto_repos: [Gitgood.Repo]
         },
         true <- actual.app == expected,
         true <-
           keyword?(actual.repo, [:url, :pool_size, :show_sensitive_data_on_connection_error]),
         true <-
           actual.repo[:url] == forge["DATABASE_URL"] and actual.repo[:pool_size] === 10 and
             actual.repo[:show_sensitive_data_on_connection_error] === false,
         true <- keyword?(actual.endpoint, @endpoint_keys),
         true <-
           keyword?(actual.endpoint[:http], [:ip, :port]) and
             actual.endpoint[:http][:ip] == {127, 0, 0, 1} and
             actual.endpoint[:http][:port] === native_port,
         true <- keyword?(actual.endpoint[:url], [:host, :port, :scheme]),
         true <-
           Map.new(actual.endpoint[:url]) == %{
             host: public.host,
             port: public.port,
             scheme: "https"
           },
         true <-
           actual.endpoint[:secret_key_base] == forge["SECRET_KEY_BASE"] and
             actual.endpoint[:server] === (mode == :runtime),
         true <-
           actual.endpoint[:adapter] == Bandit.PhoenixAdapter and
             actual.endpoint[:pubsub_server] == Gitgood.PubSub,
         true <-
           actual.endpoint[:force_ssl] == [
             rewrite_on: [:x_forwarded_proto],
             exclude: [hosts: ["localhost", "127.0.0.1"]]
           ] do
      :ok
    else
      _ -> @failure
    end
  rescue
    _ -> @failure
  catch
    _, _ -> @failure
  end

  defp exact?(value, keys), do: is_map(value) and MapSet.new(Map.keys(value)) == MapSet.new(keys)

  defp keyword?(value, keys),
    do:
      Keyword.keyword?(value) and length(value) == length(Enum.uniq(Keyword.keys(value))) and
        Enum.all?(Keyword.keys(value), &(&1 in keys))

  defp text?(value),
    do: is_binary(value) and byte_size(value) in 1..8192 and not String.contains?(value, <<0>>)

  defp executable?(value),
    do: text?(value) and byte_size(value) <= 4096 and String.starts_with?(value, "/")

  defp host?(value), do: text?(value) and Regex.match?(~r/\A[a-zA-Z0-9.-]+\z/, value)

  defp port(value, minimum \\ 1024) do
    case Integer.parse(value) do
      {number, ""} when number in minimum..65535 ->
        if Integer.to_string(number) == value, do: {:ok, number}, else: :error

      _ ->
        :error
    end
  end

  defp origin(value) do
    uri = URI.parse(value)

    if text?(value) and uri.scheme == "https" and host?(uri.host) and uri.port in 1..65535 and
         uri.userinfo == nil and uri.query == nil and uri.fragment == nil and
         uri.path in [nil, "", "/"], do: {:ok, uri}, else: :error
  end

  defp key(value) do
    case Base.decode64(value) do
      {:ok, decoded} when byte_size(decoded) == 32 ->
        if Base.encode64(decoded) == value, do: {:ok, decoded}, else: :error

      _ ->
        :error
    end
  end

  defp optional_key(nil), do: {:ok, nil}
  defp optional_key(value), do: key(value)

  defp source(forge, connection, root) do
    case forge["GITGOOD_BARKPARK_ORIGIN"] do
      nil ->
        if forge["GITGOOD_BARKPARK_CA"] == nil, do: :ok, else: :error

      value ->
        with {:ok, _} <- origin(value),
             true <- is_binary(connection),
             true <- forge["GITGOOD_BARKPARK_CA"] in [nil, root <> "/configuration/source-ca.pem"],
             do: :ok,
             else: (_ -> :error)
    end
  end

  defp edge(forge) do
    base = %{"tls_certificate" => "tls-certificate.pem", "tls_key" => "tls-key.pem"}
    if forge["GITGOOD_BARKPARK_CA"], do: Map.put(base, "source_ca", "source-ca.pem"), else: base
  end
end
