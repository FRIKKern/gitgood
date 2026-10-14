defmodule Gitgood.NativeRuntimeWorkerTest do
  use ExUnit.Case, async: true
  alias Gitgood.NativeMigrationInventory, as: Inventory

  defp build,
    do: %{"candidate" => String.duplicate("b", 40), "dirty" => false, "migrations" => ["1", "2"]}

  test "runtime inventory requires clean candidate, bounded positive versions and exact package" do
    assert {:ok, [1, 2]} = Inventory.match_build(build(), [1, 2])

    for declaration <- [
          [],
          ["0"],
          ["9223372036854775808"],
          ["2", "1"],
          ["1", "1"],
          [1, 2],
          List.duplicate("1", 1025)
        ] do
      assert :error = Inventory.match_build(Map.put(build(), "migrations", declaration), [1, 2])
    end

    for package <- [[], [1], [1, 2, 3], [2, 1]] do
      assert :error = Inventory.match_build(build(), package)
    end

    assert :error = Inventory.match_build(Map.put(build(), "candidate", "unconfigured"), [1, 2])
    assert :error = Inventory.match_build(Map.put(build(), "dirty", true), [1, 2])
  end

  test "activation cannot replay while running or after starting product workers" do
    for status <- [:running, :active] do
      state = %{status: status}

      assert {:stop, :native_runtime_unavailable, {:error, :native_runtime_unavailable}, ^state} =
               Gitgood.NativeRuntimeWorker.handle_call(:activate, {self(), make_ref()}, state)
    end
  end

  test "runtime coordinator status redacts messages, reasons and debug logs" do
    private = "synthetic-runtime-status-secret"
    status = %{state: %{private: private}, message: private, reason: private, log: [private]}
    redacted = Gitgood.NativeRuntimeWorker.format_status(status)
    assert Map.keys(redacted) == Map.keys(status)
    refute inspect(redacted) =~ private
    assert redacted.log == []
  end
end
