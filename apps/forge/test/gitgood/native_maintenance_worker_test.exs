defmodule Gitgood.NativeMaintenanceWorkerTest do
  use ExUnit.Case, async: true
  alias Gitgood.NativeMaintenanceWorker, as: Worker

  defp inputs do
    %{
      "candidate" => String.duplicate("b", 40),
      "migrations" => %{"before_versions" => [], "target_versions" => [1, 2]}
    }
  end

  defp build,
    do: %{"candidate" => String.duplicate("b", 40), "dirty" => false, "migrations" => ["1", "2"]}

  test "sealed target must match clean candidate and actual packaged inventory" do
    assert :ok = Worker.validate_inventory(inputs(), build(), [1, 2])

    for actual <- [[], [1], [1, 2, 3], [2, 1], [1, 1]] do
      assert :error = Worker.validate_inventory(inputs(), build(), actual)
    end

    assert :error =
             Worker.validate_inventory(
               put_in(inputs(), ["migrations", "target_versions"], [2]),
               build(),
               [1, 2]
             )

    assert :error =
             Worker.validate_inventory(
               Map.put(inputs(), "candidate", String.duplicate("c", 40)),
               build(),
               [1, 2]
             )

    assert :error = Worker.validate_inventory(inputs(), Map.put(build(), "dirty", true), [1, 2])
  end

  test "malformed duplicate or unordered build declarations cannot select effects" do
    for declaration <- [[], ["2", "1"], ["1", "1"], ["1", "shell"], [1, 2], [true]] do
      assert :error =
               Worker.validate_inventory(inputs(), Map.put(build(), "migrations", declaration), [
                 1,
                 2
               ])
    end
  end

  test "forward execution requires the exact ordered prefix, not only a subset" do
    for before <- [[], [1], [1, 2]] do
      assert :ok =
               Worker.validate_inventory(
                 put_in(inputs(), ["migrations", "before_versions"], before),
                 build(),
                 [1, 2]
               )
    end

    for before <- [[2], [2, 1], [1, 1], [3], nil] do
      assert :error =
               Worker.validate_inventory(
                 put_in(inputs(), ["migrations", "before_versions"], before),
                 build(),
                 [1, 2]
               )
    end
  end

  test "completed or running worker cannot replay an execute request" do
    for status <- [:running, :complete] do
      state = %{status: status, action: :migrate, result: %{private_fixture: true}}

      assert {:stop, :native_maintenance_unavailable, {:error, :native_maintenance_unavailable},
              ^state} = Worker.handle_call(:execute, {self(), make_ref()}, state)
    end
  end

  test "maintenance refuses arbitrary actions before loading product or workers" do
    for action <- [:runtime, :backup, "migrate", %{program: "shell"}, nil] do
      assert {:error, :native_maintenance_unavailable} = Gitgood.NativeMaintenance.start(action)
    end
  end

  test "worker OTP status never serializes business input or exception values" do
    private = "synthetic-maintenance-status-secret"

    status = %{
      state: %{password: private},
      message: {:private, private},
      reason: {:error, private},
      log: [private]
    }

    redacted = Worker.format_status(status)
    assert Map.keys(redacted) == Map.keys(status)
    refute inspect(redacted) =~ private
    assert redacted.log == []
  end
end
