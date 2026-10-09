unless Mix.env() == :dev and System.get_env("PGDATABASE") == "gitgood_recovery",
  do: raise("Use the isolated gitgood_recovery database")

Application.put_env(:gitgood, :reconcile, false)
alias Gitgood.{Accounts, Git, GitOperation, ImportBundle, Imports, Merges, Repo, Repositories}
path = ".gitgood/verification/import-vm-crash.json"
mode = System.fetch_env!("GITGOOD_FAILURE_POINT")

command = fn args, input ->
  {:ok, output, 0} = Git.command(args, input: input)
  String.trim(output)
end

if mode == "reconcile" do
  fixture = path |> File.read!() |> Jason.decode!()
  repository = Repo.get!(Gitgood.Repository, fixture["repository_id"])

  if fixture["point"] == "before_validation",
    do: Imports.execute(fixture["operation_id"])

  Imports.reconcile()
  operation = Repo.get!(GitOperation, fixture["operation_id"])
  state = if fixture["point"] == "before_ref", do: "failed", else: "applied"

  refs =
    Enum.map(fixture["expected_refs"], fn ref ->
      {ref["ref"], Git.ref(repository, ref["ref"])}
    end)

  expected =
    if state == "applied",
      do: Enum.map(fixture["expected_refs"], &{&1["ref"], {:ok, &1["new"]}}),
      else: Enum.map(fixture["expected_refs"], &{&1["ref"], {:error, :missing_ref}})

  unless operation.state == state and refs == expected,
    do: raise("Import VM restart outcome differs from atomic refs")

  {_, 0} = Git.run(["--git-dir", Git.path(repository), "fsck", "--full", "--strict"])

  unless not File.exists?(Imports.source_path(operation)),
    do: raise("Terminal source was not cleaned")

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

  IO.puts("PASS whole VM import crash/restart: " <> fixture["point"])
else
  unless mode in ["before_validation", "before_ref", "after_ref", "before_outcome"],
    do: raise("Invalid failure point")

  prefix = "import-vm-" <> Base.encode16(:crypto.strong_rand_bytes(5), case: :lower)
  {:ok, owner} = Accounts.create_user(prefix, "synthetic-password")
  Accounts.add_member(owner, prefix, "owner")
  {_, credential} = Accounts.issue(owner, "session")
  {:ok, repository} = Repositories.create(owner, prefix, "target", "import-vm-create")
  source = %Gitgood.Repository{storage_key: Ecto.UUID.generate()}
  :ok = Git.init(source)
  git = fn args, input -> command.(["--git-dir", Git.path(source) | args], input) end
  blob = git.(["hash-object", "-w", "--stdin"], "Synthetic import fixture\n")
  tree = git.(["mktree"], "100644 blob #{blob}\tREADME.md\n")

  main =
    git.(
      [
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit-tree",
        tree
      ],
      "Original history\n"
    )

  feature =
    git.(
      [
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit-tree",
        tree,
        "-p",
        main
      ],
      "Feature history\n"
    )

  git.(["update-ref", "refs/heads/main", main], "")
  git.(["update-ref", "refs/heads/feature", feature], "")
  git.(["update-ref", "refs/tags/v1", main], "")
  bundle = Path.join(Git.path(source), "source.bundle")
  git.(["bundle", "create", bundle, "--branches", "--tags"], "")
  {:ok, digest, bytes} = Imports.fingerprint(bundle)
  params = %{"source_name" => "source.bundle", "source_sha256" => digest, "source_bytes" => bytes}
  {:ok, operation} = Imports.begin(repository, owner, credential, params, "import-vm-intent")
  temporary = Imports.temporary_path()
  File.cp!(bundle, temporary)

  {:ok, operation} =
    Imports.accept_source(repository, owner, credential, operation.id, temporary, enqueue: false)

  {:ok, expected_refs} = ImportBundle.refs(bundle)
  point = String.to_existing_atom(mode)

  callback = fn location, current ->
    if location == point do
      File.mkdir_p!(Path.dirname(path))

      File.write!(
        path,
        Jason.encode!(
          %{
            point: mode,
            repository_id: repository.id,
            operation_id: operation.id,
            actor: owner.username,
            actor_id: owner.id,
            credential_id: credential.id,
            source: params,
            expected_refs: expected_refs,
            durable_state: current.state,
            candidate: command.(["rev-parse", "HEAD"], ""),
            requirement:
              Base.encode16(:crypto.hash(:sha256, File.read!("../../docs/journeys/J05.md")),
                case: :lower
              ),
            crashed_at: DateTime.to_iso8601(Accounts.now())
          },
          pretty: true
        )
      )

      System.halt(70)
    end
  end

  Imports.execute(operation.id, fault: callback)
  raise("Failure point was not reached")
end
