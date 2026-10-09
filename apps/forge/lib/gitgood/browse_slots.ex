defmodule Gitgood.BrowseSlots do
  @moduledoc "Bounded FIFO browse admission; waiting callers retain their own request data."
  use GenServer

  def start_link(opts),
    do: GenServer.start_link(__MODULE__, opts, name: Keyword.get(opts, :name, __MODULE__))

  def init(opts) do
    capacity = Keyword.get(opts, :capacity, 4)
    waiting = Keyword.get(opts, :waiting, 8)
    deadline = Keyword.get(opts, :deadline, 5000)
    true = capacity in 1..4 and waiting in 1..8 and deadline in 1..5000

    {:ok,
     %{
       capacity: capacity,
       waiting: waiting,
       deadline: deadline,
       active: %{},
       pending: %{},
       queue: :queue.new()
     }}
  end

  def with_slot(action, server \\ __MODULE__) do
    case GenServer.call(server, :acquire, :infinity) do
      {:ok, reference} ->
        try do
          action.()
        after
          GenServer.call(server, {:release, reference})
        end

      error ->
        error
    end
  end

  def handle_call(:acquire, {pid, _}, %{active: active, capacity: capacity} = state)
      when map_size(active) < capacity do
    reference = Process.monitor(pid)
    {:reply, {:ok, reference}, %{state | active: Map.put(active, reference, pid)}}
  end

  def handle_call(:acquire, {pid, _} = from, %{pending: pending, waiting: waiting} = state)
      when map_size(pending) < waiting do
    reference = Process.monitor(pid)
    timer = Process.send_after(self(), {:deadline, reference}, state.deadline)
    expires = System.monotonic_time(:millisecond) + state.deadline

    {:noreply,
     %{
       state
       | pending: Map.put(pending, reference, {pid, from, timer, expires}),
         queue: :queue.in(reference, state.queue)
     }}
  end

  def handle_call(:acquire, _, state), do: {:reply, {:error, :browse_busy_retry}, state}

  def handle_call({:release, reference}, {pid, _}, state) do
    if Map.get(state.active, reference) == pid do
      Process.demonitor(reference, [:flush])
      {:reply, :ok, advance(%{state | active: Map.delete(state.active, reference)})}
    else
      {:reply, {:error, :not_owner}, state}
    end
  end

  def handle_call(:counts, _, state),
    do: {:reply, %{active: map_size(state.active), waiting: map_size(state.pending)}, state}

  def handle_info({:deadline, reference}, state) do
    case Map.get(state.pending, reference) do
      nil ->
        {:noreply, state}

      {_, from, _, _} ->
        Process.demonitor(reference, [:flush])
        GenServer.reply(from, {:error, :browse_busy_retry})
        {:noreply, remove_pending(state, reference)}
    end
  end

  def handle_info({:DOWN, reference, :process, _, _}, state) do
    if Map.has_key?(state.active, reference) do
      {:noreply, advance(%{state | active: Map.delete(state.active, reference)})}
    else
      {:noreply, remove_pending(state, reference)}
    end
  end

  defp remove_pending(state, reference) do
    case Map.get(state.pending, reference) do
      {_, _, timer, _} -> Process.cancel_timer(timer)
      nil -> :ok
    end

    queue =
      state.queue |> :queue.to_list() |> Enum.reject(&(&1 == reference)) |> :queue.from_list()

    %{state | pending: Map.delete(state.pending, reference), queue: queue}
  end

  defp advance(state) do
    case :queue.out(state.queue) do
      {:empty, _} ->
        state

      {{:value, reference}, queue} ->
        {pid, from, timer, expires} = Map.fetch!(state.pending, reference)
        Process.cancel_timer(timer)
        next = %{state | queue: queue, pending: Map.delete(state.pending, reference)}

        if System.monotonic_time(:millisecond) >= expires do
          Process.demonitor(reference, [:flush])
          GenServer.reply(from, {:error, :browse_busy_retry})
          advance(next)
        else
          GenServer.reply(from, {:ok, reference})
          %{next | active: Map.put(state.active, reference, pid)}
        end
    end
  end
end
