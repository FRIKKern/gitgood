defmodule Gitgood.InstallationLease do
  @moduledoc "Single-host runtime/maintenance exclusion; process markers fail closed after lease loss."
  use GenServer

  @namespace 1_197_034_575
  @key 1
  @runtime_marker ".gitgood-runtime-v1.json"
  @maintenance_marker ".gitgood-maintenance-v1.json"
  @connection_keys [
    :hostname,
    :port,
    :socket_dir,
    :socket,
    :endpoints,
    :database,
    :username,
    :password,
    :ssl,
    :socket_options,
    :target_server_type
  ]

  def start_link(opts) do
    name = Keyword.get(opts, :name, __MODULE__)
    GenServer.start_link(__MODULE__, opts, if(name, do: [name: name], else: []))
  end

  def enabled?, do: Application.get_env(:gitgood, :environment) == :prod

  def ready? do
    if enabled?() do
      try do
        GenServer.call(__MODULE__, :held, 4000) == :ok
      catch
        :exit, _ -> false
      end
    else
      true
    end
  end

  def assert_held(pid), do: GenServer.call(pid, :held, 4000)
  def verify_recovered(pid), do: GenServer.call(pid, :verify_recovered, 600_000)
  def context(pid), do: GenServer.call(pid, :context, 600_000)

  def with_offline(mode, fun)
      when mode in [:backup, :restore, :migrate] and is_function(fun, 1) do
    # Release eval must load configuration without starting mutation workers or listeners.
    if Process.whereis(Gitgood.Supervisor),
      do: raise("Offline maintenance requires stopped runtime")

    Application.load(:gitgood)
    {:ok, _} = Application.ensure_all_started(:postgrex)
    {:ok, _} = Application.ensure_all_started(:jason)

    {:ok, lease} = start_link(mode: mode, name: nil)

    try do
      result = fun.(lease)
      :ok = assert_held(lease)
      result
    after
      if Process.alive?(lease), do: GenServer.stop(lease, :normal)
    end
  end

  @impl true
  def init(opts) do
    mode = Keyword.get(opts, :mode, :runtime)

    root =
      Keyword.get_lazy(opts, :root, fn -> Application.fetch_env!(:gitgood, :storage_root) end)

    config = Keyword.get_lazy(opts, :connection, &Gitgood.Repo.config/0)

    options =
      config
      |> Keyword.take(@connection_keys)
      |> Keyword.merge(
        pool_size: 1,
        backoff_type: :stop,
        connect_timeout: 3000,
        timeout: 3000,
        show_sensitive_data_on_connection_error: false,
        parameters: [application_name: "gitgood installation lease v1"]
      )

    case Postgrex.start_link(options) do
      {:ok, connection} ->
        case acquire(connection, mode, root) do
          {:ok, backend_pid} ->
            Process.send_after(self(), :check, 1000)
            {:ok, %{connection: connection, backend_pid: backend_pid, mode: mode, root: root}}

          {:error, reason} ->
            GenServer.stop(connection, :normal)
            {:stop, reason}
        end

      _ ->
        {:stop, :installation_lease_unavailable}
    end
  rescue
    _ -> {:stop, :installation_lease_unavailable}
  end

  defp acquire(connection, mode, root) do
    with true <- mode in [:runtime, :backup, :restore, :migrate],
         {:ok, %{rows: [[true, backend_pid]]}} <-
           Postgrex.query(
             connection,
             "SELECT pg_try_advisory_lock($1::int, $2::int), pg_backend_pid()",
             [@namespace, @key]
           ),
         :ok <- check_markers(root, mode),
         :ok <- write_marker(root, mode) do
      {:ok, backend_pid}
    else
      {:ok, %{rows: [[false, _]]}} ->
        {:error, :installation_busy}

      {:error, reason}
      when reason in [
             :installation_process_present,
             :installation_marker_invalid,
             :installation_protocol_unestablished,
             :installation_restore_incomplete
           ] ->
        {:error, reason}

      _ ->
        {:error, :installation_lease_unavailable}
    end
  end

  defp check_markers(root, mode) do
    runtime = Path.join(root, @runtime_marker)
    maintenance = Path.join(root, @maintenance_marker)

    cond do
      mode != :restore and File.exists?(Path.join(root, ".gitgood-restore-incomplete-v1.json")) ->
        {:error, :installation_restore_incomplete}

      mode == :backup and not File.exists?(runtime) ->
        {:error, :installation_protocol_unestablished}

      true ->
        Enum.reduce_while([runtime, maintenance], :ok, fn path, _ ->
          case marker_status(path, mode == :backup and path == runtime and enabled?()) do
            :clear -> {:cont, :ok}
            error -> {:halt, error}
          end
        end)
    end
  end

  defp marker_status(path, require_cgroup) do
    case File.lstat(path) do
      {:error, :enoent} ->
        :clear

      {:ok, %{type: :regular}} ->
        python = Application.fetch_env!(:gitgood, :python_executable)
        script = Application.app_dir(:gitgood, "priv/operations/process_status.py")

        arguments =
          ["-I", script, path] ++ if(require_cgroup, do: ["require-empty-cgroup"], else: [])

        case System.cmd(python, arguments, stderr_to_stdout: true) do
          {"clear\n", 0} ->
            :clear

          {"clear\r\n", 0} ->
            :clear

          {value, _} when value in ["busy\n", "busy\r\n"] ->
            {:error, :installation_process_present}

          _ ->
            {:error, :installation_marker_invalid}
        end

      _ ->
        {:error, :installation_marker_invalid}
    end
  end

  defp write_marker(root, mode) do
    {:ok, host} = :inet.gethostname()
    marker = if mode == :runtime, do: @runtime_marker, else: @maintenance_marker
    path = Path.join(root, marker)
    temporary = path <> "." <> Ecto.UUID.generate() <> ".partial"

    record = %{
      protocol: 1,
      host: to_string(host),
      owners: [String.to_integer(System.pid())],
      owner_births: %{System.pid() => owner_birth!()},
      mode: to_string(mode),
      candidate: Gitgood.Build.identity()["candidate"],
      created_at: DateTime.utc_now() |> DateTime.to_iso8601()
    }

    record = if mode == :runtime, do: Map.put(record, :cgroup, runtime_cgroup()), else: record

    with :ok <- File.mkdir_p(root),
         :ok <- File.write(temporary, Jason.encode!(record), [:exclusive]),
         :ok <- File.chmod(temporary, 0o600),
         # The database lease excludes concurrent claims. Windows rename cannot replace a stale file.
         :ok <- remove_stale(path),
         :ok <- File.rename(temporary, path) do
      :ok
    else
      _ ->
        File.rm(temporary)
        {:error, :installation_marker_invalid}
    end
  end

  defp owner_birth! do
    python = Application.fetch_env!(:gitgood, :python_executable)
    script = Application.app_dir(:gitgood, "priv/operations/process_birth.py")
    {value, 0} = System.cmd(python, ["-I", script, System.pid()], stderr_to_stdout: true)
    value = String.trim(value)

    if not Regex.match?(~r/\A[1-9][0-9]{0,19}\z/, value),
      do: raise("Process identity unavailable")

    value
  end

  defp runtime_cgroup do
    case File.read("/proc/self/cgroup") do
      {:ok, value} ->
        case Regex.run(~r/^0::([^\n]+)$/m, value) do
          [_, path] -> path
          _ -> nil
        end

      _ ->
        nil
    end
  end

  defp remove_stale(path) do
    case File.rm(path) do
      :ok -> :ok
      {:error, :enoent} -> :ok
      error -> error
    end
  end

  defp held?(state) do
    case Postgrex.query(
           state.connection,
           """
           SELECT pg_backend_pid(), EXISTS (
             SELECT 1 FROM pg_locks WHERE locktype = 'advisory' AND pid = pg_backend_pid()
             AND classid::bigint = $1 AND objid::bigint = $2 AND objsubid = 2
             AND mode = 'ExclusiveLock' AND granted)
           """,
           [@namespace, @key],
           timeout: 3000
         ) do
      {:ok, %{rows: [[pid, true]]}} -> pid == state.backend_pid
      _ -> false
    end
  rescue
    _ -> false
  catch
    :exit, _ -> false
  end

  @impl true
  def handle_call(:held, _, state) do
    if held?(state),
      do: {:reply, :ok, state},
      else: {:stop, :installation_lease_lost, {:error, :installation_lease_lost}, state}
  end

  @impl true
  def handle_call(:verify_recovered, _, state) do
    result =
      if state.mode == :restore and held?(state),
        do: recoverable_secrets(%{state | mode: :backup}),
        else: {:error, :installation_lease_lost}

    {:reply, result, state}
  end

  @impl true
  def handle_call(:context, _, state) do
    result =
      with true <- state.mode in [:backup, :restore] and held?(state),
           {:ok, %{rows: [[0]]}} <-
             Postgrex.query(
               state.connection,
               """
               SELECT count(*) FROM pg_stat_activity
               WHERE datname = current_database() AND backend_type = 'client backend'
               AND pid <> pg_backend_pid()
               """,
               [],
               timeout: 3000
             ),
           {:ok, %{rows: [[version]]}} <-
             Postgrex.query(state.connection, "SHOW server_version", []),
           {:ok, %{rows: rows}} <- migrations(state),
           :ok <- recoverable_secrets(state) do
        context = %{
          backend_pid: state.backend_pid,
          owner_pid: String.to_integer(System.pid()),
          mode: to_string(state.mode),
          root: state.root,
          postgres: version,
          identity: Gitgood.Build.identity()
        }

        inventory =
          if state.mode == :restore,
            do: %{existing_tables: List.flatten(rows), migrations: []},
            else: %{migrations: List.flatten(rows)}

        {:ok, Map.merge(context, inventory)}
      else
        {:error, :recovery_key_material_unavailable} ->
          {:error, :recovery_key_material_unavailable}

        _ ->
          {:error, :installation_not_quiescent}
      end

    {:reply, result, state}
  end

  defp recoverable_secrets(%{mode: :restore}), do: :ok

  defp recoverable_secrets(state) do
    with true <-
           recoverable_rows?(
             state.connection,
             """
             SELECT id::text, user_id, generation::text, origin, token_cipher
             FROM barkpark_connections WHERE token_cipher IS NOT NULL
             """,
             fn [id, user_id, generation, origin, cipher] ->
               Gitgood.BarkparkConnections.recoverable_secret?(%Gitgood.BarkparkConnection{
                 id: id,
                 user_id: user_id,
                 generation: generation,
                 origin: origin,
                 token_cipher: cipher
               })
             end
           ),
         true <-
           recoverable_rows?(
             state.connection,
             """
             SELECT id::text, actor_id, link_generation::text, connection_id::text,
               connection_generation::text, locator, payload_cipher, payload_digest
             FROM source_return_operations WHERE payload_cipher IS NOT NULL
             """,
             fn [
                  id,
                  actor,
                  link_generation,
                  connection,
                  connection_generation,
                  locator,
                  cipher,
                  digest
                ] ->
               Gitgood.SourceReturns.recoverable_request?(%Gitgood.SourceReturnOperation{
                 id: id,
                 actor_id: actor,
                 link_generation: link_generation,
                 connection_id: connection,
                 connection_generation: connection_generation,
                 locator: locator,
                 payload_cipher: cipher,
                 payload_digest: digest
               })
             end
           ) do
      :ok
    else
      _ -> {:error, :recovery_key_material_unavailable}
    end
  end

  defp recoverable_rows?(connection, sql, predicate) do
    case Postgrex.transaction(
           connection,
           fn database ->
             database
             |> Postgrex.stream(sql, [], max_rows: 16)
             |> Enum.all?(fn %{rows: rows} -> Enum.all?(rows, predicate) end)
           end,
           timeout: 300_000
         ) do
      {:ok, result} -> result
      _ -> false
    end
  rescue
    _ -> false
  end

  defp migrations(%{mode: :restore} = state) do
    Postgrex.query(
      state.connection,
      """
      SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename
      """,
      [],
      timeout: 3000
    )
  end

  defp migrations(state) do
    Postgrex.query(
      state.connection,
      "SELECT version::text FROM schema_migrations ORDER BY version",
      [],
      timeout: 3000
    )
  end

  @impl true
  def handle_info(:check, state) do
    if held?(state) do
      Process.send_after(self(), :check, 1000)
      {:noreply, state}
    else
      {:stop, :installation_lease_lost, state}
    end
  end

  @impl true
  def terminate(_, state) do
    # Keep markers: a live BEAM/maintenance owner still forbids a new operation after lease loss.
    if Process.alive?(state.connection), do: GenServer.stop(state.connection, :normal)
    :ok
  end
end
