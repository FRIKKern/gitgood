defmodule GitgoodWeb.AccessBoundaryTest do
  use GitgoodWeb.ConnCase, async: false
  alias Gitgood.{Access, Accounts, Membership, Repo, Repository}
  alias GitgoodWeb.Auth

  setup do
    {:ok, actor} = Accounts.create_user("boundary-actor", "synthetic-password")
    {:ok, membership} = Accounts.add_member(actor, "boundary-team", "owner")
    {token, credential} = Accounts.issue(actor, "session")
    %{actor: actor, membership: membership, token: token, credential: credential}
  end

  defp authenticated(token),
    do: build_conn() |> put_req_header("authorization", "Bearer " <> token)

  test "session and private reads stamp current access; stale context rejects before disclosure",
       ctx do
    session = authenticated(ctx.token) |> get("/api/session")
    data = json_response(session, 200)
    assert [data["access_context"]] == get_resp_header(session, "x-gitgood-access-context")
    assert [%{"team" => "boundary-team", "role" => "owner"}] == data["teams"]
    old = data["access_context"]
    Repo.update!(Ecto.Changeset.change(ctx.membership, role: "reader"))

    stale =
      authenticated(ctx.token)
      |> put_req_header("x-gitgood-access-context", old)
      |> get("/api/repos")

    assert json_response(stale, 409) == %{"error" => "authorization_changed"}
    refute get_resp_header(stale, "x-gitgood-access-context") == [old]
    current = authenticated(ctx.token) |> get("/api/session") |> json_response(200)
    assert [%{"team" => "boundary-team", "role" => "reader"}] == current["teams"]

    assert authenticated(ctx.token)
           |> put_req_header("x-gitgood-access-context", current["access_context"])
           |> get("/api/repos")
           |> json_response(200) == %{"repositories" => []}

    signed_out =
      authenticated(ctx.token)
      |> put_req_header("x-gitgood-access-context", old)
      |> delete("/api/session")

    assert json_response(signed_out, 200) == %{"signed_out" => true}
    assert get_resp_header(signed_out, "x-gitgood-access-context") == ["anonymous"]

    assert authenticated(ctx.token) |> get("/api/activity") |> json_response(401) == %{
             "error" => "sign_in_required"
           }
  end

  test "revocation or role change before send redacts body and every private attachment header",
       ctx do
    {:ok, original} = Access.load(ctx.actor, ctx.credential)

    request = fn ->
      Plug.Test.conn("GET", "/api/repos/boundary-team/project/attachment")
      |> put_req_header("authorization", "Bearer " <> ctx.token)
      |> Auth.call([])
      |> put_resp_header("content-disposition", "attachment; filename=private-secret.zip")
      |> put_resp_header("x-gitgood-sha256", "secret-digest")
      |> put_resp_header("content-length", "12345")
      |> put_resp_header("x-private-fixture", "private title")
    end

    response = request.()
    Repo.update!(Ecto.Changeset.change(ctx.membership, role: "reader"))
    changed = send_resp(response, 200, "private bytes")
    assert changed.status == 409
    assert Jason.decode!(changed.resp_body) == %{"error" => "authorization_changed"}
    refute get_resp_header(changed, "x-gitgood-access-context") == [original.context]

    for header <- [
          "content-disposition",
          "x-gitgood-sha256",
          "content-length",
          "x-private-fixture"
        ] do
      assert get_resp_header(changed, header) == []
    end

    response = request.()
    Accounts.revoke(ctx.credential)
    revoked = send_resp(response, 200, "private bytes")
    assert revoked.status == 401
    assert Jason.decode!(revoked.resp_body) == %{"error" => "sign_in_required"}
    assert get_resp_header(revoked, "cache-control") == ["no-store"]
  end

  test "repository scoped session cannot browse another repository or revoke its credentials",
       ctx do
    other_membership = Accounts.add_member(ctx.actor, "other-team", "owner")
    assert {:ok, %Membership{}} = other_membership

    create = fn team, name ->
      Repo.insert!(%Repository{
        team: team,
        name: name,
        owner_id: ctx.actor.id,
        storage_key: Ecto.UUID.generate(),
        creation_key: Ecto.UUID.generate()
      })
    end

    own = create.("boundary-team", "allowed")
    foreign = create.("other-team", "forbidden")
    Repo.update!(Ecto.Changeset.change(ctx.credential, repository_id: own.id))
    {_, own_git} = Accounts.issue(ctx.actor, "git", own.id)
    {_, foreign_git} = Accounts.issue(ctx.actor, "git", foreign.id)

    assert %{"repositories" => [%{"name" => "allowed"}]} =
             authenticated(ctx.token) |> get("/api/repos") |> json_response(200)

    assert authenticated(ctx.token)
           |> get("/api/repos/other-team/forbidden")
           |> json_response(403) == %{"error" => "credential_scope_denied"}

    assert authenticated(ctx.token)
           |> delete("/api/credentials/" <> to_string(foreign_git.id))
           |> json_response(403) == %{"error" => "credential_scope_denied"}

    assert authenticated(ctx.token)
           |> delete("/api/credentials/" <> to_string(own_git.id))
           |> json_response(200) == %{"revoked" => true}

    refute Repo.get!(Gitgood.Credential, foreign_git.id).revoked_at
  end
end
