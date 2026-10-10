defmodule Gitgood.InstallationGenerationMonitorTest do
  use ExUnit.Case, async: true
  alias Gitgood.InstallationGenerationMonitor, as: Monitor

  defp guard do
    Map.new(
      ~w(scope_sha256 history_sha256 persistent_files_sha256),
      &{&1, String.duplicate("a", 64)}
    )
  end

  defp current, do: %{"protocol" => 2, "status" => "current", "guard" => guard()}

  defp state(age \\ 0) do
    %{
      port: :fixture_port,
      guard: guard(),
      buffer: <<>>,
      admission: %{},
      observed_at: System.monotonic_time(:millisecond) - age
    }
  end

  test "valid initial response remains bound to installation, role and actual owner" do
    installation = "00000000-0000-4000-8000-000000000001"

    admission = %{
      "protocol" => 2,
      "installation" => installation,
      "worker" => "native",
      "pointer" => %{
        "protocol" => 2,
        "installation" => installation,
        "operation" => installation,
        "generation_sha256" => String.duplicate("a", 64),
        "transition_sha256" => String.duplicate("b", 64)
      },
      "binding_sha256" => String.duplicate("c", 64),
      "database" => %{},
      "worker_observation" => %{
        "worker" => "native",
        "owner" => %{"pid" => 42, "birth" => "420"},
        "service_scope" => %{
          "protocol" => 2,
          "installation" => installation,
          "service_scope_observed" => true
        }
      },
      "seal_file" => %{
        "path" =>
          "/etc/gitgood/installations/" <> installation <> "/generation-admission-v2.json",
        "device" => 1,
        "inode" => 2,
        "bytes" => 300,
        "sha256" => String.duplicate("d", 64)
      },
      "published_generation_admitted" => true,
      "writer_exclusion_established" => false,
      "installation_readiness_established" => false,
      "lifecycle_responsibility_admitted" => false
    }

    value = %{
      "protocol" => 2,
      "status" => "admitted",
      "guard" => guard(),
      "admission" => admission
    }

    assert Monitor.validate_initial(value, installation, "native", 42) == :ok
    assert Monitor.validate_initial(value, installation, "native", 43) == :error
    assert Monitor.validate_initial(value, installation, "maintenance", 42) == :error
    assert Monitor.validate_initial(value, "foreign", "native", 42) == :error
  end

  test "a partial frame cannot renew heartbeat freshness" do
    original = state()
    bytes = Jason.encode!(current())
    assert {:noreply, partial} = Monitor.handle_info({:fixture_port, {:data, bytes}}, original)
    assert partial.observed_at == original.observed_at
    assert {:noreply, complete} = Monitor.handle_info({:fixture_port, {:data, "\n"}}, partial)
    assert complete.buffer == <<>>
  end

  test "ownership context returns the original admission and token together while fresh" do
    original = %{state() | admission: %{"binding_sha256" => String.duplicate("c", 64)}}

    assert Monitor.handle_call(:ownership_context, nil, original) ==
             {:reply, {:ok, %{admission: original.admission, guard: original.guard}}, original}
  end

  test "a late valid heartbeat cannot revive a stale monitor" do
    original = state(4_000)

    assert Monitor.handle_info(
             {:fixture_port, {:data, Jason.encode!(current()) <> "\n"}},
             original
           ) ==
             {:stop, :installation_generation_lost, original}

    assert Monitor.handle_call(:current, nil, original) ==
             {:stop, :installation_generation_lost, {:error, :installation_generation_lost},
              original}

    assert Monitor.handle_call(:admission, nil, original) ==
             {:stop, :installation_generation_lost, {:error, :installation_generation_lost},
              original}

    assert Monitor.handle_call(:ownership_context, nil, original) ==
             {:stop, :installation_generation_lost, {:error, :installation_generation_lost},
              original}
  end

  test "oversized or malformed stream frames stop without adopting their content" do
    original = state()

    for bytes <- [
          String.duplicate("x", 16_386),
          "invalid\n",
          Jason.encode!(%{current() | "guard" => %{}}) <> "\n"
        ] do
      assert Monitor.handle_info({:fixture_port, {:data, bytes}}, original) ==
               {:stop, :installation_generation_lost, original}
    end
  end

  test "helper termination stops the monitor without claiming freshness" do
    original = state()

    assert Monitor.handle_info({:fixture_port, {:exit_status, 1}}, original) ==
             {:stop, :installation_generation_lost, original}
  end

  test "heartbeat must match the captured complete token" do
    assert Monitor.validate_current(current(), guard()) == :ok

    for field <- Map.keys(guard()) do
      changed = put_in(current(), ["guard", field], String.duplicate("b", 64))
      assert Monitor.validate_current(changed, guard()) == :error
    end
  end

  test "closed heartbeat rejects authority extensions and status changes" do
    for value <- [
          nil,
          %{},
          Map.put(current(), "writer_exclusion_established", true),
          %{current() | "protocol" => true},
          %{current() | "status" => "admitted"},
          %{current() | "status" => "refused"}
        ] do
      assert Monitor.validate_current(value, guard()) == :error
    end
  end

  test "malformed captured tokens cannot authorize a heartbeat" do
    for value <- [
          nil,
          %{},
          Map.delete(guard(), "scope_sha256"),
          Map.put(guard(), "extra", "value"),
          Map.put(guard(), "scope_sha256", String.duplicate("x", 64)),
          Map.put(guard(), "scope_sha256", true)
        ] do
      assert Monitor.validate_current(%{current() | "guard" => value}, value) == :error
    end
  end

  test "initial admission requires closed generation and actual owner validation" do
    for value <- [
          nil,
          %{},
          %{"protocol" => 2, "status" => "admitted", "guard" => guard(), "admission" => %{}}
        ] do
      assert Monitor.validate_initial(value, "00000000-0000-4000-8000-000000000001", "native", 42) ==
               :error
    end
  end

  test "unsupported root or mode refuses before the fixed helper opens" do
    Process.flag(:trap_exit, true)

    assert Monitor.start_link(root: "/tmp/storage", mode: :runtime) ==
             {:error, :installation_generation_unavailable}

    assert Monitor.start_link(
             root: "/var/lib/gitgood/installations/00000000-0000-4000-8000-000000000001/storage",
             mode: :unknown
           ) == {:error, :installation_generation_unavailable}
  end
end
