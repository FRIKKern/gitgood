defmodule GitgoodWeb.RepositoryController do
  use GitgoodWeb, :controller
  alias Gitgood.Repositories
  alias GitgoodWeb.Auth

  def index(conn, _),
    do:
      json(conn, %{
        repositories: Enum.map(Repositories.list(conn.assigns.user), &Repositories.public/1)
      })

  def show(conn, %{"team" => team, "name" => name}) do
    case Repositories.get(conn.assigns.user, team, name) do
      nil -> Auth.reject(conn, 404, "repository_not_found")
      repository -> json(conn, Repositories.public(repository))
    end
  end

  def create(conn, params) do
    key = get_req_header(conn, "idempotency-key") |> List.first()

    case Repositories.create(conn.assigns.user, params["team"], params["name"], key) do
      {:ok, repository} ->
        conn |> put_status(201) |> json(Repositories.public(repository))

      {:error, %Ecto.Changeset{} = changeset} ->
        fields = Ecto.Changeset.traverse_errors(changeset, fn {message, _} -> message end)
        conn |> put_status(422) |> json(%{error: "invalid_repository", fields: fields})

      {:error, :forbidden} ->
        Auth.reject(conn, 403, "repository_creation_denied")

      {:error, :storage_failed} ->
        Auth.reject(conn, 503, "creation_pending_retry_with_same_key")

      {:error, error} ->
        Auth.reject(conn, 409, Atom.to_string(error))
    end
  end
end
