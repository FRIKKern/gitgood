defmodule Gitgood.BarkparkConnectionsConcurrencyTest do
  use GitgoodWeb.RealConnCase, async: false
  import Ecto.Query

  alias Gitgood.{
    Accounts,
    BarkparkConnection,
    BarkparkConnectionEvent,
    BarkparkConnections,
    ConnectionSecrets,
    Credential,
    Repo,
    User
  }

  setup do
    saved_key = Application.get_env(:gitgood, :connection_key)
    Application.put_env(:gitgood, :connection_key, :crypto.strong_rand_bytes(32))
    suffix = Base.encode16(:crypto.strong_rand_bytes(6), case: :lower)
    {:ok, user} = Accounts.create_user("connection-race-" <> suffix, "synthetic-password")
    {_, credential} = Accounts.issue(user, "session")
    id = Ecto.UUID.generate()
    generation = Ecto.UUID.generate()
    origin = "https://fixture.example.invalid"

    {:ok, cipher} =
      ConnectionSecrets.seal("synthetic-race-credential", [user.id, id, generation, origin])

    row =
      Repo.insert!(%BarkparkConnection{
        id: id,
        user_id: user.id,
        generation: generation,
        origin: origin,
        workspace: "fixture",
        project: "default",
        dataset: "production",
        source_identity: %{"token_id" => Ecto.UUID.generate()},
        token_cipher: cipher
      })

    on_exit(fn ->
      Repo.delete_all(from e in BarkparkConnectionEvent, where: e.user_id == ^user.id)
      Repo.delete_all(from c in BarkparkConnection, where: c.user_id == ^user.id)
      Repo.delete_all(from c in Credential, where: c.user_id == ^user.id)
      Repo.delete_all(from u in User, where: u.id == ^user.id)

      if saved_key,
        do: Application.put_env(:gitgood, :connection_key, saved_key),
        else: Application.delete_env(:gitgood, :connection_key)
    end)

    %{user: user, credential: credential, row: row}
  end

  test "different simultaneous disconnect intents serialize against the expected generation", c do
    outcomes = race(c, ["disconnect-race-a", "disconnect-race-b"])
    assert Enum.count(outcomes, &match?({:ok, %{"state" => "disconnected"}}, &1)) == 1
    assert Enum.count(outcomes, &(&1 == {:error, :connection_changed})) == 1

    assert Repo.aggregate(
             from(e in BarkparkConnectionEvent, where: e.user_id == ^c.user.id),
             :count
           ) == 1

    row = Repo.get!(BarkparkConnection, c.row.id)
    assert is_nil(row.token_cipher) && row.generation != c.row.generation
  end

  test "simultaneous exact replay returns one original receipt and one durable responsibility",
       c do
    outcomes = race(c, ["disconnect-race-same", "disconnect-race-same"])
    assert [{:ok, first}, {:ok, second}] = outcomes
    assert first == second

    assert Repo.aggregate(
             from(e in BarkparkConnectionEvent, where: e.user_id == ^c.user.id),
             :count
           ) == 1

    assert Repo.get!(BarkparkConnection, c.row.id).generation == first["generation"]
  end

  defp race(c, keys) do
    supervisor = start_supervised!({Task.Supervisor, []})
    parent = self()

    tasks =
      for key <- keys do
        Task.Supervisor.async_nolink(supervisor, fn ->
          send(parent, {:ready, self()})

          receive do
            :go -> BarkparkConnections.disconnect(c.user, c.credential, c.row.generation, key)
          after
            10_000 -> raise "Connection race barrier missing"
          end
        end)
      end

    pids =
      for _ <- tasks do
        receive do
          {:ready, pid} -> pid
        after
          10_000 -> flunk("Connection workers not ready")
        end
      end

    Enum.each(pids, &send(&1, :go))
    Enum.map(tasks, &Task.await(&1, 10_000))
  end
end
