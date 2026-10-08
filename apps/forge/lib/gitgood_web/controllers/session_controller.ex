defmodule GitgoodWeb.SessionController do
  use GitgoodWeb, :controller
  alias Gitgood.Accounts
  alias GitgoodWeb.Auth

  def create(conn, params) do
    address = GitgoodWeb.ClientAddress.login(conn)

    cond do
      not Auth.valid_origin?(conn) ->
        Auth.reject(conn, 403, "origin_denied")

      match?({:error, _}, address) ->
        Auth.reject(conn, 403, "client_address_unverified")

      not allow_login?(address) ->
        Auth.reject(conn, 429, "try_again_later")

      true ->
        case Accounts.authenticate(params["username"], params["password"]) do
          {:ok, user} ->
            {token, credential} = Accounts.issue(user, "session")

            case Gitgood.Access.load(user, credential) do
              {:ok, access} ->
                conn
                |> put_resp_header("x-gitgood-access-context", access.context)
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
                  teams: access.teams,
                  access_context: access.context
                })

              {:error, _} ->
                Accounts.revoke(credential)
                Auth.reject(conn, 503, "access_unavailable")
            end

          _ ->
            Auth.reject(conn, 401, "invalid_credentials")
        end
    end
  rescue
    _ in [DBConnection.ConnectionError, Postgrex.Error] ->
      Auth.reject(conn, 503, "access_unavailable")
  end

  defp allow_login?({:ok, address}), do: Gitgood.LoginLimiter.allow?(address)

  def show(conn, _) do
    user = conn.assigns.user

    json(conn, %{
      user: %{id: user.id, username: user.username},
      csrf: Auth.csrf(conn.assigns.session_token),
      teams: conn.assigns.access_snapshot.teams,
      access_context: conn.assigns.access_snapshot.context
    })
  end

  def delete(conn, _) do
    {:ok, _} = Accounts.revoke(conn.assigns.credential)
    conn |> delete_resp_cookie("gitgood_session") |> json(%{signed_out: true})
  end
end
