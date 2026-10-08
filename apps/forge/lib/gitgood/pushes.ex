defmodule Gitgood.Pushes do
  import Ecto.Query
  alias Gitgood.{Accounts, Credential, Git, GitOperation, Membership, Repo, Repository}
  @zero String.duplicate("0", 40)

  def begin(repository, user, credential) do
    capability = Base.url_encode64(:crypto.strong_rand_bytes(32), padding: false)

    {:ok, operation} =
      Repo.insert(%GitOperation{
        repository_id: repository.id,
        actor_id: user.id,
        credential_id: credential.id,
        kind: "push",
        capability_digest: Accounts.digest(capability),
        expires_at: DateTime.add(Accounts.now(), 120)
      })

    {operation, capability}
  end

  def receive(repository, user, credential, action) do
    case DynamicSupervisor.start_child(
           Gitgood.PushWorkers,
           {Gitgood.PushWorker, {repository, user, credential, action}}
         ) do
      {:ok, worker} -> GenServer.call(worker, :run, :infinity)
      {:error, :max_children} -> {:error, :busy}
      _ -> {:error, :operation_failed}
    end
  end

  def execute(repository, user, credential, action) do
    Repo.transaction(
      fn ->
        repository =
          Repo.one!(
            from r in Repository, where: r.id == ^repository.id, lock: "FOR NO KEY UPDATE"
          )

        credential =
          Repo.one!(
            from c in Credential, where: c.id == ^credential.id, lock: "FOR NO KEY UPDATE"
          )

        membership =
          Repo.one(
            from m in Membership,
              where: m.user_id == ^user.id and m.team == ^repository.team,
              lock: "FOR UPDATE"
          )

        unless credential.kind in ["git", "ssh"] and credential.user_id == user.id and
                 Accounts.repository_credential?(credential, repository) and
                 is_nil(credential.revoked_at) and
                 DateTime.compare(credential.expires_at, Accounts.now()) == :gt and
                 not is_nil(membership) and membership.role in ["owner", "writer"],
               do: Repo.rollback(:authorization_changed)

        reconcile_repository(repository, nil)
        Gitgood.Merges.reconcile_repository(repository)
        Gitgood.Imports.reconcile_repository(repository)

        if Repo.exists?(
             from o in GitOperation,
               where: o.repository_id == ^repository.id and o.state == "uncertain"
           ),
           do: Repo.rollback(:recovery_required)

        # Independent connection commits responsibility while the repository lease is held.
        # NO KEY UPDATE allows foreign-key checks without releasing mutation serialization.
        task =
          Task.Supervisor.async_nolink(Gitgood.DurableWrites, fn ->
            begin(repository, user, credential)
          end)

        {operation, capability} = Task.await(task, 10_000)
        result = action.(operation, capability)
        current = Repo.get!(GitOperation, operation.id)
        outcome = reconcile_operation(repository, current)
        {result, outcome}
      end,
      timeout: 90_000
    )
  end

  def validate(id, capability, body) do
    with {:ok, id} <- Ecto.UUID.cast(id),
         %GitOperation{} = operation <- Repo.get(GitOperation, id),
         true <- operation.kind == "push" and is_binary(operation.capability_digest),
         true <-
           Plug.Crypto.secure_compare(operation.capability_digest, Accounts.digest(capability)),
         true <- DateTime.compare(operation.expires_at, Accounts.now()) == :gt,
         true <- operation.state in ["started", "validated"],
         {:ok, updates} <- parse_updates(body),
         %Repository{} = repository <- Repo.get(Repository, operation.repository_id),
         %Credential{} = credential <- Repo.get(Credential, operation.credential_id),
         true <-
           is_nil(credential.revoked_at) and
             DateTime.compare(credential.expires_at, Accounts.now()) == :gt,
         true <- Accounts.role(operation.actor_id, repository.team) in ["owner", "writer"],
         true <- allowed?(repository, operation, updates) do
      Repo.transaction(fn ->
        current = Repo.one!(from o in GitOperation, where: o.id == ^id, lock: "FOR UPDATE")

        unless current.state == "started" or
                 (current.state == "validated" and current.updates == updates),
               do: Repo.rollback(:denied)

        current |> Ecto.Changeset.change(state: "validated", updates: updates) |> Repo.update!()
      end)
    else
      _ -> {:error, :denied}
    end
  end

  defp parse_updates(body) when byte_size(body) <= 65536 do
    lines = String.split(body, "\n", trim: true)
    updates = Enum.map(lines, &String.split(&1, " "))

    if length(lines) in 1..64 and
         Enum.all?(updates, fn
           [old, new, "refs/heads/" <> branch] ->
             sha?(old) and sha?(new) and Gitgood.Ref.branch?("refs/heads/" <> branch) and
               new != @zero

           _ ->
             false
         end) do
      {:ok,
       Enum.map(updates, fn [old, new, ref] -> %{"old" => old, "new" => new, "ref" => ref} end)}
    else
      {:error, :invalid_updates}
    end
  end

  defp parse_updates(_), do: {:error, :invalid_updates}
  defp sha?(value), do: Regex.match?(~r/\A[0-9a-f]{40}\z/, value)

  defp allowed?(repository, operation, updates) do
    Enum.all?(updates, fn update ->
      update["ref"] != "refs/heads/main" or
        (update["old"] == @zero and operation.actor_id == repository.owner_id)
    end)
  end

  def reconcile do
    ids =
      Repo.all(
        from o in GitOperation,
          where: o.kind == "push" and o.state in ["started", "validated", "uncertain"],
          distinct: o.repository_id,
          select: o.repository_id
      )

    for id <- ids do
      Repo.transaction(fn ->
        repository = Repo.one!(from r in Repository, where: r.id == ^id, lock: "FOR UPDATE")
        reconcile_repository(repository, nil)
      end)
    end
  end

  def reconcile_repository(repository, excluded) do
    query =
      from o in GitOperation,
        where:
          o.repository_id == ^repository.id and o.kind == "push" and
            o.state in ["started", "validated", "uncertain"]

    query = if excluded, do: from(o in query, where: o.id != ^excluded), else: query
    Enum.each(Repo.all(query), &reconcile_operation(repository, &1))

    if not is_nil(excluded) and
         Repo.exists?(
           from o in GitOperation,
             where: o.repository_id == ^repository.id and o.state == "uncertain"
         ),
       do: Repo.rollback(:recovery_required)
  end

  defp reconcile_operation(repository, operation) do
    refs =
      for update <- operation.updates, into: %{} do
        value =
          case Git.ref(repository, update["ref"]) do
            {:ok, value} -> value
            {:error, :missing_ref} -> @zero
            _ -> "unavailable"
          end

        {update["ref"], value}
      end

    state =
      cond do
        operation.updates == [] -> "failed"
        Enum.all?(operation.updates, &(refs[&1["ref"]] == &1["new"])) -> "applied"
        Enum.all?(operation.updates, &(refs[&1["ref"]] == &1["old"])) -> "failed"
        true -> "uncertain"
      end

    outcome = %{refs: refs, reconciled_at: DateTime.to_iso8601(Accounts.now())}
    operation |> Ecto.Changeset.change(state: state, outcome: outcome) |> Repo.update!()
  end
end
