defmodule Gitgood.NativeOwnershipStartup do
  @moduledoc "First native child: claim once before workers; never restart original helpers."
  use GenServer

  alias Gitgood.InstallationGenerationMonitor, as: Monitor
  alias Gitgood.NativeDatabaseLease, as: Lease
  alias Gitgood.NativeOwnershipClaim, as: Claim
  alias Gitgood.NativeOwnershipFence, as: Fence
  alias Gitgood.NativeOwnershipInputs, as: Inputs
  alias Gitgood.NativeApplicationConfiguration, as: Configuration

  @failure :native_ownership_startup_unavailable
  @keys [:root, :mode]
  @root ~r"\A/var/lib/gitgood/installations/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/storage\z"

  def start_link(options) do
    if validate_options(options) == :ok,
      do: GenServer.start_link(__MODULE__, options),
      else: {:error, @failure}
  end

  def start_controller_link(options) do
    if validate_options(options) == :ok,
      do: GenServer.start_link(__MODULE__, Keyword.put(options, :controller_handoff, true)),
      else: {:error, @failure}
  end

  def start_lifecycle_link(options) do
    if validate_lifecycle_options(options) == :ok do
      {:ok, mode} = Gitgood.NativeLifecycleAction.mode(options[:action])

      GenServer.start_link(__MODULE__,
        root: options[:root],
        mode: mode,
        controller_handoff: true,
        lifecycle_action: options[:action]
      )
    else
      {:error, @failure}
    end
  end

  def current(pid), do: GenServer.call(pid, :current, 10_000)

  @impl true
  def init(options) do
    controller_handoff = Keyword.get(options, :controller_handoff, false)
    lifecycle_action = Keyword.get(options, :lifecycle_action)
    options = Keyword.drop(options, [:controller_handoff, :lifecycle_action])

    with :ok <- validate_options(options),
         {:ok, %{profile: :systemd_v2, installation: installation}} <-
           Gitgood.InstallationProfile.resolve("systemd-v2", options[:root], options[:mode]),
         {:ok, monitor} <- Monitor.start_link(root: options[:root], mode: options[:mode]),
         {:ok, admission} <- Monitor.admission(monitor),
         true <- admission["installation"] == installation,
         {:ok, inputs} <- Inputs.read_application(options[:root], admission),
         :ok <- validate_artifact(Gitgood.Build.identity(), inputs.authority),
         :ok <- Configuration.check(inputs, admission, options[:mode]),
         :ok <- validate_lifecycle(lifecycle_action, admission, inputs.authority),
         {:ok, handoff} <-
           admit_controller(controller_handoff, admission, inputs.authority, options[:mode]),
         {:ok, lease} <-
           Lease.start_link(database: admission["database"], connection: inputs.connection),
         {:ok, fence} <- Fence.start_link(monitor, lease),
         {:ok, ownership} <-
           Claim.claim(monitor, lease, inputs.authority, options[:mode], handoff),
         :ok <- Fence.current(fence) do
      {:ok,
       %{
         monitor: monitor,
         lease: lease,
         fence: fence,
         reference: Process.monitor(fence),
         ownership: ownership
       }}
    else
      _ -> {:stop, @failure}
    end
  rescue
    _ -> {:stop, @failure}
  catch
    :exit, _ -> {:stop, @failure}
  end

  defp admit_controller(false, _, _, _), do: {:ok, nil}

  defp admit_controller(true, admission, authority, mode),
    do: Gitgood.NativeOwnershipPublication.admit_owner(admission, authority, mode)

  defp validate_lifecycle(nil, _, _), do: :ok

  defp validate_lifecycle(action, admission, authority),
    do: Gitgood.NativeLifecycleAction.validate(admission, authority, action)

  @doc false
  def validate_artifact(identity, authority) do
    if is_map(identity) and is_map(authority) and identity["dirty"] === false and
         is_binary(identity["candidate"]) and
         Regex.match?(~r/\A[0-9a-f]{40}\z/, identity["candidate"]) and
         identity["candidate"] === authority["candidate"],
       do: :ok,
       else: :error
  rescue
    _ -> :error
  end

  @doc false
  def validate_options(options) do
    if Keyword.keyword?(options) and Enum.sort(Keyword.keys(options)) == Enum.sort(@keys) and
         options[:mode] in [:runtime, :backup, :restore, :migrate] and
         is_binary(options[:root]) and byte_size(options[:root]) <= 4_096 and
         Regex.match?(@root, options[:root]),
       do: :ok,
       else: :error
  rescue
    _ -> :error
  end

  @doc false
  def validate_lifecycle_options(options) do
    with true <-
           Keyword.keyword?(options) and Enum.sort(Keyword.keys(options)) == [:action, :root],
         {:ok, mode} <- Gitgood.NativeLifecycleAction.mode(options[:action]) do
      validate_options(root: options[:root], mode: mode)
    else
      _ -> :error
    end
  rescue
    _ -> :error
  end

  @impl true
  def handle_call(:current, _from, state) do
    with :ok <- Fence.current(state.fence),
         :ok <- Lease.current(state.lease),
         :ok <- Monitor.current(state.monitor) do
      {:reply, :ok, state}
    else
      _ -> {:stop, @failure, {:error, @failure}, state}
    end
  rescue
    _ -> {:stop, @failure, {:error, @failure}, state}
  catch
    :exit, _ -> {:stop, @failure, {:error, @failure}, state}
  end

  @impl true
  def handle_info(
        {:DOWN, reference, :process, fence, _},
        %{reference: reference, fence: fence} = state
      ),
      do: {:stop, @failure, state}

  def handle_info(_, state), do: {:stop, @failure, state}

  @impl true
  def terminate(_, state) do
    # Stop the watcher first, then close the original session and monitor. No
    # marker, ownership record, partial or controller responsibility is removed.
    Enum.each([state.fence, state.lease, state.monitor], fn original ->
      if Process.alive?(original), do: GenServer.stop(original, :normal, 3_000)
    end)
  catch
    :exit, _ -> :ok
  end
end
