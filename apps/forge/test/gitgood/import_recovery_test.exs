defmodule Gitgood.ImportRecoveryTest do
  use GitgoodWeb.RealConnCase, async: false
  import Ecto.Query
  alias Gitgood.{Accounts, Git, GitOperation, ImportBundle, Imports, Repo, Repositories}

  setup do
    {:ok, user} = Accounts.create_user("import-recovery", "synthetic-password")
    Accounts.add_member(user, "import-recovery", "owner")
    {_, credential} = Accounts.issue(user, "session")
    {:ok, repository} = Repositories.create(user, "import-recovery", "target", "recovery-target")
    source = %Gitgood.Repository{storage_key: Ecto.UUID.generate()}
    :ok = Git.init(source)

    {blob, 0} =
      Git.run(["--git-dir", Git.path(source), "hash-object", "-w", "--stdin"],
        input: "recovery\n"
      )

    {tree, 0} =
      Git.run(["--git-dir", Git.path(source), "mktree"],
        input: "100644 blob #{String.trim(blob)}\tREADME.md\n"
      )

    {commit, 0} =
      Git.run(
        [
          "--git-dir",
          Git.path(source),
          "-c",
          "user.name=Fixture",
          "-c",
          "user.email=fixture@example.invalid",
          "commit-tree",
          String.trim(tree)
        ],
        input: "Recovery fixture\n"
      )

    sha = String.trim(commit)
    {_, 0} = Git.run(["--git-dir", Git.path(source), "update-ref", "refs/heads/main", sha])
    bundle = Path.join(Git.path(source), "fixture.bundle")

    {_, 0} =
      Git.run(["--git-dir", Git.path(source), "bundle", "create", bundle, "--branches", "--tags"])

    {:ok, digest, bytes} = Imports.fingerprint(bundle)

    params = %{
      "source_name" => "fixture.bundle",
      "source_sha256" => digest,
      "source_bytes" => bytes
    }

    tasks = start_supervised!({Task.Supervisor, []})

    on_exit(fn ->
      Repo.all(from o in GitOperation, where: o.repository_id == ^repository.id)
      |> Enum.each(&File.rm(Imports.source_path(&1)))

      Repo.delete_all(from o in GitOperation, where: o.repository_id == ^repository.id)
      Repo.delete!(Repo.get!(Gitgood.Repository, repository.id))
      Repo.delete_all(from c in Gitgood.Credential, where: c.user_id == ^user.id)
      Repo.delete_all(from m in Gitgood.Membership, where: m.user_id == ^user.id)
      Repo.delete!(user)
      File.rm_rf!(Git.path(source))
      File.rm_rf!(Git.path(repository))
    end)

    %{
      user: user,
      credential: credential,
      repository: repository,
      source: source,
      bundle: bundle,
      params: params,
      sha: sha,
      tasks: tasks
    }
  end

  defp queued(ctx, key) do
    {:ok, operation} = Imports.begin(ctx.repository, ctx.user, ctx.credential, ctx.params, key)
    temporary = Imports.temporary_path()
    File.cp!(ctx.bundle, temporary)

    {:ok, operation} =
      Imports.accept_source(ctx.repository, ctx.user, ctx.credential, operation.id, temporary,
        enqueue: false
      )

    operation
  end

  defp interrupt(ctx, operation, point) do
    parent = self()

    task =
      Task.Supervisor.async_nolink(ctx.tasks, fn ->
        Imports.execute(operation.id,
          fault: fn
            ^point, durable ->
              send(parent, {:paused, point, durable.id})

              receive do
                :continue -> :ok
              end

            _, _ ->
              :ok
          end
        )
      end)

    id = operation.id
    assert_receive {:paused, ^point, ^id}, 30000
    Process.exit(task.pid, :kill)
    assert_receive {:DOWN, reference, :process, pid, :killed}, 5000
    assert reference == task.ref and pid == task.pid
    Repo.get!(GitOperation, id)
  end

  test "worker death before durable validation resumes; after validation before refs becomes failed; retry publishes once",
       ctx do
    operation = queued(ctx, "import-crash-before")
    current = interrupt(ctx, operation, :before_validation)
    assert current.state == "started" and current.metadata["phase"] == "queued"
    assert :ok = ImportBundle.empty?(ctx.repository)
    current = interrupt(ctx, current, :before_ref)
    assert current.state == "validated"

    assert current.updates == [
             %{"old" => String.duplicate("0", 40), "new" => ctx.sha, "ref" => "refs/heads/main"}
           ]

    assert :ok = ImportBundle.empty?(ctx.repository)
    Imports.reconcile()
    assert Repo.get!(GitOperation, current.id).state == "failed"
    refute File.exists?(Imports.source_path(current))
    refute File.exists?(ImportBundle.validation_path(Imports.source_path(current)))
    next = queued(ctx, "import-after-failure")
    assert {:ok, %{state: "applied"}} = Imports.execute(next.id)
    assert Git.ref(ctx.repository, "refs/heads/main") == {:ok, ctx.sha}

    assert Repo.aggregate(
             from(o in GitOperation, where: o.repository_id == ^ctx.repository.id),
             :count
           ) == 2
  end

  test "worker death after atomic refs before SQL outcome recovers applied event and removes complete staged source",
       ctx do
    operation = queued(ctx, "import-crash-outcome")
    current = interrupt(ctx, operation, :before_outcome)
    assert current.state == "validated"
    assert Git.ref(ctx.repository, ImportBundle.marker(current)) == {:ok, ctx.sha}
    assert Git.ref(ctx.repository, "refs/heads/main") == {:ok, ctx.sha}
    Imports.reconcile()
    assert Repo.get!(GitOperation, current.id).state == "applied"
    refute File.exists?(Imports.source_path(current))
    refute File.exists?(ImportBundle.validation_path(Imports.source_path(current)))

    assert {:ok, %{id: id, state: "applied"}} =
             Imports.begin(
               ctx.repository,
               ctx.user,
               ctx.credential,
               ctx.params,
               "import-crash-outcome"
             )

    assert id == operation.id
  end

  test "unavailable or inconsistent marker stays uncertain and blocks ordinary mutations until reconciliation",
       ctx do
    operation = queued(ctx, "import-uncertain")
    current = interrupt(ctx, operation, :before_ref)
    displaced = Git.path(ctx.repository) <> ".unavailable"
    :ok = File.rename(Git.path(ctx.repository), displaced)

    try do
      Repo.transaction(fn -> Imports.reconcile_repository(ctx.repository) end)
      assert Repo.get!(GitOperation, current.id).state == "uncertain"

      assert {:error, :recovery_required} =
               Imports.begin(
                 ctx.repository,
                 ctx.user,
                 ctx.credential,
                 ctx.params,
                 "blocked-import"
               )
    after
      :ok = File.rename(displaced, Git.path(ctx.repository))
    end

    Imports.reconcile()
    assert Repo.get!(GitOperation, current.id).state == "failed"
  end

  test "repeated interrupted preparation consumes durable attempt limit instead of cycling forever",
       ctx do
    operation = queued(ctx, "import-retry-bound")

    for expected <- 1..3 do
      current = interrupt(ctx, operation, :before_validation)
      assert current.state == "started"
      assert current.metadata["attempts"] == expected
      assert :ok = ImportBundle.empty?(ctx.repository)
    end

    assert {:ok, %{state: "failed", outcome: %{"error" => "import_retry_limit_reached"}}} =
             Imports.execute(operation.id)

    refute File.exists?(Imports.source_path(operation))
    assert :ok = ImportBundle.empty?(ctx.repository)
  end
end
