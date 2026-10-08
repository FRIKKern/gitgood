defmodule Gitgood.ReleasesTest do
  use GitgoodWeb.ConnCase, async: false
  alias Gitgood.{Accounts, Git, Releases, Repo, ReleaseAsset, ReleaseEvent, ReleaseRecord}

  setup do
    {:ok, owner} = Accounts.create_user("release-owner", "synthetic-password")
    {:ok, reader} = Accounts.create_user("release-reader", "synthetic-password")
    {:ok, outsider} = Accounts.create_user("release-outsider", "synthetic-password")

    for {user, role} <- [{owner, "owner"}, {reader, "reader"}],
        do: Accounts.add_member(user, "releases", role)

    {token, credential} = Accounts.issue(owner, "session")
    {_, reader_credential} = Accounts.issue(reader, "session")
    {_, outsider_credential} = Accounts.issue(outsider, "session")

    {:ok, repository} =
      Gitgood.Repositories.create(owner, "releases", "project", "release-project")

    on_exit(fn -> File.rm_rf!(Git.path(repository)) end)
    first = commit(repository, "First included change", nil)
    second = commit(repository, "Second included change", first)
    git(repository, ["update-ref", "refs/heads/main", second])
    git(repository, ["update-ref", "refs/tags/v1", second])

    %{
      repository: repository,
      owner: owner,
      credential: credential,
      token: token,
      reader: reader,
      reader_credential: reader_credential,
      outsider: outsider,
      outsider_credential: outsider_credential,
      first: first,
      second: second
    }
  end

  defp git(repository, args, input \\ "") do
    assert {output, 0} = Git.run(["--git-dir", Git.path(repository) | args], input: input)
    String.trim(output)
  end

  defp commit(repository, subject, parent) do
    blob = git(repository, ["hash-object", "-w", "--stdin"], subject)
    tree = git(repository, ["mktree"], "100644 blob #{blob}\tREADME.md\n")

    args = [
      "-c",
      "user.name=Fixture",
      "-c",
      "user.email=fixture@example.invalid",
      "commit-tree",
      tree
    ]

    git(repository, args ++ if(parent, do: ["-p", parent], else: []), subject <> "\n")
  end

  defp params(ctx),
    do: %{
      "tag" => "v1",
      "commit_sha" => ctx.second,
      "title" => "Private version",
      "notes" => "Reviewed actual included changes",
      "base_sha" => ctx.first
    }

  defp create(ctx) do
    {:ok, release} =
      Releases.create(ctx.repository, ctx.owner, ctx.credential, params(ctx), "create-release")

    release
  end

  defp attach(ctx, release, body \\ "Private release asset") do
    {:ok, asset} =
      Releases.asset_intent(
        ctx.repository,
        ctx.owner,
        ctx.credential,
        release.id,
        %{"name" => "private.bin", "sha256" => Releases.digest(body), "size" => byte_size(body)},
        "asset-private"
      )

    {:ok, asset} =
      Releases.upload(ctx.repository, ctx.owner, ctx.credential, release.id, asset.id, body)

    asset
  end

  defp detail(ctx, id) do
    {:ok, result} = Releases.get(ctx.repository, ctx.owner, ctx.credential, id)
    result.release
  end

  defp publish(ctx, id) do
    release = detail(ctx, id)

    request = %{
      "kind" => "publish",
      "version" => release.version,
      "notes_digest" => release.notes_digest
    }

    {:ok, result} =
      Releases.action(ctx.repository, ctx.owner, ctx.credential, id, request, "publish-release")

    {result.release, request}
  end

  test "tag/commit identity and exact change range are pinned; creation retries and annotation work",
       ctx do
    release = create(ctx)
    assert release.state == "draft"
    assert release.commit_sha == ctx.second
    assert release.tag_object == ctx.second

    assert release.changes["commits"] == [
             %{"sha" => ctx.second, "subject" => "Second included change"}
           ]

    assert {:ok, %{id: id}} =
             Releases.create(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               params(ctx),
               "create-release"
             )

    assert id == release.id
    assert Repo.aggregate(ReleaseRecord, :count) == 1
    assert Repo.aggregate(ReleaseEvent, :count) == 1

    assert {:error, :idempotency_conflict} =
             Releases.create(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               Map.put(params(ctx), "notes", "Different"),
               "create-release"
             )

    assert {:error, :release_tag_already_recorded} =
             Releases.create(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               params(ctx),
               "another-create"
             )

    git(ctx.repository, [
      "-c",
      "user.name=Fixture",
      "-c",
      "user.email=fixture@example.invalid",
      "tag",
      "-a",
      "v2",
      "-m",
      "Annotated",
      ctx.second
    ])

    tag_object = git(ctx.repository, ["rev-parse", "refs/tags/v2"])
    assert {:ok, tags} = Releases.tags(ctx.repository, ctx.owner, ctx.credential)

    assert Enum.any?(
             tags,
             &(&1.tag == "v2" and &1.commit_sha == ctx.second and &1.object == tag_object)
           )

    assert {:ok, annotated} =
             Releases.create(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               Map.put(params(ctx), "tag", "v2"),
               "annotated-create"
             )

    assert annotated.tag_object == tag_object
    assert annotated.commit_sha == ctx.second

    git(ctx.repository, [
      "-c",
      "user.name=Fixture",
      "-c",
      "user.email=fixture@example.invalid",
      "tag",
      "-a",
      "nested",
      "-m",
      "Nested annotation",
      "v2"
    ])

    assert {:ok, nested_tags} = Releases.tags(ctx.repository, ctx.owner, ctx.credential)
    assert Enum.any?(nested_tags, &(&1.tag == "nested" and &1.commit_sha == ctx.second))
    island = commit(ctx.repository, "Tag-only release history", nil)
    git(ctx.repository, ["update-ref", "refs/tags/island", island])
    assert {:ok, snapshot} = Gitgood.Browse.snapshot(ctx.repository, island, "")
    assert Enum.any?(snapshot.history, &(&1.sha == island))
    {:ok, summaries} = Releases.list(ctx.repository, ctx.owner, ctx.credential)

    assert Enum.all?(
             summaries,
             &(not Map.has_key?(&1, :notes) and not Map.has_key?(&1, :changes))
           )
  end

  test "branch names, wrong commit, untrusted fields, noncommit tags and nonancestral bases are refused",
       ctx do
    for invalid <- [
          %{"tag" => "main"},
          %{"commit_sha" => ctx.first},
          %{"actor_id" => ctx.reader.id},
          %{"source_url" => "https://example.invalid"},
          %{"tag" => "-danger"},
          %{"notes" => <<0>>}
        ] do
      assert {:error, _} =
               Releases.create(
                 ctx.repository,
                 ctx.owner,
                 ctx.credential,
                 Map.merge(params(ctx), invalid),
                 "invalid-identity"
               )
    end

    blob = git(ctx.repository, ["hash-object", "-w", "--stdin"], "Unreleased blob")
    git(ctx.repository, ["update-ref", "refs/tags/blob", blob])
    tree = git(ctx.repository, ["rev-parse", ctx.second <> "^{tree}"])
    git(ctx.repository, ["update-ref", "refs/tags/tree", tree])

    assert {:ok, [%{tag: "v1", commit_sha: commit}]} =
             Releases.tags(ctx.repository, ctx.owner, ctx.credential)

    assert commit == ctx.second

    assert {:error, :tag_commit_unavailable} =
             Releases.create(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               Map.put(params(ctx), "tag", "blob"),
               "blob-release"
             )

    unrelated = commit(ctx.repository, "Unrelated", nil)

    assert {:error, :release_base_not_ancestor} =
             Releases.create(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               Map.put(params(ctx), "base_sha", unrelated),
               "bad-base"
             )

    assert Repo.aggregate(ReleaseRecord, :count) == 0
  end

  test "empty tags are distinct from broken storage and over-limit discovery", ctx do
    git(ctx.repository, ["update-ref", "-d", "refs/tags/v1"])
    assert {:ok, []} = Releases.tags(ctx.repository, ctx.owner, ctx.credential)

    island = commit(ctx.repository, "Unavailable tag object", nil)
    git(ctx.repository, ["update-ref", "refs/tags/broken", island])
    # This path belongs to this test's disposable repository and a validated SHA.
    object_path =
      Path.join([
        Git.path(ctx.repository),
        "objects",
        String.slice(island, 0, 2),
        String.slice(island, 2, 38)
      ])

    object = File.read!(object_path)
    File.rm!(object_path)
    assert {:error, :tags_unavailable} = Releases.tags(ctx.repository, ctx.owner, ctx.credential)
    File.write!(object_path, object)
    git(ctx.repository, ["update-ref", "-d", "refs/tags/broken"])

    refs =
      Enum.map_join(1..257, "", fn index ->
        "create refs/tags/bounded-#{index} #{ctx.second}\n"
      end)

    git(ctx.repository, ["update-ref", "--stdin"], refs)
    assert {:error, :tag_limit} = Releases.tags(ctx.repository, ctx.owner, ctx.credential)
  end

  test "intake checks exact immutable bytes, pending assets cannot publish and retry remains singular",
       ctx do
    release = create(ctx)
    body = "Private immutable bytes"

    params = %{
      "name" => "asset.bin",
      "sha256" => Releases.digest(body),
      "size" => byte_size(body)
    }

    assert {:ok, asset} =
             Releases.asset_intent(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               release.id,
               params,
               "asset-intake"
             )

    assert {:ok, %{id: id}} =
             Releases.asset_intent(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               release.id,
               params,
               "asset-intake"
             )

    assert id == asset.id

    assert {:error, :idempotency_conflict} =
             Releases.asset_intent(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               release.id,
               Map.put(params, "name", "other.bin"),
               "asset-intake"
             )

    current = detail(ctx, release.id)

    assert {:error, :assets_not_ready} =
             Releases.action(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               release.id,
               %{
                 "kind" => "publish",
                 "version" => current.version,
                 "notes_digest" => current.notes_digest
               },
               "too-early"
             )

    assert {:error, :asset_digest_or_size_mismatch} =
             Releases.upload(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               release.id,
               asset.id,
               "Partial"
             )

    assert Repo.get!(ReleaseAsset, asset.id).state == "waiting"

    assert {:ok, %{state: "ready"}} =
             Releases.upload(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               release.id,
               asset.id,
               body
             )

    version = detail(ctx, release.id).version

    assert {:ok, %{state: "ready"}} =
             Releases.upload(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               release.id,
               asset.id,
               body
             )

    assert detail(ctx, release.id).version == version

    assert {:error, :asset_digest_or_size_mismatch} =
             Releases.upload(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               release.id,
               asset.id,
               "Changed"
             )

    assert {:error, :ready_asset_immutable} =
             Releases.cancel_asset(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               release.id,
               asset.id
             )

    assert Repo.aggregate(ReleaseAsset, :count) == 1
    refute Map.has_key?(asset, :data)
    assert Repo.get!(ReleaseAsset, asset.id).data == nil
  end

  test "publication validates current tag, exact reviewed notes and current revision", ctx do
    release = create(ctx)
    attach(ctx, release)
    current = detail(ctx, release.id)

    request = %{
      "kind" => "publish",
      "version" => current.version,
      "notes_digest" => current.notes_digest
    }

    assert {:error, :release_revision_changed} =
             Releases.action(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               release.id,
               Map.put(request, "version", 1),
               "stale-publication"
             )

    assert {:error, :notes_review_changed} =
             Releases.action(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               release.id,
               Map.put(request, "notes_digest", String.duplicate("0", 64)),
               "wrong-notes"
             )

    git(ctx.repository, ["update-ref", "refs/tags/v1", ctx.first, ctx.second])

    assert {:error, :tag_identity_changed} =
             Releases.action(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               release.id,
               request,
               "moved-tag"
             )

    git(ctx.repository, ["update-ref", "refs/tags/v1", ctx.second, ctx.first])
    {published, request} = publish(ctx, release.id)
    assert published.state == "published"
    assert published.published_at

    assert {:ok, %{release: %{version: version}}} =
             Releases.action(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               release.id,
               request,
               "publish-release"
             )

    assert version == published.version
    assert Enum.count(Repo.all(ReleaseEvent), &(&1.kind == "publish")) == 1
    # Subsequent legitimate branch movement does not rewrite the recorded release.
    git(ctx.repository, ["update-ref", "refs/heads/main", ctx.first, ctx.second])
    assert detail(ctx, release.id).commit_sha == ctx.second
  end

  test "correction and withdrawal retain old claims, actors and immutable identities", ctx do
    release = create(ctx)
    asset = attach(ctx, release)
    {published, publication_request} = publish(ctx, release.id)

    assert {:ok, {_asset, "Private release asset"}} =
             Releases.download(
               ctx.repository,
               ctx.reader,
               ctx.reader_credential,
               release.id,
               asset.id
             )

    correction = %{
      "kind" => "correct",
      "version" => published.version,
      "title" => "Corrected title",
      "notes" => "Corrected actual notes",
      "reason" => "Explain mistaken claim"
    }

    assert {:ok, corrected} =
             Releases.action(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               release.id,
               correction,
               "correction-one"
             )

    assert corrected.release.tag_object == published.tag_object

    assert {:ok, _} =
             Releases.action(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               release.id,
               correction,
               "correction-one"
             )

    withdrawal = %{
      "kind" => "withdraw",
      "version" => corrected.release.version,
      "reason" => "Mistaken publication"
    }

    assert {:ok, withdrawn} =
             Releases.action(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               release.id,
               withdrawal,
               "withdraw-one"
             )

    assert withdrawn.release.state == "withdrawn"
    assert withdrawn.release.withdrawn_at

    assert {:error, :asset_not_published} =
             Releases.download(
               ctx.repository,
               ctx.reader,
               ctx.reader_credential,
               release.id,
               asset.id
             )

    assert {:ok, replay} =
             Releases.action(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               release.id,
               publication_request,
               "publish-release"
             )

    assert replay.release.state == "withdrawn"
    assert replay.event.snapshot["state"] == "published"
    assert replay.event.snapshot["notes"] == params(ctx)["notes"]

    {:ok, %{events: events}} =
      Releases.get(ctx.repository, ctx.reader, ctx.reader_credential, release.id)

    assert Enum.any?(events, &(&1.kind == "correct" and &1.reason == "Explain mistaken claim"))
    assert Enum.any?(events, &(&1.kind == "withdraw" and &1.reason == "Mistaken publication"))

    assert Enum.all?(
             events,
             &(&1.actor_id == ctx.owner.id and &1.credential_id == ctx.credential.id)
           )

    assert Repo.get!(ReleaseAsset, asset.id).state == "ready"
    assert Enum.count(events, &(&1.kind == "correct")) == 1
  end

  test "every current authority check denies readers, outsiders, foreign credentials and revocation",
       ctx do
    release = create(ctx)
    asset = attach(ctx, release)

    for {actor, credential} <- [
          {ctx.reader, ctx.reader_credential},
          {ctx.outsider, ctx.outsider_credential},
          {ctx.owner, ctx.reader_credential}
        ] do
      assert {:error, :authorization_changed} =
               Releases.create(
                 ctx.repository,
                 actor,
                 credential,
                 params(ctx),
                 "unauthorized-create"
               )

      assert {:error, :authorization_changed} =
               Releases.upload(
                 ctx.repository,
                 actor,
                 credential,
                 release.id,
                 asset.id,
                 "Private release asset"
               )

      assert {:error, :authorization_changed} =
               Releases.action(
                 ctx.repository,
                 actor,
                 credential,
                 release.id,
                 %{"kind" => "publish"},
                 "unauthorized-publish"
               )
    end

    assert {:error, :authorization_changed} =
             Releases.get(ctx.repository, ctx.outsider, ctx.outsider_credential, release.id)

    {:ok, _} = Accounts.revoke(ctx.credential)

    assert {:error, :authorization_changed} =
             Releases.list(ctx.repository, ctx.owner, ctx.credential)

    assert {:error, :authorization_changed} =
             Releases.action(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               release.id,
               %{"kind" => "publish"},
               "revoked-publish"
             )

    assert detail_for_reader(ctx, release.id).state == "draft"
  end

  defp detail_for_reader(ctx, id) do
    {:ok, %{release: release}} =
      Releases.get(ctx.repository, ctx.reader, ctx.reader_credential, id)

    release
  end

  test "bounds, cancellation and cross-repository identifiers cannot bypass publication", ctx do
    release = create(ctx)

    for invalid <- [
          %{"name" => "../secret.bin"},
          %{"name" => "header\r\ninjection"},
          %{"size" => Releases.limit() + 1},
          %{"size" => 0},
          %{"sha256" => "not-a-digest"},
          %{"url" => "file:///secret"}
        ] do
      params =
        Map.merge(%{"name" => "safe.bin", "size" => 1, "sha256" => Releases.digest("x")}, invalid)

      assert {:error, _} =
               Releases.asset_intent(
                 ctx.repository,
                 ctx.owner,
                 ctx.credential,
                 release.id,
                 params,
                 "invalid-asset"
               )
    end

    {:ok, asset} =
      Releases.asset_intent(
        ctx.repository,
        ctx.owner,
        ctx.credential,
        release.id,
        %{"name" => "cancel.bin", "size" => 1, "sha256" => Releases.digest("x")},
        "cancel-asset"
      )

    assert {:ok, %{state: "cancelled"}} =
             Releases.cancel_asset(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               release.id,
               asset.id
             )

    assert {:ok, %{state: "cancelled"}} =
             Releases.cancel_asset(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               release.id,
               asset.id
             )

    assert {:error, :asset_cancelled} =
             Releases.upload(ctx.repository, ctx.owner, ctx.credential, release.id, asset.id, "x")

    for n <- 1..8 do
      assert {:ok, _} =
               Releases.asset_intent(
                 ctx.repository,
                 ctx.owner,
                 ctx.credential,
                 release.id,
                 %{"name" => "asset#{n}.bin", "size" => 1, "sha256" => Releases.digest("x")},
                 "asset-key-#{n}"
               )
    end

    assert {:error, :asset_limit} =
             Releases.asset_intent(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               release.id,
               %{"name" => "ninth.bin", "size" => 1, "sha256" => Releases.digest("x")},
               "ninth-asset"
             )

    {:ok, other} =
      Gitgood.Repositories.create(ctx.owner, "releases", "other", "other-release-repo")

    on_exit(fn -> File.rm_rf!(Git.path(other)) end)

    assert {:error, :release_not_found} =
             Releases.get(other, ctx.owner, ctx.credential, release.id)

    assert {:error, :release_not_found} =
             Releases.download(other, ctx.owner, ctx.credential, release.id, asset.id)
  end

  test "HTTP boundary enforces csrf, private scope, binary identity and attachment-only downloads",
       ctx do
    base = "/api/repos/releases/project/releases"
    cookie = put_req_header(build_conn(), "cookie", "gitgood_session=" <> ctx.token)
    assert post(cookie, base, params(ctx)).status == 403
    release = create(ctx)
    asset = attach(ctx, release)
    bearer = fn -> build_conn() |> put_req_header("authorization", "Bearer " <> ctx.token) end

    assert get(bearer.(), base <> "/" <> release.id <> "/assets/" <> asset.id <> "/download").status ==
             409

    {_, _} = publish(ctx, release.id)
    download = get(bearer.(), base <> "/" <> release.id <> "/assets/" <> asset.id <> "/download")
    assert download.status == 200
    assert download.resp_body == "Private release asset"
    assert get_resp_header(download, "content-type") == ["application/octet-stream"]

    assert get_resp_header(download, "content-disposition") == [
             ~s(attachment; filename="private.bin")
           ]

    assert get_resp_header(download, "cache-control") == ["no-store"]
    assert get_resp_header(download, "x-content-type-options") == ["nosniff"]
    assert get_resp_header(download, "x-gitgood-sha256") == [Releases.digest(download.resp_body)]
    response = get(bearer.(), base <> "/" <> release.id)
    refute response.resp_body =~ "Private release asset"
    assert get(bearer.(), base <> "/not-a-uuid").status == 409
  end
end
