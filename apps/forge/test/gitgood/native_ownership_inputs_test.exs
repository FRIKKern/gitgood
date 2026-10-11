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
