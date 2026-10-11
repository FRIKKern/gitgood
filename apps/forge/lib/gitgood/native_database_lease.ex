defmodule Gitgood.NativeDatabaseLease do
  @moduledoc "One native installation lease session; loss stops its owner without reacquisition."
  use GenServer

  @namespace 1_197_034_575
  @key 1
  @connection_keys [:hostname, :port, :database, :username, :password, :ssl, :socket_options]

  def start_link(options), do: GenServer.start_link(__MODULE__, options)
  def snapshot(pid), do: GenServer.call(pid, :snapshot, 4_000)
  def current(pid), do: GenServer.call(pid, :current, 4_000)

  @impl true
  def init(options) do
    expected = Keyword.fetch!(options, :database)
    supplied = Keyword.fetch!(options, :connection)

    with :ok <- Gitgood.InstallationDatabaseSession.validate_database(expected),
         true <- Keyword.keyword?(supplied),
         true <-
           supplied[:hostname] === expected["address"] and supplied[:port] === expected["port"],
         true <-
           supplied[:database] === expected["database"] and
             supplied[:username] === expected["role"],
         {:ok, connection} <- Postgrex.start_link(connection_options(supplied)) do
      case acquire(connection, expected) do
        {:ok, snapshot} ->
          reference = Process.monitor(connection)
          Process.send_after(self(), :check, 1_000)
          {:ok, %{connection: connection, reference: reference, snapshot: snapshot}}

        _ ->
          stop_connection(connection)
          {:stop, :native_database_lease_unavailable}
      end
    else
      _ -> {:stop, :native_database_lease_unavailable}
    end
  rescue
    _ -> {:stop, :native_database_lease_unavailable}
  catch
    :exit, _ -> {:stop, :native_database_lease_unavailable}
  end

  defp connection_options(supplied) do
    supplied
    |> Keyword.take(@connection_keys)
    |> Keyword.merge(
      pool_size: 1,
      backoff_type: :stop,
      connect_timeout: 3_000,
      timeout: 3_000,
      show_sensitive_data_on_connection_error: false,
      parameters: [
        application_name: "gitgood native installation lease v2",
        search_path: "pg_catalog",
        statement_timeout: "3000",
        default_transaction_read_only: "on"
      ]
    )
  end

  defp acquire(connection, expected) do
    with {:ok, %{rows: [[true]]}} <-
           Postgrex.query(
             connection,
             "SELECT pg_catalog.pg_try_advisory_lock($1::int, $2::int)",
             [@namespace, @key],
             timeout: 3_000
           ),
         {:ok, snapshot} <- Gitgood.InstallationDatabaseSession.capture(connection, expected) do
      {:ok, snapshot}
    else
      _ -> :error
    end
  end

  @impl true
  def handle_call(request, _from, state) when request in [:snapshot, :current] do
    case Gitgood.InstallationDatabaseSession.check(state.connection, state.snapshot) do
      :ok -> {:reply, if(request == :snapshot, do: {:ok, state.snapshot}, else: :ok), state}
      _ -> {:stop, :native_database_lease_lost, {:error, :native_database_lease_lost}, state}
    end
  end

  @impl true
  def handle_info(:check, state) do
    case Gitgood.InstallationDatabaseSession.check(state.connection, state.snapshot) do
      :ok ->
        Process.send_after(self(), :check, 1_000)
        {:noreply, state}

      _ ->
        {:stop, :native_database_lease_lost, state}
    end
  end

  def handle_info(
        {:DOWN, reference, :process, connection, _},
        %{reference: reference, connection: connection} = state
      ),
      do: {:stop, :native_database_lease_lost, state}

  @impl true
  def terminate(_, state), do: stop_connection(state.connection)

  defp stop_connection(connection) do
    if Process.alive?(connection), do: GenServer.stop(connection, :normal, 3_000)
  catch
    :exit, _ -> :ok
  end
end
