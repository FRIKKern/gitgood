defmodule Gitgood.InstallationGenerationAdmissionTest do
  use ExUnit.Case, async: true
  alias Gitgood.InstallationGenerationAdmission, as: Admission
  @installation "00000000-0000-4000-8000-000000000001"

  defp output do
    %{
      "protocol" => 2,
      "installation" => @installation,
      "worker" => "native",
      "pointer" => %{
        "protocol" => 2,
        "installation" => @installation,
        "operation" => @installation,
        "generation_sha256" => String.duplicate("a", 64),
        "transition_sha256" => String.duplicate("c", 64)
      },
      "binding_sha256" => String.duplicate("b", 64),
      "worker_observation" => %{
        "worker" => "native",
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
      "lifecycle_responsibility_admitted" => false
    }
  end

  defp lifecycle_output(worker, changes \\ %{}) do
    value = output()

    observation = %{
      "operation" => "00000000-0000-4000-8000-000000000002",
      "purpose" => "native_initial_enrollment",
      "candidate" => String.duplicate("e", 40),
      "request_sha256" => String.duplicate("f", 64),
      "origin_sha256" => String.duplicate("a", 64),
      "snapshot_sha256" => String.duplicate("b", 64),
      "generation_sha256" => value["pointer"]["generation_sha256"],
      "epoch" => 1,
      "stage" => "verify",
      "recorded_status" => "running",
      "worker" => worker
    }

    value
    |> Map.put("worker", worker)
    |> Map.put("worker_observation", Map.put(value["worker_observation"], "worker", worker))
    |> Map.put("lifecycle_observation", Map.merge(observation, changes))
  end

  test "explicit observed lifecycle windows preserve role and separate effect authority" do
    for {purpose, worker, stages} <- [
          {"native_initial_enrollment", "maintenance", ["migrate", "bootstrap"]},
          {"native_initial_enrollment", "native", ["verify", "activate", "enroll"]},
          {"native_upgrade_execution", "maintenance", ["migrate"]},
          {"native_upgrade_execution", "native", ["verify", "activate", "public_verify"]}
        ],
        stage <- stages do
      value = lifecycle_output(worker, %{"purpose" => purpose, "stage" => stage})
      assert Admission.validate(value, @installation, worker, 42) == :ok
      assert value["lifecycle_responsibility_admitted"] === false
      assert value["writer_exclusion_established"] === false
      assert value["installation_readiness_established"] === false
    end
  end

  test "malformed, unknown, uncertain and foreign-generation lifecycle observations refuse" do
    for changes <- [
          %{"operation" => @installation},
          %{"operation" => "00000000-0000-0000-0000-000000000000"},
          %{"operation" => "foreign"},
          %{"candidate" => true},
          %{"candidate" => String.duplicate("x", 40)},
          %{"request_sha256" => "short"},
          %{"epoch" => 0},
          %{"epoch" => true},
          %{"epoch" => 1.0},
          %{"epoch" => 18_446_744_073_709_551_616},
          %{"worker" => "maintenance"},
          %{"purpose" => "unknown"},
          %{"recorded_status" => "pending"},
          %{"recorded_status" => "uncertain"},
          %{"generation_sha256" => String.duplicate("f", 64)},
          %{"stage" => "bootstrap"},
          %{"path" => "/tmp/caller-inputs"}
        ] do
      assert Admission.validate(lifecycle_output("native", changes), @installation, "native", 42) ==
               {:error, :invalid_generation_admission}
    end

    for observation <- [
          nil,
          %{},
          Map.delete(lifecycle_output("native")["lifecycle_observation"], "snapshot_sha256")
        ] do
      assert Admission.validate(
               Map.put(output(), "lifecycle_observation", observation),
               @installation,
               "native",
               42
             ) ==
               {:error, :invalid_generation_admission}
    end
  end

  test "terminal ancestor metadata keeps original generation without reviving maintenance" do
    value =
      lifecycle_output("native", %{
        "recorded_status" => "complete",
        "stage" => "enroll",
        "generation_sha256" => String.duplicate("f", 64)
      })

    assert Admission.validate(value, @installation, "native", 42) == :ok
    assert value["lifecycle_responsibility_admitted"] === false

    assert Admission.validate(
             lifecycle_output("maintenance", %{
               "recorded_status" => "complete",
               "stage" => "enroll"
             }),
             @installation,
             "maintenance",
             42
           ) == {:error, :invalid_generation_admission}

    assert Admission.validate(
             lifecycle_output("native", %{"recorded_status" => "complete", "stage" => "verify"}),
             @installation,
             "native",
             42
           ) == {:error, :invalid_generation_admission}
  end

  test "fixed initial observation preserves separate lease and readiness authority" do
    assert Admission.validate(output(), @installation, "native", 42) == :ok

    assert Admission.validate(output(), @installation, "native", 43) ==
             {:error, :invalid_generation_admission}

    assert Admission.validate(output(), @installation, "maintenance", 42) ==
             {:error, :invalid_generation_admission}
  end

  test "closed response and typed flags reject extensions and forged authority" do
    for changed <- [
          nil,
          Map.delete(output(), "database"),
          Map.put(output(), "extra", true),
          %{output() | "protocol" => true},
          %{output() | "published_generation_admitted" => 1},
          %{output() | "writer_exclusion_established" => true},
          %{output() | "installation_readiness_established" => true},
          %{output() | "lifecycle_responsibility_admitted" => true}
        ] do
      assert Admission.validate(changed, @installation, "native", 42) ==
               {:error, :invalid_generation_admission}
    end
  end

  test "foreign pointer, owner, scope, seal and malformed digests refuse" do
    for changed <- [
          %{output() | "pointer" => %{"protocol" => 2, "installation" => "foreign"}},
          %{output() | "worker_observation" => %{}},
          %{output() | "binding_sha256" => String.duplicate("x", 64)},
          %{output() | "seal_file" => %{"path" => "/tmp/seal"}},
          %{output() | "worker_observation" => nil}
        ] do
      assert Admission.validate(changed, @installation, "native", 42) ==
               {:error, :invalid_generation_admission}
    end
  end

  test "unsupported roots and modes refuse before launching a helper" do
    for root <- [
          nil,
          "/tmp/storage",
          "/var/lib/gitgood/installations/../storage",
          "/var/lib/gitgood/installations/" <> @installation <> "/storage/"
        ] do
      assert Admission.admit(root, :runtime) == {:error, :installation_generation_unavailable}
    end

    assert Admission.admit(
             "/var/lib/gitgood/installations/" <> @installation <> "/storage",
             :unknown
           ) == {:error, :installation_generation_unavailable}
  end
end
