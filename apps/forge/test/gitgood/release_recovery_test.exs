defmodule Gitgood.ReleaseRecoveryTest do
  use GitgoodWeb.RealConnCase, async: false
  import Ecto.Query
  alias Gitgood.{Accounts, Git, Lease, Releases, Repo, ReleaseRecord, ReleaseAsset, ReleaseEvent}

  setup do
    {:ok, user} = Accounts.create_user("release-recovery", "synthetic-password")
    Accounts.add_member(user, "release-recovery", "owner")
    {_, credential} = Accounts.issue(user, "session")

    {:ok, repository} =
      Gitgood.Repositories.create(user, "release-recovery", "project", "release-recovery")

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
        input: "Recovery release\n"
      )

    sha = String.trim(sha)
    {_, 0} = Git.run(["--git-dir", Git.path(repository), "update-ref", "refs/tags/v1", sha])

    {:ok, release} =
      Releases.create(
        repository,
        user,
        credential,
        %{
          "tag" => "v1",
          "commit_sha" => sha,
          "title" => "Recovery release",
          "notes" => "Original notes"
        },
        "recovery-release"
      )

    {:ok, asset} =
      Releases.asset_intent(
        repository,
        user,
        credential,
        release.id,
        %{"name" => "release.bin", "size" => 1, "sha256" => Releases.digest("x")},
        "recovery-asset"
      )

    {:ok, _} = Releases.upload(repository, user, credential, release.id, asset.id, "x")
    {:ok, %{release: release}} = Releases.get(repository, user, credential, release.id)

    request = %{
      "kind" => "publish",
      "version" => release.version,
      "notes_digest" => release.notes_digest
    }

    tasks = start_supervised!({Task.Supervisor, []})

    on_exit(fn ->
      Repo.delete_all(from e in ReleaseEvent, where: e.release_id == ^release.id)
      Repo.delete_all(from a in ReleaseAsset, where: a.release_id == ^release.id)
      Repo.delete!(Repo.get!(ReleaseRecord, release.id))
      Repo.delete!(Repo.get!(Gitgood.Repository, repository.id))
      Repo.delete_all(from c in Gitgood.Credential, where: c.user_id == ^user.id)
      Repo.delete_all(from m in Gitgood.Membership, where: m.user_id == ^user.id)
      Repo.delete!(user)
      File.rm_rf!(Git.path(repository))
    end)

    %{
      repository: repository,
      user: user,
      credential: credential,
      release: release,
      request: request,
      tasks: tasks
    }
  end

  defp publish(ctx, key),
    do:
      Releases.action(ctx.repository, ctx.user, ctx.credential, ctx.release.id, ctx.request, key)

  defp current(ctx) do
    {:ok, result} = Releases.get(ctx.repository, ctx.user, ctx.credential, ctx.release.id)
    result
  end

  defp halt_worker(worker) do
    monitor = Process.monitor(worker)
    Process.exit(worker, :kill)
    assert_receive {:DOWN, ^monitor, :process, ^worker, :killed}, 10_000
  end

  test "worker loss before SQL commit cannot leave a published claim or event", ctx do
    parent = self()

    {:ok, worker} =
      Task.Supervisor.start_child(ctx.tasks, fn ->
        Lease.actor(ctx.repository, ctx.user, ctx.credential, ["owner"], fn _ ->
          {:ok, _} = publish(ctx, "before-commit")
          send(parent, {:before_commit, self()})

          receive do
            :finish -> :ok
          end
        end)
      end)

    assert_receive {:before_commit, ^worker}, 10_000
    halt_worker(worker)
    assert current(ctx).release.state == "draft"
    refute Enum.any?(current(ctx).events, &(&1.kind == "publish"))
    assert {:ok, %{release: %{state: "published"}}} = publish(ctx, "before-commit")
    assert Enum.count(current(ctx).events, &(&1.kind == "publish")) == 1
  end

  test "worker loss after committed publication retains one outcome and identical replay", ctx do
    parent = self()

    {:ok, worker} =
      Task.Supervisor.start_child(ctx.tasks, fn ->
        {:ok, result} = publish(ctx, "lost-outcome")
        send(parent, {:committed, self(), result.event.id})

        receive do
          :reply -> :ok
        end
      end)

    assert_receive {:committed, ^worker, event_id}, 10_000
    halt_worker(worker)
    assert current(ctx).release.state == "published"
    assert {:ok, %{event: %{id: ^event_id}}} = publish(ctx, "lost-outcome")
    assert Enum.count(current(ctx).events, &(&1.kind == "publish")) == 1
  end

  test "concurrent publication retries converge and concurrent revisions cannot overwrite each other",
       ctx do
    tasks =
      for _ <- 1..2,
          do:
            Task.Supervisor.async_nolink(ctx.tasks, fn ->
              receive do
                :go -> publish(ctx, "concurrent-publication")
              end
            end)

    Enum.each(tasks, &send(&1.pid, :go))
    results = Enum.map(tasks, &Task.await(&1, 10_000))
    assert Enum.all?(results, &match?({:ok, %{release: %{state: "published"}}}, &1))
    assert length(Enum.uniq(Enum.map(results, fn {:ok, result} -> result.event.id end))) == 1
    version = current(ctx).release.version

    tasks =
      for title <- ["First correction", "Second correction"],
          do:
            Task.Supervisor.async_nolink(ctx.tasks, fn ->
              receive do
                :go ->
                  Releases.action(
                    ctx.repository,
                    ctx.user,
                    ctx.credential,
                    ctx.release.id,
                    %{
                      "kind" => "correct",
                      "version" => version,
                      "title" => title,
                      "notes" => title,
                      "reason" => "Concurrent correction"
                    },
                    String.replace(title, " ", "-")
                  )
              end
            end)

    Enum.each(tasks, &send(&1.pid, :go))
    results = Enum.map(tasks, &Task.await(&1, 10_000))
    assert Enum.count(results, &match?({:ok, _}, &1)) == 1
    assert Enum.count(results, &(&1 == {:error, :release_revision_changed})) == 1
    assert current(ctx).release.version == version + 1
    assert Enum.count(current(ctx).events, &(&1.kind == "correct")) == 1
  end
end
