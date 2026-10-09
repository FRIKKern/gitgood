defmodule GitgoodWeb.EvidenceController do
  use GitgoodWeb, :controller
  alias Gitgood.{Evidence, Pulls, Repositories, SourceLinks}
  alias GitgoodWeb.Auth

  def index(conn, params) do
    with_pull(conn, params, fn repository, pull ->
      case Evidence.list(
             repository,
             pull,
             conn.assigns.user,
             conn.assigns.credential,
             params["link"],
             params["connection_generation"],
             params["cursor"]
           ) do
        {:ok, view} -> conn |> protect(repository, pull, view["source"]) |> json(view)
        error -> respond(conn, error)
      end
    end)
  end

  def events(conn, params) do
    with_pull(conn, params, fn repository, pull ->
      case Evidence.event_history(
             repository,
             pull,
             conn.assigns.user,
             conn.assigns.credential,
             params["link"],
             params["evidence"],
             params["connection_generation"],
             params["cursor"]
           ) do
        {:ok, view} -> conn |> protect(repository, pull, view["source"]) |> json(view)
        error -> respond(conn, error)
      end
    end)
  end

  def attach(conn, params) do
    with_pull(conn, params, fn repository, pull ->
      respond(
        conn,
        Evidence.attach(
          repository,
          pull,
          conn.assigns.user,
          conn.assigns.credential,
          params["link"],
          conn.body_params,
          key(conn)
        )
      )
    end)
  end

  def unavailable(conn, params) do
    with_pull(conn, params, fn repository, pull ->
      case conn.body_params do
        %{"reason" => reason} = body when map_size(body) == 1 ->
          respond(
            conn,
            Evidence.unavailable(
              repository,
              pull,
              conn.assigns.user,
              conn.assigns.credential,
              params["link"],
              params["evidence"],
              reason,
              key(conn)
            )
          )

        _ ->
          respond(conn, {:error, :invalid_evidence})
      end
    end)
  end

  def download(conn, params) do
    with_pull(conn, params, fn repository, pull ->
      case Evidence.download(
             repository,
             pull,
             conn.assigns.user,
             conn.assigns.credential,
             params["link"],
             params["evidence"],
             params["connection_generation"]
           ) do
        {:ok, {artifact, content, source}} ->
          conn
          |> protect(repository, pull, source, params["evidence"])
          |> put_resp_header("content-type", "application/octet-stream")
          |> put_resp_header(
            "content-disposition",
            ~s(attachment; filename="#{artifact.artifact_name}")
          )
          |> put_resp_header("x-content-type-options", "nosniff")
          |> put_resp_header("x-gitgood-sha256", artifact.artifact_sha256)
          |> put_resp_header("content-length", Integer.to_string(artifact.artifact_size))
          |> send_resp(200, content)

        error ->
          respond(conn, error)
      end
    end)
  end

  defp protect(conn, repository, pull, source, evidence_id \\ nil)

  defp protect(
         conn,
         repository,
         pull,
         %{"source_state" => "available", "connection_generation" => generation} = source,
         evidence_id
       ) do
    register_before_send(conn, fn response ->
      result =
        if evidence_id do
          Evidence.guard_artifact(
            repository,
            pull,
            conn.assigns.user,
            conn.assigns.credential,
            source,
            evidence_id
          )
        else
          SourceLinks.guard(
            repository,
            pull,
            conn.assigns.user,
            conn.assigns.credential,
            source["id"],
            source["generation"],
            generation
          )
        end

      case result do
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
  end

  defp protect(conn, _, _, _, _), do: conn

  defp with_pull(conn, params, action) do
    with repository when not is_nil(repository) <-
           Repositories.get(conn.assigns.user, params["team"], params["name"]),
         pull when not is_nil(pull) <- Pulls.get_public(repository, params["id"]) do
      action.(repository, pull)
    else
      _ -> Auth.reject(conn, 404, "evidence_not_found")
    end
  end

  defp key(conn), do: List.first(get_req_header(conn, "idempotency-key"))
  defp respond(conn, {:ok, result}), do: json(conn, result)

  defp respond(conn, {:error, reason}) do
    status =
      case reason do
        :evidence_not_found ->
          404

        :source_link_not_found ->
          404

        :authorization_changed ->
          403

        reason
        when reason in [:invalid_evidence, :invalid_idempotency_key, :invalid_evidence_cursor] ->
          422

        reason
        when reason in [
               :evidence_requirement_changed,
               :evidence_revision_changed,
               :idempotency_conflict,
               :evidence_artifact_unavailable,
               :evidence_limit,
               :source_link_changed,
               :connection_changed
             ] ->
          409

        _ ->
          503
      end

    Auth.reject(conn, status, Atom.to_string(reason))
  end
end
