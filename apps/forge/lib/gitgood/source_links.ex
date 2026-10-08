defmodule Gitgood.SourceLinks do
  @moduledoc "Native link responsibility; source contents are read using the current viewer."
  import Ecto.Query

  alias Gitgood.{
    Access,
    BarkparkConnections,
    Lease,
    PullRequest,
    Repo,
    Repository,
    SourceLink,
    SourceLinkEvent
  }

  def list(repository, pull, user, credential) do
    native(repository, pull, user, credential, fn ->
      Repo.all(
        from l in SourceLink,
          where: l.pull_request_id == ^pull.id,
          order_by: [asc: l.inserted_at, asc: l.id],
          limit: 100
      )
      |> Enum.map(&public/1)
    end)
  end

  def attach(repository, pull, user, credential, params, key) do
    with :ok <- parameters(params),
         {:ok, preparation} <-
           writer(repository, pull, user, credential, fn ->
             key = Lease.key!(key)
             replay(pull, user, key, Lease.digest(["attach", params])) || :new
           end) do
      case preparation do
        :new -> attach_new(repository, pull, user, credential, params, key)
        receipt -> {:ok, receipt}
      end
    end
  end

  defp attach_new(repository, pull, user, credential, params, key) do
    generation = params["connection_generation"]

    with {:ok, connection} <- BarkparkConnections.with_current(user, credential, generation, & &1),
         {:ok, document} <-
           document(
             user,
             credential,
             generation,
             connection,
             params["type"],
             params["document_id"]
           ),
         {:ok, result} <-
           writer(repository, pull, user, credential, fn ->
             digest = Lease.digest(["attach", params])

             case replay(pull, user, key, digest) do
               nil ->
                 current!(user, credential, generation, fn current ->
                   unless scope(current) == scope(connection),
                     do: Repo.rollback(:connection_changed)

                   locator =
                     Map.merge(scope(current), %{
                       "type" => params["type"],
                       "document_id" => document["_id"]
                     })

                   source_digest = Lease.digest(locator)

                   existing =
                     Repo.get_by(SourceLink,
                       pull_request_id: pull.id,
                       source_digest: source_digest
                     )

                   link =
                     cond do
                       existing && existing.state == "active" ->
                         existing

                       existing ->
                         existing
                         |> Ecto.Changeset.change(
                           state: "active",
                           generation: Ecto.UUID.generate(),
                           actor_id: user.id,
                           connection_id: current["id"],
                           source_identity: current["source_identity"],
                           verified_revision: document["_rev"]
                         )
                         |> Repo.update!()

                       true ->
                         if Repo.aggregate(
                              from(l in SourceLink, where: l.pull_request_id == ^pull.id),
                              :count
                            ) >= 100,
                            do: Repo.rollback(:source_link_limit)

                         Repo.insert!(%SourceLink{
                           repository_id: repository.id,
                           pull_request_id: pull.id,
                           actor_id: user.id,
                           connection_id: current["id"],
                           source_identity: current["source_identity"],
                           locator: locator,
                           source_digest: source_digest,
                           verified_revision: document["_rev"]
                         })
                     end

                   record(link, pull, user, key, digest, "attach", current)
                 end)

               receipt ->
                 receipt
             end
           end) do
      {:ok, result}
    end
  end

  def remove(repository, pull, user, credential, id, generation, key) do
    with {:ok, id} <- uuid(id),
         {:ok, generation} <- uuid(generation) do
      writer(repository, pull, user, credential, fn ->
        key = Lease.key!(key)
        digest = Lease.digest(["remove", id, generation])

        case replay(pull, user, key, digest) do
          nil ->
            link = find!(pull, id)
            unless link.generation == generation, do: Repo.rollback(:source_link_changed)

            changed =
              if link.state == "removed",
                do: link,
                else:
                  link
                  |> Ecto.Changeset.change(state: "removed", generation: Ecto.UUID.generate())
                  |> Repo.update!()

            record(changed, pull, user, key, digest, "remove", nil)

          receipt ->
            receipt
        end
      end)
    end
  end

  # Listing and refused source reads contain only opaque native link identities.
  # No creator credential, source locator, title or snippet is a fallback.
  def read(repository, pull, user, credential, id, generation) do
    with {:ok, id} <- uuid(id),
         {:ok, link} <- native(repository, pull, user, credential, fn -> find!(pull, id) end) do
      if link.state == "removed" do
        {:ok, Map.put(public(link), "source_state", "removed")}
      else
        source_read(repository, pull, user, credential, link, generation)
      end
    end
  end

  defp source_read(repository, pull, user, credential, link, generation) do
    source =
      with {:ok, connection} <-
             BarkparkConnections.with_current(user, credential, generation, & &1),
           true <- scope(connection) == Map.take(link.locator, Map.keys(scope(connection))),
           {:ok, document} <-
             document(
               user,
               credential,
               generation,
               connection,
               link.locator["type"],
               link.locator["document_id"]
             ) do
        %{
          "source_state" => "available",
          "title" => text(document["title"], 200),
          "summary" => text(document["purpose"] || document["description"], 2000),
          "revision" => document["_rev"],
          "criteria" => criteria(document),
          "source_actor" => connection["source_identity"],
          "locator" => link.locator,
          "studio_url" => studio(link.locator),
          "connection_generation" => generation
        }
      else
        false -> %{"source_state" => "denied"}
        {:error, reason} -> %{"source_state" => state(reason)}
      end

    native(repository, pull, user, credential, fn ->
      current = find!(pull, link.id)
      unless current.generation == link.generation, do: Repo.rollback(:source_link_changed)

      if source["source_state"] == "available" do
        current!(user, credential, generation, fn _ -> Map.merge(public(current), source) end)
      else
        Map.merge(public(current), source)
      end
    end)
  end

  # Used again immediately before sending source-authorized context.
  def guard(repository, pull, user, credential, id, link_generation, connection_generation) do
    native(repository, pull, user, credential, fn ->
      link = find!(pull, id)

      unless link.state == "active" && link.generation == link_generation,
        do: Repo.rollback(:source_link_changed)

      current!(user, credential, connection_generation, fn _ -> :current end)
    end)
  end

  defp document(user, credential, generation, connection, type, id) do
    path =
      "/w/" <>
        connection["workspace"] <>
        "/p/" <>
        connection["project"] <>
        "/v1/data/doc/" <>
        connection["dataset"] <>
        "/" <> type <> "/" <> URI.encode_www_form(id) <> "?perspective=raw"

    case BarkparkConnections.read(user, credential, generation, path) do
      {:ok, %{status: 200, body: %{"result" => result}}} when is_map(result) ->
        if result["_type"] == type && result["_id"] in [id, "drafts." <> id] &&
             valid_document?(result["_id"]) && is_binary(result["_rev"]) &&
             byte_size(result["_rev"]) in 1..128 do
          {:ok, result}
        else
          {:error, :source_contract_unavailable}
        end

      {:ok, %{status: status}} when status in [401, 403] ->
        {:error, :source_denied}

      {:ok, %{status: 404}} ->
        {:error, :source_missing_or_inaccessible}

      {:ok, _} ->
        {:error, :source_unavailable}

      {:error, reason} ->
        {:error, reason}
    end
  end

  defp scope(connection) do
    identity = connection["source_identity"]

    %{
      "origin" => connection["origin"],
      "workspace" => connection["workspace"],
      "project" => connection["project"],
      "dataset" => connection["dataset"],
      "workspace_id" => identity["workspace_id"],
      "project_id" => identity["project_id"],
      "dataset_id" => identity["dataset_id"]
    }
  end

  defp studio(locator),
    do:
      locator["origin"] <>
        "/w/" <>
        locator["workspace"] <>
        "/p/" <>
        locator["project"] <>
        "/d/" <>
        locator["dataset"] <>
        "/studio/open/" <>
        locator["type"] <> "/" <> URI.encode_www_form(locator["document_id"])

  defp native(repository, pull, user, credential, action) do
    Access.with_session(user, credential, fn snapshot ->
      current = Repo.get(Repository, repository.id)

      unless current &&
               (is_nil(snapshot.repository_scope) || snapshot.repository_scope == current.id) &&
               Enum.any?(snapshot.teams, &(&1.team == current.team)) &&
               Repo.get_by(PullRequest, id: pull.id, repository_id: current.id),
             do: Repo.rollback(:source_link_not_found)

      action.()
    end)
  end

  defp writer(repository, pull, user, credential, action) do
    Lease.actor(repository, user, credential, ["owner", "writer"], fn current ->
      unless Repo.get_by(PullRequest, id: pull.id, repository_id: current.id),
        do: Repo.rollback(:source_link_not_found)

      action.()
    end)
  end

  defp current!(user, credential, generation, action) do
    case BarkparkConnections.with_current(user, credential, generation, action) do
      {:ok, result} -> result
      {:error, reason} -> Repo.rollback(reason)
    end
  end

  defp find!(pull, id),
    do:
      Repo.get_by(SourceLink, id: id, pull_request_id: pull.id) ||
        Repo.rollback(:source_link_not_found)

  defp replay(pull, user, key, digest) do
    case Repo.get_by(SourceLinkEvent,
           pull_request_id: pull.id,
           actor_id: user.id,
           request_key: key
         ) do
      nil ->
        nil

      event ->
        unless event.request_digest == digest, do: Repo.rollback(:idempotency_conflict)
        event.receipt
    end
  end

  defp record(link, pull, user, key, digest, kind, connection) do
    receipt = public(link)

    Repo.insert!(%SourceLinkEvent{
      link_id: link.id,
      pull_request_id: pull.id,
      actor_id: user.id,
      request_key: key,
      request_digest: digest,
      kind: kind,
      receipt: receipt,
      source_actor:
        if(connection,
          do: Map.take(connection, ["id", "generation", "source_identity"]),
          else: nil
        )
    })

    receipt
  end

  defp public(link),
    do: %{"id" => link.id, "generation" => link.generation, "state" => link.state}

  defp state(:source_denied), do: "denied"
  defp state(:source_missing_or_inaccessible), do: "missing_or_inaccessible"
  defp state(:connection_changed), do: "connection_changed"
  defp state(:authorization_changed), do: "access_changed"
  defp state(_), do: "unavailable"
  defp text(value, limit) when is_binary(value), do: String.slice(value, 0, limit)
  defp text(_, _), do: ""

  defp criteria(%{"_type" => "task", "acceptance_criteria" => items}) when is_list(items) do
    if length(items) <= 100 &&
         Enum.all?(items, fn
           %{"criterion" => text} when is_binary(text) ->
             byte_size(text) in 1..2000 && String.trim(text) != ""

           _ ->
             false
         end) do
      Enum.with_index(items, fn item, index ->
        %{
          "index" => index,
          "text" => item["criterion"],
          "sha256" => Base.encode16(:crypto.hash(:sha256, item["criterion"]), case: :lower)
        }
      end)
    else
      nil
    end
  end

  defp criteria(_), do: nil

  defp uuid(value) do
    case Ecto.UUID.cast(value) do
      {:ok, id} -> {:ok, id}
      _ -> {:error, :source_link_not_found}
    end
  end

  defp valid_document?(id),
    do:
      is_binary(id) && byte_size(id) in 1..256 &&
        Regex.match?(~r/\A[a-zA-Z0-9][a-zA-Z0-9_.-]*\z/, id)

  defp parameters(params) do
    if is_map(params) &&
         Enum.sort(Map.keys(params)) == ["connection_generation", "document_id", "type"] &&
         params["type"] in ["task", "paper"] && valid_document?(params["document_id"]) &&
         match?({:ok, _}, Ecto.UUID.cast(params["connection_generation"])),
       do: :ok,
       else: {:error, :invalid_source_link}
  end
end
