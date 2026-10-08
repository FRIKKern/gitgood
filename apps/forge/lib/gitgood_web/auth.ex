defmodule GitgoodWeb.Auth do
  import Plug.Conn
  alias Gitgood.Accounts
  def init(opts), do: opts

  def call(conn, _) do
    conn = fetch_cookies(conn)

    bearer =
      case get_req_header(conn, "authorization") do
        ["Bearer " <> token] -> token
        _ -> nil
      end

    token = bearer || conn.cookies["gitgood_session"]

    case Accounts.resolve(token, "session") do
      {user, credential} ->
        if conn.method in ["GET", "HEAD", "OPTIONS"] or not is_nil(bearer) or
             valid_csrf?(conn, token) do
          conn
          |> assign(:user, user)
          |> assign(:credential, credential)
          |> assign(:session_token, token)
        else
          reject(conn, 403, "csrf_required")
        end

      nil ->
        reject(conn, 401, "sign_in_required")
    end
  end

  def csrf(token) do
    secret = Application.fetch_env!(:gitgood, GitgoodWeb.Endpoint)[:secret_key_base]
    :crypto.mac(:hmac, :sha256, secret, token) |> Base.url_encode64(padding: false)
  end

  def valid_origin?(conn) do
    case get_req_header(conn, "origin") do
      [] -> true
      [origin] -> origin == Application.fetch_env!(:gitgood, :web_origin)
      _ -> false
    end
  end

  defp valid_csrf?(conn, token) do
    case get_req_header(conn, "x-gitgood-csrf") do
      [provided] -> valid_origin?(conn) and Plug.Crypto.secure_compare(provided, csrf(token))
      _ -> false
    end
  end

  def reject(conn, status, error),
    do:
      conn
      |> put_resp_content_type("application/json")
      |> send_resp(status, Jason.encode!(%{error: error}))
      |> halt()
end
