defmodule Gitgood.NativeOwnershipClaimTest do
  use ExUnit.Case, async: true
  alias Gitgood.NativeOwnershipClaim, as: Claim

  # These are process-protocol stand-ins for the original monitor and lease.
  # They establish ordering/refusal, never installed publication or live authority.
  defmodule Captured do
    use GenServer
    def start_link(options), do: GenServer.start_link(__MODULE__, options)
    def init(options), do: {:ok, options}

    def handle_call(request, _, state) do
      send(state[:owner], {:observed_request, state[:label], request})
      {:reply, Map.fetch!(state[:replies], request), state}
    end
  end

  defp captured(label, replies) do
    start_supervised!(
      Supervisor.child_spec(
        {Captured, owner: self(), label: label, replies: replies},
        id: label
      )
    )
  end

  test "an unavailable original monitor never queries the held lease" do
    monitor = captured(:monitor, %{ownership_context: {:error, :installation_generation_lost}})
    lease = captured(:lease, %{})

    assert {:error, :native_ownership_claim_unavailable} =
             Claim.claim(monitor, lease, %{}, :runtime)

    assert_received {:observed_request, :monitor, :ownership_context}
    refute_received {:observed_request, :lease, _}
  end

  test "a lost original session refuses without recapture or retry" do
    monitor = captured(:monitor, %{ownership_context: {:ok, %{}}})
    lease = captured(:lease, %{snapshot: {:error, :native_database_lease_lost}})

    assert {:error, :native_ownership_claim_unavailable} =
             Claim.claim(monitor, lease, %{}, :runtime)

    assert_received {:observed_request, :monitor, :ownership_context}
    assert_received {:observed_request, :lease, :snapshot}
    refute_received {:observed_request, _, _}
  end

  test "dead, nonprocess, aliased and unsupported-mode inputs query neither helper" do
    monitor = captured(:monitor, %{})
    lease = captured(:lease, %{})
    {dead, reference} = spawn_monitor(fn -> :ok end)
    assert_receive {:DOWN, ^reference, :process, ^dead, :normal}

    for {selected_monitor, selected_lease, mode} <- [
          {monitor, dead, :runtime},
          {dead, lease, :runtime},
          {monitor, lease, :other},
          {monitor, monitor, :runtime},
          {:monitor_name, lease, :runtime},
          {monitor, nil, :runtime}
        ] do
      assert {:error, :native_ownership_claim_unavailable} =
               Claim.claim(selected_monitor, selected_lease, %{}, mode)
    end

    refute_received {:observed_request, _, _}
  end

  test "invalid captured values never attach ownership or check a replacement helper" do
    monitor = captured(:monitor, %{ownership_context: {:ok, %{admission: %{}, guard: %{}}}})
    lease = captured(:lease, %{snapshot: {:ok, %{}}})

    assert {:error, :native_ownership_claim_unavailable} =
             Claim.claim(monitor, lease, %{}, :runtime)

    assert_received {:observed_request, :monitor, :ownership_context}
    assert_received {:observed_request, :lease, :snapshot}
    refute_received {:observed_request, _, _}
  end
end
