defmodule Gitgood.Pulls do
  import Ecto.Query
  alias Gitgood.{Browse, Git, Lease, PullRequest, Repo, ReviewEvent}

  def list(repository),
    do:
      Repo.all(
        from p in PullRequest,
          where: p.repository_id == ^repository.id,
          order_by: [desc: p.id],
          limit: 100
      )

  def get(repository, id), do: Repo.get_by(PullRequest, id: id, repository_id: repository.id)

  def get_public(repository, value) when is_binary(value) and byte_size(value) <= 36 do
    case Ecto.UUID.cast(value) do
      {:ok, uuid} ->
        Repo.get_by(PullRequest, public_id: uuid, repository_id: repository.id)

      _ ->
        case Integer.parse(value) do
          {id, ""} when id > 0 and id <= 9_223_372_036_854_775_807 -> get(repository, id)
          _ -> nil
        end
    end
  end

  def get_public(_, _), do: nil

  def revisions(repository, %{state: "merged"} = pull) do
    operation = applied_operation(repository, pull)

    if operation,
      do:
        {:ok,
         %{
           source_sha: operation.metadata["source_sha"],
           target_sha: operation.metadata["target_sha"]
         }},
      else: {:error, :merge_audit_unavailable}
  end

  def revisions(repository, pull) do
    with {:ok, source} <- Git.ref(repository, pull.source_ref),
         {:ok, target} <- Git.ref(repository, pull.target_ref),
         do: {:ok, %{source_sha: source, target_sha: target}}
  end

  def applied_operation(repository, pull) do
    Repo.one(
      from o in Gitgood.GitOperation,
        where:
          o.repository_id == ^repository.id and o.kind == "merge" and o.state == "applied" and
            fragment("?->>'pull_request_id' = ?", o.metadata, ^Integer.to_string(pull.id)),
        limit: 1
    )
  end

  def create(repository, user, credential, params, key) do
    Lease.actor(repository, user, credential, ["owner", "writer"], fn repository ->
      key = Lease.key!(key)
      source = params["source"]
      title = params["title"]
      body = params["body"] || ""

      unless is_binary(source) and Gitgood.Ref.branch?("refs/heads/" <> source) and
               source != "main" and
               is_binary(title) and String.trim(title) != "" and byte_size(title) <= 200 and
               is_binary(body) and byte_size(body) <= 16384,
             do: Repo.rollback(:invalid_pull_request)

      digest = Lease.digest([source, title, body])

      case Repo.get_by(PullRequest,
             repository_id: repository.id,
             author_id: user.id,
             creation_key: key
           ) do
        nil ->
          pull = %PullRequest{
            repository_id: repository.id,
            author_id: user.id,
            title: title,
            body: body,
            source_ref: "refs/heads/" <> source,
            target_ref: "refs/heads/main",
            creation_key: key,
            request_digest: digest
          }

          case revisions(repository, pull) do
            {:ok, _} -> Repo.insert!(pull)
            _ -> Repo.rollback(:branches_unavailable)
          end

        existing ->
          if(existing.request_digest == digest,
            do: existing,
            else: Repo.rollback(:idempotency_conflict)
          )
      end
    end)
  end

  def events(pull),
    do:
      Repo.all(
        from e in ReviewEvent,
          where: e.pull_request_id == ^pull.id,
          order_by: [asc: e.id],
          limit: 500
      )

  def submit(repository, pull, user, credential, params, key) do
    Lease.actor(repository, user, credential, ["owner", "writer"], fn repository ->
      key = Lease.key!(key)
      pull = Repo.get!(PullRequest, pull.id)
      digest = Lease.digest(params)

      case Repo.get_by(ReviewEvent, pull_request_id: pull.id, actor_id: user.id, request_key: key) do
        %ReviewEvent{} = existing ->
          if existing.request_digest == digest,
            do: existing,
            else: Repo.rollback(:idempotency_conflict)

        nil ->
          unless pull.state == "open", do: Repo.rollback(:pull_request_closed)

          current =
            case revisions(repository, pull) do
              {:ok, current} -> current
              _ -> Repo.rollback(:branches_unavailable)
            end

          unless params["source_sha"] == current.source_sha and
                   params["target_sha"] == current.target_sha,
                 do: Repo.rollback(:revision_changed)

          kind = params["kind"]
          body = params["body"] || ""

          unless kind in ["comment", "approve", "changes_requested"] and is_binary(body) and
                   byte_size(body) <= 16384,
                 do: Repo.rollback(:invalid_review)

          if kind == "approve" and pull.author_id == user.id,
            do: Repo.rollback(:self_approval_denied)

          event = %ReviewEvent{
            pull_request_id: pull.id,
            actor_id: user.id,
            kind: kind,
            body: body,
            source_sha: current.source_sha,
            target_sha: current.target_sha,
            request_key: key,
            request_digest: digest
          }

          event = if kind == "comment", do: anchor!(repository, event, params), else: event
          Repo.insert!(event)
      end
    end)
  end

  defp anchor!(repository, event, params) do
    path = params["path"]
    line = params["line"]
    side = params["side"]

    unless is_binary(path) and byte_size(path) in 1..4096 and not String.contains?(path, <<0>>) and
             is_integer(line) and line in 1..1_000_000 and side in ["old", "new"] and
             String.trim(event.body) != "",
           do: Repo.rollback(:invalid_comment_anchor)

    with :ok <- Browse.reachable(repository, event.source_sha),
         :ok <- Browse.reachable(repository, event.target_sha),
         {:ok, diff, 0} <-
           Git.command(
             [
               "--git-dir",
               Git.path(repository),
               "--literal-pathspecs",
               "diff",
               "--no-ext-diff",
               "--no-textconv",
               "--no-renames",
               "--unified=3",
               event.target_sha,
               event.source_sha,
               "--",
               path
             ],
             limit: 262_144
           ),
         excerpt when is_binary(excerpt) <- anchor(diff, side, line) do
      %{event | path: path, line: line, side: side, excerpt: excerpt}
    else
      _ -> Repo.rollback(:comment_line_unavailable)
    end
  end

  def anchor(diff, side, wanted) do
    {_, _, found} =
      Enum.reduce(String.split(diff, "\n"), {nil, nil, nil}, fn text, {old, new, found} ->
        case Regex.run(~r/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/, text) do
          [_, a, b] ->
            {String.to_integer(a), String.to_integer(b), found}

          _ ->
            if old && new do
              prefix = String.first(text)
              valid = prefix in [" ", "+", "-"]

              match =
                valid and
                  ((side == "old" and prefix != "+" and old == wanted) or
                     (side == "new" and prefix != "-" and new == wanted))

              {old + if(valid and prefix != "+", do: 1, else: 0),
               new + if(valid and prefix != "-", do: 1, else: 0),
               if(match, do: String.slice(text, 1, 4096), else: found)}
            else
              {old, new, found}
            end
        end
      end)

    found
  end

  def public(pull),
    do:
      Map.take(pull, [
        :repository_id,
        :author_id,
        :title,
        :body,
        :source_ref,
        :target_ref,
        :state,
        :inserted_at
      ])
      |> Map.put(:id, pull.public_id)

  def event_public(event),
    do:
      Map.take(event, [
        :actor_id,
        :kind,
        :source_sha,
        :target_sha,
        :path,
        :line,
        :side,
        :excerpt,
        :body,
        :inserted_at
      ])
      |> Map.put(:id, event.public_id)
end
