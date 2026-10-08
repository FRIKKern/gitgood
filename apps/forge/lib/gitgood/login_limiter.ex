defmodule Gitgood.LoginLimiter do
  use GenServer
  def start_link(opts), do: GenServer.start_link(__MODULE__, opts, name: __MODULE__)
  def init(_), do: {:ok, %{}}
  def allow?(ip), do: GenServer.call(__MODULE__, {:allow, ip})

  def handle_call({:allow, ip}, _, state) do
    window = div(System.monotonic_time(:second), 60)
    state = Map.filter(state, fn {_, {w, _}} -> w == window end)
    {_, count} = Map.get(state, ip, {window, 0})
    allowed = count < 20 and map_size(state) < 10_000

    next =
      if Map.has_key?(state, ip) or map_size(state) < 10_000,
        do: Map.put(state, ip, {window, count + 1}),
        else: state

    {:reply, allowed, next}
  end
end
