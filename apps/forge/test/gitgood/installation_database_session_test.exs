defmodule Gitgood.InstallationDatabaseSessionTest do
  use ExUnit.Case, async: true
  alias Gitgood.InstallationDatabaseSession, as: Session

  defp database do
    %{
      "cluster" => "7694259926196269080",
      "database" => "ordinary_fixture",
      "database_oid" => 31,
      "owner_oid" => 32,
      "role" => "ordinary_fixture",
      "session_role" => "ordinary_fixture",
      "role_oid" => 32,
      "encoding" => "UTF8",
      "version" => "18.4",
      "address" => "127.0.0.1",
      "port" => 55432,
      "can_login" => true,
      "superuser" => false,
      "create_database" => false,
      "create_role" => false,
      "replication" => false,
      "bypass_rls" => false,
      "memberships" => 0
    }
  end

  defp observed do
    %{
      "database" => database(),
      "backend_pid" => 41,
      "backend_birth" => "1791623456123456",
      "held" => true
    }
  end

  test "exact ordinary identity and held backend capture a closed snapshot" do
    assert {:ok, snapshot} = Session.validate_observation(database(), observed())
    assert Map.keys(snapshot) |> Enum.sort() == ~w(backend_birth backend_pid database)
    assert snapshot["backend_pid"] == 41
    refute Map.has_key?(snapshot, "held")
  end

  test "a granted different database identity cannot replace independently expected identity" do
    for key <-
          ~w(cluster database database_oid owner_oid role session_role role_oid encoding version address port) do
      original = database()[key]
      replacement = if is_integer(original), do: original + 1, else: original <> "changed"
      changed = Map.put(database(), key, replacement)

      assert {:error, :invalid_session} =
               Session.validate_observation(database(), %{observed() | "database" => changed})
    end
  end

  test "administrative flags, role memberships and absent login refuse even when both sides agree" do
    for {key, replacement} <-
          Enum.map(~w(superuser create_database create_role replication bypass_rls), &{&1, true}) ++
            [{"memberships", 1}, {"can_login", false}] do
      changed = Map.put(database(), key, replacement)

      assert {:error, :invalid_session} =
               Session.validate_observation(changed, %{observed() | "database" => changed})
    end
  end

  test "strict wire types refuse bool, float and noncanonical identifiers" do
    for {key, replacement} <- [
          {"database_oid", true},
          {"database_oid", 31.0},
          {"memberships", 0.0},
          {"port", "55432"},
          {"cluster", "01"},
          {"cluster", "18446744073709551616"},
          {"cluster", "0"},
          {"database", String.duplicate("x", 64)},
          {"role", <<0>>}
        ] do
      changed = Map.put(database(), key, replacement)

      assert {:error, :invalid_session} =
               Session.validate_observation(changed, %{observed() | "database" => changed})
    end
  end

  test "unheld lock, PID alias and invalid backend birth refuse" do
    for {key, replacement} <- [
          {"held", false},
          {"held", 1},
          {"backend_pid", true},
          {"backend_pid", 0},
          {"backend_pid", 2_147_483_648},
          {"backend_birth", "01"},
          {"backend_birth", 1},
          {"backend_birth", "18446744073709551616"}
        ] do
      assert {:error, :invalid_session} =
               Session.validate_observation(database(), Map.put(observed(), key, replacement))
    end
  end

  test "unknown and missing fields cannot manufacture session authority" do
    for value <- [nil, [], Map.delete(observed(), "held"), Map.put(observed(), "extra", true)] do
      assert {:error, :invalid_session} = Session.validate_observation(database(), value)
    end

    for expected <- [nil, Map.delete(database(), "cluster"), Map.put(database(), "extra", true)] do
      assert {:error, :invalid_session} = Session.validate_observation(expected, observed())
    end
  end

  test "invalid expected input refuses before contacting any connection" do
    assert Session.capture(self(), %{}) == {:error, :installation_database_session_unavailable}
    assert Session.check(self(), %{}) == {:error, :installation_database_session_lost}
    assert Session.check(self(), nil) == {:error, :installation_database_session_lost}
  end
end
