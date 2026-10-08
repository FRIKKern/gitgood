defmodule GitgoodWeb.SessionController do
  use GitgoodWeb, :controller
  alias Gitgood.Accounts
  alias GitgoodWeb.Auth

  def create(conn, params) do
    cond do
      not Auth.valid_origin?(conn) ->
        Auth.reject(conn, 403, "origin_denied")

      not Gitgood.LoginLimiter.allow?(conn.remote_ip) ->
        Auth.reject(conn, 429, "try_again_later")

      true ->
        case Accounts.authenticate(params["username"], params["password"]) do
          {:ok, user} ->
            {token, _} = Accounts.issue(user, "session")

            conn
            |> put_resp_cookie("gitgood_session", token,
              http_only: true,
              same_site: "Strict",
              secure:
                String.starts_with?(Application.fetch_env!(:gitgood, :web_origin), "https://"),
              max_age: 86400
            )
            |> json(%{
              user: %{id: user.id, username: user.username},
              csrf: Auth.csrf(token),
              teams: Accounts.teams(user.id)
            })

          _ ->
            Auth.reject(conn, 401, "invalid_credentials")
        end
    end
  end

  def show(conn, _) do
    user = conn.assigns.user

    json(conn, %{
      user: %{id: user.id, username: user.username},
      csrf: Auth.csrf(conn.assigns.session_token),
      teams: Accounts.teams(user.id)
    })
  end

  def delete(conn, _) do
    {:ok, _} = Accounts.revoke(conn.assigns.credential)
    conn |> delete_resp_cookie("gitgood_session") |> json(%{signed_out: true})
  end
end
