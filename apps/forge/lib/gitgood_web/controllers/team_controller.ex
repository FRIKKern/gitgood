defmodule GitgoodWeb.TeamController do
  use GitgoodWeb, :controller
  alias Gitgood.Teams
  alias GitgoodWeb.Auth

  def index(conn, %{"team" => team}),
    do: respond(conn, Teams.members(conn.assigns.user, conn.assigns.credential, team))

  def change(conn, %{"team" => team}) do
    key = List.first(get_req_header(conn, "idempotency-key"))

    respond(
      conn,
      Teams.change(conn.assigns.user, conn.assigns.credential, team, conn.body_params, key)
    )
  end

  defp respond(conn, {:ok, result}), do: json(conn, result)

  defp respond(conn, {:error, error}) do
    status =
      case error do
        :team_not_found -> 404
        :member_not_found -> 404
        :authorization_changed -> 401
        :members_unavailable -> 503
        :invalid_membership_change -> 422
        :invalid_idempotency_key -> 422
        _ -> 409
      end

    Auth.reject(conn, status, Atom.to_string(error))
  end
end
