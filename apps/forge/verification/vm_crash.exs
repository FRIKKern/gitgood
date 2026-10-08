unless Mix.env() == :dev and System.get_env("PGDATABASE") == "gitgood_recovery",
  do: raise("Use the isolated gitgood_recovery database")

Application.put_env(:gitgood, :reconcile, false)
alias Gitgood.{Accounts, Git, GitOperation, Merges, Pulls, Repo, Repositories}
path = ".gitgood/verification/vm-crash.json"
mode = System.fetch_env!("GITGOOD_FAILURE_POINT")

if mode == "reconcile" do
  fixture = path |> File.read!() |> Jason.decode!()
  repository = Repo.get!(Gitgood.Repository, fixture["repository_id"])
  Merges.reconcile()
  operation = Repo.get!(GitOperation, fixture["operation_id"])

  expected =
    if fixture["point"] == "before_ref", do: fixture["target_sha"], else: fixture["source_sha"]

  state = if fixture["point"] == "before_ref", do: "failed", else: "applied"

  unless operation.state == state and Git.ref(repository, "refs/heads/main") == {:ok, expected},
    do: raise("VM restart outcome differs from actual refs")

  {_, 0} = Git.run(["--git-dir", Git.path(repository), "fsck", "--full", "--strict"])

  File.write!(
    path,
    Jason.encode!(
      Map.merge(fixture, %{
        "recovered" => true,
        "outcome" => Merges.public(operation),
        "recovered_at" => DateTime.to_iso8601(Accounts.now())
      }),
      pretty: true
    )
  )

  IO.puts("PASS whole VM crash/restart: " <> fixture["point"])
else
  unless mode in ["before_ref", "after_ref", "before_outcome"], do: raise("Invalid failure point")
  prefix = "vm-" <> Base.encode16(:crypto.strong_rand_bytes(5), case: :lower)
  {:ok, owner} = Accounts.create_user(prefix <> "-owner", "synthetic-password")
  {:ok, reviewer} = Accounts.create_user(prefix <> "-reviewer", "synthetic-password")
  Accounts.add_member(owner, prefix, "owner")
  Accounts.add_member(reviewer, prefix, "writer")
  {_, credential} = Accounts.issue(owner, "session")
  {_, reviewer_credential} = Accounts.issue(reviewer, "session")
  {:ok, repository} = Repositories.create(owner, prefix, "project", "vm-create")

  command = fn args, input ->
    {:ok, output, 0} = Git.command(["--git-dir", Git.path(repository) | args], input: input)
    String.trim(output)
  end

  tree = command.(["mktree"], "")

  target =
    command.(
      [
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit-tree",
        tree
      ],
      "Initial\n"
    )

  source =
    command.(
      [
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit-tree",
        tree,
        "-p",
        target
      ],
      "Change\n"
    )

  command.(["update-ref", "refs/heads/main", target], "")
  command.(["update-ref", "refs/heads/feature", source], "")

  {:ok, pull} =
    Pulls.create(
      repository,
      owner,
      credential,
      %{"source" => "feature", "title" => "Whole VM crash"},
      "vm-pull-create"
    )

  {:ok, _} =
    Pulls.submit(
      repository,
      pull,
      reviewer,
      reviewer_credential,
      %{"kind" => "approve", "source_sha" => source, "target_sha" => target},
      "vm-review"
    )

  point = String.to_existing_atom(mode)

  callback = fn location, operation ->
    if location == point do
      File.mkdir_p!(Path.dirname(path))

      File.write!(
        path,
        Jason.encode!(
          %{
            point: mode,
            repository_id: repository.id,
            operation_id: operation.id,
            source_sha: source,
            target_sha: target,
            actors: [owner.username, reviewer.username],
            candidate: command.(["rev-parse", "HEAD"], ""),
            crashed_at: DateTime.to_iso8601(Accounts.now())
          },
          pretty: true
        )
      )

      System.halt(70)
    end
  end

  Merges.request(
    repository,
    pull,
    owner,
    credential,
    %{"source_sha" => source, "target_sha" => target, "policy_version" => 1},
    "vm-merge-create",
    fault: callback
  )

  raise("Failure point was not reached")
end
