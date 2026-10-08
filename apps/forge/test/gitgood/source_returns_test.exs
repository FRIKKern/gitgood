defmodule Gitgood.SourceReturnsTest do
  use GitgoodWeb.ConnCase, async: false
  import Ecto.Query

  alias Gitgood.{
    Accounts,
    ConnectionSecrets,
    BarkparkConnections,
    Membership,
    PullRequest,
    Repo,
    Repository,
    SourceLinks,
    SourceReturns,
    SourceReturnOperation,
    PaperReturnPointer
  }

  setup do
    saved =
      Map.new(
        [:barkpark_origin, :barkpark_allow_loopback_http, :connection_key, :web_origin],
        &{&1, Application.get_env(:gitgood, &1)}
      )

    python = System.find_executable(Application.fetch_env!(:gitgood, :python_executable))
    openssl = System.find_executable(System.get_env("GITGOOD_OPENSSL", "openssl"))

    fixture =
      Port.open({:spawn_executable, python}, [
        :binary,
        :exit_status,
        :use_stdio,
        :hide,
        {:line, 1024},
        {:args,
         ["-I", Path.expand("../../verification/barkpark_http_fixture.py", __DIR__), openssl]}
      ])

    origin =
      receive do
        {^fixture, {:data, {:eol, "READY " <> ports}}} ->
          [http, _] = String.split(ports)
          "http://127.0.0.1:" <> http
      after
        20_000 -> flunk("Source wire fixture not ready")
      end

    Application.put_env(:gitgood, :barkpark_origin, origin)
    Application.put_env(:gitgood, :barkpark_allow_loopback_http, true)
    Application.put_env(:gitgood, :connection_key, :crypto.strong_rand_bytes(32))

    on_exit(fn ->
      if Port.info(fixture), do: Port.close(fixture)

      for {key, value} <- saved do
        if is_nil(value),
          do: Application.delete_env(:gitgood, key),
          else: Application.put_env(:gitgood, key, value)
      end
    end)

    {:ok, owner} = Accounts.create_user("links-owner", "synthetic-password")
    {:ok, reader} = Accounts.create_user("links-reader", "synthetic-password")
    {:ok, outsider} = Accounts.create_user("links-outsider", "synthetic-password")
    Accounts.add_member(owner, "linked-team", "owner")
    Accounts.add_member(reader, "linked-team", "reader")
    Accounts.add_member(outsider, "other-team", "owner")
    {token, credential} = Accounts.issue(owner, "session")
    {reader_token, reader_credential} = Accounts.issue(reader, "session")
    {outsider_token, outsider_credential} = Accounts.issue(outsider, "session")

    repository =
      %Repository{
        owner_id: owner.id,
        team: "linked-team",
        storage_key: Ecto.UUID.generate(),
        creation_key: "links-repository"
      }
      |> Repository.changeset(%{name: "linked-project"})
      |> Repo.insert!()

    pull =
      Repo.insert!(%PullRequest{
        repository_id: repository.id,
        author_id: owner.id,
        title: "Native private change",
        source_ref: "refs/heads/feature",
        target_ref: "refs/heads/main",
        creation_key: "links-change",
        request_digest: Accounts.digest("links-change")
      })

    connection_params = %{
      "token" => "synthetic-fixture-credential",
      "workspace" => "fixture-workspace",
      "project" => "default",
      "dataset" => "production",
      "expected_generation" => "absent"
    }

    {:ok, connection} =
      BarkparkConnections.connect(owner, credential, connection_params, "owner-connect")

    {:ok, reader_connection} =
      BarkparkConnections.connect(
        reader,
        reader_credential,
        %{connection_params | "token" => "synthetic-outsider-credential"},
        "reader-connect"
      )

    %{
      owner: owner,
      reader: reader,
      outsider: outsider,
      credential: credential,
      reader_credential: reader_credential,
      outsider_credential: outsider_credential,
      token: token,
      reader_token: reader_token,
      outsider_token: outsider_token,
      repository: repository,
      pull: pull,
      connection: connection,
      reader_connection: reader_connection,
      fixture: fixture,
      params: %{
        "type" => "paper",
        "document_id" => "drafts.private-spec",
        "connection_generation" => connection["generation"]
      }
    }
  end

  test "queued intent precedes I/O; immutable identity, actual source result and replay", c do
    first = queued(c, "return-first")
    assert first["state"] == "queued"
    assert stats()["posts"] == []
    assert queued(c, "return-first")["id"] == first["id"]
    assert Repo.aggregate(SourceReturnOperation, :count) == 1
    SourceReturns.process(first["id"])
    op = Repo.get!(SourceReturnOperation, first["id"])
    assert op.state == "applied"
    assert is_binary(op.source_transaction)
    assert op.payload_cipher == nil

    assert op.destination ==
             Application.fetch_env!(:gitgood, :web_origin) <> "/changes/" <> c.pull.public_id

    assert op.source_identity["token_id"] == c.connection["source_identity"]["token_id"]
    assert op.actor_id == c.owner.id && op.credential_id == c.credential.id
    body = stats()
    assert length(body["posts"]) == 1

    assert body["posts"] |> hd() |> Map.fetch!("sha256") ==
             Base.encode16(op.payload_digest, case: :lower)

    source = body["documents"][c.params["document_id"]]
    assert source["purpose"] == "Source owns this intention."
    assert source["blocks"] |> hd() |> Map.fetch!("id") == "source-intent"
    assert List.last(source["blocks"]) == PaperReturnPointer.block(op)
    assert length(source["blocks"]) == 2
    replay = queued(c, "return-first")
    assert replay["id"] == first["id"] && replay["state"] == "applied"
    assert length(stats()["posts"]) == 1

    assert {:error, :idempotency_conflict} =
             SourceReturns.request(
               c.repository,
               c.pull,
               c.owner,
               c.credential,
               op.link_id,
               %{
                 "generation" => op.link_generation,
                 "connection_generation" => Ecto.UUID.generate()
               },
               "return-first"
             )

    assert {:ok, [%{"state" => "applied"}]} =
             SourceReturns.list(c.repository, c.pull, c.reader, c.reader_credential, op.link_id)

    assert {:error, :source_operation_not_found} =
             SourceReturns.list(
               c.repository,
               c.pull,
               c.outsider,
               c.outsider_credential,
               op.link_id
             )
  end

  test "lost reply retains encrypted bytes then observes actual pointer without inventing transaction",
       c do
    command(c.fixture, "journal-lost 1", "JOURNAL_LOST")
    first = queued(c, "lost-return")
    SourceReturns.process(first["id"])
    op = Repo.get!(SourceReturnOperation, first["id"])
    assert op.state == "unknown" && op.sent_once
    assert is_binary(op.payload_cipher) && op.source_transaction == nil
    refute inspect(op) =~ "Unselected source content"
    refute inspect(op) =~ "payload_cipher"
    assert length(stats()["receipts"]) == 1
    command(c.fixture, "journal-lost 0", "JOURNAL_LOST")
    advance(op)
    SourceReturns.process(op.id)
    observed = Repo.get!(SourceReturnOperation, op.id)
    assert observed.state == "observed" && observed.source_transaction == nil
    assert observed.payload_cipher == nil
    assert observed.observation["actor_id"] == c.owner.id
    assert observed.observation["source_token_id"] == c.connection["source_identity"]["token_id"]
    assert length(stats()["posts"]) == 1
    assert length(stats()["documents"][c.params["document_id"]]["blocks"]) == 2
  end

  test "unknown prewrite outcome retries exact CAS bytes and preserves owner's new revision", c do
    command(c.fixture, "journal-prewrite-lost 1", "JOURNAL_PREWRITE_LOST")
    first = queued(c, "prewrite-return")
    SourceReturns.process(first["id"])
    op = Repo.get!(SourceReturnOperation, first["id"])
    assert op.state == "unknown" && is_binary(op.payload_cipher)
    cipher = op.payload_cipher
    digest = op.payload_digest
    assert op.before_revision == "fixture-revision"
    command(c.fixture, "journal-prewrite-lost 0", "JOURNAL_PREWRITE_LOST")
    command(c.fixture, "journal-owner-edit", "JOURNAL_OWNER_EDIT")
    advance(op)
    SourceReturns.process(op.id)
    current = Repo.get!(SourceReturnOperation, op.id)
    assert current.state == "unknown"
    assert current.reason == "source_refused_409"
    assert current.payload_cipher == cipher && current.payload_digest == digest
    [one, two] = stats()["posts"]
    assert one == two
    assert stats()["receipts"] == []
    blocks = stats()["documents"][c.params["document_id"]]["blocks"]
    assert Enum.any?(blocks, &(&1["id"] == "owner-edit"))
    refute Enum.any?(blocks, &(&1["id"] == PaperReturnPointer.block(op)["id"]))

    assert {:error, :source_pointer_not_observed} =
             SourceReturns.observe(
               c.repository,
               c.pull,
               c.owner,
               c.credential,
               op.link_id,
               op.id,
               c.connection["generation"]
             )
  end

  test "disconnect during source read stops activation before any mutation", c do
    first = queued(c, "disconnect-before-send")
    command(c.fixture, "hold-docs", "HOLDING_DOCS")
    worker = Task.async(fn -> SourceReturns.process(first["id"]) end)
    blocked(c.fixture, "BLOCKED_DOCUMENT")

    assert {:ok, _} =
             BarkparkConnections.disconnect(
               c.owner,
               c.credential,
               c.connection["generation"],
               "disconnect-journal"
             )

    Port.command(c.fixture, "release\n")
    Task.await(worker, 15_000)
    op = Repo.get!(SourceReturnOperation, first["id"])
    assert op.state == "stopped" && op.reason == "connection_changed"
    assert stats()["posts"] == []
  end

  test "known source reply is retained when originating connection disconnects during POST", c do
    first = queued(c, "disconnect-during-send")
    command(c.fixture, "hold-mutations", "HOLDING_MUTATIONS")
    worker = Task.async(fn -> SourceReturns.process(first["id"]) end)
    blocked(c.fixture, "BLOCKED_MUTATION")
    assert Repo.get!(SourceReturnOperation, first["id"]).state == "sending"

    assert {:ok, _} =
             BarkparkConnections.disconnect(
               c.owner,
               c.credential,
               c.connection["generation"],
               "disconnect-journal"
             )

    Port.command(c.fixture, "release\n")
    Task.await(worker, 15_000)
    op = Repo.get!(SourceReturnOperation, first["id"])
    assert op.state == "applied" && is_binary(op.source_transaction)
    assert op.source_identity["token_id"] == c.connection["source_identity"]["token_id"]
    assert length(stats()["posts"]) == 1
  end

  test "known reply survives native membership removal but journal reads are denied", c do
    first = queued(c, "revoke-during-send")
    command(c.fixture, "hold-mutations", "HOLDING_MUTATIONS")
    worker = Task.async(fn -> SourceReturns.process(first["id"]) end)
    blocked(c.fixture, "BLOCKED_MUTATION")

    Repo.delete_all(
      from m in Membership, where: m.user_id == ^c.owner.id and m.team == "linked-team"
    )

    Port.command(c.fixture, "release\n")
    Task.await(worker, 15_000)
    op = Repo.get!(SourceReturnOperation, first["id"])
    assert op.state == "applied" && is_binary(op.source_transaction)

    assert {:error, :source_operation_not_found} =
             SourceReturns.list(c.repository, c.pull, c.owner, c.credential, op.link_id)
  end

  test "interrupted sender leaves durable responsibility and expired attempt can observe it", c do
    first = queued(c, "interrupt-sender")
    command(c.fixture, "hold-mutations", "HOLDING_MUTATIONS")
    worker = Task.async(fn -> SourceReturns.process(first["id"]) end)
    blocked(c.fixture, "BLOCKED_MUTATION")
    op = Repo.get!(SourceReturnOperation, first["id"])
    assert op.state == "sending" && is_binary(op.payload_cipher)
    Task.shutdown(worker, :brutal_kill)
    Port.command(c.fixture, "release\n")
    assert eventually(fn -> length(stats()["receipts"]) == 1 end)
    # Expire the owned test lease explicitly; separate-VM recovery is a distinct proof.
    advance(op)
    SourceReturns.process(op.id)
    current = Repo.get!(SourceReturnOperation, op.id)
    assert current.state == "observed"
    assert current.source_transaction == nil
    assert length(stats()["posts"]) == 1
  end

  test "removed native generation stops queued source writes and keeps its journal", c do
    first = queued(c, "remove-before-send")
    op = Repo.get!(SourceReturnOperation, first["id"])

    assert {:ok, _} =
             SourceLinks.remove(
               c.repository,
               c.pull,
               c.owner,
               c.credential,
               op.link_id,
               op.link_generation,
               "remove-journal-link"
             )

    SourceReturns.process(op.id)
    assert Repo.get!(SourceReturnOperation, op.id).state == "stopped"
    assert stats()["posts"] == []

    assert {:ok, [_]} =
             SourceReturns.list(c.repository, c.pull, c.owner, c.credential, op.link_id)
  end

  test "independent source actor cannot write through the creator's connection", c do
    owner_intent = queued(c, "owner-return")
    owner_op = Repo.get!(SourceReturnOperation, owner_intent["id"])
    membership = Repo.get_by!(Membership, user_id: c.reader.id, team: "linked-team")
    Repo.update!(Ecto.Changeset.change(membership, role: "writer"))

    assert {:ok, intent} =
             SourceReturns.request(
               c.repository,
               c.pull,
               c.reader,
               c.reader_credential,
               owner_op.link_id,
               %{
                 "generation" => owner_op.link_generation,
                 "connection_generation" => c.reader_connection["generation"]
               },
               "reader-return"
             )

    SourceReturns.process(intent["id"])
    op = Repo.get!(SourceReturnOperation, intent["id"])
    assert op.state == "denied"
    assert op.actor_id == c.reader.id
    assert op.source_identity["token_id"] == c.reader_connection["source_identity"]["token_id"]
    assert stats()["posts"] == []
  end

  test "Paper transformation preserves unrelated content, refuses collisions and unsupported shapes",
       c do
    first = queued(c, "transform-return")
    op = Repo.get!(SourceReturnOperation, first["id"])

    document = %{
      "_id" => op.locator["document_id"],
      "_type" => "paper",
      "_rev" => "before",
      "purpose" => "Owner purpose",
      "blocks" => [%{"id" => "owner", "content" => "Owner content"}]
    }

    assert {:ok, bytes, "before"} = PaperReturnPointer.prepare(document, op)
    patch = Jason.decode!(bytes)["mutations"] |> hd() |> Map.fetch!("patch")
    assert patch["set"]["blocks"] |> hd() == hd(document["blocks"])
    assert Map.keys(patch["set"]) == ["blocks"]
    assert patch["ifRevisionID"] == "before"
    owned = PaperReturnPointer.block(op)
    assert {:ok, :present} = PaperReturnPointer.check(%{document | "blocks" => [owned]}, op)
    edited = Map.put(owned, "content", [%{"type" => "text", "value" => "Owner edited this"}])

    assert {:error, :pointer_conflict} =
             PaperReturnPointer.prepare(%{document | "blocks" => [edited]}, op)

    assert {:error, :pointer_conflict} =
             PaperReturnPointer.prepare(%{document | "blocks" => [owned, owned]}, op)

    assert {:error, :unsupported_paper} =
             PaperReturnPointer.prepare(%{document | "_id" => "foreign"}, op)

    assert {:error, :unsupported_paper} =
             PaperReturnPointer.prepare(%{document | "blocks" => "raw"}, op)
  end

  test "stale source read after lost reply reuses identical bytes/key and receives the original transaction",
       c do
    command(c.fixture, "journal-lost 1", "JOURNAL_LOST")
    first = queued(c, "exact-replay-return")
    SourceReturns.process(first["id"])
    op = Repo.get!(SourceReturnOperation, first["id"])
    original_tx = hd(stats()["receipts"])["transactionId"]
    assert op.state == "unknown"
    command(c.fixture, "journal-lost 0", "JOURNAL_LOST")
    command(c.fixture, "journal-stale 1", "JOURNAL_STALE")
    advance(op)
    SourceReturns.process(op.id)
    applied = Repo.get!(SourceReturnOperation, op.id)
    assert applied.state == "applied" && applied.source_transaction == original_tx
    assert applied.payload_cipher == nil
    [first_post, replay_post] = stats()["posts"]
    assert first_post == replay_post
    assert length(stats()["receipts"]) == 1
    assert length(stats()["documents"][c.params["document_id"]]["blocks"]) == 2
  end

  test "journal payload authentication cannot be opened as a credential or different operation",
       c do
    command(c.fixture, "journal-prewrite-lost 1", "JOURNAL_PREWRITE_LOST")
    first = queued(c, "cipher-return")
    SourceReturns.process(first["id"])
    op = Repo.get!(SourceReturnOperation, first["id"])

    binding = [
      "source-journal-payload-v1",
      op.id,
      op.actor_id,
      op.link_generation,
      op.connection_id,
      op.connection_generation,
      op.locator["origin"]
    ]

    assert {:ok, bytes} = ConnectionSecrets.open(op.payload_cipher, binding)
    assert Accounts.digest(bytes) == op.payload_digest
    assert bytes =~ "Unselected source content"

    assert {:error, :connection_secret_unavailable} =
             ConnectionSecrets.open(
               op.payload_cipher,
               [op.actor_id, op.connection_id, op.connection_generation, op.locator["origin"]]
             )

    assert {:error, :connection_secret_unavailable} =
             ConnectionSecrets.open(
               op.payload_cipher,
               [
                 "source-journal-payload-v1",
                 Ecto.UUID.generate(),
                 op.actor_id,
                 op.link_generation,
                 op.connection_id,
                 op.connection_generation,
                 op.locator["origin"]
               ]
             )
  end

  test "read-only service connection cannot queue a source write", c do
    {:ok, link} =
      SourceLinks.attach(c.repository, c.pull, c.owner, c.credential, c.params, "readonly-link")

    {:ok, current} =
      BarkparkConnections.connect(
        c.owner,
        c.credential,
        %{
          "token" => "synthetic-read-credential",
          "workspace" => "fixture-workspace",
          "project" => "default",
          "dataset" => "production",
          "expected_generation" => c.connection["generation"]
        },
        "readonly-connect"
      )

    assert current["source_identity"]["permissions"] == ["read"]

    assert {:error, :source_denied} =
             SourceReturns.request(
               c.repository,
               c.pull,
               c.owner,
               c.credential,
               link["id"],
               %{
                 "generation" => link["generation"],
                 "connection_generation" => current["generation"]
               },
               "readonly-return"
             )

    assert Repo.aggregate(SourceReturnOperation, :count) == 0
    assert stats()["posts"] == []
  end

  test "API status stays native-private and bounded while reader writes are refused", c do
    first = queued(c, "api-return")
    op = Repo.get!(SourceReturnOperation, first["id"])

    endpoint =
      "/api/repos/linked-team/linked-project/pulls/" <>
        c.pull.public_id <>
        "/links/" <> op.link_id <> "/return-pointers"

    response =
      build_conn()
      |> put_req_header("authorization", "Bearer " <> c.reader_token)
      |> get(endpoint)
      |> json_response(200)

    assert [%{"id" => id, "state" => "queued"}] = response["operations"]
    assert id == op.id
    refute Jason.encode!(response) =~ "locator"
    refute Jason.encode!(response) =~ "source_identity"
    refute Jason.encode!(response) =~ "payload"

    refused =
      build_conn()
      |> put_req_header("authorization", "Bearer " <> c.reader_token)
      |> put_req_header("idempotency-key", "reader-api-return")
      |> post(
        endpoint,
        %{
          "generation" => op.link_generation,
          "connection_generation" => c.reader_connection["generation"]
        }
      )

    assert json_response(refused, 403)["error"] == "authorization_changed"

    for link <- [op.link_id, Ecto.UUID.generate()] do
      url =
        "/api/repos/linked-team/linked-project/pulls/" <>
          c.pull.public_id <>
          "/links/" <> link <> "/return-pointers"

      denied =
        build_conn() |> put_req_header("authorization", "Bearer " <> c.outsider_token) |> get(url)

      assert json_response(denied, 404) == %{"error" => "source_operation_not_found"}
    end

    malformed =
      build_conn()
      |> put_req_header("authorization", "Bearer " <> c.token)
      |> get(String.replace(endpoint, op.link_id, "invalid-uuid"))

    assert json_response(malformed, 404) == %{"error" => "source_operation_not_found"}
  end

  test "automatic attempts pause visibly and an authorized retry keeps cumulative responsibility",
       c do
    first = queued(c, "paused-return")
    command(c.fixture, "doc-state 503", "DOC_STATE 503")

    for _ <- 1..5 do
      advance(Repo.get!(SourceReturnOperation, first["id"]))
      SourceReturns.process(first["id"])
    end

    op = Repo.get!(SourceReturnOperation, first["id"])
    assert op.state == "paused" && op.attempts == 5 && op.automatic_until == 5
    assert op.payload_cipher == nil && stats()["posts"] == []
    refute op.id in SourceReturns.pending_ids()

    assert {:ok, [public]} =
             SourceReturns.list(c.repository, c.pull, c.owner, c.credential, op.link_id)

    assert public["automatic_retry"] == false
    command(c.fixture, "doc-state 200", "DOC_STATE 200")

    params = %{
      "generation" => op.link_generation,
      "connection_generation" => op.connection_generation
    }

    assert {:ok, retry} =
             SourceReturns.retry(
               c.repository,
               c.pull,
               c.owner,
               c.credential,
               op.link_id,
               op.id,
               params
             )

    assert retry["id"] == op.id && retry["attempts"] == 5 && retry["automatic_retry"]

    assert {:ok, _} =
             SourceReturns.retry(
               c.repository,
               c.pull,
               c.owner,
               c.credential,
               op.link_id,
               op.id,
               params
             )

    assert Repo.get!(SourceReturnOperation, op.id).automatic_until == 10
    SourceReturns.process(op.id)
    applied = Repo.get!(SourceReturnOperation, op.id)
    assert applied.state == "applied" && applied.attempts == 6
    assert Repo.aggregate(SourceReturnOperation, :count) == 1
    assert length(stats()["posts"]) == 1
  end

  test "new native session or actor cannot substitute for revoked originating authority", c do
    first = queued(c, "origin-retry")
    op = Repo.get!(SourceReturnOperation, first["id"])
    Repo.update!(Ecto.Changeset.change(op, state: "paused", attempts: 5))
    Repo.update!(Ecto.Changeset.change(c.credential, revoked_at: Accounts.now()))
    {_, replacement} = Accounts.issue(c.owner, "session")

    params = %{
      "generation" => op.link_generation,
      "connection_generation" => op.connection_generation
    }

    assert {:error, :authorization_changed} =
             SourceReturns.retry(
               c.repository,
               c.pull,
               c.owner,
               replacement,
               op.link_id,
               op.id,
               params
             )

    membership = Repo.get_by!(Membership, user_id: c.reader.id, team: "linked-team")
    Repo.update!(Ecto.Changeset.change(membership, role: "writer"))

    assert {:error, :authorization_changed} =
             SourceReturns.retry(
               c.repository,
               c.pull,
               c.reader,
               c.reader_credential,
               op.link_id,
               op.id,
               params
             )

    assert Repo.get!(SourceReturnOperation, op.id).state == "paused"
    assert stats()["posts"] == []
  end

  test "independently authorized observer resolves presence after creator disconnect without inventing a write",
       c do
    command(c.fixture, "journal-lost 1", "JOURNAL_LOST")
    first = queued(c, "observer-return")
    SourceReturns.process(first["id"])
    op = Repo.get!(SourceReturnOperation, first["id"])
    assert op.state == "unknown"

    assert {:ok, _} =
             BarkparkConnections.disconnect(
               c.owner,
               c.credential,
               c.connection["generation"],
               "owner-disconnect"
             )

    {:ok, observer} =
      BarkparkConnections.connect(
        c.reader,
        c.reader_credential,
        %{
          "token" => "synthetic-second-credential",
          "workspace" => "fixture-workspace",
          "project" => "default",
          "dataset" => "production",
          "expected_generation" => c.reader_connection["generation"]
        },
        "observer-connect"
      )

    assert {:ok, value} =
             SourceReturns.observe(
               c.repository,
               c.pull,
               c.reader,
               c.reader_credential,
               op.link_id,
               op.id,
               observer["generation"]
             )

    assert value["state"] == "observed" && value["source_transaction"] == nil
    current = Repo.get!(SourceReturnOperation, op.id)
    assert current.source_identity == op.source_identity && current.actor_id == c.owner.id
    assert current.observation["actor_id"] == c.reader.id
    assert current.observation["source_token_id"] == observer["source_identity"]["token_id"]
    refute current.observation["source_token_id"] == current.source_identity["token_id"]
    assert current.payload_cipher == nil && length(stats()["posts"]) == 1
  end

  test "frontend address change stops a queued write before source mutation", c do
    first = queued(c, "frontend-origin-return")
    op = Repo.get!(SourceReturnOperation, first["id"])
    assert op.actor_label == c.owner.username

    assert op.destination ==
             Application.fetch_env!(:gitgood, :web_origin) <> "/changes/" <> c.pull.public_id

    Application.put_env(:gitgood, :web_origin, "http://localhost:59998")
    SourceReturns.process(op.id)
    stopped = Repo.get!(SourceReturnOperation, op.id)
    assert stopped.state == "stopped" && stopped.reason == "native_destination_changed"
    assert stats()["posts"] == []
  end

  defp queued(c, key) do
    {:ok, link} =
      SourceLinks.attach(c.repository, c.pull, c.owner, c.credential, c.params, "link-" <> key)

    {:ok, value} =
      SourceReturns.request(
        c.repository,
        c.pull,
        c.owner,
        c.credential,
        link["id"],
        %{
          "generation" => link["generation"],
          "connection_generation" => c.connection["generation"]
        },
        key
      )

    value
  end

  defp stats do
    {:ok, %{status: 200, body: body}} =
      Gitgood.BarkparkHTTP.get("/journal/stats", "synthetic-fixture-credential")

    body
  end

  defp advance(op),
    do:
      Repo.update!(
        Ecto.Changeset.change(op,
          next_at: DateTime.add(Accounts.now(), -1, :second),
          lease_until: nil
        )
      )

  defp command(fixture, value, ack) do
    Port.command(fixture, value <> "\n")
    blocked(fixture, ack)
  end

  defp blocked(fixture, ack) do
    receive do
      {^fixture, {:data, {:eol, ^ack}}} -> :ok
    after
      10_000 -> flunk("Owned source wire did not reach expected stage")
    end
  end

  defp eventually(check) do
    Enum.reduce_while(1..20, false, fn _, _ ->
      if check.(),
        do: {:halt, true},
        else:
          (
            Process.sleep(50)
            {:cont, false}
          )
    end)
  end
end
