defmodule Gitgood.CommandWorker do
  use GenServer, restart: :temporary
  def start_link(config), do: GenServer.start_link(__MODULE__, config)

  def init({caller, config, input}) do
    Process.flag(:trap_exit, true)

    {:ok,
     %{
       caller: caller,
       monitor: Process.monitor(caller),
       config: config,
       input: input,
       port: nil,
       from: nil,
       bytes: 0,
       chunks: []
     }}
  end

  def handle_call(:run, {caller, _} = from, %{caller: caller, port: nil} = state) do
    python = Application.fetch_env!(:gitgood, :python_executable) |> System.find_executable()
    adapter = Application.app_dir(:gitgood, "priv/git_worker.py")
    env = for {key, _} <- System.get_env(), do: {String.to_charlist(key), false}

    keep =
      for {key, value} <- state.config.env,
          do: {String.to_charlist(key), String.to_charlist(value)}

    port =
      Port.open({:spawn_executable, python}, [
        :binary,
        :exit_status,
        :use_stdio,
        :hide,
        {:args, ["-I", adapter]},
        {:env, env ++ keep}
      ])

    Port.command(port, [Jason.encode!(state.config), "\n", state.input])
    Process.send_after(self(), :deadline, state.config.timeout_ms + 5000)
    {:noreply, %{state | port: port, from: from, input: ""}}
  rescue
    _ -> {:stop, :normal, {:error, :process_failed}, state}
  end

  def handle_info({port, {:data, data}}, %{port: port} = state) do
    bytes = state.bytes + byte_size(data)

    if bytes <= state.config.output_limit + 1024 do
      {:noreply, %{state | bytes: bytes, chunks: [data | state.chunks]}}
    else
      finish(state, {:error, :output_limit})
    end
  end

  def handle_info({port, {:exit_status, _}}, %{port: port} = state) do
    output = state.chunks |> Enum.reverse() |> IO.iodata_to_binary()

    result =
      case :binary.split(output, "\n") do
        [header, body] ->
          case Jason.decode(header) do
            {:ok, %{"error" => nil, "status" => status}} ->
              {:ok, body, status}

            {:ok, %{"error" => error}}
            when error in ["timeout", "output_limit", "caller_interrupted"] ->
              {:error, error}

            _ ->
              {:error, :process_failed}
          end

        _ ->
          {:error, :process_failed}
      end

    finish(%{state | port: nil}, result)
  end

  def handle_info({:DOWN, monitor, :process, _, _}, %{monitor: monitor} = state),
    do: {:stop, :normal, state}

  def handle_info(:deadline, state), do: finish(state, {:error, :timeout})
  def handle_info({:EXIT, _, _}, state), do: {:noreply, state}

  defp finish(state, result) do
    if state.from, do: GenServer.reply(state.from, result)
    {:stop, :normal, state}
  end

  def terminate(_, %{port: port}) when is_port(port) do
    # Closing the adapter's input triggers group/job cancellation; the adapter owns child cleanup.
    if Port.info(port), do: Port.close(port)
    :ok
  end

  def terminate(_, _), do: :ok
end
