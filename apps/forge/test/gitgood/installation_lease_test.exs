defmodule Gitgood.InstallationLeaseTest do
  use ExUnit.Case, async: false
  alias Gitgood.InstallationLease

  test "an incomplete restore refuses runtime and backup even with no live owner", %{root: root} do
    File.write!(Path.join(root, ".gitgood-restore-incomplete-v1.json"), "{}")
    assert start(root) == {:error, :installation_restore_incomplete}
    assert start(root, :backup) == {:error, :installation_restore_incomplete}
    assert start(root, :migrate) == {:error, :installation_restore_incomplete}
  end

  setup do
    Process.flag(:trap_exit, true)
    root = Path.join(System.tmp_dir!(), "gitgood-lease-" <> Ecto.UUID.generate())
    File.mkdir_p!(root)
    on_exit(fn -> File.rm_rf!(root) end)
    %{root: root}
  end

  defp start(root, mode \\ :runtime) do
    InstallationLease.start_link(root: root, mode: mode, name: nil)
  end

  test "the ordinary database lease excludes another runtime and offline maintenance", %{
    root: root
  } do
    {:ok, owner} = start(root)
    assert InstallationLease.assert_held(owner) == :ok
    assert start(root) == {:error, :installation_busy}
    assert start(root, :backup) == {:error, :installation_busy}
    assert start(root, :migrate) == {:error, :installation_busy}
    GenServer.stop(owner, :normal)
    # The OS owner is still alive even though the database lease was released.
    assert start(root, :backup) == {:error, :installation_process_present}
    assert start(root) == {:error, :installation_process_present}
  end

  test "backup requires the current protocol and refuses foreign or malformed process records", %{
    root: root
  } do
    assert start(root, :backup) == {:error, :installation_protocol_unestablished}
    marker = Path.join(root, ".gitgood-runtime-v1.json")

    File.write!(
      marker,
      Jason.encode!(%{protocol: 1, host: "foreign-host.invalid", owners: [2_000_000_000]})
    )

    assert start(root, :backup) == {:error, :installation_marker_invalid}
    File.write!(marker, "not-json")
    assert start(root, :backup) == {:error, :installation_marker_invalid}
  end

  test "lost lock ownership terminates the guard and retains the live process refusal", %{
    root: root
  } do
    {:ok, owner} = start(root)
    Process.unlink(owner)
    monitor = Process.monitor(owner)
    state = :sys.get_state(owner)

    assert %{rows: [[true]]} =
             Postgrex.query!(state.connection, "SELECT pg_advisory_unlock($1::int, $2::int)", [
               1_197_034_575,
               1
             ])

    assert_receive {:DOWN, ^monitor, :process, ^owner, :installation_lease_lost}, 5000
    assert start(root, :backup) == {:error, :installation_process_present}
  end

  test "a stopped previous owner permits one maintenance operation, which excludes a new runtime",
       %{root: root} do
    {:ok, host} = :inet.gethostname()

    File.write!(
      Path.join(root, ".gitgood-runtime-v1.json"),
      Jason.encode!(%{protocol: 1, host: to_string(host), owners: [2_000_000_000]})
    )

    {:ok, maintenance} = start(root, :backup)
    assert InstallationLease.assert_held(maintenance) == :ok
    assert start(root) == {:error, :installation_busy}
    GenServer.stop(maintenance, :normal)
    assert start(root) == {:error, :installation_process_present}
  end
end
