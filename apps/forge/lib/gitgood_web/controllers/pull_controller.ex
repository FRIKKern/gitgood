defmodule GitgoodWeb.PullController do
  use GitgoodWeb, :controller
  alias Gitgood.{Checks, GitOperation, Merges, Pulls, Repo, Repositories}
  alias GitgoodWeb.Auth

  def index(conn, params),
    do:
      with_repository(conn, params, fn repository ->
        json(conn, %{pull_requests: Enum.map(Pulls.list(repository), &Pulls.public/1)})
      end)

  def create(conn, params),
    do:
      with_repository(conn, params, fn repository ->
        respond(
          conn,
          Pulls.create(repository, conn.assigns.user, conn.assigns.credential, params, key(conn)),
          &Pulls.public/1
        )
      end)

  def show(conn, params),
    do:
      with_pull(conn, params, fn repository, pull ->
        case Pulls.browse_revisions(repository, pull) do
          {:ok, revisions} ->
            audit = if pull.state == "merged", do: Pulls.applied_operation(repository, pull)

            events =
              Enum.map(Pulls.events(pull, params["review"]), fn event ->
                value = Pulls.event_public(event)
                actor = Repo.get!(Gitgood.User, event.actor_id)

                Map.merge(value, %{
                  actor: actor.username,
                  outdated:
                    event.source_sha != revisions.source_sha or
                      event.target_sha != revisions.target_sha
                })
              end)

            json(
              conn,
              Map.merge(
                Pulls.public(pull),
                Map.merge(revisions, %{
                  events: events,
                  policy:
                    if(audit,
                      do: audit.metadata["policy"],
                      else: Checks.public_policy(Checks.policy(repository))
                    ),
                  checks:
                    if(audit,
                      do: audit.metadata["checks"] || [],
                      else: Checks.results(repository, revisions.source_sha)
                    )
                })
              )
            )

          {:error, reason} ->
            revision_refusal(conn, reason)
        end
      end)

  def diff(conn, params),
    do:
      with_pull(conn, params, fn repository, pull ->
        case Pulls.browse_diff(repository, pull) do
          {:error, reason}
          when reason in [:missing_ref, :ref_unavailable, :merge_audit_unavailable] ->
            revision_refusal(conn, reason)

          {:error, reason}
          when reason in [:browse_busy_retry, :git_unavailable, :history_unavailable] ->
            Auth.reject(conn, 503, Atom.to_string(reason))

          result ->
            respond(conn, result, & &1)
        end
      end)

  def review(conn, params),
    do:
      with_pull(conn, params, fn repository, pull ->
        respond(
          conn,
          Pulls.submit(
            repository,
            pull,
            conn.assigns.user,
            conn.assigns.credential,
            params,
            key(conn)
          ),
          &Pulls.event_public/1
        )
      end)

  def merge(conn, params),
    do:
      with_pull(conn, params, fn repository, pull ->
        case Merges.request(
               repository,
               pull,
               conn.assigns.user,
               conn.assigns.credential,
               params,
               key(conn)
             ) do
          {:ok, operation} ->
            conn
            |> put_status(
              if(operation.state == "applied",
                do: 200,
                else: if(operation.state == "failed", do: 409, else: 503)
              )
            )
            |> json(%{operation: Merges.public(operation)})

          {:error, reason} ->
            Auth.reject(conn, 409, Atom.to_string(reason))
        end
      end)

  def operation(conn, params),
    do:
      with_repository(conn, params, fn repository ->
        case Ecto.UUID.cast(params["id"]) do
          {:ok, id} ->
            case Repo.get_by(GitOperation, id: id, repository_id: repository.id) do
              nil -> Auth.reject(conn, 404, "operation_not_found")
              operation -> json(conn, %{operation: Merges.public(operation)})
            end

          _ ->
            Auth.reject(conn, 404, "operation_not_found")
        end
      end)

  def operations(conn, params),
    do:
      with_repository(conn, params, fn repository ->
        import Ecto.Query

        query =
          from o in GitOperation,
            where: o.repository_id == ^repository.id,
            order_by: [desc: o.inserted_at, desc: o.id],
            limit: 50

        query =
          if id = params["pull_request_id"],
            do:
              from(o in query,
                where:
                  o.kind == "merge" and
                    fragment(
                      "?->>'pull_request_id' = ?",
                      o.metadata,
                      ^case Pulls.get_public(repository, id) do
                        nil -> "unmatched"
                        pull -> Integer.to_string(pull.id)
                      end
                    )
              ),
            else: query

        query =
          if params["kind"] in ["push", "merge", "import"],
            do: from(o in query, where: o.kind == ^params["kind"]),
            else: query

        operations = Repo.all(query)

        json(conn, %{operations: Enum.map(operations, &Merges.public/1)})
      end)

  defp with_pull(conn, params, action),
    do:
      with_repository(conn, params, fn repository ->
        case Pulls.get_public(repository, params["id"]) do
          nil -> Auth.reject(conn, 404, "pull_request_not_found")
          pull -> action.(repository, pull)
        end
      end)

  defp with_repository(conn, %{"team" => team, "name" => name}, action) do
    case Repositories.get(conn.assigns.user, team, name) do
      nil -> Auth.reject(conn, 404, "repository_not_found")
      repository -> action.(repository)
    end
  end

  defp key(conn), do: get_req_header(conn, "idempotency-key") |> List.first()

  defp revision_refusal(conn, reason) when reason in [:browse_busy_retry, :ref_unavailable],
    do: Auth.reject(conn, 503, Atom.to_string(reason))

  defp revision_refusal(conn, _), do: Auth.reject(conn, 409, "branches_unavailable")

  defp respond(conn, {:ok, value}, render), do: json(conn, render.(value))
  defp respond(conn, {:error, reason}, _), do: Auth.reject(conn, 409, Atom.to_string(reason))
end
