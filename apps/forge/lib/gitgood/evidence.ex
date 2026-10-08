defmodule Gitgood.Evidence do
  @moduledoc "Immutable producer evidence, observed against current requirement and Git revisions."
  import Ecto.Query

  alias Gitgood.{
    Accounts,
    CriterionEvidence,
    CriterionEvidenceEvent,
    Lease,
    PullRequest,
    Pulls,
    Repo,
    SourceLink,
    SourceLinks
  }

  def list(repository, pull, user, credential, link_id, connection_generation) do
    with {:ok, source} <-
           SourceLinks.read(repository, pull, user, credential, link_id, connection_generation) do
      if source["source_state"] == "available" && is_list(source["criteria"]) do
        with {:ok, revisions} <- Pulls.revisions(repository, pull),
             {:ok, view} <-
               authorized(repository, pull, user, credential, source, fn ->
                 rows = records(source["id"])
                 events = events(rows)
                 public = Enum.map(rows, &public(&1, source, revisions, events))

                 criteria =
                   Enum.map(source["criteria"], fn criterion ->
                     newest = Enum.find(public, &(&1["criterion_index"] == criterion["index"]))

                     Map.merge(criterion, %{
                       "state" => if(newest, do: newest["state"], else: "absent"),
                       "evidence_id" => if(newest, do: newest["id"], else: nil)
                     })
                   end)

                 %{
                   "source" =>
                     Map.take(source, [
                       "id",
                       "generation",
                       "connection_generation",
                       "source_state",
                       "revision"
                     ]),
                   "source_sha" => revisions.source_sha,
                   "target_sha" => revisions.target_sha,
                   "observed_at" => DateTime.to_iso8601(Accounts.now()),
                   "criteria" => criteria,
                   "records" => public
                 }
               end),
             do: {:ok, view}
      else
        {:ok,
         %{
           "source" => Map.take(source, ["id", "generation", "source_state"]),
           "criteria" => [],
           "records" => [],
           "profile" =>
             if(source["source_state"] == "available",
               do: "unsupported_criteria",
               else: "source_unavailable"
             )
         }}
      end
    end
  end

  def attach(repository, pull, user, credential, link_id, params, key) do
    with :ok <- parameters(params),
         {:ok, preparation} <-
           writer(repository, pull, user, credential, fn ->
             key = Lease.key!(key)
             link = link!(pull, link_id)
             replay(link.id, user.id, key, Lease.digest(params)) || :new
           end) do
      case preparation do
        :new -> attach_new(repository, pull, user, credential, link_id, params, key)
        receipt -> {:ok, receipt}
      end
    end
  end

  defp attach_new(repository, pull, user, credential, link_id, params, key) do
    with {:ok, source} <-
           SourceLinks.read(
             repository,
             pull,
             user,
             credential,
             link_id,
             params["connection_generation"]
           ),
         :ok <- matching_source(source, params),
         {:ok, receipt} <-
           writer(repository, pull, user, credential, fn ->
             case replay(source["id"], user.id, key, Lease.digest(params)) do
               nil ->
                 guard!(repository, pull, user, credential, source)
                 current = Repo.get!(PullRequest, pull.id)

                 revisions =
                   case Pulls.revisions(repository, current) do
                     {:ok, revisions} -> revisions
                     _ -> Repo.rollback(:evidence_revisions_unavailable)
                   end

                 unless revisions.source_sha == params["source_sha"] &&
                          revisions.target_sha == params["target_sha"],
                        do: Repo.rollback(:evidence_revision_changed)

                 if Repo.aggregate(
                      from(e in CriterionEvidence, where: e.source_link_id == ^source["id"]),
                      :count
                    ) >= 1000,
                    do: Repo.rollback(:evidence_limit)

                 artifact = params["artifact"]

                 row =
                   %CriterionEvidence{}
                   |> Ecto.Changeset.change(%{
                     repository_id: repository.id,
                     pull_request_id: pull.id,
                     source_link_id: source["id"],
                     link_generation: source["generation"],
                     actor_id: user.id,
                     credential_id: credential.id,
                     criterion_index: params["criterion_index"],
                     criterion_sha256: params["criterion_sha256"],
                     source_revision: source["revision"],
                     source_sha: revisions.source_sha,
                     target_sha: revisions.target_sha,
                     source_actor: source["source_actor"],
                     outcome: params["outcome"],
                     manifest: params["manifest"],
                     artifact_name: artifact["name"],
                     artifact_content: artifact["content"],
                     artifact_size: byte_size(artifact["content"]),
                     artifact_sha256: artifact["sha256"],
                     creation_key: key,
                     request_digest: Lease.digest(params)
                   })
                   |> Ecto.Changeset.validate_required([
                     :source_link_id,
                     :actor_id,
                     :source_revision,
                     :outcome,
                     :manifest,
                     :artifact_content
                   ])
                   |> Ecto.Changeset.unique_constraint([
                     :source_link_id,
                     :actor_id,
                     :creation_key
                   ])
                   |> Repo.insert!()

                 receipt(row)

               original ->
                 original
             end
           end),
         do: {:ok, receipt}
  end

  def unavailable(repository, pull, user, credential, link_id, evidence_id, reason, key) do
    if text?(reason, 1000) do
      writer(repository, pull, user, credential, fn ->
        key = Lease.key!(key)
        link = link!(pull, link_id)
        row = find!(link.id, evidence_id)
        digest = Lease.digest(["artifact_unavailable", evidence_id, reason])

        case Repo.get_by(CriterionEvidenceEvent,
               evidence_id: row.id,
               actor_id: user.id,
               request_key: key
             ) do
          nil ->
            if Repo.aggregate(
                 from(e in CriterionEvidenceEvent, where: e.evidence_id == ^row.id),
                 :count
               ) >= 1000,
               do: Repo.rollback(:evidence_limit)

            Repo.insert!(
              Ecto.Changeset.change(%CriterionEvidenceEvent{}, %{
                evidence_id: row.id,
                actor_id: user.id,
                credential_id: credential.id,
                kind: "artifact_unavailable",
                reason: reason,
                request_key: key,
                request_digest: digest
              })
            )

          event ->
            unless event.request_digest == digest, do: Repo.rollback(:idempotency_conflict)
        end

        %{"id" => row.public_id, "artifact_unavailable_recorded" => true}
      end)
    else
      {:error, :invalid_evidence}
    end
  end

  def download(repository, pull, user, credential, link_id, evidence_id, connection_generation) do
    with {:ok, source} <-
           SourceLinks.read(repository, pull, user, credential, link_id, connection_generation),
         true <- source["source_state"] == "available" && is_list(source["criteria"]) do
      authorized(repository, pull, user, credential, source, fn ->
        row = find!(source["id"], evidence_id)
        unless events([row]) == [], do: Repo.rollback(:evidence_artifact_unavailable)

        content =
          Repo.one(
            from(e in CriterionEvidence, where: e.id == ^row.id, select: e.artifact_content)
          )

        unless is_binary(content) && byte_size(content) == row.artifact_size &&
                 hash(content) == row.artifact_sha256,
               do: Repo.rollback(:evidence_artifact_unavailable)

        {Map.take(row, [:artifact_name, :artifact_sha256, :artifact_size]), content, source}
      end)
    else
      false -> {:error, :evidence_source_unavailable}
      error -> error
    end
  end

  def guard_artifact(repository, pull, user, credential, source, evidence_id) do
    authorized(repository, pull, user, credential, source, fn ->
      row = find!(source["id"], evidence_id)
      unless events([row]) == [], do: Repo.rollback(:evidence_artifact_unavailable)
      :current
    end)
  end

  defp matching_source(%{"source_state" => "connection_changed"}, _),
    do: {:error, :connection_changed}

  defp matching_source(source, params) do
    with "available" <- source["source_state"],
         criteria when is_list(criteria) <- source["criteria"],
         criterion when not is_nil(criterion) <-
           Enum.find(criteria, &(&1["index"] == params["criterion_index"])),
         true <-
           source["generation"] == params["link_generation"] &&
             source["revision"] == params["source_revision"] &&
             criterion["sha256"] == params["criterion_sha256"],
         do: :ok,
         else: (_ -> {:error, :evidence_requirement_changed})
  end

  defp records(link),
    do:
      Repo.all(
        from(e in CriterionEvidence,
          where: e.source_link_id == ^link,
          order_by: [desc: e.id],
          limit: 1000
        )
      )

  defp events([]), do: []

  defp events(rows),
    do:
      Repo.all(
        from(e in CriterionEvidenceEvent,
          where: e.evidence_id in ^Enum.map(rows, & &1.id),
          order_by: [asc: e.id]
        )
      )

  defp public(row, source, revisions, events) do
    history = Enum.filter(events, &(&1.evidence_id == row.id))
    criterion = Enum.find(source["criteria"], &(&1["index"] == row.criterion_index))

    stale =
      row.link_generation != source["generation"] || row.source_revision != source["revision"] ||
        is_nil(criterion) || criterion["sha256"] != row.criterion_sha256 ||
        row.source_sha != revisions.source_sha || row.target_sha != revisions.target_sha

    state =
      cond do
        history != [] -> "unavailable"
        stale -> "stale"
        true -> row.outcome
      end

    %{
      "id" => row.public_id,
      "criterion_index" => row.criterion_index,
      "criterion_sha256" => row.criterion_sha256,
      "source_revision" => row.source_revision,
      "source_sha" => row.source_sha,
      "target_sha" => row.target_sha,
      "outcome" => row.outcome,
      "state" => state,
      "manifest" => row.manifest,
      "actor_id" => row.actor_id,
      "recorded_at" => DateTime.to_iso8601(row.inserted_at),
      "artifact" => %{
        "name" => row.artifact_name,
        "sha256" => row.artifact_sha256,
        "size" => row.artifact_size,
        "available" => history == []
      },
      "events" =>
        Enum.map(
          history,
          &%{
            "kind" => &1.kind,
            "reason" => &1.reason,
            "actor_id" => &1.actor_id,
            "recorded_at" => DateTime.to_iso8601(&1.inserted_at)
          }
        )
    }
  end

  defp authorized(repository, pull, user, credential, source, action) do
    case SourceLinks.guard(
           repository,
           pull,
           user,
           credential,
           source["id"],
           source["generation"],
           source["connection_generation"]
         ) do
      {:ok, :current} ->
        # Keep the source connection and native permission locks for the complete projection.
        Gitgood.Access.with_session(user, credential, fn _ ->
          guard!(repository, pull, user, credential, source)
          action.()
        end)

      error ->
        error
    end
  end

  defp guard!(repository, pull, user, credential, source) do
    case SourceLinks.guard(
           repository,
           pull,
           user,
           credential,
           source["id"],
           source["generation"],
           source["connection_generation"]
         ) do
      {:ok, :current} -> :ok
      {:error, reason} -> Repo.rollback(reason)
    end
  end

  defp writer(repository, pull, user, credential, action),
    do:
      Lease.actor(repository, user, credential, ["owner", "writer"], fn current ->
        unless Repo.get_by(PullRequest, id: pull.id, repository_id: current.id),
          do: Repo.rollback(:evidence_not_found)

        action.()
      end)

  defp link!(pull, id) do
    case Ecto.UUID.cast(id) do
      {:ok, id} ->
        Repo.get_by(SourceLink, id: id, pull_request_id: pull.id) ||
          Repo.rollback(:evidence_not_found)

      _ ->
        Repo.rollback(:evidence_not_found)
    end
  end

  defp find!(link, id) do
    case Ecto.UUID.cast(id) do
      {:ok, id} ->
        Repo.get_by(CriterionEvidence, public_id: id, source_link_id: link) ||
          Repo.rollback(:evidence_not_found)

      _ ->
        Repo.rollback(:evidence_not_found)
    end
  end

  defp replay(link, actor, key, digest) do
    case Repo.get_by(CriterionEvidence, source_link_id: link, actor_id: actor, creation_key: key) do
      nil ->
        nil

      row ->
        unless row.request_digest == digest, do: Repo.rollback(:idempotency_conflict)
        receipt(row)
    end
  end

  defp receipt(row), do: %{"id" => row.public_id, "recorded" => true}
  defp hash(value), do: Base.encode16(:crypto.hash(:sha256, value), case: :lower)

  defp text?(value, bound),
    do:
      is_binary(value) && byte_size(value) in 1..bound && String.valid?(value) &&
        String.trim(value) != ""

  defp sha?(value, size),
    do: is_binary(value) && byte_size(value) == size && Regex.match?(~r/\A[0-9a-f]+\z/, value)

  defp uuid?(value), do: match?({:ok, _}, Ecto.UUID.cast(value))

  defp parameters(params) when is_map(params) do
    expected =
      ~w(artifact connection_generation criterion_index criterion_sha256 link_generation manifest outcome source_revision source_sha target_sha)

    valid =
      Enum.sort(Map.keys(params)) == expected && uuid?(params["connection_generation"]) &&
        uuid?(params["link_generation"]) &&
        is_integer(params["criterion_index"]) && params["criterion_index"] in 0..99 &&
        sha?(params["criterion_sha256"], 64) &&
        sha?(params["source_sha"], 40) && sha?(params["target_sha"], 40) &&
        text?(params["source_revision"], 128) &&
        params["outcome"] in ["passed", "failed", "inconclusive"] && manifest?(params["manifest"]) &&
        artifact?(params["artifact"])

    if valid, do: :ok, else: {:error, :invalid_evidence}
  end

  defp parameters(_), do: {:error, :invalid_evidence}

  defp artifact?(%{"name" => name, "content" => content, "sha256" => digest} = artifact) do
    map_size(artifact) == 3 && is_binary(name) &&
      Regex.match?(~r/\A[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}\z/, name) &&
      text?(content, 65536) && sha?(digest, 64) && hash(content) == digest
  end

  defp artifact?(_), do: false

  defp manifest?(
         %{
           "commands" => commands,
           "environment" => environment,
           "producer" => producer,
           "observed_at" => observed
         } = manifest
       ) do
    map_size(manifest) == 4 && is_list(commands) && length(commands) in 1..16 &&
      Enum.all?(commands, &text?(&1, 1024)) &&
      is_map(environment) && map_size(environment) in 1..16 &&
      Enum.all?(environment, fn {key, value} -> text?(key, 128) && text?(value, 512) end) &&
      text?(producer, 128) && is_binary(observed) && byte_size(observed) <= 64 &&
      case DateTime.from_iso8601(observed) do
        {:ok, time, 0} -> DateTime.compare(time, Accounts.now()) != :gt
        _ -> false
      end
  end

  defp manifest?(_), do: false
end
