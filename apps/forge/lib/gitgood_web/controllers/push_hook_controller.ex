defmodule GitgoodWeb.PushHookController do
  use GitgoodWeb, :controller
  alias GitgoodWeb.Auth

  def create(conn, %{"id" => id}) do
    with true <- conn.remote_ip == {127, 0, 0, 1},
         ["Bearer " <> capability] <- get_req_header(conn, "authorization"),
         {:ok, body, conn} <- read_body(conn, length: 65536),
         {:ok, _} <- Gitgood.Pushes.validate(id, capability, body) do
      json(conn, %{allowed: true})
    else
      _ -> Auth.reject(conn, 403, "push_denied")
    end
  rescue
    _ -> Auth.reject(conn, 403, "push_denied")
  end
end
