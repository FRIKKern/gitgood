defmodule GitgoodWeb.BarkparkConnectionController do
  use GitgoodWeb, :controller
  alias Gitgood.BarkparkConnections
  alias GitgoodWeb.Auth

  def show(conn, _),
    do: respond(conn, BarkparkConnections.show(conn.assigns.user, conn.assigns.credential))

  def connect(conn, _) do
    respond(
      conn,
      BarkparkConnections.connect(
        conn.assigns.user,
        conn.assigns.credential,
        conn.body_params,
        List.first(get_req_header(conn, "idempotency-key"))
      )
    )
  end

  def disconnect(conn, _) do
    result =
      case conn.body_params do
        %{"expected_generation" => generation} = params when map_size(params) == 1 ->
          BarkparkConnections.disconnect(
            conn.assigns.user,
            conn.assigns.credential,
            generation,
            List.first(get_req_header(conn, "idempotency-key"))
          )

        _ ->
          {:error, :invalid_connection_request}
      end

    respond(conn, result)
  end

  defp respond(conn, {:ok, result}), do: json(conn, result)

  defp respond(conn, {:error, error}) do
    status =
      case error do
        :authorization_changed -> 401
        :invalid_connection_request -> 422
        :invalid_idempotency_key -> 422
        :idempotency_conflict -> 409
        :connection_changed -> 409
        :barkpark_scope_denied -> 403
        :barkpark_access_denied -> 403
        :barkpark_scope_missing -> 404
        _ -> 503
      end

    Auth.reject(conn, status, Atom.to_string(error))
  end
end
