defmodule Gitgood.NativeBackendObservationTest do
  use ExUnit.Case, async: true
  alias Gitgood.NativeOwnershipPublication, as: Publication

  defp fixture do
    record =
      __DIR__
      |> Path.join("../fixtures/native_ownership_record.json")
      |> File.read!()
      |> Jason.decode!()

    admission = %{
      "installation" => record["installation"],
      "database" => record["database_session"]["database"],
      "worker_observation" => %{
        "worker" => "native",
        "owner" => record["owner"],
        "service_scope" => record["scope"]
      }
    }

    kernel = %{
      "protocol" => 2,
      "kind" => "native_backend_kernel_identity",
      "database_session" => record["database_session"],
      "kernel_birth" => "450",
      "server_scope" => %{
        "boot_id" => record["scope"]["boot_id"],
        "pid_namespace" => "pid:[12345]",
        "time_namespace" => "time:[4441]",
        "postgres_uid" => 1001
      }
    }

    reply = %{
      "protocol" => 2,
      "status" => "observed",
      "installation" => record["installation"],
      "worker" => "native",
      "owner_pid" => record["owner"]["pid"],
      "owner" => record["owner"],
      "kernel_record" => kernel,
      "service_scope_sha256" => digest(record["scope"]),
      "ownership_retained" => false,
      "writer_exclusion_established" => false,
      "installation_readiness_established" => false,
      "replacement_admitted" => false
    }

    {reply, admission, record["database_session"]}
  end

  defp digest(value),
    do: :crypto.hash(:sha256, Publication.canonical(value)) |> Base.encode16(case: :lower)

  test "closed observation preserves the original owner SQL snapshot and service boot" do
    {reply, admission, session} = fixture()
    assert :ok = Publication.validate_backend_reply(reply, admission, session)
  end

  test "changed owner birth SQL session service digest or admitted database refuses" do
    {reply, admission, session} = fixture()

    for changed <- [
          Map.put(reply, "owner_pid", reply["owner_pid"] + 1),
          put_in(reply, ["owner", "birth"], "30002"),
          put_in(
            reply,
            ["kernel_record", "database_session", "backend_pid"],
            session["backend_pid"] + 1
          ),
          Map.put(reply, "service_scope_sha256", String.duplicate("a", 64)),
          put_in(
            reply,
            ["kernel_record", "server_scope", "boot_id"],
            "11111111-1111-4111-8111-111111111111"
          )
        ] do
      assert :error = Publication.validate_backend_reply(changed, admission, session)
    end

    changed = put_in(session, ["database", "superuser"], true)

    assert :error =
             Publication.validate_backend_reply(
               put_in(reply, ["kernel_record", "database_session"], changed),
               Map.put(admission, "database", changed["database"]),
               changed
             )
  end

  test "authority flags unknown fields and aliased protocol refuse" do
    {reply, admission, session} = fixture()

    for key <-
          ~w(ownership_retained writer_exclusion_established installation_readiness_established replacement_admitted) do
      assert :error =
               Publication.validate_backend_reply(Map.put(reply, key, true), admission, session)
    end

    for changed <- [
          Map.put(reply, "extra", true),
          Map.delete(reply, "owner"),
          Map.put(reply, "protocol", 2.0),
          put_in(reply, ["kernel_record", "protocol"], 2.0),
          put_in(reply, ["kernel_record", "extra"], true),
          put_in(reply, ["kernel_record", "server_scope", "extra"], true)
        ] do
      assert :error = Publication.validate_backend_reply(changed, admission, session)
    end
  end

  test "malformed kernel births namespace identities accounts and null values refuse" do
    {reply, admission, session} = fixture()

    for birth <- ["0", "0450", "-1", "18446744073709551616", true, 450] do
      assert :error =
               Publication.validate_backend_reply(
                 put_in(reply, ["kernel_record", "kernel_birth"], birth),
                 admission,
                 session
               )
    end

    for {key, value} <- [
          {"pid_namespace", "pid:[0]"},
          {"time_namespace", "mnt:[4441]"},
          {"postgres_uid", 0},
          {"postgres_uid", 1.0},
          {"postgres_uid", 4_294_967_296}
        ] do
      assert :error =
               Publication.validate_backend_reply(
                 put_in(reply, ["kernel_record", "server_scope", key], value),
                 admission,
                 session
               )
    end

    for changed <- [nil, %{}, Map.put(reply, "kernel_record", nil)] do
      assert :error = Publication.validate_backend_reply(changed, admission, session)
    end
  end

  test "missing admission cannot execute the protected entry" do
    assert {:error, :native_backend_observation_unavailable} =
             Publication.observe_backend(%{}, %{})
  end
end
