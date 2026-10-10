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
