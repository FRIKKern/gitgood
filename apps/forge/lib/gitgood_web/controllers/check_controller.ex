defmodule GitgoodWeb.CheckController do
  use GitgoodWeb, :controller
  alias Gitgood.{Accounts, Checks, Repositories}
  alias GitgoodWeb.Auth

  def show(conn, params),
    do:
      with_repository(conn, params, fn repository ->
        json(conn, %{
          policy: Checks.public_policy(Checks.policy(repository)),
          providers:
            Enum.map(Checks.providers(repository), &Map.take(&1, [:id, :name, :credential_id]))
        })
      end)

  def policy(conn, params),
    do:
      with_repository(conn, params, fn repository ->
        respond(
          conn,
          Checks.set_policy(repository, conn.assigns.user, conn.assigns.credential, params),
          &Checks.public_policy/1
        )
      end)

  def provider(conn, params),
    do:
      with_repository(conn, params, fn repository ->
        respond(
          conn,
          Checks.create_provider(
            repository,
            conn.assigns.user,
            conn.assigns.credential,
            conn.body_params["name"]
          ),
          & &1
        )
      end)

  def report(conn, %{"team" => team, "name" => name}) do
    with ["Bearer " <> token] <- get_req_header(conn, "authorization"),
         {user, credential} <- Accounts.resolve(token, "checks"),
         repository when not is_nil(repository) <- Repositories.get(user, team, name),
         true <- credential.repository_id == repository.id do
      respond(
        conn,
        Checks.report(repository, user, credential, conn.body_params),
        &Checks.public_result/1
      )
    else
      _ -> Auth.reject(conn, 401, "provider_credential_required")
    end
  end

  def rotate(conn, params) do
    with_repository(conn, params, fn repository ->
      case Integer.parse(params["id"] || "") do
        {id, ""} when id > 0 ->
          respond(
            conn,
            Checks.rotate_provider(repository, conn.assigns.user, conn.assigns.credential, id),
            & &1
          )

        _ ->
          Auth.reject(conn, 404, "provider_unavailable")
      end
    end)
  end

  defp with_repository(conn, %{"team" => team, "name" => name}, action) do
    case Repositories.get(conn.assigns.user, team, name) do
      nil -> Auth.reject(conn, 404, "repository_not_found")
      repository -> action.(repository)
    end
  end

  defp respond(conn, {:ok, value}, render), do: json(conn, render.(value))
  defp respond(conn, {:error, reason}, _), do: Auth.reject(conn, 409, Atom.to_string(reason))
end
