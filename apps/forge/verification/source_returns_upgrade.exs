unless Mix.env() == :dev &&
         Regex.match?(
           ~r/\Agitgood_journal_upgrade_[0-9a-f]{8}\z/,
           System.get_env("PGDATABASE", "")
         ),
       do: raise("Use an isolated ordinary source-journal upgrade database")

alias Gitgood.{
  Accounts,
  BarkparkConnection,
  BarkparkConnections,
  ConnectionSecrets,
  Credential,
  PullRequest,
  Repo,
  Repository,
  SourceLink,
  SourceLinkEvent,
  SourceLinks,
  SourceReturnOperation,
  SourceReturns,
  User
}

Logger.configure(level: :warning)
Application.put_env(:gitgood, :reconcile, false)
metadata = File.read!(System.fetch_env!("GITGOOD_JOURNAL_SOURCE_METADATA")) |> Jason.decode!()

unless metadata["fixture"] == true &&
         Regex.match?(~r/\Ahttps:\/\/127\.0\.0\.1:[0-9]+\z/, metadata["origin"]),
       do: raise("Journal upgrade requires the separately owned synthetic HTTPS source")

Application.put_env(:gitgood, :barkpark_origin, metadata["origin"])
Application.put_env(:gitgood, :barkpark_ca_file, metadata["ca"])
mode = System.fetch_env!("GITGOOD_JOURNAL_UPGRADE_MODE")
file = ".gitgood/verification/source-journal-upgrade.json"
path = Application.app_dir(:gitgood, "priv/repo/migrations")
{head, 0} = System.cmd(Gitgood.Git.executable(), ["rev-parse", "HEAD"])
{status, 0} = System.cmd(Gitgood.Git.executable(), ["status", "--porcelain"])
unless status == "", do: raise("Require a clean source-journal candidate")
candidate = String.trim(head)

hash = fn p ->
  File.read!(p) |> then(&:crypto.hash(:sha256, &1)) |> Base.encode16(case: :lower)
end

spec = hash.("../../docs/journeys/J10.md")
migration = hash.(Path.join(path, "20261008172326_add_source_return_pointer_journal.exs"))
File.mkdir_p!(Path.dirname(file))

control = fn values ->
  python = System.find_executable(Application.fetch_env!(:gitgood, :python_executable))

  code = """
  import json,sys,urllib.request
  value=json.load(sys.stdin)
  body=json.dumps(value["body"]).encode()
  request=urllib.request.Request(value["url"]+"/control/journal-state",data=body,
    headers={"Authorization":"Bearer synthetic-fixture-control","Content-Type":"application/json"})
  handler=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  with handler.open(request,timeout=2) as response:
    assert response.status==200
  print("fixture-control-confirmed")
  """

  input = Jason.encode!(%{url: metadata["control"], body: values})
  {:ok, output, 0} = Gitgood.Command.run([python, "-I", "-c", code], input: input, timeout: 5000)

  unless String.trim(output) == "fixture-control-confirmed",
    do: raise("Owned fixture control failed")
end

if mode == "prepare" do
  Mix.Task.run("ecto.create")
  Mix.Task.run("ecto.migrate", ["--to", "20261008164430"])
  {:ok, _} = Application.ensure_all_started(:gitgood)

  unless Repo.config()[:pool] != Ecto.Adapters.SQL.Sandbox && Repo.aggregate(User, :count) == 0,
    do: raise("Require an empty ordinary pool, never sandbox rollback")

  name = "journal-upgrade-" <> Base.encode16(:crypto.strong_rand_bytes(5), case: :lower)
  {:ok, user} = Accounts.create_user(name, "synthetic-password")
  Accounts.add_member(user, name, "owner")
  {_, credential} = Accounts.issue(user, "session")

  repository =
    %Repository{
      owner_id: user.id,
      team: name,
      storage_key: Ecto.UUID.generate(),
      creation_key: "legacy-journal-repository"
    }
    |> Repository.changeset(%{name: "project"})
    |> Repo.insert!()

  pull =
    Repo.insert!(%PullRequest{
      repository_id: repository.id,
      author_id: user.id,
      title: "Legacy private change before source journal",
      source_ref: "refs/heads/feature",
      target_ref: "refs/heads/main",
      creation_key: "legacy-journal-change",
      request_digest: Accounts.digest("legacy-journal-change")
    })

  {:ok, connection} =
    BarkparkConnections.connect(
      user,
      credential,
      %{
        "token" => "synthetic-fixture-credential",
        "workspace" => "fixture-workspace",
        "project" => "default",
        "dataset" => "production",
        "expected_generation" => "absent"
      },
      "legacy-journal-connect"
    )

  document_id = "drafts." <> name

  {:ok, link} =
    SourceLinks.attach(
      repository,
      pull,
      user,
      credential,
      %{
        "type" => "paper",
        "document_id" => document_id,
        "connection_generation" => connection["generation"]
      },
      "legacy-journal-link"
    )

  row = Repo.get!(BarkparkConnection, connection["id"])
  Ecto.Migrator.run(Repo, path, :up, to: 20_261_008_172_326)
  Ecto.Migrator.run(Repo, path, :down, to_exclusive: 20_261_008_164_430)

  unless Repo.query!("SELECT to_regclass('source_return_operations')").rows == [[nil]] &&
           Repo.get!(BarkparkConnection, row.id).token_cipher == row.token_cipher &&
           Repo.get!(SourceLink, link["id"]).generation == link["generation"] &&
           Repo.aggregate(SourceLinkEvent, :count) == 1,
         do: raise("Empty journal downgrade changed legacy link or encrypted source identity")

  Ecto.Migrator.run(Repo, path, :up, to: 20_261_008_172_326)

  params = %{
    "generation" => link["generation"],
    "connection_generation" => connection["generation"]
  }

  parent = self()

  tasks =
    for _ <- 1..8,
        do:
          Task.async(fn ->
            send(parent, {:journal_ready, self()})

            receive do
              :journal_go -> :ok
            after
              5000 -> raise("Journal request barrier not released")
            end

            SourceReturns.request(
              repository,
              pull,
              user,
              credential,
              link["id"],
              params,
              "concurrent-journal-request"
            )
          end)

  pids =
    for _ <- tasks do
      receive do
        {:journal_ready, pid} -> pid
      after
        5000 -> raise("Journal actor not ready")
      end
    end

  Enum.each(pids, &send(&1, :journal_go))
  results = Enum.map(tasks, &Task.await(&1, 10_000))
  [{:ok, requested} | _] = results

  unless Enum.all?(results, &(&1 == {:ok, requested})) &&
           Repo.aggregate(SourceReturnOperation, :count) == 1 && requested["state"] == "queued",
         do: raise("Concurrent journal requests duplicated native responsibility")

  control.(%{
    prewrite_lost: true,
    lost_reply: false,
    outage_after_write: false,
    stale_reads: false
  })

  SourceReturns.process(requested["id"])
  op = Repo.get!(SourceReturnOperation, requested["id"])

  unless op.state == "unknown" && op.sent_once && is_binary(op.payload_cipher) &&
           is_binary(op.payload_digest) && op.before_revision == "fixture-revision" &&
           op.source_transaction == nil && op.actor_label == user.username,
         do:
           raise(
             "Actual interrupted source request did not retain encrypted immutable responsibility"
           )

  refused =
    try do
      Ecto.Migrator.run(Repo, path, :down, to_exclusive: 20_261_008_164_430)
      false
    rescue
      error in Postgrex.Error ->
        error.postgres.code == :raise_exception &&
          String.contains?(
            error.postgres.message,
            "source write responsibility must be preserved"
          )
    end

  unless refused && Repo.get!(SourceReturnOperation, op.id).payload_cipher == op.payload_cipher &&
           Repo.get!(SourceLink, link["id"]).state == "active",
         do: raise("Populated journal downgrade lost uncertain responsibility")

  control.(%{prewrite_lost: false})

  receipt = %{
    candidate: candidate,
    producer: "Codex /root",
    verifier: "Codex /root",
    prepared_at: DateTime.to_iso8601(Accounts.now()),
    specification_sha256: spec,
    migration_sha256: migration,
    ordinary_postgres_pool: true,
    concurrent_requests: 8,
    one_operation: true,
    empty_downgrade: true,
    populated_downgrade_refused: true,
    native_actor: user.id,
    native_actor_label: user.username,
    credential: credential.id,
    repository: repository.id,
    pull: pull.id,
    pull_public_id: pull.public_id,
    link: link,
    connection: connection["id"],
    connection_generation: connection["generation"],
    source_actor: op.source_identity["token_id"],
    operation: op.id,
    request: params,
    payload_sha256: Base.encode16(op.payload_digest, case: :lower),
    cipher_sha256: Base.encode16(:crypto.hash(:sha256, op.payload_cipher), case: :lower),
    original_source_key: "gitgood-pointer-" <> op.id,
    before_revision: op.before_revision,
    source_origin: metadata["origin"],
    state_before_vm_exit: op.state,
    fresh_vm_verified: false,
    limitation:
      "Owned synthetic HTTPS and metadata migration/recovery. Not live J10, deployment, or coordinated backup/restore."
  }

  File.write!(file, Jason.encode!(receipt, pretty: true))

  IO.puts(
    "PASS ordinary Postgres journal concurrency, guarded migration and encrypted unknown request; fresh VM required"
  )
else
  receipt = File.read!(file) |> Jason.decode!()

  unless receipt["candidate"] == candidate && receipt["specification_sha256"] == spec &&
           receipt["migration_sha256"] == migration &&
           receipt["source_origin"] == metadata["origin"],
         do: raise("Journal upgrade receipt does not describe this clean candidate/source")

  {:ok, _} = Application.ensure_all_started(:gitgood)
  op = Repo.get!(SourceReturnOperation, receipt["operation"])
  user = Repo.get!(User, receipt["native_actor"])
  credential = Repo.get!(Credential, receipt["credential"])
  repository = Repo.get!(Repository, receipt["repository"])
  pull = Repo.get!(PullRequest, receipt["pull"])

  unless op.state == "unknown" && op.source_transaction == nil &&
           op.actor_id == user.id && op.actor_label == receipt["native_actor_label"] &&
           op.source_identity["token_id"] == receipt["source_actor"] &&
           op.connection_generation == receipt["connection_generation"] &&
           Base.encode16(:crypto.hash(:sha256, op.payload_cipher), case: :lower) ==
             receipt["cipher_sha256"],
         do: raise("Separate VM lost origin identity or encrypted pending responsibility")

  binding = [
    "source-journal-payload-v1",
    op.id,
    op.actor_id,
    op.link_generation,
    op.connection_id,
    op.connection_generation,
    op.locator["origin"]
  ]

  {:ok, bytes} = ConnectionSecrets.open(op.payload_cipher, binding)

  unless Base.encode16(:crypto.hash(:sha256, bytes), case: :lower) == receipt["payload_sha256"],
    do: raise("Separate VM cannot authenticate exact original mutation bytes")

  deadline = System.monotonic_time(:millisecond) + 7000

  wait = fn wait ->
    if DateTime.compare(op.next_at, Accounts.now()) == :gt do
      if System.monotonic_time(:millisecond) >= deadline,
        do: raise("Owned retry delay exceeded bound")

      Process.sleep(50)
      wait.(wait)
    end
  end

  wait.(wait)
  SourceReturns.process(op.id)
  applied = Repo.get!(SourceReturnOperation, op.id)

  unless applied.state == "applied" && is_binary(applied.source_transaction) &&
           applied.payload_cipher == nil && applied.payload_digest == op.payload_digest &&
           applied.attempts == op.attempts + 1 &&
           applied.before_revision == receipt["before_revision"],
         do: raise("Separate VM did not resume original immutable source request")

  {:ok, replay} =
    SourceReturns.request(
      repository,
      pull,
      user,
      credential,
      op.link_id,
      receipt["request"],
      "concurrent-journal-request"
    )

  unless replay["id"] == op.id && replay["state"] == "applied" &&
           Repo.aggregate(SourceReturnOperation, :count) == 1,
         do: raise("Original native journal key changed responsibility after restart")

  {:ok, %{status: 200, body: stats}} =
    Gitgood.BarkparkHTTP.get("/journal/stats", "synthetic-fixture-credential")

  posts = Enum.filter(stats["posts"], &(&1["key"] == receipt["original_source_key"]))

  unless length(posts) == 2 && hd(posts) == List.last(posts) &&
           hd(posts)["sha256"] == receipt["payload_sha256"],
         do: raise("Source retry changed actual wire bytes/key after VM replacement")

  doc = stats["documents"][op.locator["document_id"]]
  pointer = Gitgood.PaperReturnPointer.block(op)

  unless Enum.count(doc["blocks"], &(&1 == pointer)) == 1 &&
           hd(doc["blocks"])["id"] == "source-intent" &&
           doc["purpose"] == "Source owns this intention.",
         do: raise("Source recovery duplicated pointer or changed unrelated intention")

  receipt =
    Map.merge(receipt, %{
      "fresh_vm_verified" => true,
      "checked_at" => DateTime.to_iso8601(Accounts.now()),
      "state_after_recovery" => applied.state,
      "source_transaction" => applied.source_transaction,
      "identical_wire_replay" => true,
      "one_owned_pointer" => true,
      "unrelated_content_preserved" => true
    })

  File.write!(file, Jason.encode!(receipt, pretty: true))

  IO.puts(
    "PASS separate VM recovered original encrypted request, exact source bytes/key, actual transaction and one preserved pointer"
  )
end
