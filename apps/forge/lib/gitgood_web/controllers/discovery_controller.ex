defmodule GitgoodWeb.DiscoveryController do
  use GitgoodWeb, :controller
  alias Gitgood.Discovery
  alias GitgoodWeb.Auth

  def search(conn, _),
    do:
      respond(
        conn,
        Discovery.search(conn.assigns.user, conn.assigns.credential, conn.query_params)
      )

  def activity(conn, _),
    do:
      respond(
        conn,
        Discovery.activity(conn.assigns.user, conn.assigns.credential, conn.query_params)
      )

  def repository_activity(conn, params) do
    query =
      conn.query_params |> Map.put("team", params["team"]) |> Map.put("name", params["name"])

    respond(conn, Discovery.activity(conn.assigns.user, conn.assigns.credential, query))
  end

  defp respond(conn, {:ok, result}), do: json(conn, result)

  defp respond(conn, {:error, :repository_not_found}),
    do: Auth.reject(conn, 404, "repository_not_found")

  defp respond(conn, {:error, :authorization_changed}),
    do: Auth.reject(conn, 401, "sign_in_required")

  defp respond(conn, {:error, :access_unavailable}),
    do: Auth.reject(conn, 503, "discovery_unavailable")

  defp respond(conn, {:error, reason}), do: Auth.reject(conn, 409, Atom.to_string(reason))
end
