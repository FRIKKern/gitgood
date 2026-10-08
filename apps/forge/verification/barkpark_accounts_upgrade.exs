unless Mix.env() == :test and
         Regex.match?(
           ~r/\Agitgood_barkpark_upgrade_[0-9a-f]{8}\z/,
           System.get_env("PGDATABASE", "")
         ),
       do: raise("Use an isolated Barkpark account upgrade database")

alias Gitgood.{Accounts, BarkparkConnection, BarkparkConnectionEvent, ConnectionSecrets, Repo}
Logger.configure(level: :warning)
mode = System.fetch_env!("GITGOOD_BARKPARK_UPGRADE_MODE")
path = Application.app_dir(:gitgood, "priv/repo/migrations")
file = ".gitgood/verification/barkpark-account-upgrade.json"
{head, 0} = System.cmd(Gitgood.Git.executable(), ["rev-parse", "HEAD"])
{status, 0} = System.cmd(Gitgood.Git.executable(), ["status", "--porcelain"])
unless status == "", do: raise("Require a clean upgrade candidate")
candidate = String.trim(head)

spec =
  File.read!("../../docs/journeys/J10.md")
  |> then(&:crypto.hash(:sha256, &1))
  |> Base.encode16(case: :lower)

migration =
  File.read!(Path.join(path, "20261008151339_create_barkpark_connections.exs"))
  |> then(&:crypto.hash(:sha256, &1))
  |> Base.encode16(case: :lower)

if mode == "prepare" do
  Mix.Task.run("ecto.create")
  Mix.Task.run("ecto.migrate", ["--to", "20261008134931"])
  {:ok, _} = Application.ensure_all_started(:gitgood)
  unless Repo.aggregate(Gitgood.User, :count) == 0, do: raise("Upgrade fixture must start empty")
  name = "upgrade-source-" <> Base.encode16(:crypto.strong_rand_bytes(5), case: :lower)
  {:ok, user} = Accounts.create_user(name, "synthetic-password")
  {_, session} = Accounts.issue(user, "session")
  Ecto.Migrator.run(Repo, path, :up, all: true)
  Ecto.Migrator.run(Repo, path, :down, step: 1)

  unless Repo.query!("SELECT to_regclass('barkpark_connections')").rows == [[nil]] and
           Repo.get!(Gitgood.User, user.id).username == name,
         do: raise("Empty rollback lost legacy account or retained tables")

  Ecto.Migrator.run(Repo, path, :up, all: true)
  id = Ecto.UUID.generate()
  generation = Ecto.UUID.generate()
  origin = "https://migration-fixture.example.invalid"

  {:ok, cipher} =
    ConnectionSecrets.seal("synthetic-upgrade-source-credential", [
      user.id,
      id,
      generation,
      origin
    ])

  row =
    Repo.insert!(%BarkparkConnection{
      id: id,
      user_id: user.id,
      generation: generation,
      origin: origin,
      workspace: "fixture",
      project: "default",
      dataset: "production",
      source_identity: %{
        "fixture" => "Synthetic migration identity; not a live source verification"
      },
      token_cipher: cipher
    })

  event =
    Repo.insert!(%BarkparkConnectionEvent{
      user_id: user.id,
      request_key: "upgrade-connection-fixture",
      request_digest: Accounts.digest("synthetic-upgrade-request"),
      receipt: %{"generation" => generation, "fixture" => true}
    })

  refused = fn ->
    try do
      Ecto.Migrator.run(Repo, path, :down, step: 1)
      false
    rescue
      error in Postgrex.Error ->
        error.postgres.code == :raise_exception and
          String.contains?(
            error.postgres.message,
            "Barkpark connections or request history exist"
          )
    end
  end

  unless refused.(), do: raise("Populated downgrade discarded connection records")
  Repo.delete!(row)
  unless refused.(), do: raise("History-only downgrade discarded original receipts")
  restored = struct(BarkparkConnection, Map.from_struct(row) |> Map.delete(:__meta__))
  Repo.insert!(restored)

  receipt = %{
    candidate: candidate,
    tracked_clean: true,
    specification_sha256: spec,
    migration_sha256: migration,
    actor_id: user.id,
    username: name,
    session_id: session.id,
    connection_id: id,
    generation: generation,
    event_id: event.id,
    cipher_sha256: Base.encode16(:crypto.hash(:sha256, cipher), case: :lower),
    empty_downgrade_verified: true,
    populated_downgrade_refused: true,
    history_only_downgrade_refused: true,
    restart_verified: false,
    producer: "Codex /root",
    verifier: "Codex /root",
    scope:
      "Synthetic migration/restart prerequisite; not J10 links or coordinated backup/restore acceptance"
  }

  File.mkdir_p!(Path.dirname(file))
  File.write!(file, Jason.encode!(receipt, pretty: true))
  IO.puts("PASS populated and history-only Barkpark migration refusal; fresh VM check required")
else
  unless mode == "check", do: raise("Unknown upgrade mode")
  {:ok, _} = Application.ensure_all_started(:gitgood)
  receipt = file |> File.read!() |> Jason.decode!()

  unless receipt["candidate"] == candidate and receipt["specification_sha256"] == spec and
           receipt["migration_sha256"] == migration,
         do: raise("Stale migration fixture")

  row = Repo.get!(BarkparkConnection, receipt["connection_id"])
  user = Repo.get!(Gitgood.User, receipt["actor_id"])
  session = Repo.get!(Gitgood.Credential, receipt["session_id"])
  event = Repo.get!(BarkparkConnectionEvent, receipt["event_id"])

  {:ok, "synthetic-upgrade-source-credential"} =
    ConnectionSecrets.open(row.token_cipher, [user.id, row.id, row.generation, row.origin])

  unless row.generation == receipt["generation"] and user.username == receipt["username"] and
           session.user_id == user.id and session.kind == "session" and is_nil(session.revoked_at) and
           event.user_id == user.id and event.receipt["generation"] == row.generation and
           Base.encode16(:crypto.hash(:sha256, row.token_cipher), case: :lower) ==
             receipt["cipher_sha256"],
         do: raise("Fresh VM lost credential ownership, ciphertext or original request history")

  receipt =
    Map.merge(receipt, %{
      "restart_verified" => true,
      "recorded_at" => DateTime.to_iso8601(Accounts.now())
    })

  File.write!(file, Jason.encode!(receipt, pretty: true))
  IO.puts("PASS fresh VM retains encrypted Barkpark account, native session and request identity")
end
