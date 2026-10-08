defmodule Gitgood.FoundationTest do
  use GitgoodWeb.ConnCase, async: false
  alias Gitgood.{Accounts, Git, Membership, Repo, Repositories, Repository}
  import Ecto.Query

  setup do
    {:ok, owner} = Accounts.create_user("owner", "synthetic-password")
    {:ok, reader} = Accounts.create_user("reader", "synthetic-password")
    {:ok, outsider} = Accounts.create_user("outsider", "synthetic-password")
    {:ok, _} = Accounts.add_member(owner, "team", "owner")
    {:ok, _} = Accounts.add_member(reader, "team", "reader")
    {token, credential} = Accounts.issue(owner, "session")

    on_exit(fn ->
      root = Application.fetch_env!(:gitgood, :storage_root) |> Path.expand()
      # Every directory here is a test-generated UUID; never touch application storage.
      for p <- Path.wildcard(Path.join(root, "*.git")) do
        if String.starts_with?(Path.expand(p), root <> "/"), do: File.rm_rf!(p)
      end
    end)

    %{owner: owner, reader: reader, outsider: outsider, token: token, credential: credential}
  end

  defp authenticated(token),
    do: build_conn() |> put_req_header("authorization", "Bearer " <> token)

  test "create persists ownership, a real bare store and canonical URL; lost response retry is stable",
       ctx do
    request = fn ->
      authenticated(ctx.token)
      |> put_req_header("idempotency-key", "creation-one")
      |> post("/api/repos", %{team: "team", name: "project"})
    end

    first = request.() |> json_response(201)
    second = request.() |> json_response(201)
    assert first["id"] == second["id"]
    assert first["owner_id"] == ctx.owner.id
    assert first["url"] == "/repos/team/project"
    assert Repo.aggregate(Repository, :count) == 1
    repository = Repo.get!(Repository, first["id"])

    assert {output, 0} =
             Git.run(["--git-dir", Git.path(repository), "rev-parse", "--is-bare-repository"])

    assert String.trim(output) == "true"

    assert authenticated(ctx.token) |> get("/api/repos/team/project") |> json_response(200) ==
             first
  end

  test "outsider lists and direct lookup disclose no private repository", ctx do
    {:ok, _} = Repositories.create(ctx.owner, "team", "project", "creation-one")
    {token, _} = Accounts.issue(ctx.outsider, "session")

    assert authenticated(token) |> get("/api/repos") |> json_response(200) == %{
             "repositories" => []
           }

    assert authenticated(token) |> get("/api/repos/team/project") |> json_response(404) == %{
             "error" => "repository_not_found"
           }

    assert {:error, :forbidden} =
             Repositories.create(ctx.reader, "team", "project-two", "creation-two")
  end

  test "duplicate name, invalid name and reused key cannot create duplicates", ctx do
    {:ok, original} = Repositories.create(ctx.owner, "team", "project", "creation-one")

    assert {:error, %Ecto.Changeset{}} =
             Repositories.create(ctx.owner, "team", "project", "creation-two")

    assert {:error, :idempotency_conflict} =
             Repositories.create(ctx.owner, "team", "other", "creation-one")

    assert {:error, %Ecto.Changeset{}} =
             Repositories.create(ctx.owner, "team", "../escape", "creation-bad")

    assert Repo.aggregate(Repository, :count) == 1
    assert {:ok, %{id: id}} = Repositories.create(ctx.owner, "team", "project", "creation-one")
    assert id == original.id
  end

  test "credential expiry, revocation and membership removal take effect on next request", ctx do
    {:ok, _} = Repositories.create(ctx.owner, "team", "project", "creation-one")
    Repo.delete_all(from m in Membership, where: m.user_id == ^ctx.owner.id)
    assert authenticated(ctx.token) |> get("/api/repos/team/project") |> json_response(404)
    {:ok, _} = Accounts.revoke(ctx.credential)
    assert authenticated(ctx.token) |> get("/api/repos") |> json_response(401)
    {token, credential} = Accounts.issue(ctx.owner, "session")

    credential
    |> Ecto.Changeset.change(expires_at: DateTime.add(Accounts.now(), -1))
    |> Repo.update!()

    assert authenticated(token) |> get("/api/repos") |> json_response(401)
  end

  test "cookie writes require csrf and same origin, logout revokes server-side credential", ctx do
    cookie = "gitgood_session=" <> ctx.token

    conn =
      build_conn()
      |> put_req_header("cookie", cookie)
      |> post("/api/repos", %{team: "team", name: "project"})

    assert json_response(conn, 403)["error"] == "csrf_required"

    conn =
      build_conn()
      |> put_req_header("cookie", cookie)
      |> put_req_header("x-gitgood-csrf", GitgoodWeb.Auth.csrf(ctx.token))
      |> put_req_header("origin", "https://attacker.invalid")
      |> delete("/api/session")

    assert json_response(conn, 403)["error"] == "csrf_required"

    conn =
      build_conn()
      |> put_req_header("cookie", cookie)
      |> put_req_header("x-gitgood-csrf", GitgoodWeb.Auth.csrf(ctx.token))
      |> delete("/api/session")

    assert json_response(conn, 200)["signed_out"]
    assert Accounts.resolve(ctx.token, "session") == nil
  end

  test "storage failure leaves visible durable responsibility and reconciles with same key",
       ctx do
    root = Application.fetch_env!(:gitgood, :storage_root)
    blocked = Path.join(root, "blocked")
    File.mkdir_p!(root)
    File.write!(blocked, "not a directory")
    Application.put_env(:gitgood, :storage_root, blocked)

    on_exit(fn ->
      Application.put_env(:gitgood, :storage_root, root)
      File.rm(blocked)
    end)

    assert {:error, :storage_failed} =
             Repositories.create(ctx.owner, "team", "project", "creation-one")

    repository = Repo.one!(Repository)
    assert repository.status == "creating"
    Application.put_env(:gitgood, :storage_root, root)
    assert [{:ok, %{id: id, status: "ready"}}] = Repositories.reconcile()
    assert id == repository.id
    assert {:ok, %{id: ^id}} = Repositories.create(ctx.owner, "team", "project", "creation-one")
  end

  test "wrong credentials are generic; stored credential has only digest", ctx do
    assert {:error, :unauthorized} = Accounts.authenticate("owner", "wrong-password")
    assert {:error, :unauthorized} = Accounts.authenticate("missing", "wrong-password")
    assert {:ok, %{id: id}} = Accounts.authenticate("owner", "synthetic-password")
    assert id == ctx.owner.id
    assert ctx.credential.digest != ctx.token
    assert byte_size(ctx.credential.digest) == 32
    assert Accounts.resolve(ctx.token, "git") == nil
  end
end
