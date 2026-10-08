defmodule Gitgood.CollaborationTest do
  use GitgoodWeb.ConnCase, async: false
  alias Gitgood.{Accounts, Checks, Git, Pulls, Repo, ReviewEvent}

  setup do
    {:ok, owner} = Accounts.create_user("collaborator", "synthetic-password")
    {:ok, reviewer} = Accounts.create_user("reviewer", "synthetic-password")
    {:ok, reader} = Accounts.create_user("reader", "synthetic-password")

    for {user, role} <- [{owner, "owner"}, {reviewer, "writer"}, {reader, "reader"}],
        do: Accounts.add_member(user, "collab", role)

    {_, owner_credential} = Accounts.issue(owner, "session")
    {_, reviewer_credential} = Accounts.issue(reviewer, "session")
    {_, reader_credential} = Accounts.issue(reader, "session")
    {:ok, repository} = Gitgood.Repositories.create(owner, "collab", "project", "collab-create")
    on_exit(fn -> File.rm_rf!(Git.path(repository)) end)
    target = commit(repository, "old\n", nil)
    source = commit(repository, "new\n", target)
    git(repository, ["update-ref", "refs/heads/main", target])
    git(repository, ["update-ref", "refs/heads/feature", source])

    %{
      repository: repository,
      owner: owner,
      reviewer: reviewer,
      reader: reader,
      owner_credential: owner_credential,
      reviewer_credential: reviewer_credential,
      reader_credential: reader_credential,
      target: target,
      source: source
    }
  end

  defp git(repository, args, input \\ "") do
    assert {output, 0} = Git.run(["--git-dir", Git.path(repository) | args], input: input)
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

    args = if parent, do: args ++ ["-p", parent], else: args
    git(repository, args, "Fixture commit\n")
  end

  defp pull(ctx) do
    {:ok, pull} =
      Pulls.create(
        ctx.repository,
        ctx.owner,
        ctx.owner_credential,
        %{"source" => "feature", "title" => "Change README"},
        "pull-create"
      )

    pull
  end

  test "pull/comment retries are stable, exact line context survives source changes and roles are enforced",
       ctx do
    pull = pull(ctx)

    assert {:ok, %{id: id}} =
             Pulls.create(
               ctx.repository,
               ctx.owner,
               ctx.owner_credential,
               %{"source" => "feature", "title" => "Change README"},
               "pull-create"
             )

    assert id == pull.id

    params = %{
      "kind" => "comment",
      "source_sha" => ctx.source,
      "target_sha" => ctx.target,
      "path" => "README.md",
      "side" => "new",
      "line" => 1,
      "body" => "Keep this context"
    }

    assert {:ok, event} =
             Pulls.submit(
               ctx.repository,
               pull,
               ctx.reviewer,
               ctx.reviewer_credential,
               params,
               "comment-one"
             )

    assert event.excerpt == "new"

    assert {:ok, %{id: event_id}} =
             Pulls.submit(
               ctx.repository,
               pull,
               ctx.reviewer,
               ctx.reviewer_credential,
               params,
               "comment-one"
             )

    assert event_id == event.id
    assert Repo.aggregate(ReviewEvent, :count) == 1

    assert {:error, :authorization_changed} =
             Pulls.submit(
               ctx.repository,
               pull,
               ctx.reader,
               ctx.reader_credential,
               params,
               "reader-comment"
             )

    assert {:error, :comment_line_unavailable} =
             Pulls.submit(
               ctx.repository,
               pull,
               ctx.reviewer,
               ctx.reviewer_credential,
               Map.put(params, "line", 100),
               "bad-line-comment"
             )

    assert {:error, :self_approval_denied} =
             Pulls.submit(
               ctx.repository,
               pull,
               ctx.owner,
               ctx.owner_credential,
               Map.put(params, "kind", "approve"),
               "self-approve"
             )

    next = commit(ctx.repository, "changed again\n", ctx.source)
    git(ctx.repository, ["update-ref", "refs/heads/feature", next, ctx.source])

    assert {:error, :revision_changed} =
             Pulls.submit(
               ctx.repository,
               pull,
               ctx.reviewer,
               ctx.reviewer_credential,
               Map.put(params, "kind", "approve"),
               "stale-approve"
             )

    assert Repo.get!(ReviewEvent, event.id).source_sha == ctx.source
    assert Repo.get!(ReviewEvent, event.id).excerpt == "new"
  end

  test "provider reports converge under replay/order and latest attempt on exact SHA controls policy",
       ctx do
    {:ok, provider} =
      Checks.create_provider(ctx.repository, ctx.owner, ctx.owner_credential, "fixture-ci")

    credential = Repo.get!(Gitgood.Credential, provider.credential_id)

    {:ok, policy} =
      Checks.set_policy(ctx.repository, ctx.owner, ctx.owner_credential, %{
        "version" => 1,
        "approvals" => 1,
        "required_checks" => [%{"provider_id" => provider.id, "name" => "build"}]
      })

    params = %{
      "sha" => ctx.source,
      "name" => "build",
      "attempt" => 1,
      "sequence" => 2,
      "status" => "running"
    }

    assert {:error, :authorization_changed} =
             Checks.report(ctx.repository, ctx.owner, ctx.owner_credential, params)

    assert {:ok, run} = Checks.report(ctx.repository, ctx.owner, credential, params)

    assert {:ok, %{id: id, sequence: 2}} =
             Checks.report(ctx.repository, ctx.owner, credential, %{
               params
               | "sequence" => 1,
                 "status" => "pending"
             })

    assert id == run.id
    assert {:ok, %{id: ^id}} = Checks.report(ctx.repository, ctx.owner, credential, params)

    assert {:error, :sequence_conflict} =
             Checks.report(ctx.repository, ctx.owner, credential, %{
               params
               | "status" => "failure"
             })

    assert not Checks.satisfied?(ctx.repository, ctx.source, policy)

    assert {:ok, _} =
             Checks.report(ctx.repository, ctx.owner, credential, %{
               params
               | "sequence" => 3,
                 "status" => "success"
             })

    assert Checks.satisfied?(ctx.repository, ctx.source, policy)
    assert not Checks.satisfied?(ctx.repository, ctx.target, policy)

    assert {:error, :terminal_result_immutable} =
             Checks.report(ctx.repository, ctx.owner, credential, %{
               params
               | "sequence" => 4,
                 "status" => "failure"
             })

    assert {:ok, _} =
             Checks.report(ctx.repository, ctx.owner, credential, %{
               params
               | "attempt" => 2,
                 "sequence" => 1,
                 "status" => "pending"
             })

    assert not Checks.satisfied?(ctx.repository, ctx.source, policy)

    {:ok, rotated} =
      Checks.rotate_provider(ctx.repository, ctx.owner, ctx.owner_credential, provider.id)

    assert Accounts.resolve(provider.token, "checks") == nil
    current_credential = Repo.get!(Gitgood.Credential, rotated.credential_id)

    assert {:error, :provider_rotated_use_new_attempt} =
             Checks.report(ctx.repository, ctx.owner, current_credential, params)

    assert {:ok, _} =
             Checks.report(ctx.repository, ctx.owner, current_credential, %{
               params
               | "attempt" => 3,
                 "status" => "success"
             })

    assert Checks.satisfied?(ctx.repository, ctx.source, policy)
    {:ok, _} = Accounts.revoke(current_credential)
    assert not Checks.satisfied?(ctx.repository, ctx.source, policy)

    assert {:error, :authorization_changed} =
             Checks.report(ctx.repository, ctx.owner, credential, params)
  end
end
