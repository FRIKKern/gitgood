defmodule Gitgood.NativeOwnershipStartupTest do
  use ExUnit.Case, async: false
  @moduletag capture_log: true
  alias Gitgood.NativeOwnershipStartup, as: Startup

  test "explicit lifecycle options select fixed actions without mode or command overrides" do
    root = "/var/lib/gitgood/installations/00000000-0000-4000-8000-000000000001/storage"

    for action <- [:runtime, :migrate, :bootstrap] do
      assert Startup.validate_lifecycle_options(root: root, action: action) == :ok
    end

    for options <- [
          nil,
          [],
          [root: root],
          [root: root, action: :backup],
          [root: root, action: "migrate"],
          [root: root, action: :migrate, mode: :runtime],
          [root: root, action: :migrate, command: "/tmp/program"],
          [root: root, action: :runtime, controller_handoff: false],
          [root: root, action: :runtime, action: :migrate]
        ] do
      assert Startup.validate_lifecycle_options(options) == :error

      assert Startup.start_lifecycle_link(options) ==
               {:error, :native_ownership_startup_unavailable}
    end
  end

  test "clean compiled candidate must equal the independently read Root candidate" do
    candidate = String.duplicate("a", 40)

    assert :ok =
             Startup.validate_artifact(%{"candidate" => candidate, "dirty" => false}, %{
               "candidate" => candidate
             })

    assert :error =
             Startup.validate_artifact(%{"candidate" => candidate, "dirty" => false}, %{
               "candidate" => String.duplicate("b", 40)
             })
  end

  test "dirty and boolean aliases cannot establish a clean native artifact" do
    candidate = String.duplicate("a", 40)

    Enum.each([true, nil, 0, "false"], fn dirty ->
      assert :error =
               Startup.validate_artifact(%{"candidate" => candidate, "dirty" => dirty}, %{
                 "candidate" => candidate
               })
    end)
  end

  test "unconfigured malformed and unsupported candidate identities refuse" do
    Enum.each(
      [
        nil,
        true,
        "unconfigured",
        String.duplicate("A", 40),
        String.duplicate("a", 39),
        String.duplicate("a", 64),
        "a" <> <<0>>
      ],
      fn candidate ->
        assert :error =
                 Startup.validate_artifact(%{"candidate" => candidate, "dirty" => false}, %{
                   "candidate" => candidate
                 })
      end
    )
  end

  test "missing identities and malformed authority refuse with a constant result" do
    candidate = String.duplicate("a", 40)
    assert :error = Startup.validate_artifact(nil, %{"candidate" => candidate})
    assert :error = Startup.validate_artifact(%{}, %{"candidate" => candidate})
    assert :error = Startup.validate_artifact(%{"candidate" => candidate, "dirty" => false}, nil)
    assert :error = Startup.validate_artifact(%{"candidate" => candidate, "dirty" => false}, %{})
  end

  test "actual compiled build cannot claim a different Root candidate" do
    identity = Gitgood.Build.identity()

    other =
      if identity["candidate"] == String.duplicate("a", 40),
        do: String.duplicate("b", 40),
        else: String.duplicate("a", 40)

    assert :error = Startup.validate_artifact(identity, %{"candidate" => other})
  end

  setup do
    # Match the root supervisor's handling of a failed linked startup child.
    Process.flag(:trap_exit, true)

    root =
      Path.join(
        System.tmp_dir!(),
        "gitgood-owned-startup-" <> Integer.to_string(System.unique_integer([:positive]))
      )

    refute File.exists?(root)
    on_exit(fn -> File.rm_rf!(root) end)
    %{root: root}
  end

  test "actual unsupported native leaf refuses before helpers or application children" do
    root = "/var/lib/gitgood/installations/" <> Ecto.UUID.generate() <> "/storage"
    options = [root: root, mode: :runtime]
    prior = Process.whereis(Gitgood.Supervisor)
    assert :ok = Startup.validate_options(options)
    refute File.exists?(root)

    # mix test already owns Gitgood.Supervisor. Exercise the actual native root
    # in a separate BEAM without stopping or renaming the running application.
    {:ok, peer, _} =
      :peer.start(%{
        connection: :standard_io,
        args: [~c"+S", ~c"2:2"],
        wait_boot: 10_000,
        shutdown: {:halt, 1_000}
      })

    try do
      assert :ok = :peer.call(peer, :code, :add_paths, [:code.get_path()], 5_000)
      assert {:ok, _} = :peer.call(peer, :application, :ensure_all_started, [:elixir], 5_000)
      assert :undefined = :peer.call(peer, :erlang, :whereis, [Gitgood.Supervisor], 5_000)

      # The peer call runs outside a supervisor; trap the linked root's expected
      # startup failure just as the application's caller does.
      assert {{:error,
               {:shutdown,
                {:failed_to_start_child, Startup, :native_ownership_startup_unavailable}}}, _} =
               :peer.call(
                 peer,
                 Code,
                 :eval_string,
                 [
                   "Process.flag(:trap_exit, true); " <>
                     "Gitgood.NativeOwnershipSupervisor.start_native_link(root, :runtime, [])",
                   [root: root]
                 ],
                 5_000
               )

      assert :undefined = :peer.call(peer, :erlang, :whereis, [Gitgood.Supervisor], 5_000)
    after
      :peer.stop(peer)
    end

    refute File.exists?(root)
    assert Process.whereis(Gitgood.Supervisor) == prior
    if is_pid(prior), do: assert(Process.alive?(prior))
  end

  test "retained native responsibility survives failed startup byte for byte", %{root: root} do
    File.mkdir!(root)
    marker = Path.join(root, ".gitgood-runtime-v2.json")
    File.write!(marker, "retained incomplete ownership")
    {:ok, before} = File.stat(marker, time: :posix)

    assert {:error, :native_ownership_startup_unavailable} =
             Startup.start_link(root: root, mode: :runtime)

    {:ok, after_failure} = File.stat(marker, time: :posix)
    fields = [:inode, :major_device, :size, :mtime, :ctime, :mode, :links]
    assert Map.take(after_failure, fields) == Map.take(before, fields)
    assert File.read!(marker) == "retained incomplete ownership"
    assert File.ls!(root) == [".gitgood-runtime-v2.json"]
  end

  test "credentials, caller programs, duplicate keys and arbitrary paths never enter a child specification",
       %{root: root} do
    base = [
      root: "/var/lib/gitgood/installations/" <> Ecto.UUID.generate() <> "/storage",
      mode: :runtime
    ]

    bad = [
      nil,
      base ++ [root: root],
      Keyword.put(base, :mode, :shell),
      Keyword.put(base, :root, root),
      Keyword.put(base, :program, "arbitrary"),
      Keyword.put(base, :authority, %{}),
      Keyword.put(base, :connection, password: "synthetic-secret-canary")
    ]

    Enum.each(bad, fn supplied ->
      assert :error = Startup.validate_options(supplied)
      assert {:error, :native_ownership_startup_unavailable} = Startup.start_link(supplied)
    end)

    refute File.exists?(root)
  end
end
