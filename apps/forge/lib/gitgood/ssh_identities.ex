defmodule Gitgood.SSHIdentities do
  use GenServer
  def start_link(opts), do: GenServer.start_link(__MODULE__, opts, name: __MODULE__)
  def init(_), do: {:ok, %{connections: %{}, monitors: %{}}}

  def offer(user, credential),
    do: GenServer.call(__MODULE__, {:offer, user.id, credential.id, user.username})

  def activate(username, method),
    do: GenServer.call(__MODULE__, {:activate, to_string(username), to_string(method)})

  def resolve(connection), do: GenServer.call(__MODULE__, {:resolve, connection})

  def handle_call({:offer, user_id, credential_id, username}, {pid, _}, state) do
    {state, monitor} =
      if Map.has_key?(state.connections, pid),
        do: {state, nil},
        else: {state, Process.monitor(pid)}

    monitors = if monitor, do: Map.put(state.monitors, monitor, pid), else: state.monitors
    binding = %{user_id: user_id, credential_id: credential_id, username: username, active: false}

    {:reply, true,
     %{state | connections: Map.put(state.connections, pid, binding), monitors: monitors}}
  end

  def handle_call({:activate, username, "publickey"}, {pid, _}, state) do
    case Map.get(state.connections, pid) do
      %{username: ^username} = binding ->
        {:reply, :ok,
         %{state | connections: Map.put(state.connections, pid, %{binding | active: true})}}

      _ ->
        {:reply, :denied, state}
    end
  end

  def handle_call({:activate, _, _}, _, state), do: {:reply, :denied, state}

  def handle_call({:resolve, connection}, _, state) do
    result =
      case Map.get(state.connections, connection) do
        %{active: true, user_id: uid, credential_id: cid} -> {:ok, uid, cid}
        _ -> {:error, :unauthorized}
      end

    {:reply, result, state}
  end

  def handle_info({:DOWN, monitor, :process, _, _}, state) do
    {pid, monitors} = Map.pop(state.monitors, monitor)
    {:noreply, %{state | monitors: monitors, connections: Map.delete(state.connections, pid)}}
  end
end
