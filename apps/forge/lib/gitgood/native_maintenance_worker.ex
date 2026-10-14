defmodule Gitgood.NativeMaintenanceWorker do
  @moduledoc "One fixed business action after original ownership and private input validation."
  use GenServer
  alias Gitgood.{Build, NativeOwnershipStartup, Repo}
  @failure :native_maintenance_unavailable

  def start_link(action) when action in [:migrate, :bootstrap],
    do: GenServer.start_link(__MODULE__, action, name: __MODULE__)

  def execute, do: GenServer.call(__MODULE__, :execute, 60_000)

  @impl true
  def init(action), do: {:ok, %{action: action, status: :pending, result: nil}}

  @impl true
  def handle_call(:execute, from, %{status: :pending} = state),
    do: begin_execution(from, state)

  def handle_call(:execute, _, state), do: {:stop, @failure, {:error, @failure}, state}

  defp begin_execution(from, state) do
    {:ok, timer} = :timer.exit_after(60_000, self(), :native_maintenance_deadline)

    {:noreply, Map.merge(%{state | status: :running}, %{from: from, timer: timer}),
     {:continue, :execute}}
  end

  @impl true
  def handle_continue(:execute, state) do
    with {NativeOwnershipStartup, startup, _, _} <-
           List.keyfind(Supervisor.which_children(Gitgood.Supervisor), NativeOwnershipStartup, 0),
         :ok <- NativeOwnershipStartup.current(startup),
         {:ok, inputs} <- NativeOwnershipStartup.private_business_inputs(startup),
         true <- inputs["action"] === Atom.to_string(state.action),
         :ok <-
           validate_inventory(inputs, Build.identity(), Gitgood.NativeMigrationInventory.read()),
         :ok <- NativeOwnershipStartup.current(startup),
         {:ok, outcome} <- apply_fixed(state.action, inputs, startup),
         :ok <- NativeOwnershipStartup.current(startup) do
      {:ok, _} = :timer.cancel(state.timer)
      GenServer.reply(state.from, {:ok, outcome})
      {:noreply, Map.delete(%{state | status: :complete, result: outcome}, :from)}
    else
      _ -> {:stop, @failure, state}
    end
  rescue
    _ -> {:stop, @failure, state}
  catch
    :exit, _ -> {:stop, @failure, state}
  end

  @doc false
  def validate_inventory(inputs, build, packaged) do
    with true <- is_map(inputs) and is_map(build) and build["dirty"] === false,
         true <- inputs["candidate"] === build["candidate"],
         {:ok, versions} <- Gitgood.NativeMigrationInventory.match_build(build, packaged),
         true <- versions === inputs["migrations"]["target_versions"],
         before when is_list(before) <- inputs["migrations"]["before_versions"],
         true <- before === Enum.take(versions, length(before)) do
      :ok
    else
      _ -> :error
    end
  rescue
    _ -> :error
  end

  defp schema_versions do
    case Repo.query!("SELECT to_regclass('public.schema_migrations') IS NOT NULL", []) do
      %{rows: [[false]]} ->
        []

      %{rows: [[true]]} ->
        Repo.query!("SELECT version FROM public.schema_migrations ORDER BY version", []).rows
        |> List.flatten()
    end
  end

  @doc false
  def validate_database(:migrate, migrations) do
    true = namespace_valid?()
    before = migrations["before_versions"]
    true = schema_versions() === before

    if before === [] do
      %{rows: [[0]]} =
        Repo.query!(
          "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%' AND n.nspname NOT LIKE 'pg_temp%' AND c.relkind IN ('r','p','v','m','S','f') AND NOT (n.nspname='public' AND c.relname='schema_migrations')",
          []
        )
    end

    :ok
  rescue
    _ -> :error
  end

  def validate_database(:bootstrap, migrations) do
    true = namespace_valid?()
    if schema_versions() === migrations["target_versions"], do: :ok, else: :error
  rescue
    _ -> :error
  end

  def validate_database(_, _), do: :error

  defp namespace_valid? do
    Repo.query!("SELECT pg_catalog.current_schemas(true)", []).rows === [
      [["pg_catalog", "public"]]
    ]
  end

  defp apply_fixed(:migrate, inputs, startup) do
    before = inputs["migrations"]["before_versions"]
    target = inputs["migrations"]["target_versions"]
    :ok = validate_database(:migrate, inputs["migrations"])

    :ok = NativeOwnershipStartup.current(startup)
    applied = Ecto.Migrator.run(Repo, :up, all: true, prefix: "public")
    true = applied === target -- before
    true = schema_versions() === target
    {:ok, outcome(inputs, applied, false)}
  end

  defp apply_fixed(:bootstrap, inputs, startup) do
    target = inputs["migrations"]["target_versions"]
    :ok = validate_database(:bootstrap, inputs["migrations"])
    params = inputs["bootstrap"]
    expected = inputs["bootstrap_request_sha256"]
    {:ok, absent} = Gitgood.InstallationOwnerBootstrap.observe(params, expected)
    true = absent.outcome === "absent"
    :ok = NativeOwnershipStartup.current(startup)
    {:ok, created} = Gitgood.InstallationOwnerBootstrap.create(params, expected)
    {:ok, observed} = Gitgood.InstallationOwnerBootstrap.observe(params, expected)
    true = observed.outcome === "recorded" and observed.user_id === created.user_id
    {:ok, user} = Gitgood.Accounts.authenticate(params["username"], params["password"])

    true =
      user.id === observed.user_id and Gitgood.Accounts.role(user.id, params["team"]) === "owner"

    true = schema_versions() === target
    {:ok, outcome(inputs, [], true)}
  end

  defp outcome(inputs, applied, bootstrap) do
    %{
      protocol: 2,
      kind: "native_maintenance_outcome",
      installation: inputs["installation"],
      operation: inputs["operation"],
      candidate: inputs["candidate"],
      action: inputs["action"],
      schema_versions: inputs["migrations"]["target_versions"],
      applied_versions: applied,
      bootstrap_owner_observed: bootstrap,
      business_effects_observed: true,
      installation_readiness_established: false,
      complete_journey_acceptance: false
    }
  end

  @impl true
  def format_status(status) do
    Map.new(status, fn
      {:state, _} -> {:state, :native_maintenance_status_redacted}
      {:message, _} -> {:message, :native_maintenance_message_redacted}
      {:reason, _} -> {:reason, @failure}
      {:log, _} -> {:log, []}
      item -> item
    end)
  end
end
