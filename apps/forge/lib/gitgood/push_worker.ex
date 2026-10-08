defmodule Gitgood.PushWorker do
  use GenServer, restart: :temporary, shutdown: 70_000
  def start_link(work), do: GenServer.start_link(__MODULE__, work)
  def init(work), do: {:ok, {work, nil}}
  def handle_call(:run, from, {work, nil}), do: {:noreply, {work, from}, {:continue, :execute}}

  def handle_continue(:execute, {{repository, user, credential, action}, from} = state) do
    # A complete upload owns durable responsibility even if its HTTP caller disconnects.
    result =
      try do
        Gitgood.Pushes.execute(repository, user, credential, action)
      rescue
        _ -> {:error, :operation_failed}
      catch
        _, _ -> {:error, :operation_failed}
      end

    GenServer.reply(from, result)
    {:stop, :normal, state}
  end
end
