defmodule Gitgood.NativeLifecycleAction do
  @moduledoc "Match a fixed requested action to the original guarded lifecycle window."

  def mode(:runtime), do: {:ok, :runtime}
  def mode(action) when action in [:migrate, :bootstrap], do: {:ok, :migrate}
  def mode(_), do: :error

  @doc false
  def validate(admission, authority, action) do
    with {:ok, mode} <- mode(action),
         true <- is_map(admission) and is_map(authority),
         true <-
           MapSet.new(Map.keys(authority)) ==
             MapSet.new(~w(protocol kind installation operation candidate binding_sha256)),
         true <-
           authority["protocol"] === 3 and
             authority["kind"] === "native_application_ownership_seal",
         installation when is_binary(installation) <- authority["installation"],
         worker <- if(mode == :runtime, do: "native", else: "maintenance"),
         owner when is_integer(owner) <- admission["worker_observation"]["owner"]["pid"],
         true <- owner > 1 and owner < 2_147_483_648,
         :ok <-
           Gitgood.InstallationGenerationAdmission.validate(
             admission,
             installation,
             worker,
             owner
           ),
         observed when is_map(observed) <- admission["lifecycle_observation"],
         true <-
           observed["operation"] === authority["operation"] and
             observed["candidate"] === authority["candidate"],
         true <- admission["binding_sha256"] === authority["binding_sha256"],
         true <- window?(observed, action) do
      :ok
    else
      _ -> :error
    end
  rescue
    _ -> :error
  end

  defp window?(observed, :migrate),
    do: observed["recorded_status"] === "running" and observed["stage"] === "migrate"

  defp window?(observed, :bootstrap),
    do:
      observed["purpose"] === "native_initial_enrollment" and
        observed["recorded_status"] === "running" and observed["stage"] === "bootstrap"

  # The generation decoder already checked the fixed native windows and any
  # terminal ancestor. This check neither relabels history nor grants effects.
  defp window?(_, :runtime), do: true
end
