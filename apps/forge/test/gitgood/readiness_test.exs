defmodule Gitgood.ReadinessTest do
  use GitgoodWeb.ConnCase, async: false

  test "verification runtime identity is distinct from ordinary activation evidence" do
    previous = Application.get_env(:gitgood, :recovery_verification)

    on_exit(fn ->
      if previous == nil,
        do: Application.delete_env(:gitgood, :recovery_verification),
        else: Application.put_env(:gitgood, :recovery_verification, previous)
    end)

    Application.put_env(:gitgood, :recovery_verification, true)

    assert build_conn()
           |> get("/health/live")
           |> json_response(200)
           |> Map.get("operational_mode") == "recovery_verification"

    Application.put_env(:gitgood, :recovery_verification, false)

    assert build_conn()
           |> get("/health/live")
           |> json_response(200)
           |> Map.get("operational_mode") == "active"
  end

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

  test "configured SSH without its supervised daemon rejects readiness" do
    previous = Application.get_env(:gitgood, :ssh_port)
    Application.put_env(:gitgood, :ssh_port, 2222)

    on_exit(fn ->
      if previous,
        do: Application.put_env(:gitgood, :ssh_port, previous),
        else: Application.delete_env(:gitgood, :ssh_port)
    end)

    response = build_conn() |> get("/health/ready") |> json_response(503)
    assert response["checks"]["ssh"] == false
  end
end
