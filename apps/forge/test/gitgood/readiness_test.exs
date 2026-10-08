defmodule Gitgood.ReadinessTest do
  use GitgoodWeb.ConnCase, async: false

  test "readiness refuses an unavailable store while liveness remains a separate fact" do
    original = Application.fetch_env!(:gitgood, :storage_root)

    Application.put_env(
      :gitgood,
      :storage_root,
      Path.join(original, "absent-" <> Ecto.UUID.generate())
    )

    on_exit(fn -> Application.put_env(:gitgood, :storage_root, original) end)
    response = build_conn() |> get("/health/ready") |> json_response(503)
    assert response["checks"]["storage"] == false

    assert build_conn() |> get("/health/live") |> json_response(200) |> Map.get("service") ==
             "gitgood"
  end

  test "readiness refuses missing native executables" do
    original = Application.fetch_env!(:gitgood, :git_executable)
    Application.put_env(:gitgood, :git_executable, "missing-gitgood-executable")
    on_exit(fn -> Application.put_env(:gitgood, :git_executable, original) end)
    response = build_conn() |> get("/health/ready") |> json_response(503)
    assert response["checks"]["executables"] == false
  end
end
