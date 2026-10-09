defmodule GitgoodWeb.SourceLinkController do
  use GitgoodWeb, :controller
  alias Gitgood.{Pulls, Repositories, SourceLinks}
  alias GitgoodWeb.Auth

  def index(conn, params),
    do:
      with_pull(conn, params, fn repository, pull ->
        case SourceLinks.list(repository, pull, conn.assigns.user, conn.assigns.credential) do
          {:ok, links} -> json(conn, %{links: links})
          error -> respond(conn, error)
        end
      end)

  def attach(conn, params),
    do:
      with_pull(conn, params, fn repository, pull ->
        respond(
          conn,
          SourceLinks.attach(
            repository,
            pull,
            conn.assigns.user,
            conn.assigns.credential,
            conn.body_params,
            key(conn)
          )
        )
      end)

  def remove(conn, params),
    do:
      with_pull(conn, params, fn repository, pull ->
        case conn.body_params do
          %{"generation" => generation} = body when map_size(body) == 1 ->
            respond(
              conn,
              SourceLinks.remove(
                repository,
                pull,
                conn.assigns.user,
                conn.assigns.credential,
                params["link"],
                generation,
                key(conn)
              )
            )

          _ ->
            respond(conn, {:error, :invalid_source_link})
        end
      end)

  def show(conn, params),
    do:
      with_pull(conn, params, fn repository, pull ->
        result =
          SourceLinks.read(
            repository,
            pull,
            conn.assigns.user,
            conn.assigns.credential,
            params["link"],
            params["connection_generation"]
          )

        conn =
          case result do
            {:ok, %{"source_state" => "available"} = value} ->
              register_before_send(conn, fn response ->
                case SourceLinks.guard(
                       repository,
                       pull,
                       conn.assigns.user,
                       conn.assigns.credential,
                       value["id"],
                       value["generation"],
                       value["connection_generation"]
                     ) do
                  {:ok, :current} ->
                    response

                  _ ->
                    safe =
                      Enum.filter(response.resp_headers, fn {name, _} ->
                        name in [
                          "x-request-id",
                          "x-gitgood-access-context",
                          "x-frame-options",
                          "x-content-type-options",
                          "referrer-policy",
                          "content-security-policy",
                          "strict-transport-security"
                        ]
                      end)

                    %{
                      response
                      | status: 409,
                        resp_headers: safe,
                        resp_body: Jason.encode!(%{error: "source_access_changed"})
                    }
                    |> put_resp_header("content-type", "application/json; charset=utf-8")
                    |> put_resp_header("cache-control", "no-store")
                end
              end)

            _ ->
              conn
          end

        respond(conn, result)
      end)

  defp with_pull(conn, params, action) do
    with repository when not is_nil(repository) <-
           Repositories.get(conn.assigns.user, params["team"], params["name"]),
         pull when not is_nil(pull) <- Pulls.get_public(repository, params["id"]) do
      action.(repository, pull)
    else
      _ -> Auth.reject(conn, 404, "source_link_not_found")
    end
  end

  defp key(conn), do: List.first(get_req_header(conn, "idempotency-key"))
  defp respond(conn, {:ok, value}), do: json(conn, value)

  defp respond(conn, {:error, reason}) do
    status =
      case reason do
        :source_link_not_found ->
          404

        :source_missing_or_inaccessible ->
          404

        :source_denied ->
          403

        :authorization_changed ->
          403

        reason when reason in [:invalid_source_link, :invalid_idempotency_key] ->
          422

        reason
        when reason in [
               :connection_changed,
               :idempotency_conflict,
               :source_link_changed,
               :source_link_limit
             ] ->
          409

        _ ->
          503
      end

    Auth.reject(conn, status, Atom.to_string(reason))
  end
end
