defmodule Gitgood.NativeLifecycleActionTest do
  use ExUnit.Case, async: true
  alias Gitgood.NativeLifecycleAction, as: Action
  @installation "00000000-0000-4000-8000-000000000001"
  @operation "00000000-0000-4000-8000-000000000002"

  # Explicit metadata stand-ins: these do not authorize a real lease or stage.
  defp fixture(action, purpose \\ "native_initial_enrollment") do
    worker = if action == :runtime, do: "native", else: "maintenance"
    stage = %{runtime: "verify", migrate: "migrate", bootstrap: "bootstrap"}[action]

    authority = %{
      "protocol" => 3,
      "kind" => "native_application_ownership_seal",
      "installation" => @installation,
      "operation" => @operation,
      "candidate" => String.duplicate("e", 40),
      "binding_sha256" => String.duplicate("b", 64)
    }

    admission = %{
      "protocol" => 2,
      "installation" => @installation,
      "worker" => worker,
      "pointer" => %{
        "protocol" => 2,
        "installation" => @installation,
        "operation" => @operation,
        "generation_sha256" => String.duplicate("a", 64),
        "transition_sha256" => String.duplicate("c", 64)
      },
      "binding_sha256" => authority["binding_sha256"],
      "worker_observation" => %{
        "worker" => worker,
        "owner" => %{"pid" => 42, "birth" => "420"},
        "service_scope" => %{
          "installation" => @installation,
          "protocol" => 2,
          "service_scope_observed" => true
        }
      },
      "database" => %{},
      "seal_file" => %{
        "device" => 1,
        "inode" => 2,
        "bytes" => 300,
        "sha256" => String.duplicate("d", 64),
        "path" =>
          "/etc/gitgood/installations/" <> @installation <> "/generation-admission-v2.json"
      },
      "published_generation_admitted" => true,
      "writer_exclusion_established" => false,
      "installation_readiness_established" => false,
      "lifecycle_responsibility_admitted" => false,
      "lifecycle_observation" => %{
        "operation" => @operation,
        "purpose" => purpose,
        "candidate" => authority["candidate"],
        "request_sha256" => String.duplicate("f", 64),
        "origin_sha256" => String.duplicate("a", 64),
        "snapshot_sha256" => String.duplicate("b", 64),
        "generation_sha256" => String.duplicate("a", 64),
        "epoch" => 1,
        "stage" => stage,
        "recorded_status" => "running",
        "worker" => worker
      }
    }

    {admission, authority}
  end

  test "only fixed business actions select their exact ownership mode" do
    assert Action.mode(:runtime) == {:ok, :runtime}
    assert Action.mode(:migrate) == {:ok, :migrate}
    assert Action.mode(:bootstrap) == {:ok, :migrate}

    for action <- [nil, true, "runtime", :backup, :restore, :retire, :command] do
      assert Action.mode(action) == :error
    end
  end

  test "original running enrollment and upgrade observations match fixed actions" do
    for {purpose, actions} <- [
          {"native_initial_enrollment", [:runtime, :migrate, :bootstrap]},
          {"native_upgrade_execution", [:runtime, :migrate]}
        ],
        action <- actions do
      {admission, authority} = fixture(action, purpose)
      assert Action.validate(admission, authority, action) == :ok
      assert admission["lifecycle_responsibility_admitted"] === false
    end
  end

  test "a matching maintenance leaf cannot exchange bootstrap and migration" do
    {bootstrap, authority} = fixture(:bootstrap)
    {migration, _} = fixture(:migrate)
    assert Action.validate(bootstrap, authority, :migrate) == :error
    assert Action.validate(migration, authority, :bootstrap) == :error
    assert Action.validate(migration, authority, :runtime) == :error
  end

  test "publication-only admission cannot become a business startup window" do
    {admission, authority} = fixture(:runtime)

    assert Action.validate(Map.delete(admission, "lifecycle_observation"), authority, :runtime) ==
             :error
  end

  test "changed Root operation candidate binding and extended authority refuse" do
    {admission, authority} = fixture(:migrate)

    for changes <- [
          %{"operation" => @installation},
          %{"candidate" => String.duplicate("f", 40)},
          %{"binding_sha256" => String.duplicate("f", 64)},
          %{"protocol" => true},
          %{"kind" => "legacy"},
          %{"command" => "/tmp/caller-program"}
        ] do
      assert Action.validate(admission, Map.merge(authority, changes), :migrate) == :error
    end

    for value <- [nil, %{}, true] do
      assert Action.validate(value, authority, :migrate) == :error
      assert Action.validate(admission, value, :migrate) == :error
    end
  end

  test "uncertainty wrong generation and forged effect authority cannot start workers" do
    {admission, authority} = fixture(:runtime)

    for changes <- [
          %{"recorded_status" => "uncertain"},
          %{"recorded_status" => "pending"},
          %{"generation_sha256" => String.duplicate("f", 64)},
          %{"epoch" => true}
        ] do
      changed =
        Map.put(
          admission,
          "lifecycle_observation",
          Map.merge(admission["lifecycle_observation"], changes)
        )

      assert Action.validate(changed, authority, :runtime) == :error
    end

    assert Action.validate(
             Map.put(admission, "lifecycle_responsibility_admitted", true),
             authority,
             :runtime
           ) == :error

    for owner <- [-1, 1, 2_147_483_648] do
      changed = put_in(admission["worker_observation"]["owner"]["pid"], owner)
      assert Action.validate(changed, authority, :runtime) == :error
    end
  end

  test "terminal original observation permits runtime but cannot replay a maintenance action" do
    {admission, authority} = fixture(:runtime)

    observed =
      Map.merge(admission["lifecycle_observation"], %{
        "recorded_status" => "complete",
        "stage" => "enroll"
      })

    terminal = Map.put(admission, "lifecycle_observation", observed)
    assert Action.validate(terminal, authority, :runtime) == :ok
    assert Action.validate(terminal, authority, :migrate) == :error
    assert Action.validate(terminal, authority, :bootstrap) == :error
  end
end
