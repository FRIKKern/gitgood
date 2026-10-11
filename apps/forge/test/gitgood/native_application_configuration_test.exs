defmodule Gitgood.NativeApplicationConfigurationTest do
  use ExUnit.Case, async: false
  alias Gitgood.NativeApplicationConfiguration, as: Configuration
  @failure {:error, :native_application_configuration_unavailable}

  defp fixture do
    record =
      Jason.decode!(
        File.read!(Path.expand("../fixtures/native_ownership_record_v3.json", __DIR__))
      )

    installation = record["installation"]
    root = "/var/lib/gitgood/installations/" <> installation
    proxy = String.duplicate("p", 32)

    forge = %{
      "DATABASE_URL" =>
        "postgres://ordinary:synthetic-private-canary@127.0.0.1:55432/owned_fixture",
      "SECRET_KEY_BASE" => String.duplicate("synthetic-private-canary", 4),
      "PHX_HOST" => "gitgood.example",
      "GITGOOD_PUBLIC_URL" => "https://gitgood.example:55443",
      "GITGOOD_WEB_ORIGIN" => "https://gitgood.example:55443",
      "GITGOOD_PROXY_KEY" => Base.encode64(proxy),
      "GITGOOD_STORAGE" => root <> "/storage",
      "PORT" => "47841",
      "GITGOOD_SSH_PORT" => "47842",
      "GITGOOD_SSH_PUBLIC_PORT" => "2222",
      "GITGOOD_SSH_PUBLIC_HOST" => "gitgood.example",
      "GITGOOD_SSH_HOST_KEY_DIRECTORY" => root <> "/ssh-host",
      "GITGOOD_INSTALLATION_ID" => installation
    }

    executables = Map.new(~w(python node git psql caddy), &{&1, "/fixed/" <> &1})

    inputs = %{
      configuration: %{
        "protocol" => 1,
        "installation" => installation,
        "forge" => forge,
        "web" => %{
          "PORT" => "47840",
          "GITGOOD_API_URL" => "http://127.0.0.1:47841",
          "GITGOOD_PROXY_KEY" => Base.encode64(proxy),
          "NODE_ENV" => "production"
        },
        "edge" => %{"tls_certificate" => "tls-certificate.pem", "tls_key" => "tls-key.pem"}
      },
      executables: executables
    }

    admission = %{"installation" => installation}

    actual = %{
      env:
        Map.merge(forge, %{
          "GITGOOD_GIT" => executables["git"],
          "GITGOOD_PYTHON" => executables["python"],
          "GITGOOD_SUPERVISION_PROFILE" => "systemd-v2",
          "PHX_SERVER" => "true"
        }),
      app: %{
        environment: :prod,
        supervision_profile: "systemd-v2",
        storage_root: root <> "/storage",
        public_url: forge["GITGOOD_PUBLIC_URL"],
        web_origin: forge["GITGOOD_WEB_ORIGIN"],
        internal_url: "http://127.0.0.1:47841",
        proxy_key: proxy,
        connection_key: nil,
        barkpark_origin: nil,
        barkpark_ca_file: nil,
        git_executable: executables["git"],
        python_executable: executables["python"],
        ssh_port: 47842,
        ssh_host_key_directory: root <> "/ssh-host",
        ssh_public_host: "gitgood.example",
        ssh_public_port: 2222,
        recovery_verification: false,
        reconcile: true,
        ecto_repos: [Gitgood.Repo]
      },
      repo: [
        url: forge["DATABASE_URL"],
        pool_size: 10,
        show_sensitive_data_on_connection_error: false
      ],
      endpoint: [
        http: [ip: {127, 0, 0, 1}, port: 47841],
        url: [host: "gitgood.example", port: 55443, scheme: "https"],
        secret_key_base: forge["SECRET_KEY_BASE"],
        server: true,
        adapter: Bandit.PhoenixAdapter,
        pubsub_server: Gitgood.PubSub,
        force_ssl: [
          rewrite_on: [:x_forwarded_proto],
          exclude: [hosts: ["localhost", "127.0.0.1"]]
        ]
      ]
    }

    {inputs, admission, actual}
  end

  test "runtime and stopped-listener maintenance match the same protected installation" do
    {inputs, admission, actual} = fixture()
    assert :ok = Configuration.validate(inputs, admission, :runtime, actual)

    maintenance =
      actual
      |> put_in([:env, "PHX_SERVER"], "false")
      |> put_in([:endpoint], Keyword.put(actual.endpoint, :server, false))

    for mode <- [:migrate, :backup, :restore],
        do: assert(:ok == Configuration.validate(inputs, admission, mode, maintenance))

    assert @failure = Configuration.validate(inputs, admission, :runtime, maintenance)
    assert @failure = Configuration.validate(inputs, admission, :migrate, actual)
  end

  test "public SSH port 22 is distinct from the ordinary installation listener port" do
    {inputs, admission, actual} = fixture()
    inputs = put_in(inputs, [:configuration, "forge", "GITGOOD_SSH_PUBLIC_PORT"], "22")

    actual =
      actual
      |> put_in([:env, "GITGOOD_SSH_PUBLIC_PORT"], "22")
      |> put_in([:app, :ssh_public_port], 22)

    assert :ok = Configuration.validate(inputs, admission, :runtime, actual)

    assert @failure =
             Configuration.validate(
               put_in(inputs, [:configuration, "forge", "GITGOOD_SSH_PORT"], "22"),
               admission,
               :runtime,
               actual
             )
  end

  test "actual runtime config evaluates to the protected settings without starting services" do
    {inputs, admission, actual} = fixture()
    preserve(actual)
    source = Path.expand("../../config", __DIR__)
    base = Config.Reader.read!(Path.join(source, "config.exs"), env: :prod, target: :host)
    runtime = Config.Reader.read!(Path.join(source, "runtime.exs"), env: :prod, target: :host)
    configured = Config.Reader.merge(base, runtime)

    Enum.each(configured[:gitgood], fn {key, value} ->
      Application.put_env(:gitgood, key, value)
    end)

    assert :ok = Configuration.check(inputs, admission, :runtime)
    assert Application.get_env(:gitgood, GitgoodWeb.Endpoint)[:url][:port] == 55443

    assert Application.get_env(:gitgood, Gitgood.Repo)[:show_sensitive_data_on_connection_error] ==
             false

    System.put_env("PHX_SERVER", "false")
    offline = Config.Reader.read!(Path.join(source, "runtime.exs"), env: :prod, target: :host)

    Enum.each(Config.Reader.merge(base, offline)[:gitgood], fn {key, value} ->
      Application.put_env(:gitgood, key, value)
    end)

    assert :ok = Configuration.check(inputs, admission, :migrate)
  end

  defp preserve(actual) do
    keys = Map.keys(actual.app) ++ [Gitgood.Repo, GitgoodWeb.Endpoint, :generators]
    application = Map.new(keys, &{&1, Application.fetch_env(:gitgood, &1)})

    controls =
      ~w(GITGOOD_CONNECTION_KEY GITGOOD_BARKPARK_ORIGIN GITGOOD_BARKPARK_CA POOL_SIZE GITGOOD_RECOVERY_VERIFY_ONLY GITGOOD_RECOVERY_VERIFY_OPERATION)

    names = Enum.uniq(Map.keys(actual.env) ++ controls)
    environment = Map.new(names, &{&1, System.get_env(&1)})

    on_exit(fn ->
      Enum.each(application, fn {key, value} ->
        case value do
          {:ok, saved} -> Application.put_env(:gitgood, key, saved)
          :error -> Application.delete_env(:gitgood, key)
        end
      end)

      Enum.each(environment, fn {key, value} ->
        if value == nil, do: System.delete_env(key), else: System.put_env(key, value)
      end)
    end)

    Enum.each(names, &System.delete_env/1)
    System.put_env(actual.env)
    Enum.each(actual.app, fn {key, value} -> Application.put_env(:gitgood, key, value) end)
    Application.put_env(:gitgood, Gitgood.Repo, actual.repo)
    Application.put_env(:gitgood, GitgoodWeb.Endpoint, actual.endpoint)
  end

  test "actual settings collection refuses changed secrets and restores no authority" do
    {inputs, admission, actual} = fixture()
    preserve(actual)
    assert :ok = Configuration.check(inputs, admission, :runtime)
    Application.put_env(:gitgood, :proxy_key, String.duplicate("other", 8))
    assert @failure = Configuration.check(inputs, admission, :runtime)
    Application.put_env(:gitgood, :proxy_key, actual.app.proxy_key)

    System.put_env(
      "DATABASE_URL",
      "postgres://foreign:synthetic-private-canary@127.0.0.1:55432/other"
    )

    assert @failure = Configuration.check(inputs, admission, :runtime)
  end

  test "missing unknown and aliased protected configuration fields refuse" do
    {inputs, admission, actual} = fixture()

    for name <- Map.keys(inputs.configuration["forge"]) do
      changed = update_in(inputs, [:configuration, "forge"], &Map.delete(&1, name))
      assert @failure == Configuration.validate(changed, admission, :runtime, actual)
    end

    for changed <- [
          put_in(inputs, [:configuration, "protocol"], true),
          put_in(inputs, [:configuration, "forge", "program"], "shell"),
          put_in(inputs, [:configuration, "forge", "PORT"], "047841"),
          put_in(inputs, [:configuration, "edge", "tls_key"], "foreign.pem")
        ] do
      assert @failure == Configuration.validate(changed, admission, :runtime, actual)
    end
  end

  test "every independently supplied forge environment value must match" do
    {inputs, admission, actual} = fixture()

    for name <- Map.keys(inputs.configuration["forge"]) do
      assert @failure ==
               Configuration.validate(
                 inputs,
                 admission,
                 :runtime,
                 put_in(actual, [:env, name], "changed")
               )
    end

    assert @failure =
             Configuration.validate(
               inputs,
               admission,
               :runtime,
               put_in(actual, [:env, "GITGOOD_BARKPARK_ORIGIN"], "https://unexpected.example")
             )
  end

  test "every resolved application setting is checked rather than trusting environment alone" do
    {inputs, admission, actual} = fixture()

    for name <- Map.keys(actual.app),
        do:
          assert(
            @failure ==
              Configuration.validate(
                inputs,
                admission,
                :runtime,
                put_in(actual, [:app, name], :changed)
              )
          )

    assert @failure =
             Configuration.validate(
               inputs,
               admission,
               :runtime,
               update_in(actual, [:app], &Map.delete(&1, :public_url))
             )
  end

  test "repo overrides callbacks duplicate keys and sensitive errors refuse before connection" do
    {inputs, admission, actual} = fixture()

    for repo <- [
          Keyword.put(
            actual.repo,
            :url,
            "postgres://foreign:synthetic-private-canary@127.0.0.1:55432/other"
          ),
          Keyword.put(actual.repo, :pool_size, 100),
          Keyword.put(actual.repo, :show_sensitive_data_on_connection_error, true),
          actual.repo ++ [password: "foreign"],
          actual.repo ++ [after_connect: fn _ -> :arbitrary end],
          actual.repo ++ [url: actual.repo[:url]],
          actual.repo ++ [socket_dir: "/foreign"],
          actual.repo ++ [ssl: true]
        ] do
      assert @failure ==
               Configuration.validate(inputs, admission, :runtime, %{actual | repo: repo})
    end
  end

  test "unbound executable recovery profile and server controls refuse" do
    {inputs, admission, actual} = fixture()

    for {name, value} <- [
          {"GITGOOD_GIT", "/foreign/git"},
          {"GITGOOD_PYTHON", "/foreign/python"},
          {"GITGOOD_SUPERVISION_PROFILE", "development"},
          {"PHX_SERVER", "true "},
          {"POOL_SIZE", "100"},
          {"GITGOOD_RECOVERY_VERIFY_ONLY", "true"},
          {"GITGOOD_RECOVERY_VERIFY_OPERATION", Ecto.UUID.generate()}
        ] do
      assert @failure ==
               Configuration.validate(
                 inputs,
                 admission,
                 :runtime,
                 put_in(actual, [:env, name], value)
               )
    end

    assert @failure =
             Configuration.validate(
               put_in(inputs, [:executables, "git"], inputs.executables["python"]),
               admission,
               :runtime,
               actual
             )
  end

  test "listener address identity secrets server state and endpoint extensions refuse" do
    {inputs, admission, actual} = fixture()

    for endpoint <- [
          Keyword.put(actual.endpoint, :http, ip: {0, 0, 0, 0}, port: 47841),
          Keyword.put(actual.endpoint, :url,
            host: "foreign.example",
            port: 55443,
            scheme: "https"
          ),
          Keyword.put(actual.endpoint, :secret_key_base, "foreign"),
          Keyword.put(actual.endpoint, :server, false),
          Keyword.put(actual.endpoint, :adapter, :foreign),
          Keyword.put(actual.endpoint, :force_ssl, false),
          actual.endpoint ++ [http: actual.endpoint[:http]],
          actual.endpoint ++ [https: [port: 443]]
        ] do
      assert @failure ==
               Configuration.validate(inputs, admission, :runtime, %{actual | endpoint: endpoint})
    end
  end

  test "origins private route ports and proxy key representations remain bounded" do
    {inputs, admission, actual} = fixture()

    for value <- [
          "http://gitgood.example",
          "https://name:pass@gitgood.example",
          "https://gitgood.example/path",
          "https://gitgood.example?x=1",
          "https://gitgood.example#fragment",
          "https://gitgood.example" <> <<0>>
        ] do
      assert @failure ==
               Configuration.validate(
                 put_in(inputs, [:configuration, "forge", "GITGOOD_PUBLIC_URL"], value),
                 admission,
                 :runtime,
                 actual
               )
    end

    for {name, value} <- [
          {"PORT", "80"},
          {"PORT", "65536"},
          {"GITGOOD_SSH_PORT", "47841"},
          {"GITGOOD_SSH_PUBLIC_PORT", "0"},
          {"GITGOOD_PROXY_KEY", String.duplicate("x", 32)},
          {"SECRET_KEY_BASE", "short"},
          {"GITGOOD_SSH_PUBLIC_HOST", "host/path"}
        ] do
      assert @failure ==
               Configuration.validate(
                 put_in(inputs, [:configuration, "forge", name], value),
                 admission,
                 :runtime,
                 actual
               )
    end

    assert @failure =
             Configuration.validate(
               put_in(inputs, [:configuration, "web", "GITGOOD_API_URL"], "http://foreign:47841"),
               admission,
               :runtime,
               actual
             )
  end

  test "optional Barkpark settings require matching keys origins and fixed private CA" do
    {inputs, admission, actual} = fixture()
    connection = String.duplicate("c", 32)
    root = Path.dirname(actual.app.storage_root)

    forge =
      Map.merge(inputs.configuration["forge"], %{
        "GITGOOD_CONNECTION_KEY" => Base.encode64(connection),
        "GITGOOD_BARKPARK_ORIGIN" => "https://studio.example",
        "GITGOOD_BARKPARK_CA" => root <> "/configuration/source-ca.pem"
      })

    inputs =
      inputs
      |> put_in([:configuration, "forge"], forge)
      |> put_in([:configuration, "edge", "source_ca"], "source-ca.pem")

    actual = %{
      actual
      | env: Map.merge(actual.env, forge),
        app: %{
          actual.app
          | connection_key: connection,
            barkpark_origin: forge["GITGOOD_BARKPARK_ORIGIN"],
            barkpark_ca_file: forge["GITGOOD_BARKPARK_CA"]
        }
    }

    assert :ok = Configuration.validate(inputs, admission, :runtime, actual)

    for {name, value} <- [
          {"GITGOOD_CONNECTION_KEY", nil},
          {"GITGOOD_BARKPARK_ORIGIN", "http://studio.example"},
          {"GITGOOD_BARKPARK_CA", "/foreign.pem"}
        ] do
      assert @failure ==
               Configuration.validate(
                 put_in(inputs, [:configuration, "forge", name], value),
                 admission,
                 :runtime,
                 actual
               )
    end
  end

  test "malformed values return only a constant error" do
    {inputs, admission, actual} = fixture()

    for invalid <- [nil, true, %{}, %{configuration: "synthetic-private-canary"}],
        do: assert(@failure == Configuration.validate(invalid, admission, :runtime, actual))

    assert @failure = Configuration.validate(inputs, admission, :shell, actual)
    assert @failure = Configuration.validate(inputs, %{}, :runtime, actual)
    refute inspect(@failure) =~ "synthetic-private-canary"
  end
end
