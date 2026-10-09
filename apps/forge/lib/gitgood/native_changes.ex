defmodule Gitgood.NativeChanges do
  @moduledoc "Opaque change landing identities resolved under current native access."
  import Ecto.Query
  alias Gitgood.{Access, PullRequest, Repo, Repository}

  def locate(user, credential, value) do
    Access.with_session(user, credential, fn access ->
      uuid =
        case Ecto.UUID.cast(value) do
          {:ok, uuid} -> uuid
          _ -> Repo.rollback(:change_not_found)
        end

      teams = Enum.map(access.teams, & &1.team)

      query =
        from p in PullRequest,
          join: r in Repository,
          on: r.id == p.repository_id,
          where: p.public_id == ^uuid and r.team in ^teams,
          select: %{id: p.public_id, title: p.title, team: r.team, name: r.name}

      query =
        if access.repository_scope,
          do: from([p, r] in query, where: r.id == ^access.repository_scope),
          else: query

      case Repo.one(query) do
        nil ->
          Repo.rollback(:change_not_found)

        change ->
          %{
            id: change.id,
            title: change.title,
            url: "/repos/" <> change.team <> "/" <> change.name <> "/pulls/" <> change.id
          }
      end
    end)
  end
end
