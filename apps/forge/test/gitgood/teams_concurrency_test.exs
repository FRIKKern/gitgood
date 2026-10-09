defmodule Gitgood.TeamsConcurrencyTest do
  use GitgoodWeb.RealConnCase, async: false
  import Ecto.Query
  alias Gitgood.{Accounts, Credential, Membership, MembershipEvent, Repo, Teams, User}

  test "two independent owner removals cannot leave a team without an owner" do
    team = "owners-" <> Base.encode16(:crypto.strong_rand_bytes(5), case: :lower)

    users =
      for suffix <- ["a", "b"] do
        {:ok, user} = Accounts.create_user(team <> "-" <> suffix, "synthetic-password")
        {:ok, _} = Accounts.add_member(user, team, "owner")
        {_, credential} = Accounts.issue(user, "session")
        {user, credential}
      end

    ids = Enum.map(users, fn {user, _} -> user.id end)

    on_exit(fn ->
      Repo.delete_all(from e in MembershipEvent, where: e.team == ^team)
      Repo.delete_all(from c in Credential, where: c.user_id in ^ids)
      Repo.delete_all(from m in Membership, where: m.team == ^team)
      Repo.delete_all(from u in User, where: u.id in ^ids)
    end)

    supervisor = start_supervised!({Task.Supervisor, []})
    parent = self()

    tasks =
      for {user, credential} <- users do
        Task.Supervisor.async_nolink(supervisor, fn ->
          send(parent, {:ready, self()})

          receive do
            :go ->
              Teams.change(
                user,
                credential,
                team,
                %{"username" => user.username, "expected_role" => "owner", "role" => "absent"},
                "concurrent-remove"
              )
          after
            10_000 -> raise "Owner change barrier missing"
          end
        end)
      end

    for _ <- tasks do
      assert_receive {:ready, pid}, 10_000
      send(pid, :go)
    end

    outcomes = Enum.map(tasks, &Task.await(&1, 10_000))
    assert Enum.count(outcomes, &match?({:ok, _}, &1)) == 1
    assert Enum.count(outcomes, &(&1 == {:error, :last_owner_required})) == 1

    assert Repo.aggregate(
             from(m in Membership, where: m.team == ^team and m.role == "owner"),
             :count
           ) == 1

    assert Repo.aggregate(from(e in MembershipEvent, where: e.team == ^team), :count) == 1
  end
end
