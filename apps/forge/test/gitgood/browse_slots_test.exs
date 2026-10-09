defmodule Gitgood.BrowseSlotsTest do
  use ExUnit.Case, async: false
  alias Gitgood.BrowseSlots

  setup do
    gate = start_supervised!({BrowseSlots, name: nil, capacity: 1, waiting: 2, deadline: 1000})
    tasks = start_supervised!({Task.Supervisor, name: nil})
    %{gate: gate, tasks: tasks}
  end

  defp counts(gate, expected, deadline \\ nil) do
    deadline = deadline || System.monotonic_time(:millisecond) + 1000
    actual = GenServer.call(gate, :counts)

    if actual == expected do
      :ok
    else
      assert System.monotonic_time(:millisecond) < deadline, inspect(actual)

      receive do
      after
        1 -> counts(gate, expected, deadline)
      end
    end
  end

  defp hold(ctx, label) do
    owner = self()

    Task.Supervisor.async_nolink(ctx.tasks, fn ->
      BrowseSlots.with_slot(
        fn ->
          send(owner, {:running, label, self()})

          receive do
            :finish -> {:done, label}
          end
        end,
        ctx.gate
      )
    end)
  end

  test "FIFO admission refuses excess callers and preserves the active limit", ctx do
    first = hold(ctx, :first)
    assert_receive {:running, :first, first_pid}
    second = hold(ctx, :second)
    counts(ctx.gate, %{active: 1, waiting: 1})
    third = hold(ctx, :third)
    counts(ctx.gate, %{active: 1, waiting: 2})

    assert {:error, :browse_busy_retry} =
             BrowseSlots.with_slot(fn -> flunk("overflow ran") end, ctx.gate)

    send(first_pid, :finish)
    assert {:done, :first} = Task.await(first)
    assert_receive {:running, :second, second_pid}
    counts(ctx.gate, %{active: 1, waiting: 1})
    refute_received {:running, :third, _}
    send(second_pid, :finish)
    assert {:done, :second} = Task.await(second)
    assert_receive {:running, :third, third_pid}
    send(third_pid, :finish)
    assert {:done, :third} = Task.await(third)
    counts(ctx.gate, %{active: 0, waiting: 0})
  end

  test "cancelled waiting and active callers return capacity without running abandoned work",
       ctx do
    first = hold(ctx, :first)
    assert_receive {:running, :first, first_pid}
    abandoned = hold(ctx, :abandoned)
    counts(ctx.gate, %{active: 1, waiting: 1})
    Process.exit(abandoned.pid, :kill)
    assert {:exit, :killed} = Task.yield(abandoned, 1000)
    counts(ctx.gate, %{active: 1, waiting: 0})
    next = hold(ctx, :next)
    counts(ctx.gate, %{active: 1, waiting: 1})
    Process.exit(first_pid, :kill)
    assert {:exit, :killed} = Task.yield(first, 1000)
    assert_receive {:running, :next, next_pid}
    refute_received {:running, :abandoned, _}
    send(next_pid, :finish)
    assert {:done, :next} = Task.await(next)
    counts(ctx.gate, %{active: 0, waiting: 0})
  end

  test "the admission deadline removes the request and never starts it later", ctx do
    gate =
      start_supervised!({BrowseSlots, name: nil, capacity: 1, waiting: 1, deadline: 100},
        id: :short_gate
      )

    short = %{ctx | gate: gate}
    first = hold(short, :first)
    assert_receive {:running, :first, first_pid}
    expired = hold(short, :expired)
    counts(gate, %{active: 1, waiting: 1})
    assert {:error, :browse_busy_retry} = Task.await(expired, 1000)
    counts(gate, %{active: 1, waiting: 0})
    send(first_pid, :finish)
    assert {:done, :first} = Task.await(first)
    counts(gate, %{active: 0, waiting: 0})
    refute_received {:running, :expired, _}
    assert :available = BrowseSlots.with_slot(fn -> :available end, gate)
  end

  test "only the holder releases a lease; exceptional reads also release", ctx do
    {:ok, reference} = GenServer.call(ctx.gate, :acquire)

    other =
      Task.Supervisor.async_nolink(ctx.tasks, fn ->
        GenServer.call(ctx.gate, {:release, reference})
      end)

    assert {:error, :not_owner} = Task.await(other)
    counts(ctx.gate, %{active: 1, waiting: 0})
    assert :ok = GenServer.call(ctx.gate, {:release, reference})

    assert_raise RuntimeError, "read failed", fn ->
      BrowseSlots.with_slot(fn -> raise "read failed" end, ctx.gate)
    end

    counts(ctx.gate, %{active: 0, waiting: 0})
  end

  test "delayed admission processing cannot start work past its absolute deadline", ctx do
    gate =
      start_supervised!({BrowseSlots, name: nil, capacity: 1, waiting: 1, deadline: 150},
        id: :delayed_gate
      )

    short = %{ctx | gate: gate}
    first = hold(short, :first)
    assert_receive {:running, :first, first_pid}
    expired = hold(short, :expired)
    counts(gate, %{active: 1, waiting: 1})
    :sys.suspend(gate)
    on_exit(fn -> if Process.alive?(gate), do: :sys.resume(gate) end)
    send(first_pid, :finish)
    Process.send_after(self(), :resume_gate, 250)
    assert_receive :resume_gate, 1000
    :sys.resume(gate)
    assert {:done, :first} = Task.await(first)
    assert {:error, :browse_busy_retry} = Task.await(expired)
    counts(gate, %{active: 0, waiting: 0})
    refute_received {:running, :expired, _}
  end
end
