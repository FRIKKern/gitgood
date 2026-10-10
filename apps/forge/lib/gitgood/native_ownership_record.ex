defmodule Gitgood.NativeOwnershipRecord do
  @moduledoc "Assemble a claim from captured observations; construction grants no live authority."

  alias Gitgood.NativeOwnershipPublication, as: Publication
  @uuid ~r/\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\z/
  @candidate ~r/\A[0-9a-f]{40}\z/
  @digest ~r/\A[0-9a-f]{64}\z/
  @failure {:error, :native_ownership_record_unavailable}

  # The protected publisher independently verifies the actual Root seal,
  # generation, original owner/socket/session and storage before any retention.
  # In particular, a map passed as `seal` does not establish Root custody.
  def build(context, session, seal, mode) do
    owner_pid = String.to_integer(System.pid())

    with true <- closed?(context, [:admission, :guard]),
         {:ok, worker} <- worker(mode),
         true <-
           closed?(seal, ~w(protocol kind installation operation candidate binding_sha256)),
         true <-
           seal["protocol"] === 2 and seal["kind"] === "native_application_ownership_seal",
         true <- matches?(@uuid, seal["installation"]) and matches?(@uuid, seal["operation"]),
         true <-
           matches?(@candidate, seal["candidate"]) and matches?(@digest, seal["binding_sha256"]),
         :ok <-
           Gitgood.InstallationGenerationAdmission.validate(
             context.admission,
             seal["installation"],
             worker,
             owner_pid
           ),
         true <- context.admission["binding_sha256"] === seal["binding_sha256"],
         true <-
           seal["operation"] not in [
             seal["installation"],
             context.admission["pointer"]["operation"]
           ],
         true <- valid_session?(session, context.admission["database"]),
         observation <- context.admission["worker_observation"],
         true <- owner_scope_matches?(observation),
         true <- closed?(context.guard, ~w(scope_sha256 history_sha256 persistent_files_sha256)),
         true <- Enum.all?(Map.values(context.guard), &matches?(@digest, &1)),
         true <-
           context.guard["scope_sha256"] ===
             digest(%{
               "scope" => observation["service_scope"],
               "owner" => observation["owner"],
               "worker" => worker
             }),
         record <- %{
           "protocol" => 2,
           "kind" => "native_application_ownership",
           "installation" => seal["installation"],
           "operation" => seal["operation"],
           "candidate" => seal["candidate"],
           "mode" => Atom.to_string(mode),
           "binding_sha256" => seal["binding_sha256"],
           "pointer" => context.admission["pointer"],
           "scope" => observation["service_scope"],
           "owner" => observation["owner"],
           "database_session" => session,
           "guard" => context.guard
         },
         {:ok, _, _} <- Publication.request(record, owner_pid) do
      {:ok, record}
    else
      _ -> @failure
    end
  rescue
    _ -> @failure
  end

  defp worker(:runtime), do: {:ok, "native"}
  defp worker(mode) when mode in [:backup, :restore, :migrate], do: {:ok, "maintenance"}
  defp worker(_), do: :error

  defp valid_session?(session, database) do
    closed?(session, ~w(database backend_pid backend_birth)) and
      session["database"] === database and
      Gitgood.InstallationDatabaseSession.validate_database(database) === :ok and
      is_integer(session["backend_pid"]) and session["backend_pid"] in 1..2_147_483_647 and
      is_binary(session["backend_birth"]) and
      Regex.match?(~r/\A[1-9][0-9]{0,19}\z/, session["backend_birth"]) and
      String.to_integer(session["backend_birth"]) < 18_446_744_073_709_551_616
  end

  defp closed?(value, fields),
    do: is_map(value) and MapSet.new(Map.keys(value)) === MapSet.new(fields)

  defp owner_scope_matches?(observation) do
    owner = observation["owner"]
    scope = observation["service_scope"]

    is_integer(owner["uid"]) and owner["uid"] in 1..4_294_967_295 and
      owner["uid"] === scope["uid"] and owner["pid"] !== scope["manager"]["pid"] and
      Enum.all?(~w(mount_namespace cgroup_namespace), &(owner[&1] === scope["manager"][&1]))
  end

  defp matches?(pattern, value), do: is_binary(value) and Regex.match?(pattern, value)

  defp digest(value),
    do: :crypto.hash(:sha256, Publication.canonical(value)) |> Base.encode16(case: :lower)
end
