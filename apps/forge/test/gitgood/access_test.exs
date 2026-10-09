defmodule Gitgood.AccessTest do
  use GitgoodWeb.ConnCase, async: false
  import Ecto.Query
  alias Gitgood.{Access, Accounts, Membership, Repo, Repository}

  test "opaque context follows the actual credential and current membership without exposing counts" do
    {:ok, actor} = Accounts.create_user("access-actor", "synthetic-password")
    {:ok, outsider} = Accounts.create_user("access-outside", "synthetic-password")
    {:ok, membership} = Accounts.add_member(actor, "access-team", "writer")
    {_, credential} = Accounts.issue(actor, "session")
    {_, other} = Accounts.issue(outsider, "session")
    assert {:ok, snapshot} = Access.load(actor, credential)
    assert byte_size(snapshot.context) == 43
    assert snapshot.teams == [%{team: "access-team", role: "writer"}]
    assert {:ok, ^snapshot} = Access.load(actor, credential)

    repository =
      Repo.insert!(%Repository{
        owner_id: actor.id,
        team: "access-team",
        name: "scoped",
        storage_key: Ecto.UUID.generate(),
        creation_key: "access-scope"
      })

    scoped = Repo.update!(Ecto.Changeset.change(credential, repository_id: repository.id))
    assert {:ok, restricted} = Access.load(actor, scoped)
    assert restricted.repository_scope == repository.id
    refute restricted.context == snapshot.context
    Repo.update!(Ecto.Changeset.change(scoped, repository_id: nil))
    assert {:error, :authorization_changed} = Access.load(actor, other)
    Repo.update!(Ecto.Changeset.change(membership, role: "reader"))
    assert {:ok, downgraded} = Access.load(actor, credential)
    refute snapshot.context == downgraded.context
    assert downgraded.teams == [%{team: "access-team", role: "reader"}]
    Repo.delete_all(from m in Membership, where: m.user_id == ^actor.id)
    assert {:ok, revoked} = Access.load(actor, credential)
    assert revoked.teams == []
    refute revoked.context == downgraded.context
    {_, replacement} = Accounts.issue(actor, "session")
    assert {:ok, new_session} = Access.load(actor, replacement)
    refute new_session.context == revoked.context
    Accounts.revoke(credential)
    assert {:error, :authorization_changed} = Access.load(actor, credential)
  end
end
