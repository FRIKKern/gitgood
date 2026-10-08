defmodule Gitgood.Lease do
  import Ecto.Query
  alias Gitgood.{Accounts, Credential, Membership, Repo, Repository}

  def actor(repository, user, credential, roles, action, kind \\ "session") do
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

        unless (credential.user_id == user.id and credential.kind == kind and
                  (credential.kind == "session" or credential.repository_id == repository.id) and
                  is_nil(credential.revoked_at) and
                  DateTime.compare(credential.expires_at, Accounts.now()) == :gt and
                  membership) && membership.role in roles,
               do: Repo.rollback(:authorization_changed)

        action.(repository)
      end,
      timeout: 90000
    )
  end

  def key!(key) do
    unless is_binary(key) and byte_size(key) in 8..128 and
             Regex.match?(~r/\A[a-zA-Z0-9_-]+\z/, key),
           do: Repo.rollback(:invalid_idempotency_key)

    key
  end

  def digest(value), do: value |> Jason.encode!() |> Accounts.digest()
end
