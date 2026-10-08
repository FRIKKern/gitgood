if Mix.env() != :dev, do: raise("Recovery verification requires an isolated development database")

unless System.get_env("PGDATABASE") == "gitgood_recovery",
  do: raise("Set PGDATABASE=gitgood_recovery and use an isolated storage root")

Application.put_env(:gitgood, :reconcile, false)
ExUnit.start(autorun: false)
{:ok, _} = Agent.start_link(fn -> [] end, name: Gitgood.VerificationReceipts)

defmodule Gitgood.MergeRecoveryVerification do
  use ExUnit.Case, async: false

  alias Gitgood.{
    Accounts,
    Checks,
    Git,
    GitOperation,
    Membership,
    Merges,
    PullRequest,
    Pulls,
    Repo,
    Repositories
  }

  import Ecto.Query

  setup_all do
    prefix = "recovery-" <> Base.encode16(:crypto.strong_rand_bytes(5), case: :lower)
    {:ok, owner} = Accounts.create_user(prefix <> "-owner", "synthetic-password")
    {:ok, reviewer} = Accounts.create_user(prefix <> "-reviewer", "synthetic-password")
    Accounts.add_member(owner, prefix, "owner")
    Accounts.add_member(reviewer, prefix, "writer")
    {_, credential} = Accounts.issue(owner, "session")
    {_, reviewer_credential} = Accounts.issue(reviewer, "session")

    %{
      team: prefix,
      owner: owner,
      reviewer: reviewer,
      credential: credential,
      reviewer_credential: reviewer_credential
    }
  end

  setup ctx do
    name = "repo-" <> Integer.to_string(System.unique_integer([:positive]))
    {:ok, repository} = Repositories.create(ctx.owner, ctx.team, name, "create-" <> name)
    target = commit(repository, "old\n", nil)
    source = commit(repository, "new\n", target)
    git(repository, ["update-ref", "refs/heads/main", target])
    git(repository, ["update-ref", "refs/heads/feature", source])

    {:ok, pull} =
      Pulls.create(
        repository,
        ctx.owner,
        ctx.credential,
        %{"source" => "feature", "title" => "Recovery fixture"},
        "pull-create"
      )

    {:ok, _} =
      Pulls.submit(
        repository,
        pull,
        ctx.reviewer,
        ctx.reviewer_credential,
        %{"kind" => "approve", "source_sha" => source, "target_sha" => target},
        "review-approve"
      )

    %{
      repository: repository,
      pull: pull,
      source: source,
      target: target,
      params: %{"source_sha" => source, "target_sha" => target, "policy_version" => 1}
    }
  end

  defp git(repository, args, input \\ "") do
    assert {:ok, output, 0} =
             Git.command(["--git-dir", Git.path(repository) | args], input: input)

    String.trim(output)
  end

  defp commit(repository, text, parent) do
    blob = git(repository, ["hash-object", "-w", "--stdin"], text)
    tree = git(repository, ["mktree"], "100644 blob #{blob}\tREADME.md\n")

    args = [
      "-c",
      "user.name=Fixture",
      "-c",
      "user.email=fixture@example.invalid",
      "commit-tree",
      tree
    ]

    git(repository, if(parent, do: args ++ ["-p", parent], else: args), "Recovery fixture\n")
  end

  defp request(ctx, key, opts \\ []),
    do: Merges.request(ctx.repository, ctx.pull, ctx.owner, ctx.credential, ctx.params, key, opts)

  defp receipt(ctx, operation, scenario) do
    git(ctx.repository, ["fsck", "--full", "--strict"])

    Agent.update(Gitgood.VerificationReceipts, fn receipts ->
      [
        %{
          scenario: scenario,
          repository: ctx.repository.id,
          operation: Merges.public(operation),
          source: ctx.source,
          target_before: ctx.target,
          actors: [ctx.owner.username, ctx.reviewer.username]
        }
        | receipts
      ]
    end)
  end

  test "one exact merge and repeated response are attributable to the same atomic marker", ctx do
    {:ok, operation} = request(ctx, "merge-complete")
    assert operation.state == "applied"
    assert {:ok, ctx.source} == Git.ref(ctx.repository, "refs/heads/main")

    assert {:ok, ctx.source} ==
             Git.ref(ctx.repository, "refs/gitgood/operations/" <> operation.id)

    assert Repo.get!(PullRequest, ctx.pull.id).state == "merged"
    assert {:ok, retry} = request(ctx, "merge-complete")
    assert retry.id == operation.id

    assert {:error, :idempotency_conflict} =
             Merges.request(
               ctx.repository,
               ctx.pull,
               ctx.owner,
               ctx.credential,
               Map.put(ctx.params, "source_sha", ctx.target),
               "merge-complete"
             )

    receipt(ctx, retry, "successful merge and response replay")
  end

  defp expected_tip(ctx, :before_ref), do: ctx.target
  defp expected_tip(ctx, _), do: ctx.source
  defp expected_state(:before_ref), do: "failed"
  defp expected_state(_), do: "applied"

  for point <- [:before_ref, :after_ref, :before_outcome] do
    test "worker termination at #{point} survives an application restart", ctx do
      point = unquote(point)
      parent = self()

      callback = fn location, operation ->
        if location == point do
          send(parent, {:boundary, self(), operation.id})

          receive do
            :continue -> :ok
          end
        end
      end

      caller = Task.async(fn -> request(ctx, "interrupted-merge", fault: callback) end)
      assert_receive {:boundary, worker, id}, 15000
      assert Repo.get!(GitOperation, id).state == "started"
      expected = expected_tip(ctx, point)
      assert {:ok, ^expected} = Git.ref(ctx.repository, "refs/heads/main")
      monitor = Process.monitor(worker)
      Process.exit(worker, :kill)
      assert_receive {:DOWN, ^monitor, :process, ^worker, _}, 10000
      assert {:error, :operation_interrupted_query_before_retry} = Task.await(caller, 15000)
      :ok = Application.stop(:gitgood)
      :ok = Application.start(:gitgood)
      Merges.reconcile()
      operation = Repo.get!(GitOperation, id)
      assert operation.state == expected_state(point)
      assert {:ok, ^expected} = Git.ref(ctx.repository, "refs/heads/main")
      assert {:ok, retry} = request(ctx, "interrupted-merge")
      assert retry.id == id
      assert retry.state == operation.state

      assert Repo.aggregate(
               from(o in GitOperation,
                 where: o.repository_id == ^ctx.repository.id and o.kind == "merge"
               ),
               :count
             ) == 1

      receipt(ctx, operation, "kill and restart: " <> Atom.to_string(point))
    end
  end

  test "concurrent merge attempts cannot create two applied operations", ctx do
    tasks =
      for key <- ["concurrent-one", "concurrent-two"], do: Task.async(fn -> request(ctx, key) end)

    results = Enum.map(tasks, &Task.await(&1, 30000))
    assert Enum.count(results, fn result -> match?({:ok, %{state: "applied"}}, result) end) == 1
    assert Enum.any?(results, &(&1 == {:error, :pull_request_closed}))

    operation =
      Repo.one!(
        from o in GitOperation, where: o.repository_id == ^ctx.repository.id and o.kind == "merge"
      )

    receipt(ctx, operation, "concurrent attempts")
  end

  test "source CAS rejects a writer between validation and Git transaction without overwriting it",
       ctx do
    next = commit(ctx.repository, "next\n", ctx.source)

    callback = fn point, _operation ->
      if point == :before_ref,
        do: git(ctx.repository, ["update-ref", "refs/heads/feature", next, ctx.source])
    end

    {:ok, operation} = request(ctx, "source-race", fault: callback)
    assert operation.state == "failed"
    assert {:ok, ctx.target} == Git.ref(ctx.repository, "refs/heads/main")
    assert {:ok, ^next} = Git.ref(ctx.repository, "refs/heads/feature")

    assert {:error, :missing_ref} =
             Git.ref(ctx.repository, "refs/gitgood/operations/" <> operation.id)

    receipt(ctx, operation, "source compare-and-swap race")
  end

  test "current policy, check attempts and revoked reviewer membership prevent merge", ctx do
    {:ok, provider} =
      Checks.create_provider(ctx.repository, ctx.owner, ctx.credential, "recovery-ci")

    provider_credential = Repo.get!(Gitgood.Credential, provider.credential_id)

    {:ok, _} =
      Checks.set_policy(ctx.repository, ctx.owner, ctx.credential, %{
        "version" => 1,
        "approvals" => 1,
        "required_checks" => [%{"provider_id" => provider.id, "name" => "build"}]
      })

    assert {:error, :validation_changed} = request(ctx, "old-policy")
    ctx = %{ctx | params: Map.put(ctx.params, "policy_version", 2)}
    assert {:error, :required_checks_not_successful} = request(ctx, "missing-check")

    report = %{
      "sha" => ctx.source,
      "name" => "build",
      "attempt" => 1,
      "sequence" => 1,
      "status" => "success"
    }

    {:ok, _} = Checks.report(ctx.repository, ctx.owner, provider_credential, report)

    {:ok, _} =
      Checks.report(ctx.repository, ctx.owner, provider_credential, %{
        report
        | "attempt" => 2,
          "status" => "failure"
      })

    assert {:error, :required_checks_not_successful} = request(ctx, "failed-check")

    {:ok, _} =
      Checks.report(ctx.repository, ctx.owner, provider_credential, %{report | "attempt" => 3})

    Repo.delete_all(
      from m in Membership, where: m.user_id == ^ctx.reviewer.id and m.team == ^ctx.team
    )

    assert {:error, :approval_required_or_changes_requested} = request(ctx, "revoked-reviewer")
    Accounts.add_member(ctx.reviewer, ctx.team, "writer")
    {:ok, operation} = request(ctx, "current-evidence")
    assert operation.state == "applied"
    receipt(ctx, operation, "policy, check attempts and reviewer revocation")
  end

  test "changed target is not overwritten and inconsistent marker evidence blocks later writes",
       ctx do
    next = commit(ctx.repository, "target changed\n", ctx.target)

    callback = fn point, _operation ->
      if point == :before_ref,
        do: git(ctx.repository, ["update-ref", "refs/heads/main", next, ctx.target])
    end

    {:ok, operation} = request(ctx, "target-race", fault: callback)
    assert operation.state == "uncertain"
    assert {:ok, ^next} = Git.ref(ctx.repository, "refs/heads/main")
    assert {:error, :recovery_required} = request(ctx, "blocked-after-race")
    receipt(ctx, operation, "target compare-and-swap race and recovery block")
  end

  test "divergent history and a revoked merge actor are refused", ctx do
    next = commit(ctx.repository, "divergent target\n", ctx.target)
    git(ctx.repository, ["update-ref", "refs/heads/main", next, ctx.target])

    {:ok, _} =
      Pulls.submit(
        ctx.repository,
        ctx.pull,
        ctx.reviewer,
        ctx.reviewer_credential,
        %{"kind" => "approve", "source_sha" => ctx.source, "target_sha" => next},
        "review-target-change"
      )

    ctx = %{ctx | params: Map.put(ctx.params, "target_sha", next)}
    assert {:error, :fast_forward_required} = request(ctx, "divergent-merge")
    {_, revoked} = Accounts.issue(ctx.owner, "session")
    Accounts.revoke(revoked)

    assert {:error, :authorization_changed} =
             Merges.request(
               ctx.repository,
               ctx.pull,
               ctx.owner,
               revoked,
               ctx.params,
               "revoked-merge"
             )

    assert {:ok, ^next} = Git.ref(ctx.repository, "refs/heads/main")
  end
end

result = ExUnit.run()
{:ok, version} = Gitgood.Repo.query("SELECT version()")

manifest = %{
  candidate:
    case Gitgood.Git.command(["rev-parse", "HEAD"]) do
      {:ok, sha, 0} -> String.trim(sha)
      _ -> "unavailable"
    end,
  recorded_at: DateTime.to_iso8601(DateTime.utc_now()),
  runtime: %{
    elixir: System.version(),
    otp: :erlang.system_info(:otp_release) |> to_string(),
    postgres: version.rows
  },
  commands: ["mix run verification/merge_recovery.exs"],
  result: result,
  receipts: Agent.get(Gitgood.VerificationReceipts, & &1)
}

File.mkdir_p!(".gitgood/verification")
File.write!(".gitgood/verification/merge-recovery.json", Jason.encode!(manifest, pretty: true))
if result.failures > 0, do: System.halt(1)
