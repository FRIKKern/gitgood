defmodule Gitgood.NativeRuntimeWorker do
  @moduledoc "One runtime activation after original ownership, package and schema prerequisites."
  use GenServer
  alias Gitgood.{Build, NativeMigrationInventory, NativeOwnershipStartup}
  @failure :native_runtime_unavailable

  def start_link(_), do: GenServer.start_link(__MODULE__, [], name: __MODULE__)
  def activate, do: GenServer.call(__MODULE__, :activate, 60_000)

  @impl true
  def init([]), do: {:ok, %{status: :pending}}

  @impl true
  def handle_call(:activate, from, %{status: :pending} = state) do
    {:ok, timer} = :timer.exit_after(60_000, self(), :native_runtime_deadline)

    {:noreply, Map.merge(state, %{status: :running, from: from, timer: timer}),
     {:continue, :activate}}
  end

  def handle_call(:activate, _, state), do: {:stop, @failure, {:error, @failure}, state}

  @impl true
  def handle_continue(:activate, state) do
    with {NativeOwnershipStartup, startup, _, _} <-
           List.keyfind(Supervisor.which_children(Gitgood.Supervisor), NativeOwnershipStartup, 0),
         :ok <- NativeOwnershipStartup.current(startup),
         {:ok, target} <-
           NativeMigrationInventory.match_build(Build.identity(), NativeMigrationInventory.read()),
         :ok <-
           Gitgood.NativeMaintenanceWorker.validate_database(:bootstrap, %{
             "target_versions" => target
           }),
         :ok <- NativeOwnershipStartup.current(startup) do
      # The root has completed init before this one-use call. Each fixed child
      # starts only after a current check of the original captured startup PID.
      Enum.each([GitgoodWeb.Telemetry | Gitgood.RuntimeWorkers.children()], fn child ->
        :ok = NativeOwnershipStartup.current(startup)

        {:ok, _} =
          Supervisor.start_child(
            Gitgood.Supervisor,
            Supervisor.child_spec(child, restart: :permanent)
          )

        :ok = NativeOwnershipStartup.current(startup)
      end)

      %{ready: true} = Gitgood.Readiness.check()
      :ok = NativeOwnershipStartup.current(startup)
      {:ok, _} = :timer.cancel(state.timer)

      outcome = %{
        protocol: 2,
        kind: "native_runtime_outcome",
        candidate: Build.identity()["candidate"],
        schema_versions: target,
        product_workers_started: true,
        internal_readiness_observed: true,
        public_activation_verified: false,
        complete_journey_acceptance: false
      }

      GenServer.reply(state.from, {:ok, outcome})
      {:noreply, %{status: :active, startup: startup, outcome: outcome}}
    else
      _ -> {:stop, @failure, state}
    end
  rescue
    _ -> {:stop, @failure, state}
  catch
    :exit, _ -> {:stop, @failure, state}
  end

  @impl true
  def handle_info(_, state), do: {:stop, @failure, state}

  @impl true
  def format_status(status) do
    Map.new(status, fn
      {:state, _} -> {:state, :native_runtime_status_redacted}
      {:message, _} -> {:message, :native_runtime_message_redacted}
      {:reason, _} -> {:reason, @failure}
      {:log, _} -> {:log, []}
      item -> item
    end)
  end
end
