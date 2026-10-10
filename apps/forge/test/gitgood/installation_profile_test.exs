defmodule Gitgood.InstallationProfileTest do
  use ExUnit.Case, async: true
  alias Gitgood.InstallationProfile, as: Profile
  @id "00000000-0000-4000-8000-000000000001"
  @root "/var/lib/gitgood/installations/#{@id}/storage"

  defp evidence(worker \\ "native") do
    %{
      native_files: true,
      kernel: {:managed, @id, worker},
      platform: {:unix, :linux},
      architecture: "x86_64-pc-linux-gnu"
    }
  end

  test "selection requires matching native kernel identity, storage and worker" do
    assert {:ok, %{profile: :systemd_v2, installation: @id, worker: "native"}} =
             Profile.select("systemd-v2", @root, :runtime, evidence())

    assert {:ok, %{profile: :systemd_v2, worker: "maintenance"}} =
             Profile.select("systemd-v2", @root, :backup, evidence("maintenance"))

    for root <- [@root <> "/", @root <> "/../storage", "/tmp/storage"],
        do: assert({:error, _} = Profile.select("systemd-v2", root, :runtime, evidence()))

    assert {:error, _} = Profile.select("systemd-v2", @root, :runtime, evidence("maintenance"))
    assert {:error, _} = Profile.select("systemd-v2", @root, :migrate, evidence())
  end

  test "unknown modes, profile values and unsupported platforms refuse" do
    for value <- ["", "native", "legacy", true, 2],
        do: assert({:error, _} = Profile.select(value, @root, :runtime, evidence()))

    assert {:error, _} = Profile.select("systemd-v2", @root, :retire, evidence())

    assert {:error, _} =
             Profile.select("systemd-v2", @root, :runtime, %{
               evidence()
               | architecture: "aarch64-pc-linux-gnu"
             })

    assert {:error, _} =
             Profile.select("systemd-v2", @root, :runtime, %{evidence() | platform: {:win32, :nt}})
  end

  test "native filesystem or kernel evidence forbids implicit downgrade" do
    assert {:error, :installation_native_profile_required} =
             Profile.select(nil, @root, :runtime, evidence())

    assert {:error, :installation_native_profile_required} =
             Profile.select(nil, @root, :runtime, %{evidence() | kernel: :none})

    assert {:error, :installation_native_profile_required} =
             Profile.select(nil, @root, :runtime, %{evidence() | native_files: false})

    assert {:error, _} =
             Profile.select(nil, @root, :runtime, %{native_files: false, kernel: :invalid_native})
  end

  test "kernel decoding rejects a malformed or nested managed leaf" do
    path = "0::/system.slice/gitgood-installation-#{@id}.service/native"
    assert {:managed, @id, "native"} = Profile.decode_kernel(path <> "\n")

    for value <- [
          path <> "/child",
          path <> "\n0::/other",
          String.replace(path, @id, "broken"),
          path <> <<0>>
        ],
        do: assert(:invalid_native == Profile.decode_kernel(value))

    assert :none = Profile.decode_kernel("0::/ordinary\n")
  end

  test "actual files preserve legacy stores and reject retained native ownership" do
    root =
      Path.join(
        System.tmp_dir!(),
        "gitgood-profile-" <> Integer.to_string(System.unique_integer([:positive]))
      )

    File.mkdir!(root)
    on_exit(fn -> File.rm_rf!(root) end)
    assert {:ok, %{profile: :development_v1}} = Profile.resolve(nil, root, :runtime)
    marker = Path.join(root, ".gitgood-runtime-v2.json")
    File.write!(marker, "incomplete native marker")
    before = File.read!(marker)
    assert {:error, :installation_native_profile_required} = Profile.resolve(nil, root, :runtime)
    assert File.read!(marker) == before
    assert {:error, _} = Profile.resolve("systemd-v2", root, :runtime)
    assert File.read!(marker) == before

    File.rm!(marker)
    ownership = Path.join(root, ".gitgood-ownership-v2")
    File.mkdir!(ownership)
    assert {:error, :installation_native_profile_required} = Profile.resolve(nil, root, :runtime)
    assert File.dir?(ownership)
  end

  test "invalid roots refuse before filesystem inspection" do
    for root <- [nil, 1, "", "/tmp/" <> <<0>>, String.duplicate("x", 4097)] do
      assert {:error, :installation_profile_unavailable} = Profile.resolve(nil, root, :runtime)
    end
  end
end
