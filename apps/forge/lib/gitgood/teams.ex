defmodule Gitgood.Teams do
  @moduledoc "Owner-controlled membership with serialized last-owner protection and durable retries."
  import Ecto.Query
  alias Gitgood.{Accounts, Credential, Lease, Membership, MembershipEvent, Repo, User}

  def members(user, credential, team) do
    owner(user, credential, team, fn memberships ->
      %{
        members:
          Enum.map(memberships, fn member ->
            %{username: Repo.get!(User, member.user_id).username, role: member.role}
          end),
        events:
          Repo.all(
            from e in MembershipEvent,
              where: e.team == ^team,
              order_by: [desc: e.inserted_at, desc: e.id],
              limit: 100
          )
          |> Enum.map(&public/1)
      }
    end)
  end

  def change(user, credential, team, params, key) do
    owner(user, credential, team, fn memberships ->
      key = Lease.key!(key)

      unless is_map(params) and
               Enum.sort(Map.keys(params)) == ["expected_role", "role", "username"] and
               is_binary(params["username"]) and byte_size(params["username"]) in 1..64 and
               params["role"] in ["owner", "writer", "reader", "absent"] and
               params["expected_role"] in ["owner", "writer", "reader", "absent"],
             do: Repo.rollback(:invalid_membership_change)

      digest = Lease.digest(params)

      case Repo.get_by(MembershipEvent, team: team, actor_id: user.id, request_key: key) do
        %MembershipEvent{} = event ->
          if event.request_digest == digest,
            do: public(event),
            else: Repo.rollback(:idempotency_conflict)

        nil ->
          target =
            Repo.get_by(User, username: params["username"]) || Repo.rollback(:member_not_found)

          current = Enum.find(memberships, &(&1.user_id == target.id))
          previous = if current, do: current.role, else: "absent"
          unless previous == params["expected_role"], do: Repo.rollback(:membership_changed)
          role = params["role"]
          unless role != previous, do: Repo.rollback(:membership_unchanged)

          if previous == "owner" and role != "owner" and
               Enum.count(memberships, &(&1.role == "owner")) == 1,
             do: Repo.rollback(:last_owner_required)

          cond do
            role == "absent" -> Repo.delete!(current)
            current -> Repo.update!(Ecto.Changeset.change(current, role: role))
            true -> Repo.insert!(%Membership{user_id: target.id, team: team, role: role})
          end

          Repo.insert!(%MembershipEvent{
            team: team,
            actor_id: user.id,
            target_id: target.id,
            previous_role: if(previous == "absent", do: nil, else: previous),
            role: if(role == "absent", do: nil, else: role),
            request_key: key,
            request_digest: digest
          })
          |> public()
      end
    end)
  end

  defp owner(user, credential, team, action) do
    Repo.transaction(fn ->
      unless is_binary(team) and Regex.match?(~r/\A[a-z][a-z0-9-]{1,39}\z/, team),
        do: Repo.rollback(:team_not_found)

      # Shared by all team changes, including additions where there is no row to lock.
      Repo.query!("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", [
        "gitgood-team:" <> team
      ])

      current = Repo.one(from c in Credential, where: c.id == ^credential.id, lock: "FOR SHARE")

      unless current && current.user_id == user.id && current.kind == "session" &&
               is_nil(current.repository_id) && is_nil(current.revoked_at) &&
               DateTime.compare(current.expires_at, Accounts.now()) == :gt,
             do: Repo.rollback(:authorization_changed)

      memberships =
        Repo.all(
          from m in Membership, where: m.team == ^team, order_by: [asc: m.id], lock: "FOR UPDATE"
        )

      unless Enum.any?(memberships, &(&1.user_id == user.id && &1.role == "owner")),
        do: Repo.rollback(:team_not_found)

      action.(memberships)
    end)
  rescue
    _ in [DBConnection.ConnectionError, Postgrex.Error] -> {:error, :members_unavailable}
  end

  defp public(event) do
    %{
      id: event.id,
      team: event.team,
      actor: Repo.get!(User, event.actor_id).username,
      username: Repo.get!(User, event.target_id).username,
      previous_role: event.previous_role || "absent",
      role: event.role || "absent",
      inserted_at: event.inserted_at
    }
  end
end
