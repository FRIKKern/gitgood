defmodule Gitgood.Checks do
  import Ecto.Query
  alias Gitgood.{Accounts, BranchPolicy, Browse, CheckProvider, CheckRun, Credential, Lease, Repo}
  @ranks %{"pending" => 0, "running" => 1, "success" => 2, "failure" => 2, "cancelled" => 2}
  def policy(repository),
    do:
      Repo.get_by(BranchPolicy, repository_id: repository.id) ||
        %BranchPolicy{repository_id: repository.id}

  def providers(repository),
    do: Repo.all(from p in CheckProvider, where: p.repository_id == ^repository.id)

  def create_provider(repository, user, credential, name) do
    Lease.actor(repository, user, credential, ["owner"], fn repository ->
      unless valid_name?(name), do: Repo.rollback(:invalid_provider_name)

      if Repo.get_by(CheckProvider, repository_id: repository.id, name: name),
        do: Repo.rollback(:provider_exists)

      {token, issued} = Accounts.issue(user, "checks", repository.id)

      provider =
        Repo.insert!(%CheckProvider{
          repository_id: repository.id,
          credential_id: issued.id,
          name: name
        })

      %{
        id: provider.id,
        credential_id: issued.id,
        name: name,
        token: token,
        expires_at: issued.expires_at
      }
    end)
  end

  def set_policy(repository, user, credential, params) do
    Lease.actor(repository, user, credential, ["owner"], fn repository ->
      approvals = params["approvals"]
      required = params["required_checks"]

      unless is_integer(approvals) and approvals in 1..10 and is_list(required) and
               length(required) <= 16 and
               Enum.all?(required, fn item ->
                 is_map(item) and is_integer(item["provider_id"]) and valid_name?(item["name"]) and
                   Repo.get_by(CheckProvider,
                     id: item["provider_id"],
                     repository_id: repository.id
                   )
               end) and length(Enum.uniq(required)) == length(required),
             do: Repo.rollback(:invalid_policy)

      current = policy(repository)
      unless params["version"] == current.version, do: Repo.rollback(:policy_changed)

      changes =
        Ecto.Changeset.change(current,
          approvals: approvals,
          required_checks: required,
          version: current.version + 1
        )

      Repo.insert_or_update!(changes)
    end)
  end

  def rotate_provider(repository, user, credential, id) do
    Lease.actor(repository, user, credential, ["owner"], fn repository ->
      provider = Repo.get_by(CheckProvider, id: id, repository_id: repository.id)
      unless provider, do: Repo.rollback(:provider_unavailable)
      {:ok, _} = Accounts.revoke(Repo.get!(Credential, provider.credential_id))
      {token, issued} = Accounts.issue(user, "checks", repository.id)
      provider |> Ecto.Changeset.change(credential_id: issued.id) |> Repo.update!()

      %{
        id: provider.id,
        name: provider.name,
        credential_id: issued.id,
        token: token,
        expires_at: issued.expires_at
      }
    end)
  end

  def report(repository, user, credential, params) do
    Lease.actor(
      repository,
      user,
      credential,
      ["owner", "writer"],
      fn repository ->
        unless credential.kind == "checks", do: Repo.rollback(:provider_credential_required)

        provider =
          Repo.get_by(CheckProvider, credential_id: credential.id, repository_id: repository.id)

        unless provider, do: Repo.rollback(:provider_unavailable)
        sha = params["sha"]
        name = params["name"]
        attempt = params["attempt"]
        sequence = params["sequence"]
        status = params["status"]

        unless valid_name?(name) and is_integer(attempt) and attempt in 1..2_147_483_647 and
                 is_integer(sequence) and sequence in 1..2_147_483_647 and
                 Map.has_key?(@ranks, status),
               do: Repo.rollback(:invalid_check_report)

        unless Browse.reachable(repository, sha) == :ok, do: Repo.rollback(:revision_unavailable)

        existing =
          Repo.get_by(CheckRun, provider_id: provider.id, sha: sha, name: name, attempt: attempt)

        cond do
          is_nil(existing) ->
            Repo.insert!(%CheckRun{
              provider_id: provider.id,
              credential_id: credential.id,
              sha: sha,
              name: name,
              attempt: attempt,
              sequence: sequence,
              status: status
            })

          existing.credential_id != credential.id ->
            Repo.rollback(:provider_rotated_use_new_attempt)

          sequence < existing.sequence ->
            existing

          sequence == existing.sequence and status == existing.status ->
            existing

          sequence == existing.sequence ->
            Repo.rollback(:sequence_conflict)

          @ranks[existing.status] == 2 and status != existing.status ->
            Repo.rollback(:terminal_result_immutable)

          @ranks[status] < @ranks[existing.status] ->
            Repo.rollback(:status_regression)

          true ->
            existing
            |> Ecto.Changeset.change(sequence: sequence, status: status)
            |> Repo.update!()
        end
      end,
      "checks"
    )
  end

  def latest(provider_id, sha, name),
    do:
      Repo.one(
        from c in CheckRun,
          where: c.provider_id == ^provider_id and c.sha == ^sha and c.name == ^name,
          order_by: [desc: c.attempt],
          limit: 1
      )

  def satisfied?(repository, sha, policy) do
    Enum.all?(policy.required_checks, fn item ->
      provider = Repo.get_by(CheckProvider, id: item["provider_id"], repository_id: repository.id)
      credential = if provider, do: Repo.get(Credential, provider.credential_id)
      result = if provider, do: latest(provider.id, sha, item["name"])

      not is_nil(credential) and is_nil(credential.revoked_at) and
        DateTime.compare(credential.expires_at, Accounts.now()) == :gt and
        Accounts.role(credential.user_id, repository.team) in ["owner", "writer"] and
        not is_nil(result) and
        result.status == "success" and result.credential_id == credential.id
    end)
  end

  def results(repository, sha),
    do:
      Repo.all(
        from c in CheckRun,
          join: p in CheckProvider,
          on: p.id == c.provider_id,
          where: p.repository_id == ^repository.id and c.sha == ^sha,
          order_by: [desc: c.attempt, desc: c.id],
          limit: 200,
          select: %{
            id: c.id,
            provider_id: p.id,
            provider: p.name,
            sha: c.sha,
            name: c.name,
            attempt: c.attempt,
            sequence: c.sequence,
            status: c.status
          }
      )

  def public_policy(policy), do: Map.take(policy, [:version, :approvals, :required_checks])

  def public_result(result),
    do: Map.take(result, [:id, :provider_id, :sha, :name, :attempt, :sequence, :status])

  defp valid_name?(value),
    do: is_binary(value) and Regex.match?(~r/\A[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}\z/, value)
end
