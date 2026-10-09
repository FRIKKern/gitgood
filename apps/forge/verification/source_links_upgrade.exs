unless Mix.env() == :dev &&
         Regex.match?(
           ~r/\Agitgood_source_upgrade_[0-9a-f]{8}\z/,
           System.get_env("PGDATABASE", "")
         ),
       do: raise("Use an isolated native source-link upgrade database")

alias Gitgood.{
  Accounts,
  BarkparkConnection,
  BarkparkConnectionEvent,
  BarkparkConnections,
  ConnectionSecrets,
  PullRequest,
  Repo,
  Repository,
  SourceLink,
  SourceLinkEvent,
  SourceLinks
}

Logger.configure(level: :warning)
Application.put_env(:gitgood, :reconcile, false)
mode = System.fetch_env!("GITGOOD_SOURCE_UPGRADE_MODE")
path = Application.app_dir(:gitgood, "priv/repo/migrations")
file = ".gitgood/verification/native-source-upgrade.json"
{head, 0} = System.cmd(Gitgood.Git.executable(), ["rev-parse", "HEAD"])
{status, 0} = System.cmd(Gitgood.Git.executable(), ["status", "--porcelain"])
unless status == "", do: raise("Require a clean source-link upgrade candidate")
candidate = String.trim(head)

hash = fn file ->
  File.read!(file) |> then(&:crypto.hash(:sha256, &1)) |> Base.encode16(case: :lower)
end

spec = hash.("../../docs/journeys/J10.md")
migration = hash.(Path.join(path, "20261008164430_add_native_source_links.exs"))
File.mkdir_p!(Path.dirname(file))

if mode == "prepare" do
  Mix.Task.run("ecto.create")
  Mix.Task.run("ecto.migrate", ["--to", "20261008151339"])
  {:ok, _} = Application.ensure_all_started(:gitgood)

  unless Repo.config()[:pool] != Ecto.Adapters.SQL.Sandbox &&
           Repo.aggregate(Gitgood.User, :count) == 0,
         do: raise("Require an empty ordinary Postgres pool, not a sandbox transaction")

  name = "source-upgrade-" <> Base.encode16(:crypto.strong_rand_bytes(5), case: :lower)
  {:ok, user} = Accounts.create_user(name, "synthetic-password")
  Accounts.add_member(user, name, "owner")
  {_, credential} = Accounts.issue(user, "session")

  repository =
    %Repository{
      owner_id: user.id,
      team: name,
      storage_key: Ecto.UUID.generate(),
      creation_key: "legacy-source-repository"
    }
    |> Repository.changeset(%{name: "project"})
    |> Repo.insert!()

  pull =
    Repo.insert!(%PullRequest{
      repository_id: repository.id,
      author_id: user.id,
      title: "Legacy change before source-link migration",
      source_ref: "refs/heads/feature",
      target_ref: "refs/heads/main",
      creation_key: "legacy-source-change",
      request_digest: Accounts.digest("legacy-source-change")
    })

  python = System.find_executable(Application.fetch_env!(:gitgood, :python_executable))
  openssl = System.find_executable(System.get_env("GITGOOD_OPENSSL", "openssl"))
  ca = Path.expand(".gitgood/verification/source-upgrade-ca.pem")

  fixture =
    Port.open({:spawn_executable, python}, [
      :binary,
      :exit_status,
      :use_stdio,
      :hide,
      {:line, 1024},
      {:args, ["-I", Path.expand("verification/barkpark_http_fixture.py"), openssl, ca]}
    ])

  origin =
    receive do
      {^fixture, {:data, {:eol, "READY " <> ports}}} ->
        [_, https, _] = String.split(ports)
        "https://127.0.0.1:" <> https
    after
      20_000 -> raise("Owned upgrade HTTPS source fixture not ready")
    end

  Application.put_env(:gitgood, :barkpark_origin, origin)
  Application.put_env(:gitgood, :barkpark_ca_file, ca)

  connection_params = %{
    "token" => "synthetic-fixture-credential",
    "workspace" => "fixture-workspace",
    "project" => "default",
    "dataset" => "production",
    "expected_generation" => "absent"
  }

  {:ok, connection} =
    BarkparkConnections.connect(user, credential, connection_params, "legacy-source-connect")

  row = Repo.get_by!(BarkparkConnection, user_id: user.id)
  cipher_hash = Base.encode16(:crypto.hash(:sha256, row.token_cipher), case: :lower)
  Ecto.Migrator.run(Repo, path, :up, to: 20_261_008_164_430)
  Ecto.Migrator.run(Repo, path, :down, to_exclusive: 20_261_008_151_339)

  unless Repo.query!("SELECT to_regclass('source_links')").rows == [[nil]] &&
           Repo.get!(PullRequest, pull.id).public_id == pull.public_id &&
           Repo.get!(BarkparkConnection, row.id).token_cipher == row.token_cipher &&
           Repo.aggregate(BarkparkConnectionEvent, :count) == 1,
         do: raise("Empty source downgrade lost legacy identity or connection responsibility")

  Ecto.Migrator.run(Repo, path, :up, to: 20_261_008_164_430)

  params = %{
    "type" => "paper",
    "document_id" => "drafts.concurrent-source-spec",
    "connection_generation" => connection["generation"]
  }

  Port.command(fixture, "hold-docs\n")

  receive do
    {^fixture, {:data, {:eol, "HOLDING_DOCS"}}} -> :ok
  after
    4000 -> raise("Source hold did not activate")
  end

  tasks =
    for _ <- 1..2,
        do:
          Task.async(fn ->
            SourceLinks.attach(
              repository,
              pull,
              user,
              credential,
              params,
              "concurrent-source-attach"
            )
          end)

  for _ <- tasks do
    receive do
      {^fixture, {:data, {:eol, "BLOCKED_DOCUMENT"}}} -> :ok
    after
      4000 -> raise("Concurrent attach did not reach external I/O independently")
    end
  end

  Port.command(fixture, "release\n")
  [{:ok, attached}, {:ok, attached_again}] = Enum.map(tasks, &Task.await(&1, 10_000))

  unless attached == attached_again && Repo.aggregate(SourceLink, :count) == 1 &&
           Repo.aggregate(SourceLinkEvent, :count) == 1,
         do: raise("Concurrent attach duplicated responsibility")

  parent = self()

  removals =
    for _ <- 1..8,
        do:
          Task.async(fn ->
            send(parent, {:remove_ready, self()})

            receive do
              :remove_go -> :ok
            after
              5000 -> raise("Removal barrier not released")
            end

            SourceLinks.remove(
              repository,
              pull,
              user,
              credential,
              attached["id"],
              attached["generation"],
              "concurrent-source-remove"
            )
          end)

  pids =
    for _ <- removals do
      receive do
        {:remove_ready, pid} -> pid
      after
        4000 -> raise("Removal actor not ready")
      end
    end

  Enum.each(pids, &send(&1, :remove_go))
  results = Enum.map(removals, &Task.await(&1, 10_000))
  [{:ok, removed} | _] = results

  unless Enum.all?(results, &(&1 == {:ok, removed})) && removed["state"] == "removed" &&
           Repo.aggregate(SourceLinkEvent, :count) == 2,
         do: raise("Concurrent removal duplicated operation or diverged receipts")

  {:ok, ^attached} =
    SourceLinks.attach(repository, pull, user, credential, params, "concurrent-source-attach")

  unless Repo.get!(SourceLink, attached["id"]).state == "removed",
    do: raise("Historical attach resurrected removed responsibility")

  refused = fn ->
    try do
      Ecto.Migrator.run(Repo, path, :down, to_exclusive: 20_261_008_151_339)
      false
    rescue
      error in Postgrex.Error ->
        error.postgres.code == :raise_exception &&
          String.contains?(
            error.postgres.message,
            "native source link responsibility must be preserved"
          )
    end
  end

  unless refused.(), do: raise("Populated source-link downgrade was not refused")
  original_events = Repo.all(SourceLinkEvent)
  {2, _} = Repo.delete_all(SourceLinkEvent)
  unless refused.(), do: raise("Link-only downgrade was not refused")

  Enum.each(original_events, fn event ->
    struct(SourceLinkEvent, Map.from_struct(event) |> Map.delete(:__meta__)) |> Repo.insert!()
  end)

  # Temporarily remove only this disposable fixture's restrictive FK to reach
  # an event-only corruption shape. Normal native operations cannot create it.
  # Restore the exact link and constraint after exercising the real migrator.
  retained_link = Repo.get!(SourceLink, attached["id"])
  Repo.query!("ALTER TABLE source_link_events DROP CONSTRAINT source_link_events_link_id_fkey")
  {1, _} = Repo.delete_all(SourceLink)
  event_only_refused = refused.()
  struct(SourceLink, Map.from_struct(retained_link) |> Map.delete(:__meta__)) |> Repo.insert!()

  Repo.query!(
    "ALTER TABLE source_link_events ADD CONSTRAINT source_link_events_link_id_fkey FOREIGN KEY (link_id) REFERENCES source_links(id) ON DELETE RESTRICT"
  )

  unless event_only_refused && Repo.aggregate(SourceLink, :count) == 1 &&
           Repo.aggregate(SourceLinkEvent, :count) == 2,
         do: raise("Event-only refusal failed or altered retained records")

  receipt = %{
    candidate: candidate,
    specification_sha256: spec,
    migration_sha256: migration,
    actor: user.id,
    username: name,
    session: credential.id,
    repository: repository.id,
    pull: pull.id,
    pull_public_id: pull.public_id,
    connection: row.id,
    connection_generation: row.generation,
    connection_origin: row.origin,
    cipher_sha256: cipher_hash,
    attach_params: params,
    original_attach_receipt: attached,
    current_link: removed,
    ordinary_postgres_pool: true,
    concurrent_attach_requests: 2,
    concurrent_remove_requests: 8,
    one_link: true,
    two_original_events: true,
    empty_downgrade: true,
    populated_downgrade_refused: true,
    link_only_downgrade_refused: true,
    event_only_downgrade_refused: true,
    fresh_vm_verified: false,
    producer: "Codex /root",
    verifier: "Codex /root",
    limitation:
      "Owned synthetic HTTPS/migration prerequisite; not managed deployment or coordinated backup/restore."
  }

  File.write!(file, Jason.encode!(receipt, pretty: true))
  Port.command(fixture, "quit\n")

  IO.puts(
    "PASS source-link ordinary Postgres concurrency and downgrade refusal; fresh VM required"
  )
else
  unless mode == "check", do: raise("Unknown source-link upgrade mode")
  {:ok, _} = Application.ensure_all_started(:gitgood)
  receipt = file |> File.read!() |> Jason.decode!()

  unless receipt["candidate"] == candidate && receipt["specification_sha256"] == spec &&
           receipt["migration_sha256"] == migration,
         do: raise("Stale native source upgrade fixture")

  user = Repo.get!(Gitgood.User, receipt["actor"])
  credential = Repo.get!(Gitgood.Credential, receipt["session"])
  repository = Repo.get!(Repository, receipt["repository"])
  pull = Repo.get!(PullRequest, receipt["pull"])
  connection = Repo.get!(BarkparkConnection, receipt["connection"])
  Application.put_env(:gitgood, :barkpark_origin, connection.origin)

  {:ok, "synthetic-fixture-credential"} =
    ConnectionSecrets.open(
      connection.token_cipher,
      [user.id, connection.id, connection.generation, connection.origin]
    )

  unless Base.encode16(:crypto.hash(:sha256, connection.token_cipher), case: :lower) ==
           receipt["cipher_sha256"] &&
           connection.generation == receipt["connection_generation"] &&
           pull.public_id == receipt["pull_public_id"],
         do: raise("Fresh VM lost source credential binding or native change identity")

  {:ok, [current]} = SourceLinks.list(repository, pull, user, credential)

  unless current == receipt["current_link"] && current["state"] == "removed",
    do: raise("Fresh VM lost current native link lifecycle")

  {:ok, original} =
    SourceLinks.attach(
      repository,
      pull,
      user,
      credential,
      receipt["attach_params"],
      "concurrent-source-attach"
    )

  unless original == receipt["original_attach_receipt"] &&
           Repo.aggregate(SourceLinkEvent, :count) == 2 &&
           Repo.get!(SourceLink, current["id"]).state == "removed",
         do: raise("Fresh VM lost original receipt or replay resurrected link")

  receipt =
    Map.merge(receipt, %{
      "fresh_vm_verified" => true,
      "checked_at" => DateTime.to_iso8601(Accounts.now())
    })

  File.write!(file, Jason.encode!(receipt, pretty: true))

  IO.puts(
    "PASS fresh VM retained native/source identity, encryption binding, lifecycle and original receipts"
  )
end
