defmodule Gitgood.CommandStreamTest do
  use ExUnit.Case, async: false
  alias Gitgood.{CommandStream, SSHChannel}

  defp python,
    do: Application.fetch_env!(:gitgood, :python_executable) |> System.find_executable()

  test "full duplex is byte exact, clears inherited secrets and delivers EOF without closing SSH" do
    System.put_env("GITGOOD_TEST_SECRET", "must-not-be-inherited")
    on_exit(fn -> System.delete_env("GITGOOD_TEST_SECRET") end)
    receiver = self()
    supervisor = start_supervised!({Task.Supervisor, name: nil})

    code =
      "import os,sys; assert 'GITGOOD_TEST_SECRET' not in os.environ; sys.stdout.buffer.write(b'ready'); sys.stdout.buffer.flush(); data=sys.stdin.buffer.read(); sys.stdout.buffer.write(data)"

    task =
      Task.Supervisor.async_nolink(supervisor, fn ->
        CommandStream.run([python(), "-c", code], receiver)
      end)

    assert_receive {:gitgood_stream_started, worker}, 5000
    assert_receive {:gitgood_stream_data, ^worker, 0, "ready"}, 5000
    assert :ok = CommandStream.input(worker, <<0, 255, 10>>)
    {:ok, state} = SSHChannel.init([])

    {:ok, state} =
      SSHChannel.handle_ssh_msg({:ssh_cm, self(), {:eof, 0}}, %{state | stream: worker})

    assert state.eof
    assert {:ok, ^state} = SSHChannel.handle_ssh_msg({:ssh_cm, self(), {:eof, 0}}, state)
    assert_receive {:gitgood_stream_data, ^worker, 0, <<0, 255, 10>>}, 5000
    assert Task.await(task, 5000) == {:ok, 0}
  end

  test "input, output, runtime and memory are bounded" do
    receiver = self()
    supervisor = start_supervised!({Task.Supervisor, name: nil})

    task =
      Task.Supervisor.async_nolink(supervisor, fn ->
        CommandStream.run([python(), "-c", "import sys; sys.stdout.write('x'*10000)"], receiver,
          limit: 100
        )
      end)

    assert Task.await(task, 5000) == {:error, "output_limit"}

    task =
      Task.Supervisor.async_nolink(supervisor, fn ->
        CommandStream.run([python(), "-c", "import sys; sys.stdin.buffer.read()"], receiver)
      end)

    assert_receive {:gitgood_stream_started, _finished_worker}, 5000
    assert_receive {:gitgood_stream_started, worker}, 5000
    assert {:error, :input_limit} = CommandStream.input(worker, :binary.copy("x", 65537))
    assert Task.await(task, 5000) == {:error, :input_limit}

    assert {:ok, status} =
             CommandStream.run([python(), "-c", "data=bytearray(700*1024*1024)"], receiver)

    assert status != 0
  end

  test "timeout, receiver and owner cancellation close descendant sockets" do
    for mode <- [:timeout, :cancel, :owner] do
      {:ok, listener} = :gen_tcp.listen(0, [:binary, active: false, ip: {127, 0, 0, 1}])
      {:ok, {_, port}} = :inet.sockname(listener)
      supervisor = start_supervised!({Task.Supervisor, name: nil}, id: {:tasks, mode})

      {:ok, receiver} =
        Task.Supervisor.start_child(supervisor, fn ->
          receive do
            :stop -> :ok
          end
        end)

      child =
        "import socket,threading; s=socket.create_connection(('127.0.0.1',#{port})); s.sendall(b'child'); threading.Event().wait()"

      root =
        "import subprocess,sys,threading; subprocess.Popen([sys.executable,'-c',#{inspect(child)}]); threading.Event().wait()"

      task =
        Task.Supervisor.async_nolink(supervisor, fn ->
          CommandStream.run([python(), "-c", root], receiver,
            timeout: if(mode == :timeout, do: 1500, else: 15000)
          )
        end)

      {:ok, socket} = :gen_tcp.accept(listener, 5000)
      assert {:ok, "child"} = :gen_tcp.recv(socket, 5, 5000)
      if mode == :cancel, do: Process.exit(receiver, :kill)
      if mode == :owner, do: Process.exit(task.pid, :kill)
      assert {:error, :closed} = :gen_tcp.recv(socket, 1, 5000)

      if mode == :owner do
        ref = task.ref
        pid = task.pid
        assert_receive {:DOWN, ^ref, :process, ^pid, :killed}, 5000
      else
        assert Task.await(task, 7000) ==
                 if(mode == :timeout,
                   do: {:error, "timeout"},
                   else: {:error, :caller_interrupted}
                 )
      end

      Process.exit(receiver, :kill)
      :gen_tcp.close(socket)
      :gen_tcp.close(listener)
    end
  end

  test "complete EOF survives receiver loss while the independent owner collects its outcome" do
    {:ok, listener} = :gen_tcp.listen(0, [:binary, active: false, ip: {127, 0, 0, 1}])
    {:ok, {_, port}} = :inet.sockname(listener)
    supervisor = start_supervised!({Task.Supervisor, name: nil})
    parent = self()

    {:ok, receiver} =
      Task.Supervisor.start_child(supervisor, fn ->
        receive do
          {:gitgood_stream_started, worker} ->
            :ok = CommandStream.input(worker, "complete")
            :ok = CommandStream.eof(worker)
            send(parent, :accepted_eof)

            receive do
              :stop -> :ok
            end
        end
      end)

    code =
      "import socket,sys; assert sys.stdin.buffer.read()==b'complete'; s=socket.create_connection(('127.0.0.1',#{port})); s.sendall(b'ready'); s.recv(1)"

    task =
      Task.Supervisor.async_nolink(supervisor, fn ->
        CommandStream.run([python(), "-c", code], receiver)
      end)

    assert_receive :accepted_eof, 5000
    {:ok, socket} = :gen_tcp.accept(listener, 5000)
    assert {:ok, "ready"} = :gen_tcp.recv(socket, 5, 5000)
    Process.exit(receiver, :kill)
    :ok = :gen_tcp.send(socket, "finish")
    assert Task.await(task, 5000) == {:ok, 0}
    :gen_tcp.close(socket)
    :gen_tcp.close(listener)
  end

  test "streaming and buffered commands share one four-process ceiling" do
    {:ok, listener} = :gen_tcp.listen(0, [:binary, active: false, ip: {127, 0, 0, 1}])
    {:ok, {_, port}} = :inet.sockname(listener)
    supervisor = start_supervised!({Task.Supervisor, name: nil})
    receiver = self()

    code =
      "import socket; s=socket.create_connection(('127.0.0.1',#{port})); s.sendall(b'ready'); s.recv(1)"

    buffered =
      for _ <- 1..3,
          do:
            Task.Supervisor.async_nolink(supervisor, fn ->
              Gitgood.Command.run([python(), "-c", code])
            end)

    stream =
      Task.Supervisor.async_nolink(supervisor, fn ->
        CommandStream.run([python(), "-c", code], receiver)
      end)

    sockets =
      for _ <- 1..4 do
        {:ok, socket} = :gen_tcp.accept(listener, 5000)
        assert {:ok, "ready"} = :gen_tcp.recv(socket, 5, 5000)
        socket
      end

    assert {:error, :busy} = CommandStream.run([python(), "-c", "pass"], receiver)
    assert {:error, :busy} = Gitgood.Command.run([python(), "-c", "pass"])
    Enum.each(sockets, &:gen_tcp.close/1)
    for task <- buffered, do: assert(Task.await(task, 5000) == {:ok, "", 0})
    assert Task.await(stream, 5000) == {:ok, 0}
    :gen_tcp.close(listener)
  end
end
