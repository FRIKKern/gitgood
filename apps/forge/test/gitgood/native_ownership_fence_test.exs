defmodule Gitgood.NativeOwnershipFenceTest do
  use ExUnit.Case, async: false
  @moduletag capture_log: true
  alias Gitgood.NativeOwnershipFence, as: Fence

  setup do
    Process.flag(:trap_exit, true)
    :ok
  end

  defmodule Original do
    use GenServer
    def start_link(observer), do: GenServer.start_link(__MODULE__, observer)

    def init(observer) do
      send(observer, {:original_started, self()})
      {:ok, observer}
    end
  end

  defp blocked_owner do
    observer = self()

    {owner, reference} =
      spawn_monitor(fn ->
        {:ok, monitor} = Original.start_link(observer)
        {:ok, lease} = Original.start_link(observer)
        {:ok, fence} = Fence.start_link(monitor, lease)
        :ok = Fence.current(fence)
        send(observer, {:blocked_startup, self(), monitor, lease, fence})
        # The owner cannot process helper-down messages during synchronous claim.
        receive do
          :finish -> :ok
        after
          5_000 -> exit(:fixture_wait_expired)
        end
      end)

    assert_receive {:blocked_startup, ^owner, monitor, lease, fence}, 1_000
    assert_receive {:original_started, ^monitor}
    assert_receive {:original_started, ^lease}
    originals = %{monitor: monitor, lease: lease, fence: fence}
    references = Map.new(originals, fn {name, pid} -> {name, Process.monitor(pid)} end)
    on_exit(fn -> if Process.alive?(owner), do: Process.exit(owner, :kill) end)
    {owner, reference, originals, references}
  end

  for helper <- [:monitor, :lease] do
    test "normal #{helper} exit aborts blocked owner and remaining originals without restart" do
      {owner, reference, originals, references} = blocked_owner()
      GenServer.stop(originals[unquote(helper)], :normal)
      assert_receive {:DOWN, ^reference, :process, ^owner, :native_ownership_helpers_lost}, 1_000

      Enum.each(originals, fn {name, pid} ->
        ref = references[name]
        assert_receive {:DOWN, ^ref, :process, ^pid, _}, 1_000
        refute Process.alive?(pid)
      end)

      refute_receive {:original_started, _}, 50
    end

    test "killed #{helper} aborts blocked owner and all original helpers" do
      {owner, reference, originals, references} = blocked_owner()
      Process.exit(originals[unquote(helper)], :kill)
      assert_receive {:DOWN, ^reference, :process, ^owner, _}, 1_000

      Enum.each(originals, fn {name, pid} ->
        ref = references[name]
        assert_receive {:DOWN, ^ref, :process, ^pid, _}, 1_000
      end)

      refute_receive {:original_started, _}, 50
    end
  end

  test "dead, aliased, caller and malformed helpers refuse without disturbing a live original" do
    {:ok, live} = Original.start_link(self())
    assert_receive {:original_started, ^live}
    dead = spawn(fn -> :ok end)
    reference = Process.monitor(dead)
    assert_receive {:DOWN, ^reference, :process, ^dead, _}

    for {monitor, lease} <- [
          {live, live},
          {self(), live},
          {dead, live},
          {nil, live},
          {live, :named_helper}
        ] do
      assert {:error, :native_ownership_helpers_unavailable} = Fence.start_link(monitor, lease)
      assert Process.alive?(live)
    end

    GenServer.stop(live, :normal)
  end

  test "owner failure ends the original fence and helpers" do
    {owner, reference, originals, references} = blocked_owner()
    Process.exit(owner, :kill)
    assert_receive {:DOWN, ^reference, :process, ^owner, :killed}, 1_000

    Enum.each(originals, fn {name, pid} ->
      ref = references[name]
      assert_receive {:DOWN, ^ref, :process, ^pid, _}, 1_000
    end)

    refute_receive {:original_started, _}, 50
  end
end
