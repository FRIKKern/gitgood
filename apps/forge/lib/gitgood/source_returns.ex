defmodule Gitgood.SourceReturns do
  @moduledoc "Durable, generation-bound Paper return-pointer responsibility."
  import Ecto.Query

  alias Gitgood.{
    Access,
    Accounts,
    BarkparkConnections,
    ConnectionSecrets,
    Credential,
    Lease,
    PaperReturnPointer,
    PullRequest,
    Repo,
    Repository,
    SourceLink,
    SourceReturnOperation,
    User
  }

  @pending ["queued", "prepared", "sending", "unknown"]

  def request(repository, pull, user, credential, id, params, key) do
    with {:ok, id} <- uuid(id),
         :ok <- parameters(params),
         {:ok, value} <-
           writer(repository, pull, user, credential, fn ->
             key = Lease.key!(key)
             digest = Lease.digest([id, params])

             case Repo.get_by(SourceReturnOperation,
                    pull_request_id: pull.id,
                    actor_id: user.id,
                    request_key: key
                  ) do
               nil ->
                 link = link!(pull, id)

                 unless link.state == "active" && link.generation == params["generation"],
                   do: Repo.rollback(:source_link_changed)

                 unless link.locator["type"] == "paper", do: Repo.rollback(:unsupported_paper)
                 connection = current!(user, credential, params["connection_generation"])
                 unless same_scope?(connection, link.locator), do: Repo.rollback(:source_denied)

                 unless "write" in connection["source_identity"]["permissions"],
                   do: Repo.rollback(:source_denied)

                 count =
                   Repo.aggregate(
                     from(o in SourceReturnOperation,
                       where: o.pull_request_id == ^pull.id
                     ),
                     :count
                   )

                 if count >= 1000, do: Repo.rollback(:source_operation_limit)

                 op =
                   Repo.insert!(%SourceReturnOperation{
                     repository_id: repository.id,
                     pull_request_id: pull.id,
                     link_id: link.id,
                     link_generation: link.generation,
                     actor_id: user.id,
                     actor_label: user.username,
                     credential_id: credential.id,
                     connection_id: connection["id"],
                     connection_generation: connection["generation"],
                     source_identity: connection["source_identity"],
                     locator: link.locator,
                     destination: destination(pull),
                     request_key: key,
                     request_digest: digest,
                     state: "queued",
                     next_at: Accounts.now()
                   })

                 public(op)

               op ->
                 unless op.request_digest == digest, do: Repo.rollback(:idempotency_conflict)
                 public(op)
             end
           end) do
      send(Gitgood.SourceReturnWorker, :scan)
      {:ok, value}
    end
  end

  def list(repository, pull, user, credential, id) do
    with {:ok, id} <- uuid(id), do: list_valid(repository, pull, user, credential, id)
  end

  defp list_valid(repository, pull, user, credential, id) do
    native(repository, pull, user, credential, fn ->
      link!(pull, id)

      Repo.all(
        from o in SourceReturnOperation,
          where: o.pull_request_id == ^pull.id and o.link_id == ^id,
          order_by: [desc: o.inserted_at, desc: o.id],
          limit: 1000
      )
      |> Enum.map(&public/1)
    end)
  end

  # Observers perform no source mutation, and are attributed separately from the writer.
  def observe(repository, pull, user, credential, link_id, id, generation) do
    with {:ok, link_id} <- uuid(link_id),
         {:ok, id} <- uuid(id),
         {:ok, op} <-
           native(repository, pull, user, credential, fn ->
             link!(pull, link_id)

             Repo.get_by(SourceReturnOperation,
               id: id,
               link_id: link_id,
               pull_request_id: pull.id
             ) ||
               Repo.rollback(:source_operation_not_found)
           end),
         {:ok, connection} <- BarkparkConnections.with_current(user, credential, generation, & &1),
         true <- same_scope?(connection, op.locator),
         {:ok, document} <- document(op, user, credential, generation),
         {:ok, :present} <- PaperReturnPointer.check(document, op),
         {:ok, value} <-
           native(repository, pull, user, credential, fn ->
             current = current!(user, credential, generation)
             unless same_scope?(current, op.locator), do: Repo.rollback(:source_denied)
             observed!(op.id, document["_rev"], user.id, current)
           end) do
      {:ok, value}
    else
      false -> {:error, :source_denied}
      {:ok, :absent} -> {:error, :source_pointer_not_observed}
      error -> error
    end
  rescue
    _ in [Ecto.Query.CastError] -> {:error, :source_operation_not_found}
  end

  def retry(repository, pull, user, credential, link_id, id, params) do
    with {:ok, link_id} <- uuid(link_id),
         {:ok, id} <- uuid(id),
         :ok <- parameters(params),
         {:ok, value} <-
           writer(repository, pull, user, credential, fn ->
             op =
               Repo.one(
                 from o in SourceReturnOperation,
                   where: o.id == ^id and o.link_id == ^link_id and o.pull_request_id == ^pull.id,
                   lock: "FOR UPDATE"
               ) || Repo.rollback(:source_operation_not_found)

             unless op.actor_id == user.id, do: Repo.rollback(:authorization_changed)

             unless params["generation"] == op.link_generation &&
                      params["connection_generation"] == op.connection_generation,
                    do: Repo.rollback(:source_link_changed)

             case authorized(op) do
               {:ok, _} -> :ok
               {:error, reason} -> Repo.rollback(reason)
             end

             if op.lease_until && DateTime.compare(op.lease_until, Accounts.now()) == :gt,
               do: Repo.rollback(:source_operation_running)

             unless op.state in (@pending ++ ["paused"]),
               do: Repo.rollback(:source_operation_resolved)

             state =
               cond do
                 op.sent_once -> "unknown"
                 is_binary(op.payload_cipher) -> "prepared"
                 true -> "queued"
               end

             Repo.update!(
               Ecto.Changeset.change(op,
                 state: state,
                 automatic_until: op.attempts + 5,
                 next_at: Accounts.now(),
                 attempt_id: nil,
                 lease_until: nil,
                 reason: nil
               )
             )
             |> public()
           end) do
      send(Gitgood.SourceReturnWorker, :scan)
      {:ok, value}
    end
  end

  def pending_ids do
    now = Accounts.now()

    Repo.all(
      from o in SourceReturnOperation,
        where:
          o.state in ^@pending and o.attempts < o.automatic_until and o.next_at <= ^now and
            (is_nil(o.lease_until) or o.lease_until <= ^now),
        order_by: [asc: o.next_at, asc: o.id],
        limit: 4,
        select: o.id
    )
  end

  def process(id) do
    case claim(id) do
      {:ok, nil} ->
        :idle

      {:ok, op} ->
        try do
          progress(op)
        rescue
          _ -> finish(op, %{state: "unknown", reason: "internal_unavailable"})
        catch
          _, _ -> finish(op, %{state: "unknown", reason: "internal_unavailable"})
        end

      _ ->
        :unavailable
    end
  end

  defp claim(id) do
    Repo.transaction(fn ->
      op = Repo.one(from o in SourceReturnOperation, where: o.id == ^id, lock: "FOR UPDATE")
      now = Accounts.now()

      if op && op.state in @pending && op.attempts < op.automatic_until &&
           DateTime.compare(op.next_at, now) != :gt &&
           (is_nil(op.lease_until) || DateTime.compare(op.lease_until, now) != :gt) do
        Repo.update!(
          Ecto.Changeset.change(op,
            attempt_id: Ecto.UUID.generate(),
            attempts: op.attempts + 1,
            lease_until: DateTime.add(now, 30, :second)
          )
        )
      end
    end)
  end

  defp progress(op) do
    case authorized(op) do
      {:ok, _connection} ->
        user = Repo.get!(User, op.actor_id)
        credential = Repo.get!(Credential, op.credential_id)

        case document(op, user, credential, op.connection_generation) do
          {:ok, document} -> prepare_and_send(op, document, user, credential)
          {:error, reason} -> failed_read(op, reason)
        end

      {:error, reason} ->
        stopped(op, reason)
    end
  end

  defp prepare_and_send(op, document, user, credential) do
    case PaperReturnPointer.check(document, op) do
      {:ok, :present} ->
        case authorized(op) do
          {:ok, current} ->
            Repo.transaction(fn ->
              observed!(op.id, document["_rev"], op.actor_id, current)
            end)

          {:error, reason} ->
            stopped(op, reason)
        end

      {:ok, :absent} ->
        case prepare(op, document) do
          {:ok, prepared} ->
            with {:ok, _} <- authorized(prepared),
                 {:ok, sending} <- sending(prepared),
                 {:ok, payload} <-
                   ConnectionSecrets.open(sending.payload_cipher, payload_binding(sending)),
                 true <- Accounts.digest(payload) == sending.payload_digest do
              response =
                BarkparkConnections.write_bytes(
                  user,
                  credential,
                  sending.connection_generation,
                  mutation_path(sending.locator),
                  payload,
                  "gitgood-pointer-" <> sending.id
                )

              record_response(sending, response, op.sent_once)
            else
              {:error, reason} -> stopped(op, reason)
              _ -> finish(op, %{state: "unknown", reason: "attempt_changed"})
            end

          {:error, :pointer_conflict} ->
            finish(op, %{state: "conflict", reason: "pointer_conflict", payload_cipher: nil})

          {:error, :unsupported_paper} ->
            finish(op, %{state: "unsupported", reason: "unsupported_paper", payload_cipher: nil})

          {:error, reason} ->
            stopped(op, reason)
        end

      {:error, reason} ->
        state =
          if op.sent_once,
            do: "unknown",
            else: if(reason == :pointer_conflict, do: "conflict", else: "unsupported")

        finish(op, %{state: state, reason: Atom.to_string(reason)})
    end
  end

  defp prepare(%{payload_cipher: cipher} = op, _) when is_binary(cipher), do: {:ok, op}

  defp prepare(op, document) do
    with {:ok, payload, revision} <- PaperReturnPointer.prepare(document, op),
         {:ok, cipher} <- ConnectionSecrets.seal(payload, payload_binding(op)) do
      transition(op, %{
        state: "prepared",
        payload_cipher: cipher,
        payload_digest: Accounts.digest(payload),
        before_revision: revision
      })
    end
  end

  # Sending is persisted before I/O; a crash here leaves uncertainty, never a fabricated success.
  defp sending(op) do
    writer_from(op, fn ->
      current = locked!(op)
      unless current.attempt_id == op.attempt_id, do: Repo.rollback(:attempt_changed)

      connection =
        current!(
          Repo.get!(User, op.actor_id),
          Repo.get!(Credential, op.credential_id),
          op.connection_generation
        )

      validate_origin!(op, connection)
      Repo.update!(Ecto.Changeset.change(current, state: "sending", sent_once: true))
    end)
  end

  defp record_response(op, {:ok, %{status: 200, body: %{"transactionId" => tx}}}, _)
       when is_binary(tx) and byte_size(tx) in 1..128 do
    # A known reply remains an actual outcome after revocation or an observer's convergence.
    # The immutable digest permits an older overlapping attempt with the same source key.
    Repo.transaction(fn ->
      current =
        Repo.get!(SourceReturnOperation, op.id)
        |> then(fn row ->
          Repo.one!(from o in SourceReturnOperation, where: o.id == ^row.id, lock: "FOR UPDATE")
        end)

      unless current.payload_digest == op.payload_digest, do: Repo.rollback(:attempt_changed)

      if current.source_transaction && current.source_transaction != tx do
        Repo.update!(
          Ecto.Changeset.change(current, state: "unknown", reason: "source_receipt_conflict")
        )
      else
        Repo.update!(
          Ecto.Changeset.change(current,
            state: "applied",
            source_transaction: tx,
            payload_cipher: nil,
            reason: nil,
            attempt_id: nil,
            lease_until: nil
          )
        )
      end
    end)
  end

  defp record_response(op, {:ok, %{status: status}}, prior)
       when status in [401, 403, 404, 409, 422] do
    state =
      if prior do
        "unknown"
      else
        cond do
          status == 409 -> "conflict"
          status == 422 -> "unsupported"
          true -> "denied"
        end
      end

    attrs = %{state: state, reason: "source_refused_" <> Integer.to_string(status)}
    attrs = if prior, do: attrs, else: Map.put(attrs, :payload_cipher, nil)
    finish(op, attrs)
  end

  defp record_response(op, _, _),
    do: finish(op, %{state: "unknown", reason: "source_reply_unknown"})

  defp authorized(op),
    do:
      writer_from(op, fn ->
        connection =
          current!(
            Repo.get!(User, op.actor_id),
            Repo.get!(Credential, op.credential_id),
            op.connection_generation
          )

        validate_origin!(op, connection)
        connection
      end)

  defp writer_from(op, action) do
    repository = Repo.get(Repository, op.repository_id)
    user = Repo.get(User, op.actor_id)
    credential = Repo.get(Credential, op.credential_id)

    if repository && user && credential do
      writer(repository, %PullRequest{id: op.pull_request_id}, user, credential, fn ->
        link = Repo.get(SourceLink, op.link_id)

        unless link && link.state == "active" && link.generation == op.link_generation &&
                 link.locator == op.locator,
               do: Repo.rollback(:source_link_changed)

        action.()
      end)
    else
      {:error, :authorization_changed}
    end
  end

  defp validate_origin!(op, connection) do
    unless op.destination == destination(Repo.get!(PullRequest, op.pull_request_id)),
      do: Repo.rollback(:native_destination_changed)

    unless connection["id"] == op.connection_id && same_scope?(connection, op.locator) &&
             connection["source_identity"]["token_id"] == op.source_identity["token_id"] &&
             "write" in connection["source_identity"]["permissions"],
           do: Repo.rollback(:connection_changed)
  end

  defp document(op, user, credential, generation) do
    case BarkparkConnections.read(user, credential, generation, document_path(op.locator)) do
      {:ok, %{status: 200, body: %{"result" => result}}} when is_map(result) -> {:ok, result}
      {:ok, %{status: status}} when status in [401, 403] -> {:error, :source_denied}
      {:ok, %{status: 404}} -> {:error, :source_missing_or_inaccessible}
      {:ok, _} -> {:error, :source_unavailable}
      {:error, reason} -> {:error, reason}
    end
  end

  defp failed_read(op, reason) when reason in [:source_denied, :source_missing_or_inaccessible] do
    finish(op, %{
      state: if(op.sent_once, do: "unknown", else: "denied"),
      reason: Atom.to_string(reason)
    })
  end

  defp failed_read(op, reason) when reason in [:connection_changed, :authorization_changed],
    do: stopped(op, reason)

  defp failed_read(op, _) do
    state =
      cond do
        op.sent_once -> "unknown"
        op.attempts >= op.automatic_until -> "paused"
        is_binary(op.payload_cipher) -> "prepared"
        true -> "queued"
      end

    finish(op, %{state: state, reason: "source_unavailable"})
  end

  defp stopped(op, reason) do
    attrs = %{
      state: if(op.sent_once, do: "unknown", else: "stopped"),
      reason: if(is_atom(reason), do: Atom.to_string(reason), else: "access_changed")
    }

    finish(op, if(op.sent_once, do: attrs, else: Map.put(attrs, :payload_cipher, nil)))
  end

  defp finish(op, attrs) do
    transition(
      op,
      Map.merge(attrs, %{
        attempt_id: nil,
        lease_until: nil,
        next_at: DateTime.add(Accounts.now(), 5, :second)
      })
    )
  end

  defp transition(op, attrs) do
    Repo.transaction(fn ->
      current = locked!(op)
      unless current.attempt_id == op.attempt_id, do: Repo.rollback(:attempt_changed)
      Repo.update!(Ecto.Changeset.change(current, attrs))
    end)
  end

  defp locked!(op),
    do: Repo.one!(from o in SourceReturnOperation, where: o.id == ^op.id, lock: "FOR UPDATE")

  defp observed!(id, revision, actor, connection) do
    op = Repo.one!(from o in SourceReturnOperation, where: o.id == ^id, lock: "FOR UPDATE")

    observation = %{
      "actor_id" => actor,
      "connection_id" => connection["id"],
      "connection_generation" => connection["generation"],
      "source_token_id" => connection["source_identity"]["token_id"],
      "revision" => revision,
      "recorded_at" => DateTime.to_iso8601(Accounts.now())
    }

    op
    |> Ecto.Changeset.change(
      state: if(op.state == "applied", do: "applied", else: "observed"),
      observation: observation,
      after_revision: revision,
      payload_cipher: nil,
      reason: nil,
      attempt_id: nil,
      lease_until: nil
    )
    |> Repo.update!()
    |> public()
  end

  defp writer(repository, pull, user, credential, action) do
    Lease.actor(repository, user, credential, ["owner", "writer"], fn current ->
      unless Repo.get_by(PullRequest, id: pull.id, repository_id: current.id),
        do: Repo.rollback(:source_link_not_found)

      action.()
    end)
  end

  defp native(repository, pull, user, credential, action) do
    Access.with_session(user, credential, fn snapshot ->
      current = Repo.get(Repository, repository.id)

      unless current &&
               (is_nil(snapshot.repository_scope) || snapshot.repository_scope == current.id) &&
               Enum.any?(snapshot.teams, &(&1.team == current.team)) &&
               Repo.get_by(PullRequest, id: pull.id, repository_id: current.id),
             do: Repo.rollback(:source_operation_not_found)

      action.()
    end)
  end

  defp link!(pull, id),
    do:
      Repo.get_by(SourceLink, id: id, pull_request_id: pull.id) ||
        Repo.rollback(:source_link_not_found)

  defp current!(user, credential, generation) do
    case BarkparkConnections.with_current(user, credential, generation, & &1) do
      {:ok, connection} -> connection
      {:error, reason} -> Repo.rollback(reason)
    end
  end

  defp same_scope?(connection, locator) do
    connection["origin"] == locator["origin"] &&
      Enum.all?(["workspace", "project", "dataset"], &(connection[&1] == locator[&1])) &&
      Enum.all?(
        ["workspace_id", "project_id", "dataset_id"],
        &(connection["source_identity"][&1] == locator[&1])
      )
  end

  defp destination(pull) do
    origin = Application.fetch_env!(:gitgood, :web_origin)

    case URI.new(origin) do
      {:ok,
       %URI{scheme: scheme, host: host, userinfo: nil, query: nil, fragment: nil, path: path}}
      when scheme in ["http", "https"] and is_binary(host) and path in [nil, "", "/"] ->
        value = String.trim_trailing(origin, "/") <> "/changes/" <> pull.public_id

        if byte_size(value) <= 2048,
          do: value,
          else: Repo.rollback(:native_destination_unconfigured)

      _ ->
        Repo.rollback(:native_destination_unconfigured)
    end
  end

  defp payload_binding(op),
    do: [
      "source-journal-payload-v1",
      op.id,
      op.actor_id,
      op.link_generation,
      op.connection_id,
      op.connection_generation,
      op.locator["origin"]
    ]

  defp prefix(locator),
    do: "/w/" <> locator["workspace"] <> "/p/" <> locator["project"] <> "/v1/data/"

  defp document_path(locator),
    do:
      prefix(locator) <>
        "doc/" <>
        locator["dataset"] <>
        "/paper/" <>
        URI.encode_www_form(locator["document_id"]) <> "?perspective=raw"

  defp mutation_path(locator), do: prefix(locator) <> "mutate/" <> locator["dataset"]

  defp uuid(value) do
    case Ecto.UUID.cast(value) do
      {:ok, id} -> {:ok, id}
      _ -> {:error, :source_operation_not_found}
    end
  end

  defp parameters(params) do
    if is_map(params) && Enum.sort(Map.keys(params)) == ["connection_generation", "generation"] &&
         Enum.all?(Map.values(params), &match?({:ok, _}, Ecto.UUID.cast(&1))),
       do: :ok,
       else: {:error, :invalid_source_operation}
  end

  defp public(op),
    do: %{
      "id" => op.id,
      "link_id" => op.link_id,
      "state" => op.state,
      "actor_id" => op.actor_id,
      "actor" => op.actor_label,
      "link_generation" => op.link_generation,
      "connection_generation" => op.connection_generation,
      "automatic_retry" => op.state in @pending && op.attempts < op.automatic_until,
      "attempts" => op.attempts,
      "reason" => op.reason,
      "source_transaction" => op.source_transaction
    }
end
