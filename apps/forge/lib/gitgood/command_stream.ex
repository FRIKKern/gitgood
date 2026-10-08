defmodule Gitgood.CommandStream do
  def run(args, receiver, opts \\ []) do
    config = %{
      args: args,
      env: Gitgood.Command.environment(Keyword.get(opts, :env, [])),
      timeout_ms: Keyword.get(opts, :timeout, 60_000),
      output_limit: Keyword.get(opts, :limit, 33_554_432)
    }

    case DynamicSupervisor.start_child(
           Gitgood.Commands,
           {Gitgood.CommandStreamWorker, {self(), receiver, config}}
         ) do
      {:ok, worker} ->
        try do
          GenServer.call(worker, :await, :infinity)
        catch
          :exit, _ -> {:error, :process_interrupted}
        end

      {:error, :max_children} ->
        {:error, :busy}

      _ ->
        {:error, :process_failed}
    end
  end

  def input(worker, data), do: call(worker, {:input, data})
  def eof(worker), do: call(worker, :eof)

  defp call(worker, request) do
    GenServer.call(worker, request, 5000)
  catch
    :exit, _ -> {:error, :process_interrupted}
  end
end
