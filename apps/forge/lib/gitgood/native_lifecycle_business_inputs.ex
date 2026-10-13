defmodule Gitgood.NativeLifecycleBusinessInputs do
  @moduledoc "Validate private fixed-action data from the original attached generation monitor."

  @fields ~w(protocol kind installation operation candidate action migrations)

  @doc false
  def window?(admission, action) when action in [:migrate, :bootstrap] do
    observed = admission["lifecycle_observation"]

    admission["worker"] === "maintenance" and is_map(observed) and
      observed["worker"] === "maintenance" and observed["recorded_status"] === "running" and
      observed["stage"] === Atom.to_string(action) and
      (action === :migrate or observed["purpose"] === "native_initial_enrollment")
  rescue
    _ -> false
  end

  def window?(_, _), do: false

  @doc false
  def validate(inputs, admission, action) do
    fields =
      if action === :bootstrap,
        do: @fields ++ ~w(bootstrap bootstrap_request_sha256),
        else: @fields

    with true <- window?(admission, action),
         true <- closed?(inputs, fields),
         true <- inputs["protocol"] === 2 and inputs["kind"] === "native_private_business_inputs",
         observed <- admission["lifecycle_observation"],
         true <- inputs["installation"] === admission["installation"],
         true <-
           inputs["operation"] === observed["operation"] and
             inputs["candidate"] === observed["candidate"],
         true <- inputs["action"] === Atom.to_string(action),
         true <- migrations?(inputs["migrations"], observed["purpose"]),
         true <- bootstrap?(inputs, action) do
      :ok
    else
      _ -> :error
    end
  rescue
    _ -> :error
  end

  defp migrations?(value, purpose) do
    closed?(value, ~w(before_versions target_versions)) and
      versions?(value["before_versions"]) and versions?(value["target_versions"]) and
      value["target_versions"] !== [] and
      MapSet.subset?(MapSet.new(value["before_versions"]), MapSet.new(value["target_versions"])) and
      case purpose do
        "native_initial_enrollment" -> value["before_versions"] === []
        "native_upgrade_execution" -> true
        _ -> false
      end
  end

  defp versions?(value) when is_list(value) and length(value) <= 1024,
    do:
      Enum.all?(value, &(is_integer(&1) and &1 > 0 and &1 < 9_223_372_036_854_775_808)) and
        value === Enum.sort(Enum.uniq(value))

  defp versions?(_), do: false

  defp bootstrap?(inputs, :bootstrap) do
    params = inputs["bootstrap"]

    with true <- is_map(params),
         true <-
           params["installation"] === inputs["installation"] and
             params["request"] === inputs["operation"],
         password when is_binary(password) <- params["password"],
         false <- String.contains?(password, <<0>>),
         {:ok, _} <-
           Gitgood.InstallationOwnerBootstrap.validate(params, inputs["bootstrap_request_sha256"]) do
      true
    else
      _ -> false
    end
  end

  defp bootstrap?(_, :migrate), do: true

  defp closed?(value, fields),
    do: is_map(value) and MapSet.new(Map.keys(value)) === MapSet.new(fields)
end
