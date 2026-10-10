defmodule Gitgood.NativeStartupPreflightTest do
  use ExUnit.Case, async: false

  setup do
    previous =
      Map.new([:storage_root, :supervision_profile], &{&1, Application.get_env(:gitgood, &1)})

    root =
      Path.join(
        System.tmp_dir!(),
        "gitgood-preflight-" <> Integer.to_string(System.unique_integer([:positive]))
      )

    refute File.exists?(root)
    Application.put_env(:gitgood, :storage_root, root)
    Application.put_env(:gitgood, :supervision_profile, "unsupported")

    on_exit(fn ->
      Enum.each(previous, fn {key, value} ->
        if is_nil(value),
          do: Application.delete_env(:gitgood, key),
          else: Application.put_env(:gitgood, key, value)
      end)

      File.rm_rf!(root)
    end)

    %{root: root}
  end

  test "actual application rejects unsupported profile before storage or children", %{root: root} do
    prior = Process.whereis(Gitgood.Supervisor)
    assert {:error, :installation_profile_unavailable} = Gitgood.Application.start(:normal, [])
    refute File.exists?(root)
    assert Process.whereis(Gitgood.Supervisor) == prior
  end

  test "actual lease initialization refuses before connection configuration", %{root: root} do
    assert {:stop, :installation_profile_unavailable} = Gitgood.InstallationLease.init(root: root)
    refute File.exists?(root)
  end

  test "retained native marker blocks actual legacy startup without changing its bytes", %{
    root: root
  } do
    File.mkdir!(root)
    path = Path.join(root, ".gitgood-runtime-v2.json")
    File.write!(path, "unfinished ownership")
    Application.delete_env(:gitgood, :supervision_profile)

    assert {:error, :installation_native_profile_required} =
             Gitgood.Application.start(:normal, [])

    assert {:stop, :installation_native_profile_required} =
             Gitgood.InstallationLease.init(root: root)

    assert File.read!(path) == "unfinished ownership"
    assert File.ls!(root) == [".gitgood-runtime-v2.json"]
  end
end
