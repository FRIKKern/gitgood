defmodule Gitgood.DiscoverySourceTest do
  use GitgoodWeb.RealConnCase, async: false
  import Ecto.Query
  alias Gitgood.{Accounts, Credential, Membership, Repo, User}

  test "an actual blocked source returns unavailable rather than an empty successful snapshot" do
    name = "source-" <> Base.encode16(:crypto.strong_rand_bytes(5), case: :lower)
    {:ok, user} = Accounts.create_user(name, "synthetic-password")
    {:ok, _} = Accounts.add_member(user, name, "owner")
    {token, _} = Accounts.issue(user, "session")

    on_exit(fn ->
      Repo.delete_all(from c in Credential, where: c.user_id == ^user.id)
      Repo.delete_all(from m in Membership, where: m.user_id == ^user.id)
      Repo.delete_all(from u in User, where: u.id == ^user.id)
    end)

    parent = self()
    supervisor = start_supervised!({Task.Supervisor, []})

    blocked =
      Task.Supervisor.async_nolink(supervisor, fn ->
        Repo.transaction(fn ->
          Repo.query!("LOCK TABLE repositories IN ACCESS EXCLUSIVE MODE")
          send(parent, {:source_locked, self()})

          receive do
            :release -> :released
          after
            10_000 -> raise "Source lock not released"
          end
        end)
      end)

    assert_receive {:source_locked, blocker}, 10_000

    try do
      conn =
        build_conn()
        |> put_req_header("authorization", "Bearer " <> token)
        |> get("/api/activity")

      assert conn.status == 503
      assert %{"error" => _} = json_response(conn, 503)
      refute String.contains?(conn.resp_body, "records")
      assert get_resp_header(conn, "cache-control") == ["no-store"]
    after
      send(blocker, :release)
      assert Task.await(blocked, 10_000) == {:ok, :released}
    end

    conn =
      build_conn() |> put_req_header("authorization", "Bearer " <> token) |> get("/api/activity")

    assert %{"records" => [], "source" => "native"} = json_response(conn, 200)
  end
end
