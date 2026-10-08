defmodule GitgoodWeb.HealthController do
  use GitgoodWeb, :controller
  def live(conn, _), do: json(conn, identity())

  def show(conn, _) do
    result = Gitgood.Readiness.check()

    conn
    |> put_status(if(result.ready, do: 200, else: 503))
    |> json(
      Map.merge(identity(), %{
        status: if(result.ready, do: "ready", else: "unavailable"),
        checks: result.checks
      })
    )
  end

  defp identity,
    do:
      Map.merge(Gitgood.Build.public(), %{
        service: "gitgood",
        version: Application.spec(:gitgood, :vsn) |> to_string(),
        runtime: %{
          elixir: System.version(),
          otp: :erlang.system_info(:otp_release) |> to_string()
        }
      })
end
