defmodule Gitgood.InstallationOwnerBootstrap do
  @moduledoc "Durable creation receipt for the first installation owner; replay does not restore access."
  alias Gitgood.{Accounts, InstallationOwnerReceipt, Membership, Repo, User}

  @purpose "gitgood-installation-owner-v1"
  @fields ~w(installation request username team password)
  @namespace 1_197_034_579

  def create(params, expected_request_sha256) do
    with {:ok, payload} <- validate(params, expected_request_sha256),
         {:ok, secret} <- secret() do
      commitment = :crypto.mac(:hmac, :sha256, secret, payload)

      Repo.transaction(fn ->
        Repo.query!("SELECT pg_advisory_xact_lock($1::int, $2::int)", [@namespace, 1])

        case Repo.get(InstallationOwnerReceipt, 1) do
          nil -> create_first(params, commitment)
          receipt -> replay(receipt, params, commitment)
        end
      end)
    end
  end

  def validate(params, expected) when is_map(params) and is_binary(expected) do
    with true <- Enum.sort(Map.keys(params)) == Enum.sort(@fields),
         true <- Enum.all?(@fields, &(is_binary(params[&1]) and String.valid?(params[&1]))),
         {:ok, installation} <- Ecto.UUID.cast(params["installation"]),
         true <- installation == params["installation"],
         {:ok, request} <- Ecto.UUID.cast(params["request"]),
         true <- request == params["request"],
         true <-
           Enum.all?(~w(username team), &Regex.match?(~r/\A[a-z][a-z0-9-]{1,39}\z/, params[&1])),
         true <- byte_size(params["password"]) in 12..256,
         true <- Regex.match?(~r/\A[0-9a-f]{64}\z/, expected),
         payload <- Jason.encode!([@purpose | Enum.map(@fields, &params[&1])]),
         observed <- Base.encode16(:crypto.hash(:sha256, payload), case: :lower),
         true <- Plug.Crypto.secure_compare(observed, expected) do
      {:ok, payload}
    else
      _ -> {:error, :invalid_bootstrap_request}
    end
  end

  def validate(_, _), do: {:error, :invalid_bootstrap_request}

  defp secret do
    value = Application.get_env(:gitgood, GitgoodWeb.Endpoint, [])[:secret_key_base]

    if is_binary(value) and byte_size(value) >= 64,
      do: {:ok, value},
      else: {:error, :bootstrap_secret_unavailable}
  end

  defp create_first(params, commitment) do
    # Account creation outside this command must also exclude a fresh bootstrap.
    # These table locks conflict with ordinary inserts through Accounts or SQL.
    Repo.query!("LOCK TABLE users, memberships IN SHARE ROW EXCLUSIVE MODE")

    if Repo.exists?(User) or Repo.exists?(Membership),
      do: Repo.rollback(:installation_not_empty)

    with {:ok, user} <- Accounts.create_user(params["username"], params["password"]),
         {:ok, _member} <- Accounts.add_member(user, params["team"], "owner") do
      receipt =
        Repo.insert!(%InstallationOwnerReceipt{
          id: 1,
          installation: params["installation"],
          request: params["request"],
          username: params["username"],
          team: params["team"],
          user_id: user.id,
          input_commitment: commitment
        })

      metadata(receipt, "created")
    else
      _ -> Repo.rollback(:bootstrap_creation_refused)
    end
  end

  defp replay(receipt, params, commitment) do
    unless receipt.installation == params["installation"] and receipt.request == params["request"] and
             receipt.username == params["username"] and receipt.team == params["team"] and
             Plug.Crypto.secure_compare(receipt.input_commitment, commitment),
           do: Repo.rollback(:bootstrap_request_conflict)

    # This receipt deliberately does not log in, reset a password or re-add a
    # membership. Present function and authorization require separate probes.
    metadata(receipt, "recorded")
  end

  defp metadata(receipt, outcome) do
    %{
      protocol: 1,
      purpose: "installation_owner_bootstrap",
      outcome: outcome,
      installation: receipt.installation,
      request: receipt.request,
      username: receipt.username,
      team: receipt.team,
      user_id: receipt.user_id,
      role_at_creation: "owner",
      limitations: [
        "Recorded creation only; no current login, permissions, readiness or artifact verification."
      ]
    }
  end
end
