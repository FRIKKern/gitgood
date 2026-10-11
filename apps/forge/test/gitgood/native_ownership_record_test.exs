defmodule Gitgood.NativeOwnershipRecordTest do
  use ExUnit.Case, async: true
  alias Gitgood.NativeOwnershipPublication, as: Publication
  alias Gitgood.NativeOwnershipRecord, as: Record

  defp fixture(mode \\ :runtime) do
    record =
      __DIR__
      |> Path.join("../fixtures/native_ownership_record_v3.json")
      |> File.read!()
      |> Jason.decode!()
      |> put_in(["owner", "pid"], String.to_integer(System.pid()))
      |> put_in(["scope", "manager", "pid"], String.to_integer(System.pid()) + 1)
      |> Map.put("mode", Atom.to_string(mode))

    worker = if mode == :runtime, do: "native", else: "maintenance"

    scope_digest =
      digest(%{"scope" => record["scope"], "owner" => record["owner"], "worker" => worker})

    record = put_in(record, ["guard", "scope_sha256"], scope_digest)

    admission = %{
      "protocol" => 2,
      "installation" => record["installation"],
      "worker" => worker,
      "pointer" => record["pointer"],
      "binding_sha256" => record["binding_sha256"],
      "database" => record["database_session"]["database"],
      "worker_observation" => %{
        "worker" => worker,
        "owner" => record["owner"],
        "service_scope" => record["scope"]
      },
      "seal_file" => %{
        "path" =>
          "/etc/gitgood/installations/#{record["installation"]}/generation-admission-v2.json",
        "device" => 1,
        "inode" => 2,
        "bytes" => 300,
        "sha256" => String.duplicate("a", 64)
      },
      "published_generation_admitted" => true,
      "writer_exclusion_established" => false,
      "installation_readiness_established" => false,
      "lifecycle_responsibility_admitted" => false
    }

    seal =
      record
      |> Map.take(~w(protocol installation operation candidate binding_sha256))
      |> Map.put("kind", "native_application_ownership_seal")

    {%{admission: admission, guard: record["guard"]}, record["database_session"], seal, record}
  end

  defp digest(value),
    do: :crypto.hash(:sha256, Publication.canonical(value)) |> Base.encode16(case: :lower)

  defp fixture_kernel do
    __DIR__
    |> Path.join("../fixtures/native_ownership_record_v3.json")
    |> File.read!()
    |> Jason.decode!()
    |> Map.fetch!("backend_kernel")
  end

  defp refused(context, session, seal, mode \\ :runtime) do
    assert {:error, :native_ownership_record_unavailable} =
             Record.build(context, session, fixture_kernel(), seal, mode)
  end

  test "constructs the closed reference record with the actual calling owner" do
    {context, session, seal, expected} = fixture()

    assert {:ok, ^expected} =
             Record.build(context, session, expected["backend_kernel"], seal, :runtime)

    assert MapSet.new(Map.keys(expected)) ==
             MapSet.new(
               ~w(protocol kind installation operation candidate mode binding_sha256 pointer scope owner database_session guard backend_kernel)
             )

    assert {:ok, _, _} = Publication.request(expected, String.to_integer(System.pid()))
  end

  test "maintenance modes require the maintenance worker and its matching guard" do
    for mode <- [:backup, :restore, :migrate] do
      {context, session, seal, expected} = fixture(mode)

      assert {:ok, ^expected} =
               Record.build(context, session, expected["backend_kernel"], seal, mode)

      refused(context, session, seal, :runtime)
    end
  end

  test "cannot borrow another owner, manager identity, UID or namespace" do
    {context, session, seal, _} = fixture()
    owner = context.admission["worker_observation"]["owner"]
    scope = context.admission["worker_observation"]["service_scope"]

    for changed <- [
          Map.put(owner, "pid", owner["pid"] + 1),
          Map.put(owner, "uid", owner["uid"] + 1),
          Map.put(owner, "mount_namespace", "mnt:[1]"),
          Map.put(owner, "cgroup_namespace", "cgroup:[1]")
        ] do
      changed_context = put_in(context, [:admission, "worker_observation", "owner"], changed)

      changed_context =
        put_in(
          changed_context,
          [:guard, "scope_sha256"],
          digest(%{"scope" => scope, "owner" => changed, "worker" => "native"})
        )

      refused(changed_context, session, seal)
    end

    refused(
      put_in(
        context,
        [:admission, "worker_observation", "service_scope", "manager", "pid"],
        owner["pid"]
      ),
      session,
      seal
    )
  end

  test "seal must have distinct canonical identities and match the admitted binding" do
    {context, session, seal, _} = fixture()

    for changed <- [
          Map.put(seal, "protocol", 2.0),
          Map.put(seal, "kind", "arbitrary"),
          Map.put(seal, "candidate", String.duplicate("A", 40)),
          Map.put(seal, "operation", seal["installation"]),
          Map.put(seal, "operation", context.admission["pointer"]["operation"]),
          Map.put(seal, "binding_sha256", String.duplicate("0", 64)),
          Map.put(seal, "installation", "00000000-0000-4000-8000-000000000099"),
          Map.put(seal, "replacement_admitted", true)
        ],
        do: refused(context, session, changed)
  end

  test "session must preserve the original database and closed bounded backend identity" do
    {context, session, seal, _} = fixture()

    for changed <- [
          Map.put(session, "backend_pid", 0),
          Map.put(session, "backend_pid", 2_147_483_648),
          Map.put(session, "backend_pid", 1.0),
          Map.put(session, "backend_birth", false),
          Map.put(session, "backend_birth", "018"),
          Map.put(session, "backend_birth", "18446744073709551616"),
          put_in(session, ["database", "superuser"], true),
          Map.put(session, "password", "synthetic forbidden field")
        ],
        do: refused(context, changed, seal)
  end

  test "guard fields are closed and must describe the exact owner, scope and worker" do
    {context, session, seal, _} = fixture()
    refused(put_in(context, [:guard, "scope_sha256"], String.duplicate("0", 64)), session, seal)
    refused(put_in(context, [:guard, "history_sha256"], false), session, seal)
    refused(Map.update!(context, :guard, &Map.put(&1, "lease_acquired", true)), session, seal)
  end

  test "construction refuses unknown context fields, modes and added admission authority" do
    {context, session, seal, _} = fixture()
    refused(Map.put(context, :command, "arbitrary"), session, seal)
    refused(context, session, seal, :retire)
    refused(context, session, seal, "runtime")

    refused(
      put_in(context, [:admission, "installation_readiness_established"], true),
      session,
      seal
    )

    refused(put_in(context, [:admission, "writer_exclusion_established"], true), session, seal)
  end

  test "oversized canonical construction refuses before publication" do
    {context, session, seal, _} = fixture()

    changed =
      put_in(
        context,
        [:admission, "worker_observation", "service_scope", "padding"],
        String.duplicate("a", 16_384)
      )

    scope = changed.admission["worker_observation"]["service_scope"]
    owner = changed.admission["worker_observation"]["owner"]

    changed =
      put_in(
        changed,
        [:guard, "scope_sha256"],
        digest(%{"scope" => scope, "owner" => owner, "worker" => "native"})
      )

    refused(changed, session, seal)
  end

  test "kernel identity is mandatory and matches original SQL session and service boot" do
    {context, session, seal, expected} = fixture()
    kernel = expected["backend_kernel"]

    for changed <- [
          nil,
          Map.delete(kernel, "kernel_birth"),
          Map.put(kernel, "kernel_birth", "0"),
          put_in(kernel, ["database_session", "backend_pid"], session["backend_pid"] + 1),
          put_in(kernel, ["server_scope", "boot_id"], "11111111-1111-4111-8111-111111111111"),
          Map.put(kernel, "protocol", 2.0),
          Map.put(kernel, "extra", true)
        ] do
      assert {:error, :native_ownership_record_unavailable} =
               Record.build(context, session, changed, seal, :runtime)
    end

    assert {:error, :native_ownership_record_unavailable} =
             Record.build(context, session, kernel, Map.put(seal, "protocol", 2), :runtime)
  end
end
