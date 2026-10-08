defmodule Gitgood.Access do
  @moduledoc "Current session access snapshot; public identity is a keyed opaque digest."
  import Ecto.Query
  alias Gitgood.{Accounts, Credential, Membership, Repo, User}

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

      memberships =
        Repo.all(
          from m in Membership,
            where: m.user_id == ^actor.id,
            order_by: [asc: m.id],
            lock: "FOR SHARE"
        )

      claims = [
        actor.id,
        current.id,
        DateTime.to_iso8601(current.expires_at),
        Enum.map(memberships, &Map.take(&1, [:id, :team, :role, :inserted_at, :updated_at]))
      ]

      secret = Application.fetch_env!(:gitgood, GitgoodWeb.Endpoint)[:secret_key_base]

      context =
        :crypto.mac(:hmac, :sha256, secret, Jason.encode!(claims))
        |> Base.url_encode64(padding: false)

      action.(%{
        context: context,
        user: %{id: actor.id, username: actor.username},
        teams: Enum.map(memberships, &Map.take(&1, [:team, :role]))
      })
    end)
  rescue
    _ in [DBConnection.ConnectionError, Postgrex.Error] -> {:error, :access_unavailable}
  end
end
