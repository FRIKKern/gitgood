defmodule Gitgood.Access do
  @moduledoc "Current session access snapshot; public identity is a keyed opaque digest."
  import Ecto.Query
  alias Gitgood.{Accounts, Credential, Membership, Repo, Repository, User}

  def load(user, credential), do: with_session(user, credential, & &1)

  def with_session(user, credential, action) do
    Repo.transaction(fn ->
      # Lock in the same credential-before-membership order as native writes.
      # Revocation/role updates serialize with the complete read callback.
      current = Repo.one(from c in Credential, where: c.id == ^credential.id, lock: "FOR SHARE")

      unless current && current.user_id == user.id && current.kind == "session" &&
               is_nil(current.revoked_at) &&
               DateTime.compare(current.expires_at, Accounts.now()) == :gt,
             do: Repo.rollback(:authorization_changed)

      actor = Repo.get(User, user.id) || Repo.rollback(:authorization_changed)

      query =
        from m in Membership,
          where: m.user_id == ^actor.id,
          order_by: [asc: m.id],
          lock: "FOR SHARE"

      query =
        if current.repository_id do
          repository =
            Repo.get(Repository, current.repository_id) || Repo.rollback(:authorization_changed)

          from m in query, where: m.team == ^repository.team
        else
          query
        end

      memberships = Repo.all(query)

      claims = [
        actor.id,
        current.id,
        current.repository_id,
        DateTime.to_iso8601(current.expires_at),
        Enum.map(memberships, &Map.take(&1, [:id, :team, :role, :inserted_at, :updated_at]))
      ]

      secret = Application.fetch_env!(:gitgood, GitgoodWeb.Endpoint)[:secret_key_base]

      context =
        :crypto.mac(:hmac, :sha256, secret, Jason.encode!(claims))
        |> Base.url_encode64(padding: false)

      action.(%{
        context: context,
        repository_scope: current.repository_id,
        user: %{id: actor.id, username: actor.username},
        teams: Enum.map(memberships, &Map.take(&1, [:team, :role]))
      })
    end)
  rescue
    _ in [DBConnection.ConnectionError, Postgrex.Error] -> {:error, :access_unavailable}
  end
end
