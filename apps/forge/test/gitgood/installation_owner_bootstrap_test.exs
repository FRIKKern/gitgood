defmodule Gitgood.InstallationOwnerBootstrapTest do
  use GitgoodWeb.RealConnCase, async: false
  import Ecto.Query

  alias Gitgood.{
    Accounts,
    InstallationOwnerBootstrap,
    InstallationOwnerReceipt,
    Membership,
    Repo,
    User
  }

  setup do
    assert Repo.aggregate(InstallationOwnerReceipt, :count) == 0
    assert Repo.aggregate(User, :count) == 0
    assert Repo.aggregate(Membership, :count) == 0

    params = %{
      "installation" => Ecto.UUID.generate(),
      "request" => Ecto.UUID.generate(),
      "username" => "initial-owner",
      "team" => "initial-team",
      "password" => "private-bootstrap-password"
    }

    on_exit(fn ->
      receipts = Repo.all(InstallationOwnerReceipt)
      ids = Enum.map(receipts, & &1.user_id)
      Repo.delete_all(InstallationOwnerReceipt)
      Repo.delete_all(from m in Membership, where: m.user_id in ^ids)
      Repo.delete_all(from u in User, where: u.id in ^ids)
    end)

    %{params: params}
  end

  defp expected(params) do
    Jason.encode!([
      "gitgood-installation-owner-v1",
      params["installation"],
      params["request"],
      params["username"],
      params["team"],
      params["password"]
    ])
    |> then(&:crypto.hash(:sha256, &1))
    |> Base.encode16(case: :lower)
  end

  test "first owner, membership and private commitment commit together", %{params: params} do
    assert {:ok, result} = InstallationOwnerBootstrap.create(params, expected(params))
    assert result.outcome == "created" and result.role_at_creation == "owner"
    assert {:ok, user} = Accounts.authenticate(params["username"], params["password"])
    assert user.id == result.user_id and Accounts.role(user.id, params["team"]) == "owner"
    receipt = Repo.get!(InstallationOwnerReceipt, 1)
    assert byte_size(receipt.input_commitment) == 32
    refute receipt.input_commitment == :crypto.hash(:sha256, params["password"])
    refute Jason.encode!(result) =~ params["password"]
    refute Map.has_key?(result, :input_commitment)
    assert Repo.aggregate(User, :count) == 1 and Repo.aggregate(Membership, :count) == 1
  end

  test "lost response repeats exact receipt without changing credentials or ownership", %{
    params: params
  } do
    assert {:ok, initial} = InstallationOwnerBootstrap.create(params, expected(params))
    before = {Repo.all(InstallationOwnerReceipt), Repo.all(User), Repo.all(Membership)}

    for _ <- 1..3 do
      assert {:ok, repeated} = InstallationOwnerBootstrap.create(params, expected(params))
      assert repeated == %{initial | outcome: "recorded"}
      assert {Repo.all(InstallationOwnerReceipt), Repo.all(User), Repo.all(Membership)} == before
    end
  end

  test "changed private input, installation or request cannot adopt the completed owner", %{
    params: params
  } do
    assert {:ok, _} = InstallationOwnerBootstrap.create(params, expected(params))
    before = {Repo.all(InstallationOwnerReceipt), Repo.all(User), Repo.all(Membership)}

    for {field, value} <- [
          {"password", "different-private-password"},
          {"username", "other-owner"},
          {"team", "other-team"},
          {"installation", Ecto.UUID.generate()},
          {"request", Ecto.UUID.generate()}
        ] do
      changed = Map.put(params, field, value)

      assert {:error, :bootstrap_request_conflict} =
               InstallationOwnerBootstrap.create(changed, expected(changed))

      assert {Repo.all(InstallationOwnerReceipt), Repo.all(User), Repo.all(Membership)} == before
    end
  end

  test "malformed or unpinned inputs refuse before creating any actor", %{params: params} do
    assert {:error, :invalid_bootstrap_request} =
             InstallationOwnerBootstrap.create(params, String.duplicate("0", 64))

    for changed <- [
          Map.put(params, "command", "must-never-execute"),
          Map.put(params, "role", "reader"),
          Map.put(params, "installation", "wrong"),
          Map.put(params, "team", "invalid/team"),
          Map.put(params, "password", "short")
        ] do
      assert {:error, :invalid_bootstrap_request} =
               InstallationOwnerBootstrap.create(changed, expected(changed))
    end

    assert Repo.aggregate(InstallationOwnerReceipt, :count) == 0 and
             Repo.aggregate(User, :count) == 0
  end

  test "existing actor data refuses initial enrollment without alteration", %{params: params} do
    assert {:ok, user} = Accounts.create_user("existing-owner", "existing-private-password")
    on_exit(fn -> Repo.delete_all(from u in User, where: u.id == ^user.id) end)
    before = Repo.all(User)

    assert {:error, :installation_not_empty} =
             InstallationOwnerBootstrap.create(params, expected(params))

    assert Repo.all(User) == before and Repo.aggregate(InstallationOwnerReceipt, :count) == 0
  end

  test "membership failure rolls back the user and creation receipt", %{params: params} do
    Repo.query!(
      "ALTER TABLE memberships ADD CONSTRAINT bootstrap_test_membership_refusal CHECK (team <> 'initial-team')"
    )

    on_exit(fn ->
      Repo.query!("ALTER TABLE memberships DROP CONSTRAINT bootstrap_test_membership_refusal")
    end)

    assert_raise Ecto.ConstraintError, fn ->
      InstallationOwnerBootstrap.create(params, expected(params))
    end

    assert Repo.aggregate(User, :count) == 0 and Repo.aggregate(Membership, :count) == 0
    assert Repo.aggregate(InstallationOwnerReceipt, :count) == 0
  end

  test "recorded replay cannot reset a changed password or restore a changed membership", %{
    params: params
  } do
    assert {:ok, initial} = InstallationOwnerBootstrap.create(params, expected(params))
    Repo.update_all(User, set: [password_hash: <<0::256>>])
    Repo.update_all(Membership, set: [role: "reader"])
    before = {Repo.all(User), Repo.all(Membership)}
    assert {:ok, result} = InstallationOwnerBootstrap.create(params, expected(params))
    assert result.outcome == "recorded" and result.user_id == initial.user_id
    assert {Repo.all(User), Repo.all(Membership)} == before
    assert {:error, :unauthorized} = Accounts.authenticate(params["username"], params["password"])
    assert Accounts.role(initial.user_id, params["team"]) == "reader"
  end

  defp competing(params, same_request) do
    supervisor = start_supervised!({Task.Supervisor, []})
    parent = self()

    tasks =
      for number <- 1..2 do
        input =
          if same_request,
            do: params,
            else: %{params | "request" => Ecto.UUID.generate(), "username" => "owner-#{number}"}

        Task.Supervisor.async_nolink(supervisor, fn ->
          send(parent, {:ready, self()})

          receive do
            :go -> InstallationOwnerBootstrap.create(input, expected(input))
          after
            10_000 -> raise "Bootstrap barrier missing"
          end
        end)
      end

    pids =
      for _ <- tasks do
        assert_receive {:ready, pid}, 10_000
        pid
      end

    Enum.each(pids, &send(&1, :go))
    Enum.map(tasks, &Task.await(&1, 15_000))
  end

  test "different concurrent first requests create exactly one owner", %{params: params} do
    results = competing(params, false)
    assert Enum.count(results, &match?({:ok, %{outcome: "created"}}, &1)) == 1
    assert Enum.count(results, &(&1 == {:error, :bootstrap_request_conflict})) == 1
    assert Repo.aggregate(InstallationOwnerReceipt, :count) == 1
    assert Repo.aggregate(User, :count) == 1 and Repo.aggregate(Membership, :count) == 1
  end

  test "same concurrent request creates once and returns the same recorded result", %{
    params: params
  } do
    results = competing(params, true)
    assert Enum.count(results, &match?({:ok, %{outcome: "created"}}, &1)) == 1
    assert Enum.count(results, &match?({:ok, %{outcome: "recorded"}}, &1)) == 1

    assert Enum.map(results, fn {:ok, r} -> Map.delete(r, :outcome) end)
           |> Enum.uniq()
           |> length() == 1

    assert Repo.aggregate(User, :count) == 1 and Repo.aggregate(Membership, :count) == 1
  end
end
