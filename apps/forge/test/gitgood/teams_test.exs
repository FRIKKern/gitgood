defmodule Gitgood.TeamsTest do
  use GitgoodWeb.ConnCase, async: false
  alias Gitgood.{Access, Accounts, MembershipEvent, Repo, Teams}

  setup do
    {:ok, owner} = Accounts.create_user("team-owner", "synthetic-password")
    {:ok, other} = Accounts.create_user("team-other", "synthetic-password")
    {:ok, writer} = Accounts.create_user("team-writer", "synthetic-password")
    {:ok, outsider} = Accounts.create_user("team-outsider", "synthetic-password")

    for {user, role} <- [{owner, "owner"}, {writer, "writer"}],
        do: Accounts.add_member(user, "managed-team", role)

    {token, credential} = Accounts.issue(owner, "session")
    {_, writer_credential} = Accounts.issue(writer, "session")

    %{
      owner: owner,
      other: other,
      writer: writer,
      outsider: outsider,
      token: token,
      credential: credential,
      writer_credential: writer_credential
    }
  end

  test "owner changes are durable, retries retain one audit record, access fingerprints change",
       ctx do
    {_, other_credential} = Accounts.issue(ctx.other, "session")
    {:ok, before} = Access.load(ctx.other, other_credential)
    params = %{"username" => ctx.other.username, "role" => "reader", "expected_role" => "absent"}

    assert {:ok, first} =
             Teams.change(ctx.owner, ctx.credential, "managed-team", params, "membership-add")

    assert {:ok, ^first} =
             Teams.change(ctx.owner, ctx.credential, "managed-team", params, "membership-add")

    assert Repo.aggregate(MembershipEvent, :count) == 1
    assert {:ok, after_add} = Access.load(ctx.other, other_credential)
    refute before.context == after_add.context
    assert after_add.teams == [%{team: "managed-team", role: "reader"}]

    assert {:error, :idempotency_conflict} =
             Teams.change(
               ctx.owner,
               ctx.credential,
               "managed-team",
               %{params | "role" => "writer"},
               "membership-add"
             )

    assert {:error, :membership_changed} =
             Teams.change(
               ctx.owner,
               ctx.credential,
               "managed-team",
               %{params | "role" => "writer"},
               "membership-stale"
             )

    assert {:ok, removed} =
             Teams.change(
               ctx.owner,
               ctx.credential,
               "managed-team",
               %{params | "role" => "absent", "expected_role" => "reader"},
               "membership-remove"
             )

    assert removed.previous_role == "reader" && removed.role == "absent"
    assert {:ok, after_remove} = Access.load(ctx.other, other_credential)
    assert after_remove.teams == []
    refute after_remove.context == after_add.context
    assert {:ok, %{events: events}} = Teams.members(ctx.owner, ctx.credential, "managed-team")
    assert length(events) == 2
    assert Enum.all?(events, &match?({:ok, _}, Ecto.UUID.cast(&1.id)))
  end

  test "writer, foreign user, revoked or scoped credentials cannot manage membership; last owner survives",
       ctx do
    params = %{"username" => ctx.owner.username, "role" => "absent", "expected_role" => "owner"}

    assert {:error, :last_owner_required} =
             Teams.change(ctx.owner, ctx.credential, "managed-team", params, "owner-remove")

    assert Accounts.role(ctx.owner.id, "managed-team") == "owner"

    assert {:error, :team_not_found} =
             Teams.change(
               ctx.writer,
               ctx.writer_credential,
               "managed-team",
               params,
               "writer-remove"
             )

    assert {:error, :authorization_changed} =
             Teams.change(ctx.outsider, ctx.credential, "managed-team", params, "foreign-remove")

    assert Repo.aggregate(MembershipEvent, :count) == 0
    Accounts.revoke(ctx.credential)

    assert {:error, :authorization_changed} =
             Teams.members(ctx.owner, ctx.credential, "managed-team")
  end

  test "HTTP uses actual owner, strict body, CSRF and current expected role", ctx do
    conn = fn ->
      build_conn()
      |> put_req_header("authorization", "Bearer " <> ctx.token)
      |> put_req_header("idempotency-key", "http-member-add")
    end

    params = %{username: ctx.other.username, role: "writer", expected_role: "absent"}
    first = conn.() |> post("/api/teams/managed-team/members", params) |> json_response(200)
    assert first["actor"] == ctx.owner.username
    assert first["username"] == ctx.other.username

    assert conn.() |> post("/api/teams/managed-team/members", params) |> json_response(200) ==
             first

    assert build_conn() |> post("/api/teams/managed-team/members", params) |> json_response(401) ==
             %{"error" => "sign_in_required"}

    assert conn.()
           |> put_req_header("idempotency-key", "bad-body-member")
           |> post("/api/teams/managed-team/members", Map.put(params, :actor, "spoof"))
           |> json_response(422) == %{"error" => "invalid_membership_change"}
  end
end
