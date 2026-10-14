defmodule Gitgood.CommandPortTest do
  use ExUnit.Case, async: true
  alias Gitgood.{CommandPort, CommandStreamWorker, CommandWorker}

  defp adapter(code) do
    python = Application.fetch_env!(:gitgood, :python_executable) |> System.find_executable()

    Port.open({:spawn_executable, python}, [
      :binary,
      :exit_status,
      :use_stdio,
      :hide,
      {:args, ["-I", "-B", "-c", code]}
    ])
  end

  defp ended_adapter do
    port = adapter("pass")
    monitor = Port.monitor(port)
    assert_receive {:DOWN, ^monitor, :port, ^port, _}, 5000
    port
  end

  test "cleanup of an already exited or concurrently closed owned adapter succeeds" do
    port = ended_adapter()
    assert :ok = CommandPort.close(port)

    live = adapter("import sys; sys.stdin.buffer.read()")
    monitor = Port.monitor(live)
    parent = self()

    tasks =
      for _ <- 1..4 do
        Task.async(fn ->
          send(parent, {:close_ready, self()})

          receive do
            :close -> CommandPort.close(live)
          end
        end)
      end

    for _ <- tasks, do: assert_receive({:close_ready, _}, 5000)
    Enum.each(tasks, &send(&1.pid, :close))
    for task <- tasks, do: assert(Task.await(task, 5000) == :ok)
    assert_receive {:DOWN, ^monitor, :port, ^live, _}, 5000
    assert :ok = CommandPort.close(live)
  end

  test "terminal stream result survives an adapter exit before it is collected" do
    port = ended_adapter()
    payload = Jason.encode!(%{status: 0, error: nil})
    state = %{port: port, receiver: self(), from: nil, buffer: "", result: nil}

    assert {:noreply, %{result: {:ok, 0}, port: nil} = finished} =
             CommandStreamWorker.handle_info(
               {port, {:data, <<2, byte_size(payload)::32, payload::binary>>}},
               state
             )

    assert_receive {:gitgood_stream_finished, _}
    owned = Map.put(finished, :owner, self())

    assert {:stop, :normal, {:ok, 0}, ^owned} =
             CommandStreamWorker.handle_call(:await, {self(), :tag}, owned)

    assert :ok = CommandStreamWorker.terminate(:normal, state)
    assert :ok = CommandWorker.terminate(:normal, state)
  end
end
