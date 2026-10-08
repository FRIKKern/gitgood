defmodule GitgoodWeb.HealthController do
  use GitgoodWeb, :controller

  def show(conn, _) do
    case Ecto.Adapters.SQL.query(Gitgood.Repo, "SELECT 1", []) do
      {:ok, _} ->
        json(conn, %{
          status: "ready",
          service: "gitgood",
          version: Application.spec(:gitgood, :vsn) |> to_string()
        })

      _ ->
        conn |> put_status(503) |> json(%{status: "unavailable"})
    end
  end
end
