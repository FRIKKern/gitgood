defmodule Gitgood.Reconciler do
  use GenServer
  def start_link(opts), do: GenServer.start_link(__MODULE__, opts, name: __MODULE__)
  def init(_), do: {:ok, nil, {:continue, :reconcile}}
  def handle_continue(:reconcile, state), do: handle_info(:reconcile, state)

  def handle_info(:reconcile, state) do
    if Application.get_env(:gitgood, :reconcile, true), do: Gitgood.Repositories.reconcile()
    Process.send_after(self(), :reconcile, 30_000)
    {:noreply, state}
  end
end
