defmodule Gitgood.NativeChangesTest do
  use GitgoodWeb.ConnCase, async: false
  alias Gitgood.{Accounts, Membership, NativeChanges, PullRequest, Repo, Repository}

  setup do
    {:ok, reader} = Accounts.create_user("change-reader", "synthetic-password")
    {:ok, foreign} = Accounts.create_user("change-foreign", "synthetic-password")
    Accounts.add_member(reader, "visible", "reader")
    Accounts.add_member(foreign, "hidden", "owner")
    {token, credential} = Accounts.issue(reader, "session")
    {foreign_token, foreign_credential} = Accounts.issue(foreign, "session")

    make = fn user, team, name ->
      %Repository{
        owner_id: user.id,
        team: team,
        storage_key: Ecto.UUID.generate(),
        creation_key: name
      }
      |> Repository.changeset(%{name: name})
      |> Repo.insert!()
    end

    first = make.(reader, "visible", "project-one")
    second = make.(reader, "visible", "project-two")
    hidden = make.(foreign, "hidden", "private-project")

    add = fn repository, user ->
      # Read-only identity fixtures; actual Git and browser navigation are separate proof.
      Repo.insert!(%PullRequest{
        repository_id: repository.id,
        author_id: user.id,
        title: "Private change in " <> repository.name,
        source_ref: "refs/heads/feature",
        target_ref: "refs/heads/main",
        creation_key: repository.name,
        request_digest: Accounts.digest(repository.name)
      })
    end

    %{
      reader: reader,
      credential: credential,
      token: token,
      foreign: foreign,
      foreign_credential: foreign_credential,
      foreign_token: foreign_token,
      first: first,
      second: second,
      allowed: add.(first, reader),
      other: add.(second, reader),
      hidden: add.(hidden, foreign)
    }
  end

  test "opaque native address returns context only for current permitted reader", c do
    assert {:ok, change} = NativeChanges.locate(c.reader, c.credential, c.allowed.public_id)
    assert change.id == c.allowed.public_id
    assert change.url == "/repos/visible/project-one/pulls/" <> c.allowed.public_id
    assert change.title == c.allowed.title
    conn = build_conn() |> put_req_header("authorization", "Bearer " <> c.token)
    response = get(conn, "/api/changes/" <> c.allowed.public_id)
    assert json_response(response, 200)["url"] == change.url
    assert get_resp_header(response, "cache-control") == ["no-store"]
    assert [context] = get_resp_header(response, "x-gitgood-access-context")
    assert byte_size(context) == 43
  end

  test "unknown, malformed and foreign identities reveal the same native absence", c do
    for id <- [
          Ecto.UUID.generate(),
          c.hidden.public_id,
          "not-a-uuid",
          Integer.to_string(c.allowed.id)
        ] do
      assert {:error, :change_not_found} = NativeChanges.locate(c.reader, c.credential, id)
      conn = build_conn() |> put_req_header("authorization", "Bearer " <> c.token)

      assert json_response(get(conn, "/api/changes/" <> id), 404) == %{
               "error" => "change_not_found"
             }
    end

    conn = build_conn() |> put_req_header("authorization", "Bearer " <> c.foreign_token)

    assert json_response(get(conn, "/api/changes/" <> c.allowed.public_id), 404) == %{
             "error" => "change_not_found"
           }

    assert json_response(get(build_conn(), "/api/changes/" <> c.allowed.public_id), 401) == %{
             "error" => "sign_in_required"
           }
  end

  test "repository-scoped native session resolves only its own change", c do
    {token, scoped} = Accounts.issue(c.reader, "session", c.first.id)
    assert {:ok, _} = NativeChanges.locate(c.reader, scoped, c.allowed.public_id)
    assert {:error, :change_not_found} = NativeChanges.locate(c.reader, scoped, c.other.public_id)

    for {id, status} <- [
          {c.allowed.public_id, 200},
          {c.other.public_id, 404},
          {c.hidden.public_id, 404}
        ] do
      conn = build_conn() |> put_req_header("authorization", "Bearer " <> token)
      assert get(conn, "/api/changes/" <> id).status == status
    end
  end

  test "revoked sessions and removed memberships cannot resolve previously visible changes", c do
    assert {:error, :authorization_changed} =
             NativeChanges.locate(c.reader, c.foreign_credential, c.allowed.public_id)

    {:ok, _} = Accounts.revoke(c.credential)

    assert {:error, :authorization_changed} =
             NativeChanges.locate(c.reader, c.credential, c.allowed.public_id)

    {replacement, _} = Accounts.issue(c.reader, "session")
    Repo.get_by!(Membership, user_id: c.reader.id, team: "visible") |> Repo.delete!()
    conn = build_conn() |> put_req_header("authorization", "Bearer " <> replacement)

    assert json_response(get(conn, "/api/changes/" <> c.allowed.public_id), 404) == %{
             "error" => "change_not_found"
           }
  end
end
