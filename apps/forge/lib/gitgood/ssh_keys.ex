defmodule Gitgood.SSHKeys do
  import Ecto.Query
  alias Gitgood.{Accounts, Credential, Repo, SSHKey, User}

  def parse(value) when is_binary(value) and byte_size(value) <= 1024 do
    with ["ssh-ed25519", encoded | _] <- String.split(String.trim(value)),
         {:ok, <<11::32, "ssh-ed25519", 32::32, _key::binary-size(32)>> = blob} <-
           Base.decode64(encoded) do
      digest = Accounts.digest(blob)

      {:ok,
       %{
         canonical: "ssh-ed25519 " <> Base.encode64(blob),
         digest: digest,
         fingerprint: "SHA256:" <> Base.encode64(digest, padding: false)
       }}
    else
      _ -> {:error, :supported_ed25519_public_key_required}
    end
  end

  def parse(_), do: {:error, :supported_ed25519_public_key_required}

  def register(user, session, params, request_key) do
    with {:ok, key} <- parse(params["public_key"]),
         label when is_binary(label) and byte_size(label) in 1..80 <- params["label"] do
      Repo.transaction(fn ->
        session = Repo.one!(from c in Credential, where: c.id == ^session.id, lock: "FOR UPDATE")

        unless session.user_id == user.id and session.kind == "session" and
                 is_nil(session.revoked_at) and
                 DateTime.compare(session.expires_at, Accounts.now()) == :gt,
               do: Repo.rollback(:authorization_changed)

        Gitgood.Lease.key!(request_key)
        # Separate sessions for one actor still serialize the same registration.
        Repo.one!(from u in User, where: u.id == ^user.id, lock: "FOR NO KEY UPDATE")
        digest = Gitgood.Lease.digest(%{public_key: key.canonical, label: label})

        case Repo.get_by(SSHKey, user_id: user.id, request_key: request_key) do
          %SSHKey{request_digest: ^digest} = existing ->
            existing

          %SSHKey{} ->
            Repo.rollback(:idempotency_conflict)

          nil ->
            if Repo.get_by(SSHKey, fingerprint: key.fingerprint),
              do: Repo.rollback(:ssh_key_already_registered)

            credential =
              Repo.insert!(%Credential{
                user_id: user.id,
                kind: "ssh",
                digest: key.digest,
                expires_at: DateTime.add(Accounts.now(), 365 * 86400)
              })

            %SSHKey{
              user_id: user.id,
              credential_id: credential.id,
              public_key: key.canonical,
              fingerprint: key.fingerprint,
              label: label,
              request_key: request_key,
              request_digest: digest
            }
            |> Ecto.Changeset.change()
            |> Ecto.Changeset.unique_constraint(:fingerprint)
            |> Ecto.Changeset.unique_constraint([:user_id, :request_key])
            |> Repo.insert()
            |> case do
              {:ok, value} -> value
              {:error, _} -> Repo.rollback(:ssh_key_already_registered)
            end
        end
      end)
    else
      {:error, error} -> {:error, error}
      _ -> {:error, :key_label_required}
    end
  rescue
    Ecto.ConstraintError -> {:error, :ssh_key_already_registered}
  end

  def list(user),
    do: Repo.all(from k in SSHKey, where: k.user_id == ^user.id, order_by: [desc: k.id])

  def public(key) do
    credential = Repo.get!(Credential, key.credential_id)

    %{
      id: key.id,
      credential_id: credential.id,
      label: key.label,
      public_key: key.public_key,
      fingerprint: key.fingerprint,
      expires_at: credential.expires_at,
      revoked: not is_nil(credential.revoked_at)
    }
  end

  def authenticate(public_key, username) do
    with {:ok, key} <- parse(public_key),
         {user, credential} <-
           Repo.one(
             from c in Credential,
               join: k in SSHKey,
               on: k.credential_id == c.id and k.user_id == c.user_id,
               join: u in User,
               on: c.user_id == u.id,
               where:
                 c.digest == ^key.digest and c.kind == "ssh" and u.username == ^username and
                   is_nil(c.revoked_at) and c.expires_at > ^Accounts.now(),
               select: {u, c}
           ) do
      {:ok, user, credential}
    else
      _ -> {:error, :unauthorized}
    end
  end

  def current(user_id, credential_id) do
    case Repo.one(
           from c in Credential,
             join: k in SSHKey,
             on: k.credential_id == c.id and k.user_id == c.user_id,
             join: u in User,
             on: c.user_id == u.id,
             where:
               c.id == ^credential_id and c.user_id == ^user_id and c.kind == "ssh" and
                 is_nil(c.revoked_at) and c.expires_at > ^Accounts.now(),
             select: {u, c}
         ) do
      {user, credential} -> {:ok, user, credential}
      _ -> {:error, :unauthorized}
    end
  end
end
