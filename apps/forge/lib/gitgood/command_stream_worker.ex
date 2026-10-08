defmodule Gitgood.CommandStreamWorker do
  use GenServer, restart: :temporary
  def start_link(args), do: GenServer.start_link(__MODULE__, args)

  def init({owner, receiver, config}) do
    Process.flag(:trap_exit, true)
    python = Application.fetch_env!(:gitgood, :python_executable) |> System.find_executable()
    adapter = Application.app_dir(:gitgood, "priv/git_stream_worker.py")
    removed = for {key, _} <- System.get_env(), do: {String.to_charlist(key), false}

    keep =
      for {key, value} <- config.env, do: {String.to_charlist(key), String.to_charlist(value)}

    port =
      Port.open({:spawn_executable, python}, [
        :binary,
        :exit_status,
        :use_stdio,
        :hide,
        {:args, ["-I", "-B", adapter]},
        {:env, removed ++ keep}
      ])

    # This and all output messages have the same sender, so advertising cannot
    # overtake the receiver's worker binding even when a child starts immediately.
    send(receiver, {:gitgood_stream_started, self()})
    Port.command(port, [Jason.encode!(config), "\n"])
    Process.send_after(self(), :deadline, config.timeout_ms + 5000)

    {:ok,
     %{
       owner: owner,
       receiver: receiver,
       owner_monitor: Process.monitor(owner),
       receiver_monitor: Process.monitor(receiver),
       config: config,
       port: port,
       buffer: "",
       from: nil,
       input_bytes: 0,
       output_bytes: 0,
       stderr_bytes: 0,
       eof: false,
       result: nil
     }}
  end

  def handle_call(:await, {owner, _}, %{owner: owner, result: result} = state)
      when not is_nil(result),
      do: {:stop, :normal, result, state}

  def handle_call(:await, {owner, _} = from, %{owner: owner, from: nil} = state),
    do: {:noreply, %{state | from: from}}

  def handle_call(
        {:input, data},
        {receiver, _},
        %{receiver: receiver, eof: false, port: port} = state
      )
      when is_binary(data) and is_port(port) do
    bytes = state.input_bytes + byte_size(data)

    if byte_size(data) <= 65536 and bytes <= 33_554_432 do
      Port.command(port, [<<0, byte_size(data)::32>>, data])
      {:reply, :ok, %{state | input_bytes: bytes}}
    else
      stop_reply(state, {:error, :input_limit})
    end
  end

  def handle_call(:eof, {receiver, _}, %{receiver: receiver, port: port, eof: false} = state)
      when is_port(port) do
    Port.command(port, <<1, 0::32>>)
    Process.demonitor(state.receiver_monitor, [:flush])
    {:reply, :ok, %{state | eof: true, receiver_monitor: nil}}
  end

  def handle_call(_, _, state), do: {:reply, {:error, :not_owner_or_closed}, state}

  def handle_info({port, {:data, data}}, %{port: port} = state) do
    consume(%{state | buffer: state.buffer <> data})
  end

  def handle_info({port, {:exit_status, _}}, %{port: port, result: nil} = state),
    do: finish(%{state | port: nil}, {:error, :process_failed})

  def handle_info({:DOWN, monitor, :process, _, _}, state)
      when monitor == state.owner_monitor or monitor == state.receiver_monitor,
      do: finish(state, {:error, :caller_interrupted})

  def handle_info(:deadline, state), do: finish(state, {:error, :timeout})
  def handle_info({:EXIT, _, _}, state), do: {:noreply, state}
  def handle_info(_, state), do: {:noreply, state}

  defp consume(%{buffer: <<kind, size::32, rest::binary>>} = state)
       when size <= 65536 and byte_size(rest) >= size do
    <<payload::binary-size(^size), tail::binary>> = rest
    state = %{state | buffer: tail}

    case kind do
      0 ->
        bytes = state.output_bytes + size

        if bytes <= state.config.output_limit do
          send(state.receiver, {:gitgood_stream_data, self(), 0, payload})
          consume(%{state | output_bytes: bytes})
        else
          finish(state, {:error, :output_limit})
        end

      1 ->
        bytes = state.stderr_bytes + size

        if bytes <= 65536 do
          send(state.receiver, {:gitgood_stream_data, self(), 1, payload})
          consume(%{state | stderr_bytes: bytes})
        else
          finish(state, {:error, :output_limit})
        end

      2 ->
        result =
          case Jason.decode(payload) do
            {:ok, %{"status" => status, "error" => nil}} when is_integer(status) ->
              {:ok, status}

            {:ok, %{"error" => error}}
            when error in ["timeout", "input_limit", "output_limit", "caller_interrupted"] ->
              {:error, error}

            _ ->
              {:error, :process_failed}
          end

        finish(state, result)

      _ ->
        finish(state, {:error, :process_failed})
    end
  end

  defp consume(%{buffer: buffer} = state) when byte_size(buffer) <= 65541, do: {:noreply, state}
  defp consume(state), do: finish(state, {:error, :output_limit})

  defp finish(state, result) do
    state = close_port(state)
    send(state.receiver, {:gitgood_stream_finished, self()})

    if state.from do
      GenServer.reply(state.from, result)
      {:stop, :normal, state}
    else
      {:noreply, %{state | result: result}}
    end
  end

  defp stop_reply(state, result) do
    state = close_port(state)
    send(state.receiver, {:gitgood_stream_finished, self()})

    if state.from do
      GenServer.reply(state.from, result)
      {:stop, :normal, result, state}
    else
      # Receiver input can race the owner's await. Preserve the actual outcome
      # until that owner collects it instead of returning a generic process exit.
      {:reply, result, %{state | result: result}}
    end
  end

  defp close_port(%{port: port} = state) when is_port(port) do
    if Port.info(port), do: Port.close(port)
    %{state | port: nil}
  end

  defp close_port(state), do: state

  def terminate(_, %{port: port}) when is_port(port) do
    if Port.info(port), do: Port.close(port)
    :ok
  end

  def terminate(_, _), do: :ok
end
