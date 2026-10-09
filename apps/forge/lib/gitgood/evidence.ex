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

  @history_page 20
  @event_page 25

  def validate_input(params), do: parameters(params)

  def validate_reason(reason),
    do: if(text?(reason, 1000), do: :ok, else: {:error, :invalid_evidence})

  def resolve_request(repository, pull, user, credential, link_id, payload, key) do
    writer(repository, pull, user, credential, fn ->
      key = Lease.key!(key)
      link = link!(pull, link_id)

      case payload do
        %{"kind" => "attach", "body" => body} ->
          case Repo.get_by(CriterionEvidence,
                 source_link_id: link.id,
                 actor_id: user.id,
                 creation_key: key
               ) do
            nil ->
              :absent

            row ->
              if(row.request_digest == Lease.digest(Jason.decode!(body)),
                do: receipt(row),
                else: :conflict
              )
          end

        %{"kind" => "unavailable", "evidence_id" => id, "body" => body} ->
          row = Repo.get_by(CriterionEvidence, public_id: id, source_link_id: link.id)
          digest = Lease.digest(["artifact_unavailable", id, Jason.decode!(body)["reason"]])

          case row &&
                 Repo.get_by(CriterionEvidenceEvent,
                   evidence_id: row.id,
                   actor_id: user.id,
                   request_key: key
                 ) do
            nil ->
              :absent

            event ->
              if event.request_digest == digest,
                do: %{"id" => row.public_id, "artifact_unavailable_recorded" => true},
                else: :conflict
          end
      end
    end)
  end

  def list(repository, pull, user, credential, link_id, connection_generation, cursor \\ nil) do
    with {:ok, source} <-
           SourceLinks.read(repository, pull, user, credential, link_id, connection_generation) do
      if source["source_state"] == "available" && is_list(source["criteria"]) do
        with {:ok, revisions} <- Pulls.revisions(repository, pull),
             {:ok, view} <-
               authorized(repository, pull, user, credential, source, fn ->
                 {rows, next_cursor} = records(source["id"], cursor)
                 latest = latest(source["id"])
                 counts = event_counts(rows ++ latest)
                 events = record_events(rows)
                 public = Enum.map(rows, &public(&1, source, revisions, counts, events))
                 newest = Map.new(latest, &{&1.criterion_index, &1})

                 criteria =
                   Enum.map(source["criteria"], fn criterion ->
                     row = newest[criterion["index"]]

                     Map.merge(criterion, %{
                       "state" =>
                         if(row, do: state(row, source, revisions, counts), else: "absent"),
                       "evidence_id" => if(row, do: row.public_id, else: nil)
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
                   "records" => public,
                   "history" => %{
                     "total" =>
                       Repo.aggregate(
                         from(e in CriterionEvidence, where: e.source_link_id == ^source["id"]),
                         :count
                       ),
                     "next_cursor" => next_cursor
                   }
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

  def event_history(
        repository,
        pull,
        user,
        credential,
        link_id,
        evidence_id,
        generation,
        cursor \\ nil
      ) do
    with {:ok, source} <-
           SourceLinks.read(repository, pull, user, credential, link_id, generation),
         true <- source["source_state"] == "available" && is_list(source["criteria"]) do
      authorized(repository, pull, user, credential, source, fn ->
        row = find!(source["id"], evidence_id)
        position = event_position!(row.id, cursor)

        events =
          Repo.all(
            from(e in CriterionEvidenceEvent,
              where: e.evidence_id == ^row.id and e.id > ^position,
              order_by: [asc: e.id],
              limit: ^(@event_page + 1)
            )
          )

        page = Enum.take(events, @event_page)

        %{
          "source" =>
            Map.take(source, ["id", "generation", "connection_generation", "source_state"]),
          "events" => Enum.map(page, &public_event/1),
          "total" => Map.get(event_counts([row]), row.id, 0),
          "next_cursor" =>
            if(length(events) > @event_page, do: Integer.to_string(List.last(page).id), else: nil)
        }
      end)
    else
      false -> {:error, :evidence_source_unavailable}
      error -> error
    end
  end

  def attach(repository, pull, user, credential, link_id, params, key) do
    with {:ok, preparation} <-
           writer(repository, pull, user, credential, fn ->
             key = Lease.key!(key)
             link = link!(pull, link_id)
             replay(link.id, user.id, key, Lease.digest(params)) || :new
           end) do
      case preparation do
        :new ->
          with :ok <- parameters(params),
               do: attach_new(repository, pull, user, credential, link_id, params, key)

        receipt ->
          {:ok, receipt}
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
        if unavailable?(row), do: Repo.rollback(:evidence_artifact_unavailable)

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
      if unavailable?(row), do: Repo.rollback(:evidence_artifact_unavailable)
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

  defp records(link, cursor) do
    position = if is_nil(cursor), do: nil, else: find!(link, cursor).id

    query =
      from(e in CriterionEvidence,
        where: e.source_link_id == ^link,
        order_by: [desc: e.id],
        limit: ^(@history_page + 1)
      )

    query = if position, do: from(e in query, where: e.id < ^position), else: query
    rows = Repo.all(query)
    page = Enum.take(rows, @history_page)
    {page, if(length(rows) > @history_page, do: List.last(page).public_id, else: nil)}
  end

  defp latest(link) do
    # Only binding/state fields are needed for current criteria; manifests and artifacts stay out.
    Repo.all(
      from(e in CriterionEvidence,
        where: e.source_link_id == ^link,
        distinct: e.criterion_index,
        order_by: [asc: e.criterion_index, desc: e.id],
        select:
          struct(e, [
            :id,
            :public_id,
            :criterion_index,
            :criterion_sha256,
            :link_generation,
            :source_revision,
            :source_sha,
            :target_sha,
            :outcome
          ])
      )
    )
  end

  defp event_counts([]), do: %{}

  defp event_counts(rows) do
    ids = Enum.uniq(Enum.map(rows, & &1.id))

    Map.new(
      Repo.all(
        from(e in CriterionEvidenceEvent,
          where: e.evidence_id in ^ids,
          group_by: e.evidence_id,
          select: {e.evidence_id, count(e.id)}
        )
      )
    )
  end

  defp unavailable?(row),
    do: Repo.exists?(from(e in CriterionEvidenceEvent, where: e.evidence_id == ^row.id))

  defp record_events([]), do: %{}

  defp record_events(rows) do
    ids = Enum.map(rows, & &1.id)

    ranked =
      from(e in CriterionEvidenceEvent,
        where: e.evidence_id in ^ids,
        windows: [record: [partition_by: e.evidence_id, order_by: e.id]],
        select: %{
          id: e.id,
          evidence_id: e.evidence_id,
          actor_id: e.actor_id,
          kind: e.kind,
          reason: e.reason,
          inserted_at: e.inserted_at,
          ordinal: over(row_number(), :record)
        }
      )

    Repo.all(
      from(e in subquery(ranked),
        where: e.ordinal <= ^@event_page,
        order_by: [asc: e.evidence_id, asc: e.id]
      )
    )
    |> Enum.group_by(& &1.evidence_id)
  end

  defp event_position!(_, nil), do: 0

  defp event_position!(evidence_id, cursor) when is_binary(cursor) and byte_size(cursor) <= 20 do
    case Integer.parse(cursor) do
      {position, ""} when position > 0 and position < 9_223_372_036_854_775_808 ->
        unless Integer.to_string(position) == cursor &&
                 Repo.exists?(
                   from(e in CriterionEvidenceEvent,
                     where: e.id == ^position and e.evidence_id == ^evidence_id
                   )
                 ),
               do: Repo.rollback(:invalid_evidence_cursor)

        position

      _ ->
        Repo.rollback(:invalid_evidence_cursor)
    end
  end

  defp event_position!(_, _), do: Repo.rollback(:invalid_evidence_cursor)

  defp state(row, source, revisions, counts) do
    criterion = Enum.find(source["criteria"], &(&1["index"] == row.criterion_index))

    stale =
      row.link_generation != source["generation"] || row.source_revision != source["revision"] ||
        is_nil(criterion) || criterion["sha256"] != row.criterion_sha256 ||
        row.source_sha != revisions.source_sha || row.target_sha != revisions.target_sha

    cond do
      Map.get(counts, row.id, 0) > 0 -> "unavailable"
      stale -> "stale"
      true -> row.outcome
    end
  end

  defp public(row, source, revisions, counts, events) do
    history = Map.get(events, row.id, [])
    total = Map.get(counts, row.id, 0)

    %{
      "id" => row.public_id,
      "criterion_index" => row.criterion_index,
      "criterion_sha256" => row.criterion_sha256,
      "source_revision" => row.source_revision,
      "source_sha" => row.source_sha,
      "target_sha" => row.target_sha,
      "outcome" => row.outcome,
      "state" => state(row, source, revisions, counts),
      "manifest" => row.manifest,
      "actor_id" => row.actor_id,
      "recorded_at" => DateTime.to_iso8601(row.inserted_at),
      "artifact" => %{
        "name" => row.artifact_name,
        "sha256" => row.artifact_sha256,
        "size" => row.artifact_size,
        "available" => total == 0
      },
      "events" => Enum.map(history, &public_event/1),
      "events_total" => total,
      "events_next_cursor" =>
        if(total > length(history), do: Integer.to_string(List.last(history).id), else: nil)
    }
  end

  defp public_event(event),
    do: %{
      "kind" => event.kind,
      "reason" => event.reason,
      "actor_id" => event.actor_id,
      "recorded_at" => DateTime.to_iso8601(event.inserted_at)
    }

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
        not String.contains?(value, <<0>>) && String.trim(value) != ""

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
        {:ok, time, 0} -> DateTime.compare(time, DateTime.utc_now()) != :gt
        _ -> false
      end
  end

  defp manifest?(_), do: false
end
