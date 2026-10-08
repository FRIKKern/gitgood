defmodule Gitgood.Accounts do
  import Ecto.Query
  alias Gitgood.{Credential, Membership, Repo, User}
  @iterations 600_000
  def create_user(username, password)
      when is_binary(password) and byte_size(password) in 12..256 do
    salt = :crypto.strong_rand_bytes(16)

    %User{password_salt: salt, password_hash: hash(password, salt)}
    |> User.changeset(%{username: username})
    |> Repo.insert()
  end

  def create_user(_, _), do: {:error, :password_length}

  def authenticate(username, password)
      when is_binary(username) and is_binary(password) and byte_size(password) <= 256 do
    user = Repo.get_by(User, username: username)
    salt = if user, do: user.password_salt, else: <<0::128>>
    expected = if user, do: user.password_hash, else: <<0::256>>
    actual = hash(password, salt)

    if Plug.Crypto.secure_compare(actual, expected) and user,
      do: {:ok, user},
      else: {:error, :unauthorized}
  end

  def authenticate(_, _), do: {:error, :unauthorized}

  def add_member(user, team, role) when role in ["owner", "writer", "reader"] do
    %Membership{user_id: user.id, team: team, role: role}
    |> Ecto.Changeset.change()
    |> Ecto.Changeset.validate_format(:team, ~r/\A[a-z][a-z0-9-]{1,39}\z/)
    |> Ecto.Changeset.unique_constraint([:user_id, :team])
    |> Repo.insert()
  end

  def issue(user, kind, repository_id \\ nil) when kind in ["session", "git", "checks"] do
    token = Base.url_encode64(:crypto.strong_rand_bytes(32), padding: false)
    days = if kind == "session", do: 1, else: 30

    {:ok, credential} =
      Repo.insert(%Credential{
        user_id: user.id,
        digest: digest(token),
        kind: kind,
        repository_id: repository_id,
        expires_at: DateTime.add(now(), days * 86400)
      })

    {token, credential}
  end

  def resolve(token, kind) when is_binary(token) and byte_size(token) in 32..128 do
    Repo.one(
      from c in Credential,
        join: u in User,
        on: c.user_id == u.id,
        where:
          c.digest == ^digest(token) and c.kind == ^kind and is_nil(c.revoked_at) and
            c.expires_at > ^now(),
        select: {u, c}
    )
  end

  def resolve(_, _), do: nil

  def role(user_id, team),
    do:
      Repo.one(
        from m in Membership, where: m.user_id == ^user_id and m.team == ^team, select: m.role
      )

  def teams(user_id),
    do:
      Repo.all(
        from m in Membership, where: m.user_id == ^user_id, select: %{team: m.team, role: m.role}
      )

  def revoke(credential), do: Repo.update(Ecto.Changeset.change(credential, revoked_at: now()))
  def digest(token), do: :crypto.hash(:sha256, token)
  def now, do: DateTime.utc_now() |> DateTime.truncate(:second)
  defp hash(password, salt), do: :crypto.pbkdf2_hmac(:sha256, password, salt, @iterations, 32)
end
