defmodule Gitgood.Merges do
  import Ecto.Query

  alias Gitgood.{
    Accounts,
    Checks,
    Git,
    GitOperation,
    Lease,
    Membership,
    PullRequest,
    Pulls,
    Repo,
    Repository,
    ReviewEvent
  }

  def request(repository, pull, user, credential, params, key, opts \\ []) do
    case DynamicSupervisor.start_child(
           Gitgood.MergeWorkers,
           {Gitgood.MergeWorker, {repository, pull, user, credential, params, key, opts}}
         ) do
      {:ok, worker} ->
        try do
          GenServer.call(worker, :run, :infinity)
        catch
          :exit, _ -> {:error, :operation_interrupted_query_before_retry}
        end

      _ ->
        {:error, :merge_busy_retry}
    end
  end

  def execute(repository, pull, user, credential, params, key, opts) do
    Lease.actor(repository, user, credential, ["owner", "writer"], fn repository ->
      key = Lease.key!(key)
      digest = Lease.digest([pull.id, params])
      Gitgood.Pushes.reconcile_repository(repository, nil)
      reconcile_repository(repository)
      Gitgood.Imports.reconcile_repository(repository)

      if Repo.exists?(
           from o in GitOperation,
             where: o.repository_id == ^repository.id and o.state == "uncertain"
         ),
         do: Repo.rollback(:recovery_required)

      existing =
        Repo.get_by(GitOperation,
          repository_id: repository.id,
          actor_id: user.id,
          kind: "merge",
          request_key: key
        )

      if existing do
        if existing.request_digest == digest,
          do: existing,
          else: Repo.rollback(:idempotency_conflict)
      else
        pull = Repo.get!(PullRequest, pull.id)
        unless pull.state == "open", do: Repo.rollback(:pull_request_closed)

        current =
          case Pulls.revisions(repository, pull) do
            {:ok, current} -> current
            _ -> Repo.rollback(:branches_unavailable)
          end

        policy = Checks.policy(repository)

        unless params["source_sha"] == current.source_sha and
                 params["target_sha"] == current.target_sha and
                 params["policy_version"] == policy.version,
               do: Repo.rollback(:validation_changed)

        unless approved?(repository, pull, current, policy),
          do: Repo.rollback(:approval_required_or_changes_requested)

        lock_providers!(repository, policy)

        unless Checks.satisfied?(repository, current.source_sha, policy),
          do: Repo.rollback(:required_checks_not_successful)

        unless match?(
                 {:ok, _, 0},
                 Git.command([
                   "--git-dir",
                   Git.path(repository),
                   "merge-base",
                   "--is-ancestor",
                   current.target_sha,
                   current.source_sha
                 ])
               ),
               do: Repo.rollback(:fast_forward_required)

        if current.source_sha == current.target_sha, do: Repo.rollback(:already_up_to_date)

        unless match?(
                 {:ok, _, 0},
                 Git.command([
                   "--git-dir",
                   Git.path(repository),
                   "config",
                   "transfer.hideRefs",
                   "refs/gitgood/"
                 ])
               ),
               do: Repo.rollback(:git_configuration_unavailable)

        metadata = %{
          "pull_request_id" => pull.id,
          "source_ref" => pull.source_ref,
          "target_ref" => pull.target_ref,
          "source_sha" => current.source_sha,
          "target_sha" => current.target_sha,
          "policy" => Checks.public_policy(policy),
          "checks" => Checks.results(repository, current.source_sha),
          "reviews" =>
            Enum.map(
              Pulls.events(pull),
              &Map.take(&1, [:id, :actor_id, :kind, :source_sha, :target_sha])
            ),
          "strategy" => "fast_forward",
          "validated_at" => DateTime.to_iso8601(Accounts.now())
        }

        task =
          Task.Supervisor.async_nolink(Gitgood.DurableWrites, fn ->
            Repo.insert!(%GitOperation{
              repository_id: repository.id,
              actor_id: user.id,
              credential_id: credential.id,
              kind: "merge",
              request_key: key,
              request_digest: digest,
              metadata: metadata
            })
          end)

        operation = Task.await(task, 10000)
        fault(opts, :before_ref, operation)
        marker = marker(operation)

        transaction =
          "start\nverify #{pull.source_ref} #{current.source_sha}\nupdate #{pull.target_ref} #{current.source_sha} #{current.target_sha}\ncreate #{marker} #{current.source_sha}\nprepare\ncommit\n"

        _result =
          Git.command(["--git-dir", Git.path(repository), "update-ref", "--stdin"],
            input: transaction,
            timeout: 15000,
            limit: 4096
          )

        fault(opts, :after_ref, operation)
        fault(opts, :before_outcome, operation)
        reconcile_operation(repository, operation)
      end
    end)
  end

  defp approved?(repository, pull, current, policy) do
    events =
      Repo.all(
        from e in ReviewEvent,
          where: e.pull_request_id == ^pull.id and e.kind != "comment",
          order_by: [desc: e.id]
      )
      |> Enum.uniq_by(& &1.actor_id)

    current_events =
      Enum.filter(events, fn event ->
        membership =
          Repo.one(
            from m in Membership,
              where: m.user_id == ^event.actor_id and m.team == ^repository.team,
              lock: "FOR SHARE"
          )

        not is_nil(membership) and
          membership.role in ["owner", "writer"] and
          event.source_sha == current.source_sha and event.target_sha == current.target_sha
      end)

    Enum.count(current_events, &(&1.kind == "approve" and &1.actor_id != pull.author_id)) >=
      policy.approvals and
      not Enum.any?(current_events, &(&1.kind == "changes_requested"))
  end

  defp lock_providers!(repository, policy) do
    for item <- Enum.sort_by(policy.required_checks, & &1["provider_id"]) do
      provider = Repo.get(Gitgood.CheckProvider, item["provider_id"])

      if provider do
        Repo.one(
          from c in Gitgood.Credential,
            where: c.id == ^provider.credential_id,
            lock: "FOR NO KEY UPDATE"
        )

        credential = Repo.get!(Gitgood.Credential, provider.credential_id)

        Repo.one(
          from m in Membership,
            where: m.user_id == ^credential.user_id and m.team == ^repository.team,
            lock: "FOR SHARE"
        )
      end
    end
  end

  def reconcile do
    ids =
      Repo.all(
        from o in GitOperation,
          where: o.kind == "merge" and o.state in ["started", "uncertain"],
          distinct: o.repository_id,
          select: o.repository_id
      )

    for id <- ids do
      Repo.transaction(fn ->
        repository =
          Repo.one!(from r in Repository, where: r.id == ^id, lock: "FOR NO KEY UPDATE")

        reconcile_repository(repository)
      end)
    end
  end

  def reconcile_repository(repository) do
    operations =
      Repo.all(
        from o in GitOperation,
          where:
            o.repository_id == ^repository.id and o.kind == "merge" and
              o.state in ["started", "uncertain"]
      )

    Enum.each(operations, &reconcile_operation(repository, &1))
  end

  def reconcile_operation(repository, operation) do
    metadata = operation.metadata
    source = metadata["source_sha"]
    target = lookup(repository, metadata["target_ref"])
    marker_sha = lookup(repository, marker(operation))

    state =
      cond do
        marker_sha == source and ancestor?(repository, source, target) -> "applied"
        marker_sha == "missing" and target == metadata["target_sha"] -> "failed"
        true -> "uncertain"
      end

    outcome = %{
      "merge_sha" => if(state == "applied", do: source, else: nil),
      "target_at_reconciliation" => target,
      "marker" => marker(operation),
      "marker_sha" => marker_sha,
      "reconciled_at" => DateTime.to_iso8601(Accounts.now())
    }

    operation =
      operation |> Ecto.Changeset.change(state: state, outcome: outcome) |> Repo.update!()

    if state == "applied" do
      Repo.get!(PullRequest, metadata["pull_request_id"])
      |> Ecto.Changeset.change(state: "merged")
      |> Repo.update!()
    end

    operation
  end

  defp ancestor?(repository, source, target) do
    Regex.match?(~r/\A[0-9a-f]{40}\z/, target) and
      match?(
        {:ok, _, 0},
        Git.command([
          "--git-dir",
          Git.path(repository),
          "merge-base",
          "--is-ancestor",
          source,
          target
        ])
      )
  end

  defp lookup(repository, ref) do
    case Git.ref(repository, ref) do
      {:ok, sha} -> sha
      {:error, :missing_ref} -> "missing"
      _ -> "unavailable"
    end
  end

  defp marker(operation), do: "refs/gitgood/operations/" <> operation.id

  defp fault(opts, point, operation) do
    if callback = opts[:fault], do: callback.(point, operation)
  end

  def public(operation),
    do:
      Map.take(operation, [
        :id,
        :actor_id,
        :credential_id,
        :kind,
        :state,
        :updates,
        :metadata,
        :outcome,
        :inserted_at
      ])
end
