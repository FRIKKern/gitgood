defmodule Gitgood.SSHKeysTest do
  use GitgoodWeb.ConnCase, async: false
  alias Gitgood.{Accounts, Credential, Repo, SSHKey, SSHKeys, SSHTransport}

  setup do
    {:ok, owner} = Accounts.create_user("ssh-owner", "synthetic-password")
    {:ok, other} = Accounts.create_user("ssh-other", "synthetic-password")
    {token, session} = Accounts.issue(owner, "session")

    public_key =
      "ssh-ed25519 " <>
        Base.encode64(<<11::32, "ssh-ed25519", 32::32, :crypto.strong_rand_bytes(32)::binary>>)

    %{owner: owner, other: other, token: token, session: session, public_key: public_key}
  end

  test "registration assigns identity, lost-reply retry is stable and changed bodies conflict",
       ctx do
    params = %{
      "public_key" => ctx.public_key <> " fixture",
      "label" => "Workstation",
      "user_id" => ctx.other.id
    }

    assert {:ok, key} = SSHKeys.register(ctx.owner, ctx.session, params, "ssh-registration")
    assert key.user_id == ctx.owner.id
    assert key.public_key == ctx.public_key
    assert {:ok, %{id: id}} = SSHKeys.register(ctx.owner, ctx.session, params, "ssh-registration")
    assert id == key.id
    assert Repo.aggregate(SSHKey, :count) == 1

    assert {:error, :idempotency_conflict} =
             SSHKeys.register(
               ctx.owner,
               ctx.session,
               %{params | "label" => "Different"},
               "ssh-registration"
             )

    assert {:ok, user, credential} = SSHKeys.authenticate(ctx.public_key, ctx.owner.username)
    assert user.id == ctx.owner.id
    assert credential.kind == "ssh"
    assert credential.repository_id == nil
    assert SSHKeys.authenticate(ctx.public_key, ctx.other.username) == {:error, :unauthorized}
    assert SSHKeys.current(ctx.other.id, credential.id) == {:error, :unauthorized}
    assert Accounts.resolve(Base.encode64(credential.digest), "git") == nil
  end

  test "duplicates cannot steal or reactivate identity; revocation and expiry take effect", ctx do
    params = %{"public_key" => ctx.public_key, "label" => "Workstation"}
    assert {:ok, key} = SSHKeys.register(ctx.owner, ctx.session, params, "ssh-registration")
    {_, other_session} = Accounts.issue(ctx.other, "session")

    assert {:error, :ssh_key_already_registered} =
             SSHKeys.register(ctx.other, other_session, params, "ssh-other-key")

    credential = Repo.get!(Credential, key.credential_id)
    assert {:ok, _} = Accounts.revoke(credential)
    assert SSHKeys.authenticate(ctx.public_key, ctx.owner.username) == {:error, :unauthorized}
    assert SSHKeys.current(ctx.owner.id, credential.id) == {:error, :unauthorized}

    assert {:error, :ssh_key_already_registered} =
             SSHKeys.register(ctx.owner, ctx.session, params, "ssh-readd-key")

    assert {:ok, %{id: id}} = SSHKeys.register(ctx.owner, ctx.session, params, "ssh-registration")
    assert id == key.id
    assert SSHKeys.public(key).revoked

    credential
    |> Ecto.Changeset.change(revoked_at: nil, expires_at: DateTime.add(Accounts.now(), -1))
    |> Repo.update!()

    assert SSHKeys.authenticate(ctx.public_key, ctx.owner.username) == {:error, :unauthorized}
  end

  test "registration rechecks session and malformed key is rejected without records", ctx do
    for key <- [
          "ssh-rsa AAAA",
          "ssh-ed25519 !!!!",
          ctx.public_key <> String.duplicate("x", 1024),
          "-----BEGIN OPENSSH PRIVATE KEY-----"
        ] do
      assert {:error, :supported_ed25519_public_key_required} =
               SSHKeys.register(
                 ctx.owner,
                 ctx.session,
                 %{"public_key" => key, "label" => "Fixture"},
                 "ssh-registration"
               )
    end

    {:ok, _} = Accounts.revoke(ctx.session)

    assert {:error, :authorization_changed} =
             SSHKeys.register(
               ctx.owner,
               ctx.session,
               %{"public_key" => ctx.public_key, "label" => "Fixture"},
               "ssh-registration"
             )

    assert Repo.aggregate(SSHKey, :count) == 0
  end

  test "HTTP registration needs CSRF and lists only the authenticated owner's keys", ctx do
    conn =
      build_conn()
      |> put_req_header("cookie", "gitgood_session=" <> ctx.token)
      |> post("/api/ssh-keys", %{public_key: ctx.public_key, label: "Fixture"})

    assert json_response(conn, 403)["error"] == "csrf_required"

    conn =
      build_conn()
      |> put_req_header("authorization", "Bearer " <> ctx.token)
      |> put_req_header("idempotency-key", "ssh-registration")
      |> post("/api/ssh-keys", %{public_key: ctx.public_key, label: "Fixture"})

    key = json_response(conn, 201)
    {other_token, _} = Accounts.issue(ctx.other, "session")

    conn =
      build_conn()
      |> put_req_header("authorization", "Bearer " <> other_token)
      |> get("/api/ssh-keys")

    assert json_response(conn, 200)["keys"] == []

    conn =
      build_conn()
      |> put_req_header("authorization", "Bearer " <> other_token)
      |> delete("/api/credentials/#{key["credential_id"]}")

    assert conn.status == 404
  end

  test "only exact native Git commands and canonical repo paths are accepted" do
    assert {:ok, "receive", "team", "project"} =
             SSHTransport.parse("git-receive-pack '/team/project.git'")

    assert {:ok, "upload", "team", "project"} =
             SSHTransport.parse(~c"git-upload-pack 'team/project.git'")

    for command <- [
          "sh",
          "git-upload-pack '/team/project.git'; id",
          "git-upload-pack '--help'",
          "git-receive-pack '/team/../project.git'",
          "git-upload-pack '/team/project.git' --strict",
          String.duplicate("x", 257)
        ] do
      assert SSHTransport.parse(command) == {:error, :command_denied}
    end
  end
end
