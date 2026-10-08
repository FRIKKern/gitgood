defmodule Gitgood.SSHChannel do
  @behaviour :ssh_server_channel
  @impl true
  def init(_),
    do:
      {:ok,
       %{
         connection: nil,
         channel: nil,
         job: nil,
         job_monitor: nil,
         stream: nil,
         stream_finished: false,
         pending_result: nil,
         pending: [],
         pending_bytes: 0,
         input_bytes: 0,
         eof: false,
         protocol: "",
         done: false
       }}

  @impl true
  def handle_msg({:ssh_channel_up, channel, connection}, state) do
    Process.send_after(self(), :deadline, 90_000)
    {:ok, %{state | channel: channel, connection: connection}}
  end

  def handle_msg({:gitgood_stream_started, worker}, %{stream: nil} = state) do
    result =
      Enum.reduce_while(Enum.reverse(state.pending), :ok, fn data, _ ->
        case input(worker, data) do
          :ok -> {:cont, :ok}
          error -> {:halt, error}
        end
      end)

    state = %{state | stream: worker, pending: [], pending_bytes: 0}

    if result == :ok and (not state.eof or Gitgood.CommandStream.eof(worker) == :ok),
      do: {:ok, state},
      else: denied(state)
  end

  def handle_msg({:gitgood_stream_data, worker, type, data}, %{stream: worker} = state) do
    case :ssh_connection.send(state.connection, state.channel, type, data, 5000) do
      :ok -> {:ok, state}
      _ -> finish(state, 1)
    end
  end

  def handle_msg({:gitgood_ssh_result, job, {:ok, status}}, %{job: job} = state),
    do:
      if(state.stream_finished,
        do: finish(state, status),
        else: {:ok, %{state | pending_result: status}}
      )

  def handle_msg({:gitgood_stream_finished, worker}, %{stream: worker} = state) do
    state = %{state | stream_finished: true}
    if is_nil(state.pending_result), do: {:ok, state}, else: finish(state, state.pending_result)
  end

  def handle_msg({:gitgood_ssh_result, job, _}, %{job: job} = state), do: denied(state)

  def handle_msg({:DOWN, monitor, :process, _, :normal}, %{job_monitor: monitor} = state),
    do: {:ok, state}

  def handle_msg({:DOWN, monitor, :process, _, _}, %{job_monitor: monitor} = state),
    do: denied(state)

  def handle_msg(:deadline, state), do: denied(state)
  def handle_msg(_, state), do: {:ok, state}
  @impl true
  def handle_ssh_msg(
        {:ssh_cm, connection, {:exec, channel, want_reply, command}},
        %{job: nil} = state
      ) do
    state = %{state | connection: connection, channel: channel}

    case Gitgood.SSHTransport.parse(command) do
      {:ok, _, _, _} ->
        receiver = self()

        {:ok, job} =
          Task.Supervisor.start_child(Gitgood.SSHJobs, fn ->
            Gitgood.SSHTransport.serve(connection, receiver, command, state.protocol)
          end)

        :ssh_connection.reply_request(connection, want_reply, :success, channel)
        {:ok, %{state | job: job, job_monitor: Process.monitor(job)}}

      _ ->
        :ssh_connection.reply_request(connection, want_reply, :failure, channel)
        denied(state)
    end
  end

  def handle_ssh_msg(
        {:ssh_cm, connection, {:env, channel, want_reply, name, value}},
        %{job: nil} = state
      ) do
    allowed = to_string(name) == "GIT_PROTOCOL" and to_string(value) in ["version=1", "version=2"]

    :ssh_connection.reply_request(
      connection,
      want_reply,
      if(allowed, do: :success, else: :failure),
      channel
    )

    {:ok, %{state | protocol: if(allowed, do: to_string(value), else: state.protocol)}}
  end

  def handle_ssh_msg({:ssh_cm, _, {:data, _, 0, data}}, %{eof: false} = state) do
    bytes = state.input_bytes + byte_size(data)

    cond do
      bytes > 33_554_432 ->
        denied(state)

      state.stream ->
        if input(state.stream, data) == :ok,
          do: {:ok, %{state | input_bytes: bytes}},
          else: denied(state)

      state.pending_bytes + byte_size(data) <= 1_048_576 ->
        {:ok,
         %{
           state
           | pending: [data | state.pending],
             pending_bytes: state.pending_bytes + byte_size(data),
             input_bytes: bytes
         }}

      true ->
        denied(state)
    end
  end

  def handle_ssh_msg({:ssh_cm, _, {:eof, _}}, state) do
    if is_nil(state.stream) or state.eof or Gitgood.CommandStream.eof(state.stream) == :ok,
      do: {:ok, %{state | eof: true}},
      else: denied(state)
  end

  def handle_ssh_msg({:ssh_cm, connection, {:shell, channel, want_reply}}, state) do
    :ssh_connection.reply_request(connection, want_reply, :failure, channel)
    denied(%{state | connection: connection, channel: channel})
  end

  def handle_ssh_msg({:ssh_cm, connection, {:pty, channel, want_reply, _}}, state) do
    :ssh_connection.reply_request(connection, want_reply, :failure, channel)
    {:ok, state}
  end

  def handle_ssh_msg({:ssh_cm, _, {:signal, _, _}}, state), do: {:ok, state}

  def handle_ssh_msg({:ssh_cm, connection, {:exec, channel, want_reply, _}}, state) do
    :ssh_connection.reply_request(connection, want_reply, :failure, channel)
    {:ok, state}
  end

  def handle_ssh_msg({:ssh_cm, connection, {:env, channel, want_reply, _, _}}, state) do
    :ssh_connection.reply_request(connection, want_reply, :failure, channel)
    {:ok, state}
  end

  def handle_ssh_msg(_, state), do: {:ok, state}

  defp input(worker, data) when byte_size(data) > 65536 do
    <<head::binary-size(65536), rest::binary>> = data

    case Gitgood.CommandStream.input(worker, head) do
      :ok -> input(worker, rest)
      error -> error
    end
  end

  defp input(worker, data), do: Gitgood.CommandStream.input(worker, data)

  defp denied(state) do
    :ssh_connection.send(
      state.connection,
      state.channel,
      1,
      "Gitgood: command, identity or repository unavailable.\n",
      5000
    )

    finish(state, 1)
  end

  defp finish(state, status) do
    status = if status in 0..255, do: status, else: 1
    :ssh_connection.exit_status(state.connection, state.channel, status)
    :ssh_connection.send_eof(state.connection, state.channel)
    {:stop, state.channel, %{state | done: true}}
  end

  @impl true
  def terminate(_, _), do: :ok
end
