defmodule Gitgood.TransportSlots do
  use GenServer
  def start_link(opts), do: GenServer.start_link(__MODULE__, opts, name: __MODULE__)
  def init(_), do: {:ok, %{}}

  def with_slot(action) do
    case GenServer.call(__MODULE__, :acquire) do
      {:ok, reference} ->
        try do
          action.()
        after
          GenServer.call(__MODULE__, {:release, reference})
        end

      error ->
        error
    end
  end

  def handle_call(:acquire, {pid, _}, state) when map_size(state) < 4 do
    reference = Process.monitor(pid)
    {:reply, {:ok, reference}, Map.put(state, reference, pid)}
  end

  def handle_call(:acquire, _, state), do: {:reply, {:error, :busy}, state}

  def handle_call({:release, reference}, {pid, _}, state) do
    if Map.get(state, reference) == pid do
      Process.demonitor(reference, [:flush])
      {:reply, :ok, Map.delete(state, reference)}
    else
      {:reply, {:error, :not_owner}, state}
    end
  end

  def handle_info({:DOWN, reference, :process, _, _}, state),
    do: {:noreply, Map.delete(state, reference)}
end
