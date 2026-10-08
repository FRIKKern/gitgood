defmodule Gitgood.CommandTest do
  use ExUnit.Case, async: false
  alias Gitgood.Command

  defp python,
    do: Application.fetch_env!(:gitgood, :python_executable) |> System.find_executable()

  test "stdin receives real EOF; output remains byte-exact and credentials are not inherited" do
    System.put_env("GITGOOD_TEST_SECRET", "must-not-be-inherited")
    on_exit(fn -> System.delete_env("GITGOOD_TEST_SECRET") end)

    code =
      "import os,sys; data=sys.stdin.buffer.read(); sys.stdout.buffer.write(data); assert 'GITGOOD_TEST_SECRET' not in os.environ"

    assert {:ok, <<0, 255, 10>>, 0} = Command.run([python(), "-c", code], input: <<0, 255, 10>>)
  end

  test "output and input are bounded" do
    assert {:error, "output_limit"} =
             Command.run([python(), "-c", "import sys; sys.stdout.write('x'*10000)"], limit: 100)

    assert {:error, :input_limit} =
             Command.run([python(), "-c", "pass"], input: :binary.copy("x", 33_554_433))
  end

  test "timeout kills child and grandchild; caller cancellation also closes descendant connections" do
    for mode <- [:timeout, :cancel] do
      {:ok, listener} = :gen_tcp.listen(0, [:binary, active: false, ip: {127, 0, 0, 1}])
      {:ok, {_, port}} = :inet.sockname(listener)
      supervisor = start_supervised!({Task.Supervisor, name: nil}, id: {:tasks, mode})

      child =
        "import socket,threading; s=socket.create_connection(('127.0.0.1',#{port})); s.sendall(b'child'); threading.Event().wait()"

      root =
        "import subprocess,sys,threading; subprocess.Popen([sys.executable,'-c',#{inspect(child)}]); threading.Event().wait()"

      task =
        Task.Supervisor.async_nolink(supervisor, fn ->
          Command.run([python(), "-c", root],
            timeout: if(mode == :timeout, do: 1500, else: 15000)
          )
        end)

      {:ok, socket} = :gen_tcp.accept(listener, 5000)
      assert {:ok, "child"} = :gen_tcp.recv(socket, 5, 5000)
      if mode == :cancel, do: Process.exit(task.pid, :kill)
      assert {:error, :closed} = :gen_tcp.recv(socket, 1, 5000)
      if mode == :timeout, do: assert(Task.await(task, 7000) == {:error, "timeout"})
      :gen_tcp.close(socket)
      :gen_tcp.close(listener)
    end
  end

  test "at most four command processes run concurrently" do
    {:ok, listener} = :gen_tcp.listen(0, [:binary, active: false, ip: {127, 0, 0, 1}])
    {:ok, {_, port}} = :inet.sockname(listener)
    supervisor = start_supervised!({Task.Supervisor, name: nil})

    code =
      "import socket; s=socket.create_connection(('127.0.0.1',#{port})); s.sendall(b'ready'); s.recv(1)"

    tasks =
      for _ <- 1..4,
          do:
            Task.Supervisor.async_nolink(supervisor, fn ->
              Command.run([python(), "-c", code], timeout: 15000)
            end)

    sockets =
      for _ <- 1..4 do
        {:ok, socket} = :gen_tcp.accept(listener, 5000)
        assert {:ok, "ready"} = :gen_tcp.recv(socket, 5, 5000)
        socket
      end

    assert {:error, :busy} = Command.run([python(), "-c", "pass"])
    Enum.each(sockets, &:gen_tcp.close/1)
    for task <- tasks, do: assert(Task.await(task, 5000) == {:ok, "", 0})
    :gen_tcp.close(listener)
  end

  test "each child has a memory ceiling" do
    assert {:ok, _, status} = Command.run([python(), "-c", "data=bytearray(700*1024*1024)"])
    assert status != 0
  end
end
