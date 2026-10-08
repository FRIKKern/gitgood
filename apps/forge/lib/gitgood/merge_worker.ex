defmodule Gitgood.MergeWorker do
  use GenServer, restart: :temporary
  def start_link(args), do: GenServer.start_link(__MODULE__, args)
  def init(args), do: {:ok, args}

  def handle_call(:run, _from, {repository, pull, user, credential, params, key, opts} = state) do
    result =
      try do
        Gitgood.Merges.execute(repository, pull, user, credential, params, key, opts)
      rescue
        _ -> {:error, :merge_failed_query_operation}
      catch
        _, _ -> {:error, :merge_interrupted_query_operation}
      end

    {:stop, :normal, result, state}
  end
end
