defmodule Gitgood.NativeOwnershipStartupTest do
  use ExUnit.Case, async: false
  @moduletag capture_log: true
  alias Gitgood.NativeOwnershipStartup, as: Startup

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

    assert {:error,
            {:shutdown, {:failed_to_start_child, Startup, :native_ownership_startup_unavailable}}} =
             Gitgood.NativeOwnershipSupervisor.start_native_link(root, :runtime, [])

    refute File.exists?(root)
    assert Process.whereis(Gitgood.Supervisor) == prior
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
