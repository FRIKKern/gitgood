defmodule Gitgood.EvidenceTest do
  use GitgoodWeb.ConnCase, async: false
  import Ecto.Query

  alias Gitgood.{
    Accounts,
    BarkparkConnections,
    CriterionEvidence,
    CriterionEvidenceEvent,
    Evidence,
    Git,
    Membership,
    Pulls,
    Repo,
    SourceLinks
  }

  setup do
    saved =
      Map.new(
        [:barkpark_origin, :barkpark_allow_loopback_http, :connection_key],
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
        20_000 -> flunk("Evidence source fixture not ready")
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

    {:ok, owner} = Accounts.create_user("evidence-owner", "synthetic-password")
    {:ok, reader} = Accounts.create_user("evidence-reader", "synthetic-password")
    {:ok, outsider} = Accounts.create_user("evidence-outsider", "synthetic-password")
    Accounts.add_member(owner, "evidence-team", "owner")
    Accounts.add_member(reader, "evidence-team", "reader")
    Accounts.add_member(outsider, "outside-team", "owner")
    {token, credential} = Accounts.issue(owner, "session")
    {reader_token, reader_credential} = Accounts.issue(reader, "session")
    {_, outsider_credential} = Accounts.issue(outsider, "session")

    {:ok, repository} =
      Gitgood.Repositories.create(owner, "evidence-team", "project", "evidence-repo")

    on_exit(fn -> File.rm_rf!(Git.path(repository)) end)
    target = commit(repository, "base\n", nil)
    source = commit(repository, "feature\n", target)
    git(repository, ["update-ref", "refs/heads/main", target])
    git(repository, ["update-ref", "refs/heads/feature", source])

    {:ok, pull} =
      Pulls.create(
        repository,
        owner,
        credential,
        %{"source" => "feature", "title" => "Evidence fixture"},
        "evidence-pull"
      )

    params = %{
      "token" => "synthetic-fixture-credential",
      "workspace" => "fixture-workspace",
      "project" => "default",
      "dataset" => "production",
      "expected_generation" => "absent"
    }

    {:ok, connection} = BarkparkConnections.connect(owner, credential, params, "evidence-connect")

    {:ok, reader_connection} =
      BarkparkConnections.connect(reader, reader_credential, params, "reader-evidence-connect")

    {:ok, link} =
      SourceLinks.attach(
        repository,
        pull,
        owner,
        credential,
        %{
          "type" => "task",
          "document_id" => "evidence-task",
          "connection_generation" => connection["generation"]
        },
        "evidence-link"
      )

    c = %{
      repository: repository,
      pull: pull,
      owner: owner,
      reader: reader,
      outsider: outsider,
      credential: credential,
      reader_credential: reader_credential,
      outsider_credential: outsider_credential,
      token: token,
      reader_token: reader_token,
      connection: connection,
      reader_connection: reader_connection,
      link: link,
      source: source,
      target: target,
      fixture: fixture
    }

    {:ok, view} = view(c)
    artifact = "Synthetic reproducible report\n"

    Map.put(c, :params, %{
      "connection_generation" => connection["generation"],
      "link_generation" => link["generation"],
      "source_revision" => view["source"]["revision"],
      "criterion_index" => 0,
      "criterion_sha256" => hd(view["criteria"])["sha256"],
      "source_sha" => source,
      "target_sha" => target,
      "outcome" => "passed",
      "manifest" => %{
        "commands" => ["synthetic verifier --restore"],
        "environment" => %{"fixture" => "isolated Postgres and Git"},
        "producer" => "synthetic-verifier",
        "observed_at" => DateTime.to_iso8601(Accounts.now())
      },
      "artifact" => %{"name" => "report.txt", "content" => artifact, "sha256" => hash(artifact)}
    })
  end

  test "durable preparation encrypts original bytes and survives a fresh session", c do
    payload = %{"kind" => "attach", "body" => Jason.encode!(c.params)}
    assert {:ok, saved} = prepare(c, payload, "durable-reload")
    assert saved["state"] == "pending"
    row = Repo.get_by!(Gitgood.EvidenceIntent, public_id: saved["id"])

    cipher =
      Repo.one(
        from(i in Gitgood.EvidenceIntent, where: i.id == ^row.id, select: i.payload_cipher)
      )

    refute :binary.match(cipher, c.params["artifact"]["content"]) != :nomatch
    assert Gitgood.EvidenceIntents.recoverable_request?(%{row | payload_cipher: cipher})

    refute Gitgood.EvidenceIntents.recoverable_request?(%{
             row
             | payload_cipher: cipher,
               actor_id: c.reader.id
           })

    assert {:ok, %{"intents" => [^saved]}} = pending(c)
    assert {:ok, ^saved} = prepare(c, payload, "durable-reload")

    assert {:error, :idempotency_conflict} =
             prepare(
               c,
               Map.put(payload, "body", Jason.encode!(Map.put(c.params, "outcome", "failed"))),
               "durable-reload"
             )

    assert {:error, :evidence_intent_pending} = prepare(c, payload, "durable-second")
    {_, credential} = Accounts.issue(c.owner, "session")
    fresh = %{c | credential: credential}
    assert {:ok, receipt} = retry_intent(fresh, saved["id"])
    assert receipt["recorded"] == true
    assert {:ok, ^receipt} = retry_intent(fresh, saved["id"])
    assert {:ok, %{"intents" => [%{"id" => id, "state" => "confirmed"}]}} = pending(fresh)
    assert id == saved["id"]

    assert {:ok, %{"acknowledged" => true}} =
             Gitgood.EvidenceIntents.acknowledge(
               c.repository,
               c.pull,
               c.owner,
               credential,
               c.link["id"],
               id
             )

    assert {:ok, %{"intents" => []}} = pending(fresh)
    assert Repo.aggregate(CriterionEvidence, :count) == 1
    record = Repo.get_by!(CriterionEvidence, public_id: receipt["id"])
    assert record.credential_id == credential.id
    assert record.request_digest == Gitgood.Lease.digest(c.params)
  end

  test "durable replay resolves a pre-existing receipt during source outage", c do
    payload = %{"kind" => "attach", "body" => Jason.encode!(c.params)}
    {:ok, saved} = prepare(c, payload, "durable-lost-reply")
    {:ok, original} = attach(c, "durable-lost-reply")
    command(c, "doc-state 503", "DOC_STATE 503")
    assert {:ok, result} = retry_intent(c, saved["id"])
    assert result["id"] == original["id"]
    assert Repo.aggregate(CriterionEvidence, :count) == 1
    assert {:error, :evidence_source_unavailable} = download(c, original["id"])
  end

  test "opaque pending IDs are actor-only and current writer permission gates every transition",
       c do
    {:ok, saved} =
      prepare(c, %{"kind" => "attach", "body" => Jason.encode!(c.params)}, "durable-actor")

    other = %{c | owner: c.reader, credential: c.reader_credential}
    assert {:error, :authorization_changed} = pending(other)

    Repo.update_all(
      from(m in Membership, where: m.user_id == ^c.reader.id and m.team == "evidence-team"),
      set: [role: "writer"]
    )

    assert {:ok, %{"intents" => []}} = pending(other)
    assert {:error, :evidence_not_found} = retry_intent(other, saved["id"])
    assert {:error, :evidence_not_found} = retire_intent(other, saved["id"])
    Repo.delete_all(from(m in Membership, where: m.user_id == ^c.owner.id))
    assert {:error, :authorization_changed} = pending(c)
    assert {:error, :authorization_changed} = retry_intent(c, saved["id"])
    assert {:error, :authorization_changed} = retire_intent(c, saved["id"])
    assert Repo.aggregate(CriterionEvidence, :count) == 0
  end

  test "stale unapplied requests preserve original identity and can be safely retired", c do
    {:ok, saved} =
      prepare(c, %{"kind" => "attach", "body" => Jason.encode!(c.params)}, "durable-stale")

    command(c, "journal-owner-edit", "JOURNAL_OWNER_EDIT")
    assert {:error, :evidence_requirement_changed} = retry_intent(c, saved["id"])
    assert {:ok, %{"intents" => [^saved]}} = pending(c)
    assert {:ok, %{"retired" => true}} = retire_intent(c, saved["id"])
    assert {:error, :evidence_intent_retired} = retry_intent(c, saved["id"])
    assert Repo.aggregate(CriterionEvidence, :count) == 0
    {:ok, view} = view(c)
    updated = Map.put(c.params, "source_revision", view["source"]["revision"])

    {:ok, next} =
      prepare(c, %{"kind" => "attach", "body" => Jason.encode!(updated)}, "durable-new-revision")

    assert {:ok, %{"recorded" => true}} = retry_intent(c, next["id"])
  end

  test "a rotated connection refuses a saved draft without poisoning its enclosing transaction",
       c do
    {:ok, saved} =
      prepare(c, %{"kind" => "attach", "body" => Jason.encode!(c.params)}, "durable-rotated")

    {:ok, changed} =
      BarkparkConnections.connect(
        c.owner,
        c.credential,
        %{
          "token" => "synthetic-fixture-credential",
          "workspace" => "fixture-workspace",
          "project" => "default",
          "dataset" => "production",
          "expected_generation" => c.connection["generation"]
        },
        "durable-rotate-source"
      )

    refute changed["generation"] == c.connection["generation"]
    assert {:error, :connection_changed} = retry_intent(c, saved["id"])
    assert {:ok, %{"intents" => [^saved]}} = pending(c)
    assert Repo.aggregate(CriterionEvidence, :count) == 0
    assert {:ok, %{"retired" => true}} = retire_intent(c, saved["id"])
    assert {:error, :evidence_intent_retired} = retry_intent(c, saved["id"])
  end

  test "retirement confirms an already applied request and retains protected history", c do
    {:ok, saved} =
      prepare(
        c,
        %{"kind" => "attach", "body" => Jason.encode!(c.params)},
        "durable-retire-applied"
      )

    {:ok, original} = attach(c, "durable-retire-applied")
    assert {:ok, result} = retire_intent(c, saved["id"])
    assert result["id"] == original["id"]
    assert result["recorded"] == true
    assert {:ok, ^result} = retry_intent(c, saved["id"])
    assert Repo.aggregate(CriterionEvidence, :count) == 1
  end

  test "tampered encrypted intent cannot apply or retire its original responsibility", c do
    {:ok, saved} =
      prepare(c, %{"kind" => "attach", "body" => Jason.encode!(c.params)}, "durable-tamper")

    Repo.update_all(from(i in Gitgood.EvidenceIntent, where: i.public_id == ^saved["id"]),
      set: [payload_cipher: :crypto.strong_rand_bytes(64)]
    )

    assert {:error, :evidence_intent_unavailable} = retry_intent(c, saved["id"])
    assert {:error, :evidence_intent_unavailable} = retire_intent(c, saved["id"])
    assert {:ok, %{"intents" => [^saved]}} = pending(c)
    assert Repo.aggregate(CriterionEvidence, :count) == 0
  end

  test "withdrawal request resumes exactly once after losing its response", c do
    {:ok, attached} = attach(c, "durable-withdraw-template")

    payload = %{
      "kind" => "unavailable",
      "evidence_id" => attached["id"],
      "body" => Jason.encode!(%{"reason" => "Original reason"})
    }

    {:ok, saved} = prepare(c, payload, "durable-withdraw")
    assert {:ok, %{"artifact_unavailable_recorded" => true}} = retry_intent(c, saved["id"])
    assert {:ok, %{"artifact_unavailable_recorded" => true}} = retry_intent(c, saved["id"])
    assert Repo.aggregate(CriterionEvidenceEvent, :count) == 1
    assert Repo.one(CriterionEvidenceEvent).reason == "Original reason"
  end

  test "a stricter artifact profile retains exact legacy receipts and protected bytes", c do
    legacy_content = "Legacy text\0artifact\n"

    legacy_params =
      Map.put(c.params, "artifact", %{
        "name" => "legacy.txt",
        "content" => legacy_content,
        "sha256" => hash(legacy_content)
      })

    assert {:error, :invalid_evidence} = attach(c, "new-nul-refused", legacy_params)
    {:ok, template_receipt} = attach(c, "legacy-template")
    template = Repo.get_by!(CriterionEvidence, public_id: template_receipt["id"])

    # An upgrade fixture represents bytes accepted by the original UTF-8 profile.
    # Its actor, key and digest are canonical; no existing artifact is rewritten.
    legacy =
      %CriterionEvidence{}
      |> Ecto.Changeset.change(
        template
        |> Map.from_struct()
        |> Map.drop([:id, :__meta__])
        |> Map.merge(%{
          public_id: Ecto.UUID.generate(),
          creation_key: "legacy-exact-retry",
          request_digest: Gitgood.Lease.digest(legacy_params),
          artifact_name: "legacy.txt",
          artifact_content: legacy_content,
          artifact_size: byte_size(legacy_content),
          artifact_sha256: hash(legacy_content)
        })
      )
      |> Repo.insert!()

    receipt = %{"id" => legacy.public_id, "recorded" => true}
    assert {:ok, {metadata, ^legacy_content, _}} = download(c, legacy.public_id)
    assert metadata.artifact_sha256 == hash(legacy_content)
    assert {:ok, ^receipt} = attach(c, "legacy-exact-retry", legacy_params)

    command(c, "doc-state 503", "DOC_STATE 503")
    assert {:ok, ^receipt} = attach(c, "legacy-exact-retry", legacy_params)
    assert {:error, :idempotency_conflict} = attach(c, "legacy-exact-retry", c.params)
    assert {:error, :invalid_evidence} = attach(c, "new-nul-still-refused", legacy_params)
    assert Repo.aggregate(CriterionEvidence, :count) == 2

    Repo.delete_all(from(m in Membership, where: m.user_id == ^c.owner.id))
    assert {:error, :authorization_changed} = attach(c, "legacy-exact-retry", legacy_params)
  end

  test "NUL metadata and text artifacts are refused before database storage", c do
    for params <- [
          put_in(c.params, ["manifest", "commands"], ["command\0argument"]),
          put_in(c.params, ["manifest", "environment"], %{"fixture\0key" => "value"}),
          put_in(c.params, ["manifest", "producer"], "producer\0label"),
          Map.put(c.params, "source_revision", "revision\0value"),
          Map.put(c.params, "artifact", %{
            "name" => "nul.txt",
            "content" => "text\0value",
            "sha256" => hash("text\0value")
          })
        ] do
      assert {:error, :invalid_evidence} = attach(c, "nul-body", params)
    end

    assert Repo.aggregate(CriterionEvidence, :count) == 0
    {:ok, first} = attach(c, "valid-nul-test-template")

    endpoint =
      "/api/repos/evidence-team/project/pulls/#{c.pull.public_id}/links/#{c.link["id"]}/evidence/#{first["id"]}/unavailable"

    conn =
      build_conn()
      |> put_req_header("authorization", "Bearer " <> c.token)
      |> put_req_header("idempotency-key", "nul-reason")

    assert json_response(post(conn, endpoint, %{"reason" => "missing\0reason"}), 422)["error"] ==
             "invalid_evidence"

    assert Repo.aggregate(CriterionEvidenceEvent, :count) == 0
  end

  test "history pages retain every result without inheriting an older visible pass", c do
    {:ok, first} = attach(c, "history-template")
    template = Repo.get_by!(CriterionEvidence, public_id: first["id"])
    seed_records(c, template, 39)
    {:ok, final} = attach(c, "history-newest-failed", Map.put(c.params, "outcome", "failed"))
    newest = Repo.get_by!(CriterionEvidence, public_id: final["id"])

    assert {:ok, initial} = view(c)
    assert length(initial["records"]) == 20
    assert initial["history"]["total"] == 41
    assert hd(initial["criteria"])["state"] == "failed"
    assert hd(initial["records"])["id"] == newest.public_id
    assert {:ok, older} = view(c, initial["history"]["next_cursor"])
    assert length(older["records"]) == 20
    assert hd(older["criteria"])["state"] == "failed"
    assert Enum.all?(older["records"], &(&1["state"] == "passed"))
    assert {:ok, oldest} = view(c, older["history"]["next_cursor"])
    assert Enum.map(oldest["records"], & &1["id"]) == [first["id"]]
    assert oldest["history"]["next_cursor"] == nil
    assert hd(oldest["criteria"])["evidence_id"] == newest.public_id
    ids = Enum.map(initial["records"] ++ older["records"] ++ oldest["records"], & &1["id"])
    assert length(Enum.uniq(ids)) == 41
    assert Repo.aggregate(CriterionEvidence, :count) == 41
    assert Enum.all?(initial["records"], &(not Map.has_key?(&1["artifact"], "content")))

    {:ok, second_link} =
      SourceLinks.attach(
        c.repository,
        c.pull,
        c.owner,
        c.credential,
        %{
          "type" => "task",
          "document_id" => "other-evidence-task",
          "connection_generation" => c.connection["generation"]
        },
        "other-history-link"
      )

    assert {:error, :evidence_not_found} = view(%{c | link: second_link}, first["id"])
  end

  test "withdrawal event pages preserve old reasons and refuse cross-record cursors", c do
    {:ok, first} = attach(c, "events-template")

    assert {:ok, _} =
             Evidence.unavailable(
               c.repository,
               c.pull,
               c.owner,
               c.credential,
               c.link["id"],
               first["id"],
               "Original artifact missing",
               "event-template"
             )

    row = Repo.get_by!(CriterionEvidence, public_id: first["id"])
    event = Repo.one!(from(e in CriterionEvidenceEvent, where: e.evidence_id == ^row.id))
    attrs = event |> Map.from_struct() |> Map.drop([:id, :__meta__])

    Repo.insert_all(
      CriterionEvidenceEvent,
      for(
        index <- 1..26,
        do:
          Map.merge(attrs, %{
            reason: "Retained reason #{index}",
            request_key: "history-event-#{index}",
            request_digest:
              Gitgood.Lease.digest([
                "artifact_unavailable",
                first["id"],
                "Retained reason #{index}"
              ])
          })
      )
    )

    assert {:ok, initial} = view(c)
    record = hd(initial["records"])
    assert record["state"] == "unavailable"
    assert record["events_total"] == 27
    assert length(record["events"]) == 25
    assert hd(record["events"])["reason"] == "Original artifact missing"

    endpoint =
      "/api/repos/evidence-team/project/pulls/#{c.pull.public_id}/links/#{c.link["id"]}/evidence/#{first["id"]}/events"

    query = "?connection_generation=" <> c.connection["generation"]
    conn = build_conn() |> put_req_header("authorization", "Bearer " <> c.token)

    remaining =
      json_response(
        get(conn, endpoint <> query <> "&cursor=" <> record["events_next_cursor"]),
        200
      )

    assert Enum.map(remaining["events"], & &1["reason"]) == [
             "Retained reason 25",
             "Retained reason 26"
           ]

    assert remaining["next_cursor"] == nil
    assert remaining["total"] == 27

    {:ok, second} = attach(c, "different-events-template")

    assert {:ok, _} =
             Evidence.unavailable(
               c.repository,
               c.pull,
               c.owner,
               c.credential,
               c.link["id"],
               second["id"],
               "Another record",
               "other-event"
             )

    other = Repo.one!(from(e in CriterionEvidenceEvent, order_by: [desc: e.id], limit: 1))

    assert json_response(
             get(conn, endpoint <> query <> "&cursor=" <> Integer.to_string(other.id)),
             422
           )["error"] == "invalid_evidence_cursor"

    assert json_response(get(conn, endpoint <> query <> "&cursor=-1"), 422)["error"] ==
             "invalid_evidence_cursor"

    reader = build_conn() |> put_req_header("authorization", "Bearer " <> c.reader_token)
    reader_query = "?connection_generation=" <> c.reader_connection["generation"]
    assert length(json_response(get(reader, endpoint <> reader_query), 200)["events"]) == 25
    command(c, "doc-state 503", "DOC_STATE 503")

    assert json_response(get(conn, endpoint <> query), 503)["error"] ==
             "evidence_source_unavailable"

    Repo.delete_all(from(m in Membership, where: m.user_id == ^c.owner.id))
    assert json_response(get(conn, endpoint <> query), 404)["error"] == "evidence_not_found"
    assert Repo.aggregate(CriterionEvidenceEvent, :count) == 28
  end

  test "past fractional observation times are retained exactly while future times are refused",
       c do
    observation = DateTime.utc_now() |> DateTime.to_iso8601()
    params = put_in(c.params, ["manifest", "observed_at"], observation)
    assert {:ok, receipt} = attach(c, "fractional-observation", params)
    assert {:ok, recorded} = view(c)
    assert hd(recorded["records"])["id"] == receipt["id"]
    assert hd(recorded["records"])["manifest"]["observed_at"] == observation

    future = DateTime.utc_now() |> DateTime.add(10, :second) |> DateTime.to_iso8601()

    assert {:error, :invalid_evidence} =
             attach(
               c,
               "future-fractional-observation",
               put_in(params, ["manifest", "observed_at"], future)
             )

    assert Repo.aggregate(CriterionEvidence, :count) == 1
  end

  test "actual criteria remain absent despite upstream met and evidence claims; immutable result and artifact retries",
       c do
    assert {:ok, empty} = view(c)
    assert Enum.all?(empty["criteria"], &(&1["state"] == "absent"))
    refute Jason.encode!(empty) =~ "Upstream claim"
    assert {:ok, receipt} = attach(c, "attach-proof")
    assert {:ok, ^receipt} = attach(c, "attach-proof")
    assert Repo.aggregate(CriterionEvidence, :count) == 1
    assert {:ok, actual} = view(c)
    assert hd(actual["criteria"])["state"] == "passed"
    [record] = actual["records"]
    assert record["source_sha"] == c.source
    assert record["target_sha"] == c.target
    assert record["actor_id"] == c.owner.id
    refute Jason.encode!(actual) =~ "synthetic-fixture-credential"
    assert {:ok, {artifact, content, _}} = download(c, receipt["id"])
    assert artifact.artifact_sha256 == hash(content)
    assert content == c.params["artifact"]["content"]

    assert {:error, :idempotency_conflict} =
             attach(c, "attach-proof", %{c.params | "outcome" => "failed"})
  end

  test "newest failed and inconclusive evidence never fall back to an older pass", c do
    assert {:ok, _} = attach(c, "older-pass")
    assert {:ok, _} = attach(c, "new-failure", %{c.params | "outcome" => "failed"})
    assert {:ok, failed} = view(c)
    assert hd(failed["criteria"])["state"] == "failed"
    assert {:ok, _} = attach(c, "new-inconclusive", %{c.params | "outcome" => "inconclusive"})
    assert {:ok, inconclusive} = view(c)
    assert hd(inconclusive["criteria"])["state"] == "inconclusive"
    assert length(inconclusive["records"]) == 3
  end

  test "requirement revision and criterion edits make evidence stale without rewriting history",
       c do
    {:ok, _} = attach(c, "before-requirement")
    original = Repo.one!(CriterionEvidence)
    command(c, "journal-owner-edit", "JOURNAL_OWNER_EDIT")
    assert {:ok, stale} = view(c)
    assert hd(stale["criteria"])["state"] == "stale"
    assert {:error, :evidence_requirement_changed} = attach(c, "old-requirement")
    assert {:ok, _} = attach(c, "before-requirement")
    refreshed = refresh_params(c, stale)
    assert {:ok, _} = attach(c, "reassessment", refreshed)
    command(c, "evidence-criterion-change", "EVIDENCE_CRITERION_CHANGE")
    assert {:ok, changed} = view(c)
    assert hd(changed["criteria"])["state"] == "stale"
    assert Repo.get!(CriterionEvidence, original.id) == original
  end

  test "both Git branch revisions are bound and mismatched attach refuses", c do
    {:ok, _} = attach(c, "before-code")
    next = commit(c.repository, "another feature\n", c.source)
    git(c.repository, ["update-ref", "refs/heads/feature", next])
    assert {:ok, source_changed} = view(c)
    assert hd(source_changed["criteria"])["state"] == "stale"
    assert {:error, :evidence_revision_changed} = attach(c, "wrong-code")
    assert {:ok, _} = attach(c, "source-reassessment", refresh_params(c, source_changed))
    git(c.repository, ["update-ref", "refs/heads/main", c.source])
    assert {:ok, target_changed} = view(c)
    assert hd(target_changed["criteria"])["state"] == "stale"
  end

  test "unavailable artifact adds retained events, denies download and requires another result",
       c do
    {:ok, first} = attach(c, "before-unavailable")
    original = Repo.one!(CriterionEvidence)

    assert {:ok, unavailable} =
             Evidence.unavailable(
               c.repository,
               c.pull,
               c.owner,
               c.credential,
               c.link["id"],
               first["id"],
               "Artifact withdrawn by producer",
               "artifact-unavailable"
             )

    assert {:ok, ^unavailable} =
             Evidence.unavailable(
               c.repository,
               c.pull,
               c.owner,
               c.credential,
               c.link["id"],
               first["id"],
               "Artifact withdrawn by producer",
               "artifact-unavailable"
             )

    assert Repo.aggregate(CriterionEvidenceEvent, :count) == 1
    assert {:ok, view} = view(c)
    assert hd(view["criteria"])["state"] == "unavailable"
    assert hd(view["records"])["artifact"]["sha256"] == original.artifact_sha256
    assert {:error, :evidence_artifact_unavailable} = download(c, first["id"])
    assert Repo.get!(CriterionEvidence, original.id) == original
    assert {:ok, _} = attach(c, "after-unavailable")
    assert {:ok, reassessed} = view(c)
    assert hd(reassessed["criteria"])["state"] == "passed"
    assert length(reassessed["records"]) == 2
  end

  test "native reader can read with own source access but cannot attach, retire or borrow owner source permission",
       c do
    {:ok, first} = attach(c, "permission-proof")

    assert {:ok, {_, _, _}} =
             Evidence.download(
               c.repository,
               c.pull,
               c.reader,
               c.reader_credential,
               c.link["id"],
               first["id"],
               c.reader_connection["generation"]
             )

    assert {:error, :authorization_changed} =
             Evidence.attach(
               c.repository,
               c.pull,
               c.reader,
               c.reader_credential,
               c.link["id"],
               c.params,
               "reader-write"
             )

    assert {:error, :authorization_changed} =
             Evidence.unavailable(
               c.repository,
               c.pull,
               c.reader,
               c.reader_credential,
               c.link["id"],
               first["id"],
               "Reader refusal",
               "reader-retire"
             )

    {:ok, denied} =
      BarkparkConnections.connect(
        c.reader,
        c.reader_credential,
        %{
          "token" => "synthetic-outsider-credential",
          "workspace" => "fixture-workspace",
          "project" => "default",
          "dataset" => "production",
          "expected_generation" => c.reader_connection["generation"]
        },
        "deny-reader-source"
      )

    assert {:ok, hidden} =
             Evidence.list(
               c.repository,
               c.pull,
               c.reader,
               c.reader_credential,
               c.link["id"],
               denied["generation"]
             )

    assert hidden["records"] == []
    assert hidden["criteria"] == []
    assert hidden["source"]["source_state"] == "denied"

    assert {:error, :evidence_source_unavailable} =
             Evidence.download(
               c.repository,
               c.pull,
               c.reader,
               c.reader_credential,
               c.link["id"],
               first["id"],
               denied["generation"]
             )

    assert {:error, :source_link_not_found} =
             Evidence.list(
               c.repository,
               c.pull,
               c.outsider,
               c.outsider_credential,
               c.link["id"],
               c.connection["generation"]
             )
  end

  test "source outage or deletion hides records while exact creation retry retains receipt", c do
    {:ok, first} = attach(c, "outage-proof")

    for status <- [503, 404] do
      command(c, "doc-state #{status}", "DOC_STATE #{status}")
      assert {:ok, hidden} = view(c)
      assert hidden["records"] == []
      assert {:ok, ^first} = attach(c, "outage-proof")
      assert {:error, :evidence_requirement_changed} = attach(c, "new-during-#{status}")
    end

    assert Repo.aggregate(CriterionEvidence, :count) == 1
    command(c, "doc-state 200", "DOC_STATE 200")
    assert {:ok, available} = view(c)
    assert hd(available["criteria"])["state"] == "passed"
  end

  test "body digest, time, field ownership and artifact bounds fail before storage", c do
    for invalid <- [
          put_in(c.params, ["artifact", "sha256"], String.duplicate("0", 64)),
          put_in(c.params, ["artifact", "name"], "../escape.txt"),
          Map.put(c.params, "actor_id", c.reader.id),
          put_in(c.params, ["manifest", "observed_at"], "2999-01-01T00:00:00Z"),
          put_in(c.params, ["artifact", "content"], String.duplicate("x", 65537))
        ] do
      assert {:error, :invalid_evidence} = attach(c, "invalid-proof", invalid)
    end

    assert Repo.aggregate(CriterionEvidence, :count) == 0
  end

  test "disconnect while source read is held prevents evidence insertion", c do
    fixture = c.fixture
    Port.command(fixture, "hold-docs\n")
    assert_receive {^fixture, {:data, {:eol, "HOLDING_DOCS"}}}, 4000
    task = Task.async(fn -> attach(c, "held-evidence") end)
    assert_receive {^fixture, {:data, {:eol, "BLOCKED_DOCUMENT"}}}, 4000

    assert {:ok, _} =
             BarkparkConnections.disconnect(
               c.owner,
               c.credential,
               c.connection["generation"],
               "disconnect-evidence"
             )

    Port.command(fixture, "release\n")
    assert {:error, :connection_changed} = Task.await(task, 8000)
    assert Repo.aggregate(CriterionEvidence, :count) == 0
  end

  test "actual API exposes attachment downloads and refuses membership loss", c do
    {:ok, first} = attach(c, "api-evidence")

    endpoint =
      "/api/repos/evidence-team/project/pulls/#{c.pull.public_id}/links/#{c.link["id"]}/evidence"

    connection = "?connection_generation=" <> c.connection["generation"]
    conn = build_conn() |> put_req_header("authorization", "Bearer " <> c.token)
    assert json_response(get(conn, endpoint <> connection), 200)["records"] |> length() == 1
    downloaded = get(conn, endpoint <> "/#{first["id"]}/download" <> connection)
    assert downloaded.status == 200
    assert downloaded.resp_body == c.params["artifact"]["content"]
    assert get_resp_header(downloaded, "x-gitgood-sha256") == [c.params["artifact"]["sha256"]]

    assert get_resp_header(downloaded, "content-disposition") == [
             ~s(attachment; filename="report.txt")
           ]

    Repo.delete_all(from m in Membership, where: m.user_id == ^c.owner.id)
    assert json_response(get(conn, endpoint <> connection), 404)["error"] == "evidence_not_found"
  end

  defp prepare(c, payload, key),
    do:
      Gitgood.EvidenceIntents.prepare(
        c.repository,
        c.pull,
        c.owner,
        c.credential,
        c.link["id"],
        payload,
        key
      )

  defp pending(c),
    do: Gitgood.EvidenceIntents.pending(c.repository, c.pull, c.owner, c.credential, c.link["id"])

  defp retry_intent(c, id),
    do:
      Gitgood.EvidenceIntents.retry(c.repository, c.pull, c.owner, c.credential, c.link["id"], id)

  defp retire_intent(c, id),
    do:
      Gitgood.EvidenceIntents.retire(
        c.repository,
        c.pull,
        c.owner,
        c.credential,
        c.link["id"],
        id
      )

  defp view(c),
    do:
      Evidence.list(
        c.repository,
        c.pull,
        c.owner,
        c.credential,
        c.link["id"],
        c.connection["generation"]
      )

  defp attach(c, key, params \\ nil),
    do:
      Evidence.attach(
        c.repository,
        c.pull,
        c.owner,
        c.credential,
        c.link["id"],
        params || c.params,
        key
      )

  defp view(c, cursor),
    do:
      Evidence.list(
        c.repository,
        c.pull,
        c.owner,
        c.credential,
        c.link["id"],
        c.connection["generation"],
        cursor
      )

  defp seed_records(c, template, count) do
    attrs = template |> Map.from_struct() |> Map.drop([:id, :__meta__])

    Repo.insert_all(
      CriterionEvidence,
      for(
        index <- 1..count,
        do:
          Map.merge(attrs, %{
            public_id: Ecto.UUID.generate(),
            creation_key: "seed-history-#{index}",
            artifact_content: c.params["artifact"]["content"]
          })
      )
    )
  end

  defp download(c, id),
    do:
      Evidence.download(
        c.repository,
        c.pull,
        c.owner,
        c.credential,
        c.link["id"],
        id,
        c.connection["generation"]
      )

  defp hash(content), do: Base.encode16(:crypto.hash(:sha256, content), case: :lower)

  defp refresh_params(c, view),
    do:
      Map.merge(c.params, %{
        "source_revision" => view["source"]["revision"],
        "source_sha" => view["source_sha"],
        "target_sha" => view["target_sha"],
        "criterion_sha256" => hd(view["criteria"])["sha256"]
      })

  defp command(c, command, expected) do
    fixture = c.fixture
    Port.command(fixture, command <> "\n")
    assert_receive {^fixture, {:data, {:eol, ^expected}}}, 4000
  end

  defp git(repository, args, input \\ "") do
    assert {output, 0} = Git.run(["--git-dir", Git.path(repository) | args], input: input)
    String.trim(output)
  end

  defp commit(repository, text, parent) do
    blob = git(repository, ["hash-object", "-w", "--stdin"], text)
    tree = git(repository, ["mktree"], "100644 blob #{blob}\tREADME.md\n")

    args = [
      "-c",
      "user.name=Fixture",
      "-c",
      "user.email=fixture@example.invalid",
      "commit-tree",
      tree
    ]

    git(
      repository,
      if(parent, do: args ++ ["-p", parent], else: args),
      "Fixture evidence commit\n"
    )
  end
end
