defmodule Gitgood.Releases do
  import Ecto.Query
  alias Gitgood.{Accounts, Git, Lease, ReleaseRecord, ReleaseAsset, ReleaseEvent, Repo}
  @limit 16_777_216
  def limit, do: @limit

  # Every call rechecks the current session, credential and membership under the
  # same repository lease as Git publication. No caller-supplied actor or path.
  def list(repository, user, credential) do
    Lease.actor(repository, user, credential, ["owner", "writer", "reader"], fn repository ->
      Repo.all(
        from r in ReleaseRecord,
          where: r.repository_id == ^repository.id,
          order_by: [desc: r.inserted_at, desc: r.id],
          limit: 100,
          select:
            map(r, [
              :id,
              :creator_id,
              :tag,
              :tag_object,
              :commit_sha,
              :base_sha,
              :title,
              :state,
              :version,
              :published_at,
              :withdrawn_at,
              :inserted_at
            ])
      )
    end)
  end

  def get(repository, user, credential, id) do
    Lease.actor(repository, user, credential, ["owner", "writer", "reader"], fn repository ->
      release = record!(repository, id)
      %{release: public(release), events: events(release)}
    end)
  end

  def tags(repository, user, credential) do
    Lease.actor(repository, user, credential, ["owner", "writer", "reader"], fn repository ->
      case run(
             repository,
             ["for-each-ref", "--count=257", "--format=%(objectname) %(refname)", "refs/tags/"],
             262_144
           ) do
        {:ok, output, 0} ->
          lines = String.split(output, "\n", trim: true)

          records =
            for line <- lines,
                [object, ref] <- [String.split(line, " ", parts: 2)],
                do: {object, ref}

          if length(records) > 256, do: Repo.rollback(:tag_limit)

          unless length(records) == length(lines) and
                   Enum.all?(records, fn {object, ref} ->
                     sha?(object) and Gitgood.Ref.tag?(ref)
                   end),
                 do: Repo.rollback(:tags_unavailable)

          input =
            records
            |> Enum.with_index()
            |> Enum.map_join("", fn {{object, _ref}, index} ->
              object <> "^{} " <> Integer.to_string(index) <> "\n"
            end)

          # Starred for-each-ref fields peel differently across Git versions.
          # Resolve recursively in one bounded batch and retain input identities.
          case Git.command(
                 [
                   "--git-dir",
                   Git.path(repository),
                   "cat-file",
                   "--batch-check=%(objectname) %(objecttype) %(rest)"
                 ],
                 input: input,
                 limit: 65_536
               ) do
            {:ok, peeled, 0} ->
              peeled_lines = String.split(peeled, "\n", trim: true)

              resolved =
                for line <- peeled_lines,
                    [sha, kind, index] <- [String.split(line, " ", parts: 3)],
                    kind in ["commit", "tree", "blob"] and sha?(sha),
                    {index, ""} <- [Integer.parse(index)],
                    index >= 0 and index < length(records),
                    do: {index, sha, kind}

              unless length(peeled_lines) == length(records) and
                       length(resolved) == length(records) and
                       length(Enum.uniq_by(resolved, &elem(&1, 0))) == length(records),
                     do: Repo.rollback(:tags_unavailable)

              for {index, commit, "commit"} <- resolved do
                {object, ref} = Enum.at(records, index)

                %{
                  tag: String.replace_prefix(ref, "refs/tags/", ""),
                  object: object,
                  commit_sha: commit
                }
              end

            _ ->
              Repo.rollback(:tags_unavailable)
          end

        _ ->
          Repo.rollback(:tags_unavailable)
      end
    end)
  end

  def create(repository, user, credential, params, key) do
    Lease.actor(repository, user, credential, ["owner", "writer"], fn repository ->
      key = Lease.key!(key)
      exact!(params, ["tag", "commit_sha", "base_sha", "title", "notes"])
      tag = params["tag"]
      title = text!(params["title"], 200, false)
      notes = text!(params["notes"], 16_384, false)
      sha = params["commit_sha"]
      base = params["base_sha"]

      unless sha?(sha) and (is_nil(base) or sha?(base)) and tag?(tag),
        do: Repo.rollback(:invalid_release_identity)

      digest = Lease.digest([tag, sha, base, title, notes])

      case Repo.get_by(ReleaseRecord,
             repository_id: repository.id,
             creator_id: user.id,
             creation_key: key
           ) do
        nil ->
          if Repo.exists?(
               from r in ReleaseRecord, where: r.repository_id == ^repository.id and r.tag == ^tag
             ),
             do: Repo.rollback(:release_tag_already_recorded)

          if Repo.aggregate(
               from(r in ReleaseRecord, where: r.repository_id == ^repository.id),
               :count
             ) >= 500,
             do: Repo.rollback(:release_limit)

          {object, commit} = identity!(repository, tag)
          unless commit == sha, do: Repo.rollback(:tag_commit_mismatch)
          changes = changes!(repository, sha, base)

          release =
            Repo.insert!(%ReleaseRecord{
              repository_id: repository.id,
              creator_id: user.id,
              credential_id: credential.id,
              tag: tag,
              tag_object: object,
              commit_sha: sha,
              base_sha: base,
              changes: %{"commits" => changes},
              title: title,
              notes: notes,
              creation_key: key,
              request_digest: digest
            })

          event!(release, user, credential, "created", "")
          public(release)

        release ->
          unless release.request_digest == digest, do: Repo.rollback(:idempotency_conflict)
          public(release)
      end
    end)
  end

  def asset_intent(repository, user, credential, id, params, key) do
    Lease.actor(repository, user, credential, ["owner", "writer"], fn repository ->
      key = Lease.key!(key)
      release = record!(repository, id)
      exact!(params, ["name", "sha256", "size"])
      name = params["name"]
      sha = params["sha256"]
      size = params["size"]

      unless is_binary(name) and Regex.match?(~r/\A[a-zA-Z0-9][a-zA-Z0-9._-]{0,119}\z/, name) and
               is_binary(sha) and Regex.match?(~r/\A[0-9a-f]{64}\z/, sha) and is_integer(size) and
               size in 1..@limit,
             do: Repo.rollback(:invalid_asset_identity)

      digest = Lease.digest([name, sha, size])

      case Repo.get_by(ReleaseAsset, release_id: release.id, actor_id: user.id, creation_key: key) do
        nil ->
          draft!(release)

          if Repo.aggregate(
               from(a in ReleaseAsset,
                 where: a.release_id == ^release.id and a.state != "cancelled"
               ),
               :count
             ) >= 8,
             do: Repo.rollback(:asset_limit)

          if Repo.exists?(
               from a in ReleaseAsset,
                 where: a.release_id == ^release.id and a.name == ^name and a.state != "cancelled"
             ),
             do: Repo.rollback(:asset_name_already_recorded)

          asset =
            Repo.insert!(%ReleaseAsset{
              release_id: release.id,
              actor_id: user.id,
              credential_id: credential.id,
              name: name,
              sha256: sha,
              size: size,
              creation_key: key,
              request_digest: digest
            })

          release = advance!(release, %{})

          event!(release, user, credential, "asset_reserved", "", nil, nil, %{
            asset: asset_public(asset)
          })

          asset_public(asset)

        asset ->
          unless asset.request_digest == digest, do: Repo.rollback(:idempotency_conflict)
          asset_public(asset)
      end
    end)
  end

  def upload_allowed(repository, user, credential, id, asset_id) do
    Lease.actor(repository, user, credential, ["owner", "writer"], fn repository ->
      release = record!(repository, id)
      asset = asset!(release, asset_id)
      unless asset.state == "ready", do: draft!(release)
      if asset.state == "cancelled", do: Repo.rollback(:asset_cancelled)
      asset_public(asset)
    end)
  end

  def upload(repository, user, credential, id, asset_id, body)
      when is_binary(body) and byte_size(body) <= @limit do
    Lease.actor(repository, user, credential, ["owner", "writer"], fn repository ->
      release = record!(repository, id)
      asset = asset!(release, asset_id)

      unless byte_size(body) == asset.size and digest(body) == asset.sha256,
        do: Repo.rollback(:asset_digest_or_size_mismatch)

      if asset.state == "ready" do
        asset_public(asset)
      else
        draft!(release)
        unless asset.state == "waiting", do: Repo.rollback(:asset_cancelled)
        asset = asset |> Ecto.Changeset.change(state: "ready", data: body) |> Repo.update!()
        release = advance!(release, %{})

        event!(release, user, credential, "asset_ready", "", nil, nil, %{
          asset: asset_public(asset)
        })

        asset_public(asset)
      end
    end)
  end

  def upload(_, _, _, _, _, _), do: {:error, :asset_too_large}

  def cancel_asset(repository, user, credential, id, asset_id) do
    Lease.actor(repository, user, credential, ["owner", "writer"], fn repository ->
      release = record!(repository, id)
      asset = asset!(release, asset_id)

      if asset.state == "cancelled" do
        asset_public(asset)
      else
        draft!(release)
        unless asset.state == "waiting", do: Repo.rollback(:ready_asset_immutable)
        asset = asset |> Ecto.Changeset.change(state: "cancelled") |> Repo.update!()
        release = advance!(release, %{})

        event!(release, user, credential, "asset_cancelled", "", nil, nil, %{
          asset: asset_public(asset)
        })

        asset_public(asset)
      end
    end)
  end

  def download(repository, user, credential, id, asset_id) do
    Lease.actor(repository, user, credential, ["owner", "writer", "reader"], fn repository ->
      release = record!(repository, id)
      asset = asset!(release, asset_id)

      unless release.state == "published" and asset.state == "ready",
        do: Repo.rollback(:asset_not_published)

      data = Repo.one(from a in ReleaseAsset, where: a.id == ^asset.id, select: a.data)

      unless is_binary(data) and byte_size(data) == asset.size and digest(data) == asset.sha256,
        do: Repo.rollback(:asset_storage_unavailable)

      {asset_public(asset), data}
    end)
  end

  def action(repository, user, credential, id, params, key) do
    Lease.actor(repository, user, credential, ["owner", "writer"], fn repository ->
      release = record!(repository, id)
      key = Lease.key!(key)
      digest = Lease.digest(params)

      case Repo.get_by(ReleaseEvent, release_id: release.id, actor_id: user.id, request_key: key) do
        nil ->
          kind = params["kind"]

          exact!(
            params,
            case kind do
              "publish" -> ["kind", "version", "notes_digest"]
              "withdraw" -> ["kind", "version", "reason"]
              _ -> ["kind", "version", "title", "notes", "reason"]
            end
          )

          unless is_integer(params["version"]) and params["version"] == release.version,
            do: Repo.rollback(:release_revision_changed)

          {attrs, reason} = transition!(repository, release, kind, params)
          release = advance!(release, attrs)
          event = event!(release, user, credential, kind, reason, key, digest)
          %{release: public(release), event: event_public(event)}

        event ->
          unless event.request_digest == digest, do: Repo.rollback(:idempotency_conflict)
          %{release: public(release), event: event_public(event)}
      end
    end)
  end

  defp transition!(repository, release, "publish", params) do
    draft!(release)

    unless params["notes_digest"] == digest(release.notes),
      do: Repo.rollback(:notes_review_changed)

    {object, commit} = identity!(repository, release.tag)

    unless object == release.tag_object and commit == release.commit_sha,
      do: Repo.rollback(:tag_identity_changed)

    assets = assets(release)

    unless length(assets) > 0 and Enum.all?(assets, &(&1.state == "ready")),
      do: Repo.rollback(:assets_not_ready)

    # Asset identity is checked again at publication, not only at intake.
    for asset <- assets do
      data = Repo.one(from a in ReleaseAsset, where: a.id == ^asset.id, select: a.data)

      unless is_binary(data) and byte_size(data) == asset.size and digest(data) == asset.sha256,
        do: Repo.rollback(:asset_storage_unavailable)
    end

    {%{state: "published", published_at: Accounts.now()}, ""}
  end

  defp transition!(_repository, release, kind, params) when kind in ["revise", "correct"] do
    if kind == "revise", do: draft!(release)

    if kind == "correct" and release.state != "published",
      do: Repo.rollback(:release_not_published)

    title = text!(params["title"], 200, false)
    notes = text!(params["notes"], 16_384, false)
    reason = if kind == "correct", do: text!(params["reason"], 2048, false), else: ""
    {%{title: title, notes: notes}, reason}
  end

  defp transition!(_repository, release, "withdraw", params) do
    unless release.state == "published", do: Repo.rollback(:release_not_published)
    {%{state: "withdrawn", withdrawn_at: Accounts.now()}, text!(params["reason"], 2048, false)}
  end

  defp transition!(_, _, _, _), do: Repo.rollback(:invalid_release_action)

  defp record!(repository, id) do
    uuid!(id)

    Repo.get_by(ReleaseRecord, id: id, repository_id: repository.id) ||
      Repo.rollback(:release_not_found)
  end

  defp asset!(release, id) do
    uuid!(id)
    Repo.get_by(ReleaseAsset, id: id, release_id: release.id) || Repo.rollback(:asset_not_found)
  end

  defp uuid!(id),
    do: if(match?({:ok, _}, Ecto.UUID.cast(id)), do: :ok, else: Repo.rollback(:invalid_identity))

  defp draft!(release),
    do: unless(release.state == "draft", do: Repo.rollback(:release_not_draft))

  defp advance!(release, attrs),
    do:
      release
      |> Ecto.Changeset.change(Map.put(attrs, :version, release.version + 1))
      |> Repo.update!()

  defp exact!(params, allowed),
    do:
      unless(is_map(params) and Enum.all?(Map.keys(params), &(&1 in allowed)),
        do: Repo.rollback(:invalid_release_fields)
      )

  defp text!(value, limit, empty) do
    unless is_binary(value) and String.valid?(value) and byte_size(value) <= limit and
             (empty or String.trim(value) != "") and not String.contains?(value, <<0>>),
           do: Repo.rollback(:invalid_release_text)

    value
  end

  defp sha?(sha), do: is_binary(sha) and Regex.match?(~r/\A[0-9a-f]{40}\z/, sha)
  defp tag?(tag), do: is_binary(tag) and Gitgood.Ref.tag?("refs/tags/" <> tag)

  defp identity!(repository, tag) do
    with {:ok, object} <- Git.ref(repository, "refs/tags/" <> tag),
         {:ok, output, 0} <-
           run(repository, ["rev-parse", "--verify", object <> "^{commit}"], 128),
         commit = String.trim(output),
         true <- sha?(commit) do
      {object, commit}
    else
      _ -> Repo.rollback(:tag_commit_unavailable)
    end
  end

  defp changes!(repository, sha, base) do
    if base do
      case run(repository, ["merge-base", "--is-ancestor", base, sha], 128) do
        {:ok, _, 0} -> :ok
        _ -> Repo.rollback(:release_base_not_ancestor)
      end
    end

    args =
      ["log", "--max-count=201", "--format=%H%x00%s%x00", sha] ++
        if(base, do: ["^" <> base, "--"], else: ["--"])

    case run(repository, args, 262_144) do
      {:ok, output, 0} ->
        unless String.valid?(output), do: Repo.rollback(:unsupported_commit_encoding)

        commits =
          output
          |> String.split(<<0>>)
          |> Enum.chunk_every(2, 2, :discard)
          |> Enum.map(fn [sha, subject] -> %{"sha" => String.trim(sha), "subject" => subject} end)

        if length(commits) > 200, do: Repo.rollback(:release_change_limit_choose_base)
        commits

      _ ->
        Repo.rollback(:release_changes_unavailable)
    end
  end

  defp run(repository, args, limit),
    do: Git.command(["--git-dir", Git.path(repository) | args], limit: limit)

  def digest(body), do: :crypto.hash(:sha256, body) |> Base.encode16(case: :lower)

  defp assets(release),
    do:
      Repo.all(
        from a in ReleaseAsset,
          where: a.release_id == ^release.id and a.state != "cancelled",
          order_by: [asc: a.inserted_at, asc: a.id]
      )

  def public(release),
    do:
      release
      |> Map.take([
        :id,
        :creator_id,
        :credential_id,
        :tag,
        :tag_object,
        :commit_sha,
        :base_sha,
        :changes,
        :title,
        :notes,
        :state,
        :version,
        :published_at,
        :withdrawn_at,
        :inserted_at
      ])
      |> Map.put(:notes_digest, digest(release.notes))
      |> Map.put(:assets, Enum.map(assets(release), &asset_public/1))

  def asset_public(asset),
    do:
      Map.take(asset, [
        :id,
        :name,
        :sha256,
        :size,
        :state,
        :actor_id,
        :credential_id,
        :inserted_at
      ])

  defp events(release),
    do:
      Repo.all(
        from e in ReleaseEvent,
          where: e.release_id == ^release.id,
          order_by: [desc: e.id],
          limit: 100
      )
      |> Enum.map(&event_public/1)

  def event_public(event),
    do: Map.take(event, [:id, :actor_id, :credential_id, :kind, :snapshot, :reason, :inserted_at])

  defp event!(release, user, credential, kind, reason, key \\ nil, digest \\ nil, extra \\ %{}) do
    Repo.insert!(%ReleaseEvent{
      release_id: release.id,
      actor_id: user.id,
      credential_id: credential.id,
      kind: kind,
      snapshot: Map.merge(Map.delete(public(release), :changes), extra),
      reason: reason,
      request_key: key,
      request_digest: digest
    })
  end
end
