defmodule Gitgood.Command do
  @moduledoc "Bounded process execution under an independent supervisor; sensitive configuration travels through stdin."
  def run(args, opts \\ []) do
    config = %{
      args: args,
      env: environment(Keyword.get(opts, :env, [])),
      input_size: byte_size(Keyword.get(opts, :input, "")),
      timeout_ms: Keyword.get(opts, :timeout, 15_000),
      output_limit: Keyword.get(opts, :limit, 2_097_152)
    }

    if config.input_size > 33_554_432 do
      {:error, :input_limit}
    else
      case DynamicSupervisor.start_child(
             Gitgood.Commands,
             {Gitgood.CommandWorker, {self(), config, Keyword.get(opts, :input, "")}}
           ) do
        {:ok, worker} ->
          monitor = Process.monitor(worker)
          result = GenServer.call(worker, :run, :infinity)

          receive do
            {:DOWN, ^monitor, :process, ^worker, _} -> result
          after
            5000 -> {:error, :process_failed}
          end

        {:error, :max_children} ->
          {:error, :busy}

        _ ->
          {:error, :process_failed}
      end
    end
  end

  def environment(overrides) do
    allowed = ~w(PATH Path SystemRoot SYSTEMROOT WINDIR TEMP TMP TMPDIR LANG LC_ALL)
    base = System.get_env() |> Map.take(allowed)

    Map.merge(base, Map.new(overrides))
    |> Map.put("GIT_CONFIG_NOSYSTEM", "1")
    |> Map.put(
      "GIT_CONFIG_GLOBAL",
      if(match?({:win32, _}, :os.type()), do: "NUL", else: "/dev/null")
    )
    |> Map.put("GIT_TERMINAL_PROMPT", "0")
  end
end
