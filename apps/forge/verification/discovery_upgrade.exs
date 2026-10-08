unless Mix.env() == :dev and
         Regex.match?(
           ~r/\Agitgood_activity_upgrade_[0-9a-f]{8}\z/,
           System.get_env("PGDATABASE", "")
         ),
       do: raise("Use an isolated discovery upgrade database")

alias Gitgood.{Accounts, Git, Lease, Pulls, Releases, Repo}
Logger.configure(level: :warning)
mode = System.fetch_env!("GITGOOD_DISCOVERY_MODE")
file = ".gitgood/verification/discovery-upgrade.json"
migration_path = Application.app_dir(:gitgood, "priv/repo/migrations")

if mode == "prepare" do
  Mix.Task.run("ecto.create")
  Mix.Task.run("ecto.migrate", ["--to", "20261008114348"])
  {:ok, _} = Application.ensure_all_started(:gitgood)

  unless Repo.query!("SELECT count(*) FROM users").rows == [[0]],
    do: raise("Upgrade fixture must start empty")

  name = "upgrade-" <> Base.encode16(:crypto.strong_rand_bytes(5), case: :lower)
  {:ok, actor} = Accounts.create_user(name, "synthetic-password")
  Accounts.add_member(actor, name, "owner")
  {_, credential} = Accounts.issue(actor, "session")
  {:ok, repository} = Gitgood.Repositories.create(actor, name, "project", "legacy-repository")

  command = fn args, input ->
    {output, 0} = Git.run(["--git-dir", Git.path(repository) | args], input: input)
    String.trim(output)
  end

  tree = command.(["mktree"], "")

  commit_args = [
    "-c",
    "user.name=Fixture",
    "-c",
    "user.email=fixture@example.invalid",
    "commit-tree",
    tree
  ]

  target = command.(commit_args, "Legacy base\n")
  source = command.(commit_args ++ ["-p", target], "Legacy intended change\n")
  command.(["update-ref", "refs/heads/main", target], "")
  command.(["update-ref", "refs/heads/feature", source], "")
  command.(["update-ref", "refs/tags/legacy-v1", source], "")
  now = Accounts.now() |> DateTime.to_naive()
  params = %{"source" => "feature", "title" => "Legacy pull", "body" => "Retained body"}

  [[pull_id]] =
    Repo.query!(
      """
        INSERT INTO pull_requests (repository_id,author_id,title,body,source_ref,target_ref,
          creation_key,request_digest,inserted_at,updated_at)
        VALUES ($1,$2,$3,$4,'refs/heads/feature','refs/heads/main','legacy-pull',$5,$6,$6)
        RETURNING id
      """,
      [
        repository.id,
        actor.id,
        params["title"],
        params["body"],
        Lease.digest(["feature", params["title"], params["body"]]),
        now
      ]
    ).rows

  [[review_id]] =
    Repo.query!(
      """
        INSERT INTO review_events (pull_request_id,actor_id,kind,source_sha,target_sha,body,
          request_key,request_digest,inserted_at,updated_at)
        VALUES ($1,$2,'changes_requested',$3,$4,'Legacy review','legacy-review',$5,$6,$6)
        RETURNING id
      """,
      [pull_id, actor.id, source, target, Lease.digest("legacy-review"), now]
    ).rows

  release_id = Ecto.UUID.generate()

  release_params = %{
    "tag" => "legacy-v1",
    "commit_sha" => source,
    "base_sha" => target,
    "title" => "Legacy release",
    "notes" => "Legacy notes"
  }

  Repo.query!(
    """
      INSERT INTO release_records (id,repository_id,creator_id,credential_id,tag,tag_object,
        commit_sha,base_sha,changes,title,notes,creation_key,request_digest,inserted_at,updated_at)
      VALUES ($1::text::uuid,$2,$3,$4,'legacy-v1',$5,$5,$6,$7,$8,$9,'legacy-release',$10,$11,$11)
    """,
    [
      release_id,
      repository.id,
      actor.id,
      credential.id,
      source,
      target,
      %{"commits" => [%{"sha" => source, "subject" => "Legacy intended change"}]},
      release_params["title"],
      release_params["notes"],
      Lease.digest([
        "legacy-v1",
        source,
        target,
        release_params["title"],
        release_params["notes"]
      ]),
      now
    ]
  )

  [[event_id]] =
    Repo.query!(
      """
        INSERT INTO release_events (release_id,actor_id,credential_id,kind,snapshot,inserted_at,updated_at)
        VALUES ($1::text::uuid,$2,$3,'created',$4,$5,$5) RETURNING id
      """,
      [release_id, actor.id, credential.id, %{"notes" => "Legacy notes"}, now]
    ).rows

  Ecto.Migrator.run(Repo, migration_path, :up, all: true)
  pull = Repo.get!(Gitgood.PullRequest, pull_id)
  review = Repo.get!(Gitgood.ReviewEvent, review_id)
  event = Repo.get!(Gitgood.ReleaseEvent, event_id)
  identities = [pull.public_id, review.public_id, event.public_id]

  unless Enum.all?(identities, &match?({:ok, _}, Ecto.UUID.cast(&1))) and
           length(Enum.uniq(identities)) == 3,
         do: raise("Opaque backfill failed")

  refused =
    try do
      Ecto.Migrator.run(Repo, migration_path, :down, to: 20_261_008_114_348)
      false
    rescue
      error in Postgrex.Error ->
        error.postgres.code == :raise_exception and
          String.contains?(error.postgres.message, "Opaque collaboration links exist")
    end

  unless refused, do: raise("Downgrade discarded published identities")
  Ecto.Migrator.run(Repo, migration_path, :up, all: true)
  {:ok, member} = Accounts.create_user(name <> "-member", "synthetic-password")

  {:ok, granted} =
    Gitgood.Teams.change(
      actor,
      credential,
      name,
      %{"username" => member.username, "expected_role" => "absent", "role" => "reader"},
      "upgrade-member-add"
    )

  {:ok, removed} =
    Gitgood.Teams.change(
      actor,
      credential,
      name,
      %{"username" => member.username, "expected_role" => "reader", "role" => "absent"},
      "upgrade-member-remove"
    )

  audit_refused =
    try do
      Ecto.Migrator.run(Repo, migration_path, :down, step: 1)
      false
    rescue
      error in Postgrex.Error ->
        error.postgres.code == :raise_exception and
          String.contains?(error.postgres.message, "Membership audit records must be preserved")
    end

  unless audit_refused, do: raise("Downgrade discarded membership audit")

  fixture = %{
    repository_id: repository.id,
    actor_id: actor.id,
    credential_id: credential.id,
    pull_id: pull_id,
    review_id: review_id,
    event_id: event_id,
    release_id: release_id,
    source: source,
    target: target,
    release_params: release_params,
    public_ids: identities,
    downgrade_refused: refused,
    membership_event_ids: [granted.id, removed.id],
    membership_target_id: member.id,
    membership_downgrade_refused: audit_refused
  }

  File.mkdir_p!(Path.dirname(file))
  File.write!(file, Jason.encode!(fixture, pretty: true))
  IO.puts("PASS populated opaque-link upgrade and downgrade refusal; fresh VM check required")
else
  unless mode == "check", do: raise("Unknown discovery verification mode")
  {:ok, _} = Application.ensure_all_started(:gitgood)
  fixture = file |> File.read!() |> Jason.decode!()
  repository = Repo.get!(Gitgood.Repository, fixture["repository_id"])
  actor = Repo.get!(Gitgood.User, fixture["actor_id"])
  credential = Repo.get!(Gitgood.Credential, fixture["credential_id"])
  {:ok, membership_history} = Gitgood.Teams.members(actor, credential, repository.team)

  unless Enum.all?(fixture["membership_event_ids"], fn id ->
           Enum.any?(membership_history.events, &(&1.id == id))
         end) and
           is_nil(Accounts.role(fixture["membership_target_id"], repository.team)),
         do: raise("Restart lost membership audit or restored removed access")

  pull = Repo.get!(Gitgood.PullRequest, fixture["pull_id"])
  review = Repo.get!(Gitgood.ReviewEvent, fixture["review_id"])
  event = Repo.get!(Gitgood.ReleaseEvent, fixture["event_id"])

  unless [pull.public_id, review.public_id, event.public_id] == fixture["public_ids"],
    do: raise("Restart lost stable public identities")

  unless Pulls.get_public(repository, pull.public_id).id == pull.id and
           Pulls.get_public(repository, Integer.to_string(pull.id)).id == pull.id and
           pull.body == "Retained body" and review.body == "Legacy review" and
           review.actor_id == actor.id and event.snapshot["notes"] == "Legacy notes",
         do: raise("Upgrade lost legacy context or compatibility")

  {:ok, retried} =
    Releases.create(repository, actor, credential, fixture["release_params"], "legacy-release")

  unless retried.id == fixture["release_id"] and retried.notes == "Legacy notes",
    do: raise("Upgrade broke creation replay")

  {_, 0} = Git.run(["--git-dir", Git.path(repository), "fsck", "--full", "--strict"])
  {head, 0} = Git.run(["rev-parse", "HEAD"])
  {dirty, 0} = Git.run(["status", "--porcelain", "--untracked-files=no"])

  receipt =
    Map.merge(fixture, %{
      "candidate" => String.trim(head),
      "tracked_clean" => dirty == "",
      "restart_verified" => true,
      "recorded_at" => DateTime.to_iso8601(Accounts.now())
    })

  File.write!(file, Jason.encode!(receipt, pretty: true))
  IO.puts("PASS fresh VM retains opaque collaboration links, legacy aliases and context")
end
