defmodule Gitgood.NativeOwnershipInputsTest do
  use ExUnit.Case, async: true
  alias Gitgood.NativeOwnershipInputs, as: Inputs
  alias Gitgood.NativeOwnershipPublication, as: Publication

  defp fixture do
    record =
      Jason.decode!(
        File.read!(Path.expand("../fixtures/native_ownership_record_v3.json", __DIR__))
      )

    storage = "/var/lib/gitgood/installations/" <> record["installation"] <> "/storage"

    authority =
      Map.take(record, ~w(installation operation candidate binding_sha256))
      |> Map.merge(%{"protocol" => 3, "kind" => "native_application_ownership_seal"})

    admission = %{
      "installation" => record["installation"],
      "database" => record["database_session"]["database"],
      "binding_sha256" => record["binding_sha256"]
    }

    configuration = %{
      "protocol" => 1,
      "installation" => record["installation"],
      "forge" => %{
        "GITGOOD_INSTALLATION_ID" => record["installation"],
        "GITGOOD_STORAGE" => storage,
        "GITGOOD_SSH_HOST_KEY_DIRECTORY" => Path.dirname(storage) <> "/ssh-host",
        "DATABASE_URL" =>
          "postgresql://ordinary:synthetic%3Acanary%40value@127.0.0.1:55432/owned_fixture"
      },
      "web" => %{},
      "edge" => %{}
    }

    {configuration, authority, storage, admission}
  end

  defp application_fixture do
    {_, _, storage, admission} = fixture()

    path =
      "/etc/gitgood/installations/" <>
        admission["installation"] <> "/generation-admission-v2.json"

    executables = Map.new(~w(python node git psql caddy), &{&1, "/fixed/" <> &1})

    seal = %{
      "protocol" => 2,
      "kind" => "native_generation_admission_seal",
      "installation" => admission["installation"],
      "binding_sha256" => admission["binding_sha256"],
      "history_identity" => %{"device" => 1, "inode" => 2, "uid" => 1000},
      "lock_identity" => %{"device" => 1, "inode" => 3, "uid" => 1000},
      "unit_sha256" => String.duplicate("a", 64),
      "executables" => executables,
      "limits" => %{"cpu_quota_us" => 200_000, "memory_bytes" => 268_435_456},
      "database" => admission["database"]
    }

    raw = Publication.canonical(seal)

    admission =
      Map.merge(admission, %{
        "seal_file" => %{
          "path" => path,
          "sha256" => Base.encode16(:crypto.hash(:sha256, raw), case: :lower)
        },
        "worker_observation" => %{
          "service_scope" => %{"unit_definition" => %{"sha256" => seal["unit_sha256"]}}
        }
      })

    {raw, path, admission, seal, storage}
  end

  test "application executables come from the exact observed fixed Root seal" do
    {raw, path, admission, seal, _} = application_fixture()
    assert {:ok, executables} = Inputs.application_executables(raw, path, admission)
    assert executables == seal["executables"]

    assert {:error, :native_ownership_inputs_unavailable} =
             Inputs.application_executables(raw, "/foreign.json", admission)

    assert {:error, :native_ownership_inputs_unavailable} =
             Inputs.application_executables(raw <> "\n", path, admission)

    assert {:error, :native_ownership_inputs_unavailable} =
             Inputs.application_executables(
               raw,
               path,
               put_in(admission, ["seal_file", "sha256"], String.duplicate("f", 64))
             )
  end

  test "canonical hashes cannot bless wrong unit database binding or dependency sets" do
    {_, path, admission, seal, _} = application_fixture()

    for changed <- [
          Map.put(seal, "protocol", true),
          Map.put(seal, "kind", "legacy"),
          Map.put(seal, "binding_sha256", String.duplicate("c", 64)),
          Map.put(seal, "unit_sha256", String.duplicate("c", 64)),
          put_in(seal, ["database", "role"], "foreign"),
          put_in(seal, ["executables", "git"], "relative"),
          put_in(seal, ["executables", "git"], seal["executables"]["python"]),
          put_in(seal, ["executables", "other"], "/fixed/other"),
          Map.put(seal, "unknown", true)
        ] do
      raw = Publication.canonical(changed)

      admission =
        put_in(
          admission,
          ["seal_file", "sha256"],
          Base.encode16(:crypto.hash(:sha256, raw), case: :lower)
        )

      assert {:error, :native_ownership_inputs_unavailable} =
               Inputs.application_executables(raw, path, admission)
    end

    duplicate =
      String.replace(Publication.canonical(seal), "{", "{\"protocol\":2,", global: false)

    admission =
      put_in(
        admission,
        ["seal_file", "sha256"],
        Base.encode16(:crypto.hash(:sha256, duplicate), case: :lower)
      )

    assert {:error, :native_ownership_inputs_unavailable} =
             Inputs.application_executables(duplicate, path, admission)
  end

  test "bounded parsed credentials stay internal and match the admitted local database" do
    {configuration, authority, storage, admission} = fixture()

    assert {:ok, inputs} =
             Inputs.decode(
               Jason.encode!(configuration),
               Publication.canonical(authority),
               storage,
               admission
             )

    assert inputs.authority == authority

    assert inputs.connection == [
             hostname: "127.0.0.1",
             port: 55432,
             database: "owned_fixture",
             username: "ordinary",
             password: "synthetic:canary@value"
           ]

    local =
      put_in(
        configuration,
        ["forge", "DATABASE_URL"],
        "postgres://ordinary@localhost:55432/owned_fixture"
      )

    assert {:ok, local_inputs} =
             Inputs.decode(
               Jason.encode!(local),
               Publication.canonical(authority),
               storage,
               admission
             )

    refute Keyword.has_key?(local_inputs.connection, :password)
    assert local_inputs.connection[:hostname] == "127.0.0.1"
  end

  test "duplicate JSON fields refuse at every nesting level" do
    {configuration, authority, storage, admission} = fixture()
    raw = Jason.encode!(configuration)

    for changed <- [
          String.replace(raw, "{", "{\"protocol\":1,", global: false),
          String.replace(raw, "\"forge\":{", "\"forge\":{\"DATABASE_URL\":\"fake\",",
            global: false
          ),
          String.replace(raw, "\"web\":{}", "\"web\":{\"a\":1,\"a\":2}")
        ] do
      assert changed != raw
      assert {:ok, _} = Jason.decode(changed, objects: :ordered_objects)

      assert {:error, :native_ownership_inputs_unavailable} =
               Inputs.decode(changed, Publication.canonical(authority), storage, admission)
    end

    duplicate =
      String.replace(Publication.canonical(authority), "{", "{\"protocol\":3,", global: false)

    assert {:ok, _} = Jason.decode(duplicate, objects: :ordered_objects)

    assert {:error, :native_ownership_inputs_unavailable} =
             Inputs.decode(raw, duplicate, storage, admission)
  end

  test "legacy, changed binding, missing fields and noncanonical authority refuse" do
    {configuration, authority, storage, admission} = fixture()

    for changed <- [
          Map.put(authority, "protocol", 2),
          Map.put(authority, "binding_sha256", String.duplicate("c", 64)),
          Map.put(authority, "extra", true),
          Map.delete(authority, "operation")
        ] do
      assert {:error, :native_ownership_inputs_unavailable} =
               Inputs.decode(
                 Jason.encode!(configuration),
                 Publication.canonical(changed),
                 storage,
                 admission
               )
    end

    assert {:error, :native_ownership_inputs_unavailable} =
             Inputs.decode(
               Jason.encode!(configuration),
               Publication.canonical(authority) <> "\n",
               storage,
               admission
             )
  end

  test "foreign server, identity, URI options and decoded NUL credentials refuse" do
    {configuration, authority, storage, admission} = fixture()

    for url <- [
          "postgres://ordinary@foreign.example:55432/owned_fixture",
          "postgres://other@127.0.0.1:55432/owned_fixture",
          "postgres://ordinary@127.0.0.1:55433/owned_fixture",
          "postgres://ordinary@127.0.0.1:55432/other",
          "postgres://ordinary@127.0.0.1:55432/owned_fixture?options=arbitrary",
          "postgres://ordinary@127.0.0.1:55432/owned_fixture#fragment",
          "postgres://ordinary:%00@127.0.0.1:55432/owned_fixture"
        ] do
      changed = put_in(configuration, ["forge", "DATABASE_URL"], url)

      assert {:error, :native_ownership_inputs_unavailable} =
               Inputs.decode(
                 Jason.encode!(changed),
                 Publication.canonical(authority),
                 storage,
                 admission
               )
    end

    assert {:error, :native_ownership_inputs_unavailable} =
             Inputs.decode(
               Jason.encode!(configuration),
               Publication.canonical(authority),
               storage <> "/other",
               admission
             )
  end

  test "oversized input, nested objects and changed installation refuse" do
    {configuration, authority, storage, admission} = fixture()

    assert {:error, :native_ownership_inputs_unavailable} =
             Inputs.decode(
               String.duplicate(" ", 131_073),
               Publication.canonical(authority),
               storage,
               admission
             )

    assert {:error, :native_ownership_inputs_unavailable} =
             Inputs.decode(
               Jason.encode!(configuration),
               String.duplicate(" ", 16_385),
               storage,
               admission
             )

    nested = Enum.reduce(1..18, %{}, fn _, inner -> %{"nested" => inner} end)

    assert {:error, :native_ownership_inputs_unavailable} =
             Inputs.decode(
               Jason.encode!(Map.put(configuration, "web", nested)),
               Publication.canonical(authority),
               storage,
               admission
             )

    assert {:error, :native_ownership_inputs_unavailable} =
             Inputs.decode(
               Jason.encode!(Map.put(configuration, "installation", authority["operation"])),
               Publication.canonical(authority),
               storage,
               admission
             )
  end
end
