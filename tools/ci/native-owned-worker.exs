# Loaded by the clean packaged release's `eval` command. Only this fixture app
# is started: Gitgood.Application still refuses native product startup.
defmodule GitgoodOwnedProof.Diagnostics do
  # Observe actual exported startup calls. Never serialize trace arguments,
  # return values, exception reasons, or process state into this event stream.
  @calls [
    {Gitgood.InstallationProfile, :resolve, 3, "profile"},
    {Gitgood.InstallationGenerationMonitor, :start_link, 1, "monitor"},
    {Gitgood.InstallationGenerationMonitor, :admission, 1, "admission"},
    {Gitgood.NativeOwnershipInputs, :read_application, 2, "inputs"},
    {Gitgood.NativeOwnershipStartup, :validate_artifact, 2, "artifact"},
    {Gitgood.NativeApplicationConfiguration, :check, 3, "configuration"},
    {Gitgood.NativeDatabaseLease, :start_link, 1, "lease"},
    {Gitgood.NativeOwnershipFence, :start_link, 2, "fence"},
    {Gitgood.NativeOwnershipClaim, :claim, 4, "claim"},
    {Gitgood.InstallationGenerationMonitor, :attach_ownership, 3, "attachment"}
  ]

  def start do
    path = Path.join(System.fetch_env!("GITGOOD_OWNED_PROOF_DIRECTORY"), "startup-events.txt")
    {:ok, file} = :file.open(String.to_charlist(path), [:write, :exclusive, :raw, :binary])
    :ok = :file.close(file)
    File.chmod!(path, 0o600)

    labels =
      Map.new(@calls, fn {module, function, arity, label} ->
        {{module, function, arity}, label}
      end)

    tracer = spawn(fn -> loop(path, labels, 0) end)
    Process.register(tracer, __MODULE__)

    Enum.each(@calls, fn {module, function, arity, _} ->
      Code.ensure_loaded!(module)
      1 = :erlang.trace_pattern({module, function, arity}, [{:_, [], [{:exception_trace}]}], [])
    end)

    :erlang.trace(:all, true, [:call, :arity, {:tracer, tracer}])
    :ok
  end

  def mark(label)
      when label in [
             "bootstrap",
             "build-valid",
             "dependencies",
             "application-start",
             "application-started",
             "witness-started",
             "witness-current",
             "witness-samples",
             "descendant-started",
             "attached"
           ] do
    send(__MODULE__, {:mark, label})
    :ok
  end

  defp loop(path, labels, count) do
    receive do
      {:trace, _, :call, mfa} ->
        record(path, labels, count, Map.fetch!(labels, mfa) <> ":entered")

      {:trace, _, :return_from, mfa, value} ->
        outcome =
          case value do
            :ok -> "accepted"
            {:ok, _} -> "accepted"
            {:ok, _, _} -> "accepted"
            _ -> "refused"
          end

        record(path, labels, count, Map.fetch!(labels, mfa) <> ":" <> outcome)

      {:trace, _, :exception_from, mfa, _} ->
        record(path, labels, count, Map.fetch!(labels, mfa) <> ":exception")

      {:mark, label} ->
        record(path, labels, count, label <> ":observed")
    end
  end

  defp record(path, labels, count, event) when count < 64 do
    File.write!(path, event <> "\n", [:append])
    loop(path, labels, count + 1)
  end

  # A fixture diagnostic overflow terminates the original BEAM; it cannot
  # silently discard events or grow an unbounded log and still report success.
  defp record(_, _, _, _), do: System.halt(78)
end

defmodule GitgoodOwnedProof.Witness do
  use GenServer

  def start_link(options), do: GenServer.start_link(__MODULE__, options)

  @impl true
  def init(options) do
    GitgoodOwnedProof.Diagnostics.mark("witness-started")
    send(self(), :observe)

    {:ok,
     %{
       directory: options[:directory],
       observed: nil,
       count: 0,
       deadline: now() + 20_000,
       private_inputs_observed: false
     }}
  end

  @impl true
  def handle_info(:observe, state) do
    true = now() < state.deadline

    {Gitgood.NativeOwnershipStartup, startup, _, _} =
      List.keyfind(
        Supervisor.which_children(Gitgood.Supervisor),
        Gitgood.NativeOwnershipStartup,
        0
      )

    :ok = Gitgood.NativeOwnershipStartup.current(startup)
    action = System.get_env("GITGOOD_OWNED_PROOF_LIFECYCLE_ACTION")

    state =
      if System.get_env("GITGOOD_OWNED_PROOF_PRIVATE_INPUTS") == "true" and
           action in ["migrate", "bootstrap"] and not state.private_inputs_observed do
        {:ok, inputs} = Gitgood.NativeOwnershipStartup.private_business_inputs(startup)
        true = inputs["action"] == action
        true = inputs["migrations"] == %{"before_versions" => [], "target_versions" => [1, 2]}

        if action == "bootstrap" do
          {:ok, _} =
            Gitgood.InstallationOwnerBootstrap.validate(
              inputs["bootstrap"],
              inputs["bootstrap_request_sha256"]
            )

          true = inputs["bootstrap"]["password"] == "synthetic-secret-éé"
        else
          false = Map.has_key?(inputs, "bootstrap")
          false = Map.has_key?(inputs, "bootstrap_request_sha256")
        end

        source = :sys.get_state(startup)
        status = inspect(:sys.get_status(source.monitor), limit: :infinity)
        false = String.contains?(status, "synthetic-secret-éé")

        write!(state.directory, "private-inputs-observed.json", %{
          action: action,
          original_guard_and_ownership_bound: true,
          credential_status_redacted: true,
          bootstrap_digest_validated: action == "bootstrap",
          business_effects_executed: false
        })

        %{state | private_inputs_observed: true}
      else
        state
      end

    owner = :sys.get_state(startup)
    monitor = :sys.get_state(owner.monitor)
    true = is_map(monitor.ownership) and is_nil(monitor.ownership_pending)
    true = now() - monitor.observed_at < 3_000
    if is_nil(state.observed), do: GitgoodOwnedProof.Diagnostics.mark("witness-current")
    # The first sample can be the ownership_attached acknowledgement. Treat it
    # as a baseline; only subsequent changed timestamps prove current frames.
    count =
      if not is_nil(state.observed) and monitor.observed_at != state.observed,
        do: state.count + 1,
        else: state.count

    if count >= 5 do
      GitgoodOwnedProof.Diagnostics.mark("witness-samples")
      # A real BEAM-owned subprocess in a separate session ignores TERM. Its
      # cgroup custody is checked by the root observer before the loss action.
      # Fork before setsid: the port process itself may already be a process
      # group leader, and closing the port must not terminate this descendant.
      program = """
      import os, signal, time
      child = os.fork()
      if child:
          os.waitpid(child, 0)
      else:
          os.setsid()
          signal.signal(signal.SIGTERM, signal.SIG_IGN)
          signal.signal(signal.SIGHUP, signal.SIG_IGN)
          print(os.getpid(), flush=True)
          time.sleep(300)
      """

      port =
        Port.open({:spawn_executable, "/usr/bin/python3.12"}, [
          :binary,
          :exit_status,
          {:args, ["-I", "-S", "-c", program]}
        ])

      descendant =
        receive do
          {^port, {:data, raw}} -> raw |> String.trim() |> String.to_integer()
        after
          3_000 -> raise "fixture descendant unavailable"
        end

      {:os_pid, helper} = Port.info(monitor.port, :os_pid)
      GitgoodOwnedProof.Diagnostics.mark("descendant-started")
      {:ok, session} = Gitgood.NativeDatabaseLease.snapshot(owner.lease)
      true = session == owner.ownership.record["database_session"]
      :ok = Gitgood.NativeOwnershipStartup.current(startup)

      repeated_admission_refused =
        if owner.ownership.record["protocol"] == 4 do
          {:ok, admission} = Gitgood.InstallationGenerationMonitor.admission(owner.monitor)

          {:ok, inputs} =
            Gitgood.NativeOwnershipInputs.read_application(
              System.fetch_env!("GITGOOD_STORAGE"),
              admission
            )

          mode = if owner.ownership.record["mode"] == "runtime", do: :runtime, else: :migrate

          {:error, :native_ownership_publication_unavailable} =
            Gitgood.NativeOwnershipPublication.admit_owner(admission, inputs.authority, mode)

          true
        else
          false
        end

      write!(state.directory, "attached.json", %{
        protocol: 1,
        scope: "publication-only-component",
        native_application_acceptance: false,
        beam_pid: String.to_integer(System.pid()),
        helper_pid: helper,
        descendant_pid: descendant,
        distinct_attached_heartbeat_samples: count,
        repeated_admission_refused: repeated_admission_refused,
        record: owner.ownership.record,
        publication: owner.ownership.receipt
      })

      GitgoodOwnedProof.Diagnostics.mark("attached")

      {:noreply, Map.put(state, :descendant_port, port)}
    else
      Process.send_after(self(), :observe, 100)
      {:noreply, %{state | count: count, observed: monitor.observed_at}}
    end
  end

  # Any unexpected fixture/helper event fails the permanent fixture application.
  def handle_info(_, state), do: {:stop, :fixture_witness_lost, state}

  defp now, do: System.monotonic_time(:millisecond)

  defp write!(directory, name, value) do
    temporary = Path.join(directory, name <> ".partial")
    File.write!(temporary, Jason.encode!(value), [:exclusive])
    File.chmod!(temporary, 0o600)
    File.rename!(temporary, Path.join(directory, name))
  end
end

defmodule GitgoodOwnedProof.Application do
  use Application

  @impl true
  def start(_, _) do
    workers = [
      {GitgoodOwnedProof.Witness, directory: System.fetch_env!("GITGOOD_OWNED_PROOF_DIRECTORY")}
    ]

    case System.get_env("GITGOOD_OWNED_PROOF_LIFECYCLE_ACTION") do
      "migrate" ->
        Gitgood.NativeOwnershipSupervisor.start_lifecycle_link(
          System.fetch_env!("GITGOOD_STORAGE"),
          :migrate,
          workers
        )

      "bootstrap" ->
        Gitgood.NativeOwnershipSupervisor.start_lifecycle_link(
          System.fetch_env!("GITGOOD_STORAGE"),
          :bootstrap,
          workers
        )

      "runtime" ->
        Gitgood.NativeOwnershipSupervisor.start_lifecycle_link(
          System.fetch_env!("GITGOOD_STORAGE"),
          :runtime,
          workers
        )

      nil ->
        case System.get_env("GITGOOD_OWNED_PROOF_CONTROLLER_MODE") do
          nil ->
            Gitgood.NativeOwnershipSupervisor.start_native_link(
              System.fetch_env!("GITGOOD_STORAGE"),
              :runtime,
              workers
            )

          "migrate" ->
            Gitgood.NativeOwnershipSupervisor.start_controller_link(
              System.fetch_env!("GITGOOD_STORAGE"),
              :migrate,
              workers
            )

          "runtime" ->
            Gitgood.NativeOwnershipSupervisor.start_controller_link(
              System.fetch_env!("GITGOOD_STORAGE"),
              :runtime,
              workers
            )
        end
    end
  end
end

GitgoodOwnedProof.Diagnostics.start()
GitgoodOwnedProof.Diagnostics.mark("bootstrap")
true = Gitgood.Build.valid?()
GitgoodOwnedProof.Diagnostics.mark("build-valid")
false = Enum.any?(Application.started_applications(), fn {name, _, _} -> name == :gitgood end)
{:ok, _} = Application.ensure_all_started(:postgrex)
{:ok, _} = Application.ensure_all_started(:jason)
GitgoodOwnedProof.Diagnostics.mark("dependencies")

:ok =
  :application.load(
    {:application, :gitgood_owned_proof,
     [
       description: ~c"Isolated native ownership component proof",
       vsn: ~c"1",
       modules: [GitgoodOwnedProof.Application, GitgoodOwnedProof.Witness],
       registered: [],
       applications: [:kernel, :stdlib, :elixir, :logger, :postgrex, :jason],
       mod: {GitgoodOwnedProof.Application, []}
     ]}
  )

# A failed original monitor, lease, fence or startup root terminates this BEAM.
# The ordinary manager does not signal the BEAM during the loss observation.
GitgoodOwnedProof.Diagnostics.mark("application-start")
:ok = Application.start(:gitgood_owned_proof, :permanent)
GitgoodOwnedProof.Diagnostics.mark("application-started")
Process.sleep(:infinity)
