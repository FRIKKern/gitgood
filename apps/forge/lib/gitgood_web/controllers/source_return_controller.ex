defmodule GitgoodWeb.SourceReturnController do
  use GitgoodWeb, :controller
  alias Gitgood.{Pulls, Repositories, SourceReturns}
  alias GitgoodWeb.Auth

  def index(conn, params),
    do:
      with_pull(conn, params, fn repository, pull ->
        case SourceReturns.list(
               repository,
               pull,
               conn.assigns.user,
               conn.assigns.credential,
               params["link"]
             ) do
          {:ok, values} -> json(conn, %{operations: values})
          error -> respond(conn, error)
        end
      end)

  def request(conn, params),
    do:
      with_pull(conn, params, fn repository, pull ->
        respond(
          conn,
          SourceReturns.request(
            repository,
            pull,
            conn.assigns.user,
            conn.assigns.credential,
            params["link"],
            conn.body_params,
            List.first(get_req_header(conn, "idempotency-key"))
          )
        )
      end)

  def retry(conn, params),
    do:
      with_pull(conn, params, fn repository, pull ->
        respond(
          conn,
          SourceReturns.retry(
            repository,
            pull,
            conn.assigns.user,
            conn.assigns.credential,
            params["link"],
            params["operation"],
            conn.body_params
          )
        )
      end)

  def observe(conn, params),
    do:
      with_pull(conn, params, fn repository, pull ->
        case conn.body_params do
          %{"connection_generation" => generation} = body when map_size(body) == 1 ->
            respond(
              conn,
              SourceReturns.observe(
                repository,
                pull,
                conn.assigns.user,
                conn.assigns.credential,
                params["link"],
                params["operation"],
                generation
              )
            )

          _ ->
            respond(conn, {:error, :invalid_source_operation})
        end
      end)

  defp with_pull(conn, params, action) do
    with repository when not is_nil(repository) <-
           Repositories.get(conn.assigns.user, params["team"], params["name"]),
         pull when not is_nil(pull) <- Pulls.get_public(repository, params["id"]) do
      action.(repository, pull)
    else
      _ -> Auth.reject(conn, 404, "source_operation_not_found")
    end
  end

  defp respond(conn, {:ok, value}), do: json(conn, value)

  defp respond(conn, {:error, reason}) do
    status =
      cond do
        reason in [
          :source_link_not_found,
          :source_operation_not_found,
          :source_missing_or_inaccessible
        ] ->
          404

        reason in [:authorization_changed, :source_denied] ->
          403

        reason in [:invalid_source_operation, :invalid_idempotency_key, :unsupported_paper] ->
          422

        reason in [
          :source_link_changed,
          :connection_changed,
          :idempotency_conflict,
          :source_operation_limit,
          :source_operation_running,
          :source_operation_resolved,
          :source_pointer_not_observed,
          :pointer_conflict
        ] ->
          409

        true ->
          503
      end

    Auth.reject(conn, status, Atom.to_string(reason))
  end
end
