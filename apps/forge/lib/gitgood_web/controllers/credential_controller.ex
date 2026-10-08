defmodule GitgoodWeb.CredentialController do
  use GitgoodWeb, :controller
  alias Gitgood.{Accounts, Credential, Repo, Repositories}
  alias GitgoodWeb.Auth

  def create(conn, %{"team" => team, "name" => name}) do
    case Repositories.get(conn.assigns.user, team, name) do
      nil ->
        Auth.reject(conn, 404, "repository_not_found")

      repository ->
        {token, credential} = Accounts.issue(conn.assigns.user, "git", repository.id)

        json(conn, %{
          token: token,
          id: credential.id,
          username: conn.assigns.user.username,
          expires_at: credential.expires_at,
          repository_id: repository.id
        })
    end
  end

  def delete(conn, %{"id" => id}) do
    with {id, ""} <- Integer.parse(id),
         %Credential{user_id: user_id} = credential <- Repo.get(Credential, id),
         true <- user_id == conn.assigns.user.id do
      {:ok, _} = Accounts.revoke(credential)
      json(conn, %{revoked: true})
    else
      _ -> Auth.reject(conn, 404, "credential_not_found")
    end
  end
end
