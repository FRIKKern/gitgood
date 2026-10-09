unless Mix.env() == :dev and
         System.get_env("PGDATABASE") in ["gitgood_recovery", "gitgood_releases_recovery"],
       do: raise("Use an isolated Gitgood recovery database")

alias Gitgood.{Accounts, Git, Lease, Releases, Repo, Repositories}
mode = System.fetch_env!("GITGOOD_FAILURE_POINT")
path = ".gitgood/verification/release-vm-crash.json"

if mode == "reconcile" do
  fixture = path |> File.read!() |> Jason.decode!()
  repository = Repo.get!(Gitgood.Repository, fixture["repository_id"])
  actor = Repo.get!(Gitgood.User, fixture["actor_id"])
  credential = Repo.get!(Gitgood.Credential, fixture["credential_id"])
  {:ok, initial} = Releases.get(repository, actor, credential, fixture["release_id"])
  expected = if fixture["point"] == "before_commit", do: "draft", else: "published"

  unless initial.release.state == expected,
    do: raise("Publication crossed the SQL commit boundary")

  {:ok, result} =
    Releases.action(
      repository,
      actor,
      credential,
      fixture["release_id"],
      fixture["request"],
      "vm-publication"
    )

  unless result.release.state == "published", do: raise("Retry did not publish")

  {:ok, repeated} =
    Releases.action(
      repository,
      actor,
      credential,
      fixture["release_id"],
      fixture["request"],
      "vm-publication"
    )

  unless result.event.id == repeated.event.id, do: raise("Retry duplicated publication")
  {:ok, final} = Releases.get(repository, actor, credential, fixture["release_id"])

  unless Enum.count(final.events, &(&1.kind == "publish")) == 1,
    do: raise("Duplicate release claim")

  {:ok, {asset, bytes}} =
    Releases.download(repository, actor, credential, fixture["release_id"], fixture["asset_id"])

  unless bytes == "durable release asset" and asset.sha256 == fixture["asset_sha256"],
    do: raise("Asset identity did not survive")

  {_, 0} = Git.run(["--git-dir", Git.path(repository), "fsck", "--full", "--strict"])

  File.write!(
    path,
    Jason.encode!(
      Map.merge(fixture, %{
        "recovered" => true,
        "outcome" => final.release,
        "recovered_at" => DateTime.to_iso8601(Accounts.now())
      }),
      pretty: true
    )
  )

  IO.puts("PASS whole VM release crash/restart: " <> fixture["point"])
else
  unless mode in ["before_commit", "after_commit"], do: raise("Invalid release failure point")
  prefix = "release-vm-" <> Base.encode16(:crypto.strong_rand_bytes(5), case: :lower)
  {:ok, actor} = Accounts.create_user(prefix, "synthetic-password")
  Accounts.add_member(actor, prefix, "owner")
  {_, credential} = Accounts.issue(actor, "session")
  {:ok, repository} = Repositories.create(actor, prefix, "target", "release-vm-create")
  {tree, 0} = Git.run(["--git-dir", Git.path(repository), "mktree"], input: "")

  {sha, 0} =
    Git.run(
      [
        "--git-dir",
        Git.path(repository),
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit-tree",
        String.trim(tree)
      ],
      input: "VM release fixture\n"
    )

  sha = String.trim(sha)
  {_, 0} = Git.run(["--git-dir", Git.path(repository), "update-ref", "refs/tags/v1", sha])

  {:ok, release} =
    Releases.create(
      repository,
      actor,
      credential,
      %{
        "tag" => "v1",
        "commit_sha" => sha,
        "title" => "VM release",
        "notes" => "Actual VM release change"
      },
      "vm-release-create"
    )

  bytes = "durable release asset"

  {:ok, asset} =
    Releases.asset_intent(
      repository,
      actor,
      credential,
      release.id,
      %{"name" => "durable.bin", "size" => byte_size(bytes), "sha256" => Releases.digest(bytes)},
      "vm-asset"
    )

  {:ok, _} = Releases.upload(repository, actor, credential, release.id, asset.id, bytes)
  {:ok, %{release: release}} = Releases.get(repository, actor, credential, release.id)

  request = %{
    "kind" => "publish",
    "version" => release.version,
    "notes_digest" => release.notes_digest
  }

  {candidate, 0} = System.cmd(Git.executable(), ["rev-parse", "HEAD"])
  {status, 0} = System.cmd(Git.executable(), ["status", "--porcelain"])

  fixture = %{
    "candidate" => String.trim(candidate),
    "tracked_worktree_clean" => status == "",
    "specification_sha256" => File.read!("../../docs/journeys/J12.md") |> Releases.digest(),
    "point" => mode,
    "repository_id" => repository.id,
    "actor_id" => actor.id,
    "credential_id" => credential.id,
    "release_id" => release.id,
    "asset_id" => asset.id,
    "asset_sha256" => asset.sha256,
    "request" => request
  }

  File.mkdir_p!(Path.dirname(path))
  File.write!(path, Jason.encode!(fixture, pretty: true))

  publish = fn ->
    {:ok, _} =
      Releases.action(repository, actor, credential, release.id, request, "vm-publication")
  end

  if mode == "before_commit" do
    Lease.actor(repository, actor, credential, ["owner"], fn _ ->
      publish.()
      System.halt(70)
    end)
  else
    publish.()
    System.halt(70)
  end
end
