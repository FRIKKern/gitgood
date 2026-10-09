defmodule GitgoodWeb.Auth do
  import Plug.Conn
  alias Gitgood.{Access, Accounts, Credential, Repo, Repository}
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
          establish(conn, user, credential, token)
        else
          reject(conn, 403, "csrf_required")
        end

      nil ->
        reject(conn, 401, "sign_in_required")
    end
  rescue
    _ in [DBConnection.ConnectionError, Postgrex.Error] -> reject(conn, 503, "access_unavailable")
  end

  defp establish(conn, user, credential, token) do
    case Access.load(user, credential) do
      {:ok, snapshot} ->
        conn = put_resp_header(conn, "x-gitgood-access-context", snapshot.context)
        supplied = get_req_header(conn, "x-gitgood-access-context")

        cond do
          supplied != [] and supplied != [snapshot.context] and
              not (conn.request_path == "/api/session" and conn.method == "DELETE") ->
            reject(conn, 409, "authorization_changed")

          not permitted_scope?(conn, snapshot) ->
            reject(conn, 403, "credential_scope_denied")

          true ->
            conn
            |> assign(:user, user)
            |> assign(:credential, credential)
            |> assign(:session_token, token)
            |> assign(:access_snapshot, snapshot)
            |> register_before_send(fn response ->
              if response.request_path == "/api/session" and response.method == "DELETE" and
                   response.status in 200..299 do
                put_resp_header(response, "x-gitgood-access-context", "anonymous")
              else
                case Access.load(user, credential) do
                  {:ok, %{context: context}} when context == snapshot.context ->
                    response

                  {:ok, changed} ->
                    redact(response, 409, "authorization_changed", changed.context)

                  {:error, :authorization_changed} ->
                    redact(response, 401, "sign_in_required", "anonymous")

                  {:error, _} ->
                    redact(response, 503, "access_unavailable", nil)
                end
              end
            end)
        end

      {:error, :authorization_changed} ->
        reject(conn, 401, "sign_in_required")

      {:error, _} ->
        reject(conn, 503, "access_unavailable")
    end
  end

  defp permitted_scope?(_, %{repository_scope: nil}), do: true

  defp permitted_scope?(conn, snapshot) do
    cond do
      conn.request_path == "/api/session" ->
        true

      conn.method == "GET" and conn.request_path in ["/api/repos", "/api/search", "/api/activity"] ->
        true

      conn.method == "GET" and match?(["api", "changes", _], conn.path_info) ->
        # NativeChanges applies the current credential's repository scope inside its read.
        true

      is_binary(conn.path_params["team"]) and is_binary(conn.path_params["name"]) ->
        repository =
          Repo.get_by(Repository,
            id: snapshot.repository_scope,
            team: conn.path_params["team"],
            name: conn.path_params["name"]
          )

        not is_nil(repository) and Enum.any?(snapshot.teams, &(&1.team == repository.team))

      conn.method == "DELETE" and String.starts_with?(conn.request_path, "/api/credentials/") ->
        with {id, ""} <- Integer.parse(conn.path_params["id"] || ""),
             %Credential{} = credential <- Repo.get(Credential, id) do
          credential.user_id == snapshot.user.id and
            credential.repository_id == snapshot.repository_scope
        else
          _ -> false
        end

      true ->
        false
    end
  end

  defp redact(conn, status, error, context) do
    # None of a rejected attachment's name/digest/length may survive in headers.
    safe =
      Enum.filter(conn.resp_headers, fn {name, _} ->
        name in [
          "x-request-id",
          "x-frame-options",
          "x-content-type-options",
          "referrer-policy",
          "content-security-policy",
          "strict-transport-security"
        ]
      end)

    conn =
      %{conn | status: status, resp_headers: safe, resp_body: Jason.encode!(%{error: error})}
      |> put_resp_header("content-type", "application/json; charset=utf-8")
      |> put_resp_header("cache-control", "no-store")

    if context, do: put_resp_header(conn, "x-gitgood-access-context", context), else: conn
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
