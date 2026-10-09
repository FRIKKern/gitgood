defmodule GitgoodWeb.BrowseController do
  use GitgoodWeb, :controller
  alias Gitgood.{Browse, Repositories}
  alias GitgoodWeb.Auth
  def branches(conn, params), do: serve(conn, params, &Browse.branches/1, :branches)

  def snapshot(conn, params),
    do: serve(conn, params, &Browse.snapshot(&1, params["sha"], params["path"] || ""), nil)

  def diff(conn, params),
    do: serve(conn, params, &Browse.diff(&1, params["sha"], params["base"]), nil)

  defp serve(conn, %{"team" => team, "name" => name}, action, wrapper) do
    case Repositories.get(conn.assigns.user, team, name) do
      nil ->
        Auth.reject(conn, 404, "repository_not_found")

      repository ->
        case action.(repository) do
          {:ok, value} ->
            json(conn, if(wrapper, do: %{wrapper => value}, else: value))

          {:error, reason} ->
            Auth.reject(
              conn,
              if(reason in [:git_unavailable, :history_unavailable, :browse_busy_retry],
                do: 503,
                else: 422
              ),
              Atom.to_string(reason)
            )
        end
    end
  end
end
