defmodule Gitgood.InstallationGenerationMonitor do
  @moduledoc "Bounded, linked observation of one captured native generation."
  use GenServer
  import Bitwise

  @python "/usr/bin/python3.12"
  @entry "/opt/gitgood/native/v2/native_generation_monitor_entry.py"
  @maximum 16_385
  @initial_timeout 30_000
  @freshness 3_000
  @digest ~r/\A[0-9a-f]{64}\z/
  @uuid ~r/\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\z/

  def start_link(options), do: GenServer.start_link(__MODULE__, options)
  def admission(pid), do: GenServer.call(pid, :admission)
  def ownership_context(pid), do: GenServer.call(pid, :ownership_context)
  def current(pid), do: GenServer.call(pid, :current)

  def attach_ownership(pid, record, receipt),
    do: GenServer.call(pid, {:attach_ownership, record, receipt}, 5_000)

  @impl true
  def init(options) do
    with {:unix, :linux} <- :os.type(),
         {:ok, installation} <- installation(Keyword.fetch!(options, :root)),
         {:ok, worker} <- worker(Keyword.fetch!(options, :mode)),
         {:ok, python} <- trusted_file(@python, true),
         {:ok, entry} <- trusted_file(@entry, false) do
      owner = String.to_integer(System.pid())
      port = open_port()

      try do
        true =
          Port.command(
            port,
            Jason.encode!(%{
              protocol: 2,
              installation: installation,
              worker: worker,
              owner_pid: owner
            }) <> "\n"
          )

        with {:ok, line, rest} <- initial_line(port, <<>>, now() + @initial_timeout),
             {:ok, value} <- Jason.decode(line),
             :ok <- validate_initial(value, installation, worker, owner),
             {:ok, ^python} <- trusted_file(@python, true),
             {:ok, ^entry} <- trusted_file(@entry, false),
             {:ok, pending, _} <- lines(rest, value["guard"]) do
          Process.send_after(self(), :freshness, 1_000)

          {:ok,
           %{
             port: port,
             admission: value["admission"],
             guard: value["guard"],
             buffer: pending,
             ownership: nil,
             ownership_pending: nil,
             observed_at: now()
           }}
        else
          _ ->
            close(port)
            {:stop, :installation_generation_unavailable}
        end
      rescue
        _ ->
          close(port)
          {:stop, :installation_generation_unavailable}
      catch
        _, _ ->
          close(port)
          {:stop, :installation_generation_unavailable}
      end
    else
      _ -> {:stop, :installation_generation_unavailable}
    end
  rescue
    _ -> {:stop, :installation_generation_unavailable}
  end

  defp installation(root) when is_binary(root) do
    case String.split(root, "/") do
      ["", "var", "lib", "gitgood", "installations", value, "storage"] ->
        if Regex.match?(@uuid, value), do: {:ok, value}, else: :error

      _ ->
        :error
    end
  end

  defp installation(_), do: :error
  defp worker(:runtime), do: {:ok, "native"}
  defp worker(mode) when mode in [:backup, :restore, :migrate], do: {:ok, "maintenance"}
  defp worker(_), do: :error

  defp trusted_file(path, executable) do
    with {:ok, info} <- File.lstat(path),
         true <-
           info.type == :regular and info.uid == 0 and info.links == 1 and
             (info.mode &&& 0o022) == 0,
         true <- not executable or (info.mode &&& 0o111) != 0,
         true <- trusted_parents?(Path.dirname(path)) do
      {:ok,
       {info.inode, info.major_device, info.minor_device, info.size, info.mtime, info.ctime,
        info.mode}}
    else
      _ -> :error
    end
  end

  defp trusted_parents?(path) do
    case File.lstat(path) do
      {:ok, info} when info.type == :directory and info.uid == 0 ->
        (info.mode &&& 0o022) == 0 and (path == "/" or trusted_parents?(Path.dirname(path)))

      _ ->
        false
    end
  end

  defp open_port do
    environment =
      Enum.map(System.get_env(), fn {name, _} -> {String.to_charlist(name), false} end)

    environment = environment ++ [{~c"PATH", ~c"/usr/bin:/bin"}, {~c"LANG", ~c"C.UTF-8"}]

    Port.open({:spawn_executable, @python}, [
      :binary,
      :exit_status,
      :use_stdio,
      {:args, ["-I", "-S", @entry]},
      {:env, environment}
    ])
  end

  defp initial_line(port, buffer, deadline) do
    remaining = deadline - now()

    if remaining <= 0 or byte_size(buffer) > @maximum do
      :error
    else
      case :binary.split(buffer, "\n") do
        [line, rest] ->
          {:ok, line, rest}

        [_] ->
          receive do
            {^port, {:data, bytes}} -> initial_line(port, buffer <> bytes, deadline)
            {^port, {:exit_status, _}} -> :error
          after
            remaining -> :error
          end
      end
    end
  end

  @doc false
  def validate_initial(value, installation, worker, owner) do
    with true <-
           is_map(value) and
             MapSet.new(Map.keys(value)) ==
               MapSet.new(~w(protocol status admission guard)),
         true <- value["protocol"] === 2 and value["status"] === "admitted",
         true <- valid_guard?(value["guard"]),
         :ok <-
           Gitgood.InstallationGenerationAdmission.validate(
             value["admission"],
             installation,
             worker,
             owner
           ) do
      :ok
    else
      _ -> :error
    end
  rescue
    _ -> :error
  end

  @doc false
  def validate_current(value, expected) do
    if is_map(value) and MapSet.new(Map.keys(value)) == MapSet.new(~w(protocol status guard)) and
         value["protocol"] === 2 and value["status"] === "current" and valid_guard?(expected) and
         value["guard"] === expected, do: :ok, else: :error
  end

  defp valid_guard?(value) do
    is_map(value) and
      MapSet.new(Map.keys(value)) ==
        MapSet.new(~w(scope_sha256 history_sha256 persistent_files_sha256)) and
      Enum.all?(Map.values(value), &(is_binary(&1) and Regex.match?(@digest, &1)))
  end

  defp lines(buffer, guard, count \\ 0) do
    if byte_size(buffer) > @maximum or count > 64 do
      :error
    else
      case :binary.split(buffer, "\n") do
        [line, rest] ->
          with {:ok, value} <- Jason.decode(line),
               :ok <- validate_current(value, guard),
               do: lines(rest, guard, count + 1)

        [_] ->
          {:ok, buffer, count}
      end
    end
  end

  @doc false
  def ownership_token(record, receipt, owner) do
    alias Gitgood.NativeOwnershipPublication, as: Publication

    with {:ok, _, digest} <- Publication.request(record, owner),
         :ok <- Publication.validate_reply(receipt, record["operation"], digest),
         true <- Regex.match?(@uuid, record["operation"]) do
      {:ok,
       %{
         "operation" => record["operation"],
         "record_sha256" => digest,
         "marker_sha256" => receipt["marker_sha256"],
         "ownership_marker_observed" => true,
         "original_database_session_observed" => true,
         "owner_socket_observed" => true,
         "lease_acquired" => false,
         "replacement_admitted" => false,
         "installation_readiness_established" => false,
         "lifecycle_responsibility_admitted" => false
       }}
    else
      _ -> :error
    end
  rescue
    _ -> :error
  end

  defp stream_lines(buffer, state, count \\ 0) do
    if byte_size(buffer) > @maximum or count > 64 do
      :error
    else
      case :binary.split(buffer, "\n") do
        [line, rest] ->
          with {:ok, value} <- Jason.decode(line),
               true <- line == Gitgood.NativeOwnershipPublication.canonical(value),
               {:ok, next} <- consume_frame(value, state),
               do: stream_lines(rest, next, count + 1)

        [_] ->
          {:ok, buffer, state, count}
      end
    end
  rescue
    _ -> :error
  end

  defp consume_frame(value, state) do
    ownership = Map.get(state, :ownership)
    pending = Map.get(state, :ownership_pending)

    cond do
      value["status"] == "ownership_attached" and not is_nil(pending) and is_nil(ownership) ->
        with true <-
               MapSet.new(Map.keys(value)) == MapSet.new(~w(protocol status guard ownership)),
             true <- value["protocol"] === 2 and value["guard"] === state.guard,
             true <- value["ownership"] === pending.expected do
          {:ok,
           Map.merge(state, %{
             ownership: pending.expected,
             ownership_pending: nil,
             ownership_reply: pending.from
           })}
        else
          _ -> :error
        end

      is_nil(ownership) ->
        with :ok <- validate_current(value, state.guard), do: {:ok, state}

      true ->
        with true <-
               MapSet.new(Map.keys(value)) == MapSet.new(~w(protocol status guard ownership)),
             true <- value["protocol"] === 2 and value["status"] === "current",
             true <- value["guard"] === state.guard and value["ownership"] === ownership do
          {:ok, state}
        else
          _ -> :error
        end
    end
  end

  @impl true
  def handle_info({port, {:data, bytes}}, %{port: port} = state) do
    with true <- now() - state.observed_at < @freshness,
         {:ok, rest, next, count} <- stream_lines(state.buffer <> bytes, state) do
      if reply = Map.get(next, :ownership_reply), do: GenServer.reply(reply, :ok)
      next = Map.delete(next, :ownership_reply)

      {:noreply,
       %{next | buffer: rest, observed_at: if(count > 0, do: now(), else: state.observed_at)}}
    else
      _ -> {:stop, :installation_generation_lost, state}
    end
  end

  def handle_info({port, {:exit_status, _}}, %{port: port} = state),
    do: {:stop, :installation_generation_lost, state}

  def handle_info(:freshness, state) do
    if now() - state.observed_at < @freshness do
      Process.send_after(self(), :freshness, 1_000)
      {:noreply, state}
    else
      {:stop, :installation_generation_lost, state}
    end
  end

  def handle_info({:ownership_deadline, reference}, state) do
    case Map.get(state, :ownership_pending) do
      %{reference: ^reference} -> {:stop, :installation_generation_lost, state}
      _ -> {:noreply, state}
    end
  end

  @impl true
  def handle_call({:attach_ownership, record, receipt}, from, state) do
    with true <- now() - state.observed_at < @freshness,
         true <- is_nil(Map.get(state, :ownership)) and is_nil(Map.get(state, :ownership_pending)),
         {:ok, expected} <- ownership_token(record, receipt, String.to_integer(System.pid())),
         true <- record["guard"] === state.guard,
         true <- record["pointer"] === state.admission["pointer"],
         true <- record["binding_sha256"] === state.admission["binding_sha256"],
         true <- record["owner"] === get_in(state.admission, ["worker_observation", "owner"]),
         true <-
           record["scope"] === get_in(state.admission, ["worker_observation", "service_scope"]),
         request <-
           Gitgood.NativeOwnershipPublication.canonical(%{
             "protocol" => 2,
             "action" => "attach_ownership",
             "record" => record
           }) <> "\n",
         true <- byte_size(request) <= 20_000,
         true <- Port.command(state.port, request) do
      reference = make_ref()
      Process.send_after(self(), {:ownership_deadline, reference}, @freshness)

      {:noreply,
       Map.put(state, :ownership_pending, %{from: from, expected: expected, reference: reference})}
    else
      _ -> {:stop, :installation_generation_lost, {:error, :installation_generation_lost}, state}
    end
  rescue
    _ -> {:stop, :installation_generation_lost, {:error, :installation_generation_lost}, state}
  end

  def handle_call(:admission, _, state) do
    if now() - state.observed_at < @freshness,
      do: {:reply, {:ok, state.admission}, state},
      else: {:stop, :installation_generation_lost, {:error, :installation_generation_lost}, state}
  end

  def handle_call(:ownership_context, _, state) do
    if now() - state.observed_at < @freshness,
      do: {:reply, {:ok, %{admission: state.admission, guard: state.guard}}, state},
      else: {:stop, :installation_generation_lost, {:error, :installation_generation_lost}, state}
  end

  def handle_call(:current, _, state) do
    if now() - state.observed_at < @freshness,
      do: {:reply, :ok, state},
      else: {:stop, :installation_generation_lost, {:error, :installation_generation_lost}, state}
  end

  @impl true
  def terminate(_, state), do: close(state.port)
  defp now, do: System.monotonic_time(:millisecond)

  defp close(port) do
    if Port.info(port), do: Port.close(port)
    :ok
  rescue
    _ -> :ok
  end
end
