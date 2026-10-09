defmodule Gitgood.SourceReturnWorker do
  use GenServer
  def start_link(opts), do: GenServer.start_link(__MODULE__, opts, name: __MODULE__)

  def init(_) do
    Process.send_after(self(), :tick, 5000)
    {:ok, nil, {:continue, :scan}}
  end

  def handle_continue(:scan, state), do: handle_info(:scan, state)

  def handle_info(:scan, state) do
    if Application.get_env(:gitgood, :reconcile, true) do
      ids =
        try do
          Gitgood.SourceReturns.pending_ids()
        rescue
          _ in [DBConnection.ConnectionError, Postgrex.Error] -> []
        end

      for id <- ids do
        Task.Supervisor.start_child(Gitgood.SourceReturnJobs, fn ->
          Gitgood.SourceReturns.process(id)
        end)
      end
    end

    {:noreply, state}
  end

  def handle_info(:tick, state) do
    Process.send_after(self(), :tick, 5000)
    handle_info(:scan, state)
  end
end
