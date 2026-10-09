defmodule Gitgood.EvidenceIntents do
  @moduledoc "Actor-owned encrypted requests survive browser lifecycle changes without exposing draft bytes."
  import Ecto.Query

  alias Gitgood.{
    ConnectionSecrets,
    Evidence,
    EvidenceIntent,
    Lease,
    PullRequest,
    Repo,
    SourceLink
  }

  # Preparation records responsibility, not an assessment or permission grant.
  # Actual application still uses Evidence's current native/source authorization.
  def prepare(repository, pull, user, credential, link_id, params, key) do
    with {:ok, payload} <- payload(params) do
      actor(repository, pull, user, credential, link_id, fn link ->
        key = Lease.key!(key)
        digest = Lease.digest(payload)

        case Repo.get_by(EvidenceIntent,
               source_link_id: link.id,
               actor_id: user.id,
               creation_key: key
             ) do
          nil ->
            case Evidence.resolve_request(
                   repository,
                   pull,
                   user,
                   credential,
                   link_id,
                   payload,
                   key
                 ) do
              {:ok, :conflict} -> Repo.rollback(:idempotency_conflict)
              {:ok, _} -> :ok
              {:error, reason} -> Repo.rollback(reason)
            end

            case creation_input(payload) do
              :ok -> :ok
              {:error, reason} -> Repo.rollback(reason)
            end

            if Repo.exists?(
                 from(i in EvidenceIntent,
                   where:
                     i.source_link_id == ^link.id and i.actor_id == ^user.id and
                       i.state in ["pending", "confirmed"]
                 )
               ),
               do: Repo.rollback(:evidence_intent_pending)

            if Repo.aggregate(
                 from(i in EvidenceIntent,
                   where: i.source_link_id == ^link.id and i.actor_id == ^user.id
                 ),
                 :count
               ) >= 1000,
               do: Repo.rollback(:evidence_limit)

            row = %EvidenceIntent{
              public_id: Ecto.UUID.generate(),
              repository_id: repository.id,
              pull_request_id: pull.id,
              source_link_id: link.id,
              actor_id: user.id,
              creation_key: key,
              request_digest: digest
            }

            cipher =
              case ConnectionSecrets.seal(Jason.encode!(payload), payload_binding(row)) do
                {:ok, cipher} -> cipher
                _ -> Repo.rollback(:evidence_intent_unavailable)
              end

            row |> Ecto.Changeset.change(payload_cipher: cipher) |> Repo.insert!() |> public()

          row ->
            unless row.request_digest == digest, do: Repo.rollback(:idempotency_conflict)
            public(row)
        end
      end)
    end
  end

  def pending(repository, pull, user, credential, link_id) do
    actor(repository, pull, user, credential, link_id, fn link ->
      rows =
        Repo.all(
          from(i in EvidenceIntent,
            where:
              i.source_link_id == ^link.id and i.actor_id == ^user.id and
                i.state in ["pending", "confirmed"],
            order_by: i.id,
            limit: 1
          )
        )

      %{"intents" => Enum.map(rows, &public/1)}
    end)
  end

  def retry(repository, pull, user, credential, link_id, intent_id) do
    actor(repository, pull, user, credential, link_id, fn link ->
      row = find!(link, user, intent_id)

      case row.state do
        state when state in ["confirmed", "acknowledged"] ->
          Map.put(row.receipt, "intent_id", row.public_id)

        "retired" ->
          Repo.rollback(:evidence_intent_retired)

        "pending" ->
          case apply_request(repository, pull, user, credential, link_id, row, open!(row)) do
            {:ok, receipt} -> confirm!(row, receipt)
            {:error, reason} -> Repo.rollback(reason)
          end
      end
    end)
  end

  # The same repository lease spans retry and retirement. Resolve actual custody
  # before retirement; it cannot race an in-flight application or erase a success.
  def retire(repository, pull, user, credential, link_id, intent_id) do
    actor(repository, pull, user, credential, link_id, fn link ->
      row = find!(link, user, intent_id)

      case row.state do
        state when state in ["confirmed", "acknowledged"] ->
          Map.put(row.receipt, "intent_id", row.public_id)

        "retired" ->
          %{"id" => row.public_id, "intent_id" => row.public_id, "retired" => true}

        "pending" ->
          payload = open!(row)

          case Evidence.resolve_request(
                 repository,
                 pull,
                 user,
                 credential,
                 link_id,
                 payload,
                 row.creation_key
               ) do
            {:ok, missing} when missing in [:absent, :conflict] ->
              row |> Ecto.Changeset.change(state: "retired") |> Repo.update!()
              %{"id" => row.public_id, "intent_id" => row.public_id, "retired" => true}

            {:ok, receipt} ->
              confirm!(row, receipt)

            {:error, reason} ->
              Repo.rollback(reason)
          end
      end
    end)
  end

  defp confirm!(row, receipt) do
    row |> Ecto.Changeset.change(state: "confirmed", receipt: receipt) |> Repo.update!()
    Map.put(receipt, "intent_id", row.public_id)
  end

  def acknowledge(repository, pull, user, credential, link_id, intent_id) do
    actor(repository, pull, user, credential, link_id, fn link ->
      row = find!(link, user, intent_id)

      unless row.state in ["confirmed", "acknowledged"],
        do: Repo.rollback(:evidence_intent_pending)

      row |> Ecto.Changeset.change(state: "acknowledged") |> Repo.update!()
      %{"id" => row.public_id, "acknowledged" => true}
    end)
  end

  defp apply_request(repository, pull, user, credential, link, row, %{
         "kind" => "attach",
         "body" => body
       }),
       do:
         Evidence.attach(
           repository,
           pull,
           user,
           credential,
           link,
           Jason.decode!(body),
           row.creation_key
         )

  defp apply_request(repository, pull, user, credential, link, row, %{
         "kind" => "unavailable",
         "evidence_id" => id,
         "body" => body
       }),
       do:
         Evidence.unavailable(
           repository,
           pull,
           user,
           credential,
           link,
           id,
           Jason.decode!(body)["reason"],
           row.creation_key
         )

  defp payload(%{"kind" => "attach", "body" => body} = params) when map_size(params) == 2 do
    with {:ok, _} <- decode(body),
         do: {:ok, params}
  end

  defp payload(%{"kind" => "unavailable", "evidence_id" => id, "body" => body} = params)
       when map_size(params) == 3 do
    with {:ok, _} <- Ecto.UUID.cast(id),
         {:ok, %{"reason" => reason} = decoded} <- decode(body),
         true <- map_size(decoded) == 1,
         true <- is_binary(reason),
         do: {:ok, params},
         else: (_ -> {:error, :invalid_evidence})
  end

  defp payload(_), do: {:error, :invalid_evidence}

  defp creation_input(%{"kind" => "attach", "body" => body}),
    do: Evidence.validate_input(Jason.decode!(body))

  defp creation_input(%{"kind" => "unavailable", "body" => body}),
    do: Evidence.validate_reason(Jason.decode!(body)["reason"])

  defp decode(body) when is_binary(body) and byte_size(body) <= 524_288 do
    case Jason.decode(body) do
      {:ok, value} when is_map(value) -> {:ok, value}
      _ -> {:error, :invalid_evidence}
    end
  end

  defp decode(_), do: {:error, :invalid_evidence}

  defp actor(repository, pull, user, credential, link_id, action) do
    Lease.actor(repository, user, credential, ["owner", "writer"], fn current ->
      unless Repo.get_by(PullRequest, id: pull.id, repository_id: current.id),
        do: Repo.rollback(:evidence_not_found)

      with {:ok, id} <- Ecto.UUID.cast(link_id),
           %SourceLink{} = link <- Repo.get_by(SourceLink, id: id, pull_request_id: pull.id) do
        action.(link)
      else
        _ -> Repo.rollback(:evidence_not_found)
      end
    end)
  end

  defp find!(link, user, id) do
    with {:ok, id} <- Ecto.UUID.cast(id),
         %EvidenceIntent{} = row <-
           Repo.get_by(EvidenceIntent, public_id: id, source_link_id: link.id, actor_id: user.id),
         do: row,
         else: (_ -> Repo.rollback(:evidence_not_found))
  end

  defp open!(row) do
    cipher = Repo.one(from(i in EvidenceIntent, where: i.id == ^row.id, select: i.payload_cipher))

    with {:ok, bytes} <- ConnectionSecrets.open(cipher, payload_binding(row)),
         {:ok, payload} <- Jason.decode(bytes),
         true <- Lease.digest(payload) == row.request_digest,
         do: payload,
         else: (_ -> Repo.rollback(:evidence_intent_unavailable))
  end

  def recoverable_request?(%EvidenceIntent{} = row) do
    with {:ok, bytes} <- ConnectionSecrets.open(row.payload_cipher, payload_binding(row)),
         {:ok, payload} <- Jason.decode(bytes),
         true <- Lease.digest(payload) == row.request_digest do
      true
    else
      _ -> false
    end
  rescue
    _ -> false
  end

  defp payload_binding(row),
    do: [
      "evidence-intent-v1",
      row.public_id,
      row.repository_id,
      row.pull_request_id,
      row.source_link_id,
      row.actor_id,
      row.creation_key
    ]

  defp public(row), do: %{"id" => row.public_id, "state" => row.state}
end
