defmodule Gitgood.ImportWorker do
  use GenServer, restart: :temporary
  def start_link(id), do: GenServer.start_link(__MODULE__, id)
  def init(id), do: {:ok, id, {:continue, :run}}

  def handle_continue(:run, id) do
    {:ok, timer} = :timer.exit_after(90_000, self(), :kill)

    try do
      Gitgood.Imports.execute(id)
    after
      :timer.cancel(timer)
    end

    {:stop, :normal, id}
  end
end
