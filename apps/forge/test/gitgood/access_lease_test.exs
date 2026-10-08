defmodule Gitgood.AccessLeaseTest do
  use GitgoodWeb.RealConnCase, async: false
  import Ecto.Query
  alias Gitgood.{Access, Accounts, Credential, Membership, Repo, User}

  test "current read lease serializes with credential revocation and membership downgrade" do
    name = "read-lease-" <> Base.encode16(:crypto.strong_rand_bytes(5), case: :lower)
    {:ok, actor} = Accounts.create_user(name, "synthetic-password")
    {:ok, member} = Accounts.add_member(actor, name, "writer")
    {_, credential} = Accounts.issue(actor, "session")

    on_exit(fn ->
      Repo.delete_all(from c in Credential, where: c.user_id == ^actor.id)
      Repo.delete_all(from m in Membership, where: m.user_id == ^actor.id)
      Repo.delete_all(from u in User, where: u.id == ^actor.id)
    end)

    supervisor = start_supervised!({Task.Supervisor, []})
    parent = self()

    read =
      Task.Supervisor.async_nolink(supervisor, fn ->
        Access.with_session(actor, credential, fn context ->
          send(parent, {:read_locked, self(), context})

          receive do
            :release -> context
          after
            10_000 -> raise "Read lease barrier was not released"
          end
        end)
      end)

    assert_receive {:read_locked, reader, snapshot}, 10_000
    assert snapshot.teams == [%{team: name, role: "writer"}]

    for mutation <- [
          fn -> Accounts.revoke(credential) end,
          fn -> Repo.update!(Ecto.Changeset.change(member, role: "reader")) end
        ] do
      blocked =
        Task.Supervisor.async_nolink(supervisor, fn ->
          try do
            Repo.transaction(fn ->
              # Database-observed lock refusal, rather than a timing sleep.
              Repo.query!("SET LOCAL lock_timeout = '100ms'")
              mutation.()
            end)
          rescue
            error in Postgrex.Error -> {:blocked, error.postgres.code}
          end
        end)

      assert Task.await(blocked, 10_000) == {:blocked, :lock_not_available}
    end

    send(reader, :release)
    assert Task.await(read, 10_000) == {:ok, snapshot}
    Repo.update!(Ecto.Changeset.change(member, role: "reader"))
    assert {:ok, changed} = Access.load(actor, credential)
    refute changed.context == snapshot.context
    assert {:ok, _} = Accounts.revoke(credential)
    assert {:error, :authorization_changed} = Access.load(actor, credential)
  end
end
