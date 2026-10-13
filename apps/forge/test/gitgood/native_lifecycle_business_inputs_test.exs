defmodule Gitgood.NativeLifecycleBusinessInputsTest do
  use ExUnit.Case, async: true
  alias Gitgood.NativeLifecycleBusinessInputs, as: Inputs
  alias Gitgood.InstallationGenerationMonitor, as: Monitor

  defp admission(stage \\ "migrate") do
    %{
      "installation" => "11111111-1111-4111-8111-111111111111",
      "worker" => "maintenance",
      "lifecycle_observation" => %{
        "operation" => "22222222-2222-4222-8222-222222222222",
        "candidate" => String.duplicate("b", 40),
        "worker" => "maintenance",
        "stage" => stage,
        "recorded_status" => "running",
        "purpose" => "native_initial_enrollment"
      }
    }
  end

  defp inputs(action \\ "migrate") do
    base = %{
      "protocol" => 2,
      "kind" => "native_private_business_inputs",
      "installation" => admission()["installation"],
      "operation" => admission()["lifecycle_observation"]["operation"],
      "candidate" => String.duplicate("b", 40),
      "action" => action,
      "migrations" => %{"before_versions" => [], "target_versions" => [1, 2]}
    }

    if action == "bootstrap" do
      Map.merge(base, %{
        "bootstrap" => %{
          "installation" => base["installation"],
          "request" => base["operation"],
          "username" => "owner",
          "team" => "pilot",
          "password" => "synthetic-secret-éé"
        },
        "bootstrap_request_sha256" =>
          "7c88ecc40ded65bf7c1b507bd8712a6c61c5e8afac39177aec4689cf56444fc2"
      })
    else
      base
    end
  end

  test "private data remains fixed to the original stage and identity" do
    assert :ok = Inputs.validate(inputs(), admission(), :migrate)
    assert :ok = Inputs.validate(inputs("bootstrap"), admission("bootstrap"), :bootstrap)

    for {key, value} <- [
          {"candidate", String.duplicate("c", 40)},
          {"operation", admission()["installation"]},
          {"protocol", true},
          {"action", "bootstrap"},
          {"command", "shell"}
        ] do
      assert :error = Inputs.validate(Map.put(inputs(), key, value), admission(), :migrate)
    end

    assert :error = Inputs.validate(inputs(), admission("bootstrap"), :migrate)
    assert :error = Inputs.validate(inputs(), admission(), :runtime)
    terminal = put_in(admission(), ["lifecycle_observation", "recorded_status"], "complete")
    assert :error = Inputs.validate(inputs(), terminal, :migrate)
  end

  test "bootstrap rejects role overrides changed password or digest and nul" do
    for {key, value} <- [
          {"password", "changed-synthetic-secret"},
          {"password", "synthetic-secret\0"},
          {"role", "owner"},
          {"request", admission()["installation"]}
        ] do
      changed = put_in(inputs("bootstrap"), ["bootstrap", key], value)
      assert :error = Inputs.validate(changed, admission("bootstrap"), :bootstrap)
    end

    assert :error =
             Inputs.validate(
               Map.put(
                 inputs("bootstrap"),
                 "bootstrap_request_sha256",
                 String.duplicate("a", 64)
               ),
               admission("bootstrap"),
               :bootstrap
             )

    assert :error =
             Inputs.validate(
               Map.put(inputs(), "bootstrap", inputs("bootstrap")["bootstrap"]),
               admission(),
               :migrate
             )
  end

  test "migration expectations are bounded ordered and forward only" do
    for target <- [
          [],
          [true],
          [0],
          [-1],
          [9_223_372_036_854_775_808],
          [2, 1],
          [1, 1],
          Enum.to_list(1..1025)
        ] do
      changed = put_in(inputs(), ["migrations", "target_versions"], target)
      assert :error = Inputs.validate(changed, admission(), :migrate)
    end

    upgrade =
      put_in(admission(), ["lifecycle_observation", "purpose"], "native_upgrade_execution")

    forward = put_in(inputs(), ["migrations", "before_versions"], [1])
    assert :ok = Inputs.validate(forward, upgrade, :migrate)
    assert :error = Inputs.validate(forward, admission(), :migrate)

    assert :error =
             Inputs.validate(
               put_in(forward, ["migrations", "target_versions"], [2]),
               upgrade,
               :migrate
             )

    assert :error =
             Inputs.validate(
               inputs("bootstrap"),
               put_in(upgrade, ["lifecycle_observation", "stage"], "bootstrap"),
               :bootstrap
             )
  end

  defp guarded_state(action, tag, deadline \\ System.monotonic_time(:millisecond) + 3_000) do
    %{
      port: :fixture_port,
      guard: %{"scope_sha256" => String.duplicate("a", 64)},
      buffer: <<>>,
      admission: admission(Atom.to_string(action)),
      ownership: %{"record_sha256" => String.duplicate("d", 64)},
      ownership_pending: nil,
      observed_at: System.monotonic_time(:millisecond),
      business_used: true,
      business_pending: %{
        from: {self(), tag},
        action: action,
        reference: make_ref(),
        deadline: deadline
      }
    }
  end

  defp reply(state, action) do
    %{
      "protocol" => 2,
      "status" => "private_business_inputs",
      "guard" => state.guard,
      "ownership" => state.ownership,
      "inputs" => inputs(Atom.to_string(action))
    }
  end

  test "private frame is accepted once after original guard ownership and stage match" do
    tag = make_ref()
    state = guarded_state(:bootstrap, tag)
    raw = Gitgood.NativeOwnershipPublication.canonical(reply(state, :bootstrap)) <> "\n"
    split = div(byte_size(raw), 2)
    <<first::binary-size(split), rest::binary>> = raw
    assert {:noreply, partial} = Monitor.handle_info({:fixture_port, {:data, first}}, state)
    refute_receive {^tag, _}
    assert {:noreply, complete} = Monitor.handle_info({:fixture_port, {:data, rest}}, partial)
    assert_receive {^tag, {:ok, received}}
    assert received == inputs("bootstrap")
    refute Map.has_key?(complete, :business_reply)
    assert complete.business_pending == nil and complete.business_used

    assert {:stop, :installation_generation_lost, _} =
             Monitor.handle_info({:fixture_port, {:data, raw}}, complete)
  end

  test "changed late unsolicited and pipelined invalid frames cannot emit credentials" do
    tag = make_ref()
    state = guarded_state(:bootstrap, tag)

    for changed <- [
          Map.put(reply(state, :bootstrap), "guard", %{}),
          Map.put(reply(state, :bootstrap), "ownership", %{}),
          Map.put(reply(state, :bootstrap), "callback", "shell")
        ] do
      raw = Gitgood.NativeOwnershipPublication.canonical(changed) <> "\n"

      assert {:stop, :installation_generation_lost, _} =
               Monitor.handle_info({:fixture_port, {:data, raw}}, state)

      refute_receive {^tag, _}
    end

    raw = Gitgood.NativeOwnershipPublication.canonical(reply(state, :bootstrap)) <> "\n"
    late = guarded_state(:bootstrap, tag, System.monotonic_time(:millisecond) - 1)

    assert {:stop, :installation_generation_lost, _} =
             Monitor.handle_info({:fixture_port, {:data, raw}}, late)

    assert {:stop, :installation_generation_lost, _} =
             Monitor.handle_info({:fixture_port, {:data, raw <> "{}\n"}}, state)

    refute_receive {^tag, _}
  end

  test "native status callbacks redact private state messages reasons and debug log" do
    secret = "synthetic-private-status-secret"

    status = %{
      state: %{buffer: secret},
      message: {:data, secret},
      reason: {:invalid, secret},
      log: [secret],
      pid: self()
    }

    for module <- [Monitor, Gitgood.NativeOwnershipStartup] do
      redacted = module.format_status(status)
      assert Map.keys(redacted) == Map.keys(status)
      assert redacted.pid == self()
      refute inspect(redacted) =~ secret
      assert redacted.log == []
    end
  end
end
