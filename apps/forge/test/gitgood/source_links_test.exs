defmodule Gitgood.SourceLinksTest do
  use GitgoodWeb.ConnCase, async: false

  alias Gitgood.{
    Accounts,
    BarkparkConnections,
    Membership,
    PullRequest,
    Repo,
    Repository,
    SourceLink,
    SourceLinkEvent,
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

  test "attach stores exact provenance and opaque listing, retries and duplicate identity remain singular",
       c do
    assert {:ok, first} = attach(c, "attach-first")
    assert {:ok, ^first} = attach(c, "attach-first")
    assert {:ok, ^first} = attach(c, "attach-again")
    assert Repo.aggregate(SourceLink, :count) == 1
    assert Repo.aggregate(SourceLinkEvent, :count) == 2
    link = Repo.get!(SourceLink, first["id"])
    assert link.locator["document_id"] == "drafts.private-spec"
    assert link.locator["workspace_id"] == c.connection["source_identity"]["workspace_id"]
    assert link.verified_revision == "fixture-revision"
    assert link.actor_id == c.owner.id
    assert link.source_identity["token_id"] == c.connection["source_identity"]["token_id"]
    event = Repo.get_by!(SourceLinkEvent, request_key: "attach-again")
    assert event.actor_id == c.owner.id
    assert event.source_actor["generation"] == c.connection["generation"]
    assert event.source_actor["source_identity"]["token_id"] == link.source_identity["token_id"]
    refute inspect(link) =~ "Private source specification"
    refute inspect(event) =~ "synthetic-fixture-credential"
    assert {:ok, [^first]} = SourceLinks.list(c.repository, c.pull, c.reader, c.reader_credential)
    assert Enum.sort(Map.keys(first)) == ["generation", "id", "state"]

    assert {:error, :idempotency_conflict} =
             SourceLinks.attach(
               c.repository,
               c.pull,
               c.owner,
               c.credential,
               %{c.params | "document_id" => "another-spec"},
               "attach-first"
             )
  end

  test "viewer source actor authorizes independently; source refusal never borrows creator access",
       c do
    {:ok, link} = attach(c, "attach-first")

    assert {:ok, allowed} =
             SourceLinks.read(
               c.repository,
               c.pull,
               c.owner,
               c.credential,
               link["id"],
               c.connection["generation"]
             )

    assert c.connection["source_identity"]["token_id"] !=
             c.reader_connection["source_identity"]["token_id"]

    assert allowed["source_state"] == "available"
    assert allowed["title"] == "Private source specification"
    assert allowed["summary"] == "Source owns this intention."
    assert allowed["studio_url"] =~ "/studio/open/paper/drafts.private-spec"
    refute Jason.encode!(allowed) =~ "Unselected source content"

    assert {:ok, denied} =
             SourceLinks.read(
               c.repository,
               c.pull,
               c.reader,
               c.reader_credential,
               link["id"],
               c.reader_connection["generation"]
             )

    assert denied == Map.put(link, "source_state", "denied")

    assert {:ok, changed} =
             SourceLinks.read(
               c.repository,
               c.pull,
               c.reader,
               c.reader_credential,
               link["id"],
               c.connection["generation"]
             )

    assert changed == Map.put(link, "source_state", "connection_changed")

    assert {:error, :source_link_not_found} =
             SourceLinks.read(
               c.repository,
               c.pull,
               c.outsider,
               c.outsider_credential,
               link["id"],
               c.connection["generation"]
             )

    assert {:error, :authorization_changed} =
             SourceLinks.attach(
               c.repository,
               c.pull,
               c.reader,
               c.reader_credential,
               %{c.params | "connection_generation" => c.reader_connection["generation"]},
               "reader-attach"
             )
  end

  test "remove tombstones and historical attach replay cannot reactivate; explicit fresh attach can",
       c do
    {:ok, first} = attach(c, "attach-first")

    assert {:ok, removed} =
             SourceLinks.remove(
               c.repository,
               c.pull,
               c.owner,
               c.credential,
               first["id"],
               first["generation"],
               "remove-first"
             )

    assert removed["state"] == "removed"
    assert removed["generation"] != first["generation"]

    assert {:ok, ^removed} =
             SourceLinks.remove(
               c.repository,
               c.pull,
               c.owner,
               c.credential,
               first["id"],
               first["generation"],
               "remove-first"
             )

    assert {:ok, ^first} = attach(c, "attach-first")
    assert Repo.get!(SourceLink, first["id"]).state == "removed"

    assert {:ok, %{"source_state" => "removed"}} =
             SourceLinks.read(c.repository, c.pull, c.owner, c.credential, first["id"], nil)

    assert {:ok, reactivated} = attach(c, "attach-fresh")
    assert reactivated["id"] == first["id"]
    assert reactivated["generation"] not in [first["generation"], removed["generation"]]

    assert {:error, :source_link_changed} =
             SourceLinks.remove(
               c.repository,
               c.pull,
               c.owner,
               c.credential,
               first["id"],
               first["generation"],
               "remove-stale"
             )

    assert Repo.aggregate(SourceLink, :count) == 1
  end

  test "denied, missing, unavailable and wrong document identities do not create native links",
       c do
    for {id, reason} <- [
          {"denied-document", :source_denied},
          {"missing-document", :source_missing_or_inaccessible},
          {"unavailable-document", :source_unavailable},
          {"wrong-identity", :source_contract_unavailable}
        ] do
      assert {:error, ^reason} =
               SourceLinks.attach(
                 c.repository,
                 c.pull,
                 c.owner,
                 c.credential,
                 %{c.params | "document_id" => id},
                 "attach-" <> id
               )
    end

    assert Repo.aggregate(SourceLink, :count) == 0
    assert Repo.aggregate(SourceLinkEvent, :count) == 0

    for params <- [
          Map.put(c.params, "origin", "https://attacker.invalid"),
          %{c.params | "document_id" => "../secret"},
          %{c.params | "type" => "user"}
        ] do
      assert {:error, :invalid_source_link} =
               SourceLinks.attach(
                 c.repository,
                 c.pull,
                 c.owner,
                 c.credential,
                 params,
                 "bad-input"
               )
    end
  end

  test "source reply held through connection disconnect is discarded", c do
    {:ok, link} = attach(c, "attach-first")
    hold(c)

    task =
      Task.async(fn ->
        SourceLinks.read(
          c.repository,
          c.pull,
          c.owner,
          c.credential,
          link["id"],
          c.connection["generation"]
        )
      end)

    fixture = c.fixture
    assert_receive {^fixture, {:data, {:eol, "BLOCKED_DOCUMENT"}}}, 4000

    assert {:ok, _} =
             BarkparkConnections.disconnect(
               c.owner,
               c.credential,
               c.connection["generation"],
               "disconnect-held"
             )

    Port.command(fixture, "release\n")
    assert {:ok, denied} = Task.await(task, 8000)
    assert denied == Map.put(link, "source_state", "connection_changed")

    assert {:error, :connection_changed} =
             SourceLinks.guard(
               c.repository,
               c.pull,
               c.owner,
               c.credential,
               link["id"],
               link["generation"],
               c.connection["generation"]
             )

    assert {:ok, ^link} = attach(c, "attach-first")
    assert Repo.aggregate(SourceLink, :count) == 1
  end

  test "native permission removed while source read is held cannot release private context", c do
    {:ok, link} = attach(c, "attach-first")
    hold(c)

    task =
      Task.async(fn ->
        SourceLinks.read(
          c.repository,
          c.pull,
          c.owner,
          c.credential,
          link["id"],
          c.connection["generation"]
        )
      end)

    fixture = c.fixture
    assert_receive {^fixture, {:data, {:eol, "BLOCKED_DOCUMENT"}}}, 4000
    Repo.get_by!(Membership, user_id: c.owner.id, team: "linked-team") |> Repo.delete!()
    Port.command(fixture, "release\n")
    assert {:error, :source_link_not_found} = Task.await(task, 8000)
    assert {:error, :authorization_changed} = attach(c, "attach-first")
  end

  test "HTTP exposes source context only to both owners, uses no-store and rejects foreign and absent links equally",
       c do
    base = "/api/repos/linked-team/linked-project/pulls/" <> c.pull.public_id <> "/links"

    owner = fn ->
      build_conn()
      |> put_req_header("authorization", "Bearer " <> c.token)
      |> put_req_header("idempotency-key", "http-attach")
    end

    attached = owner.() |> post(base, c.params) |> json_response(200)
    assert owner.() |> get(base) |> json_response(200) == %{"links" => [attached]}

    response =
      owner.()
      |> get(base <> "/" <> attached["id"], %{
        "connection_generation" => c.connection["generation"]
      })

    assert json_response(response, 200)["source_state"] == "available"
    assert get_resp_header(response, "cache-control") == ["no-store"]
    reader = build_conn() |> put_req_header("authorization", "Bearer " <> c.reader_token)

    denied =
      reader
      |> get(base <> "/" <> attached["id"], %{
        "connection_generation" => c.reader_connection["generation"]
      })
      |> json_response(200)

    assert denied == Map.put(attached, "source_state", "denied")

    for id <- [attached["id"], Ecto.UUID.generate()] do
      outsider = build_conn() |> put_req_header("authorization", "Bearer " <> c.outsider_token)

      assert outsider |> get(base <> "/" <> id) |> json_response(404) == %{
               "error" => "source_link_not_found"
             }
    end

    cookie = build_conn() |> put_req_cookie("gitgood_session", c.token)
    assert cookie |> post(base, c.params) |> json_response(403) == %{"error" => "csrf_required"}
  end

  test "source outage and missing records retain native access and recover without new link writes",
       c do
    {:ok, link} = attach(c, "attach-first")
    fixture = c.fixture

    for {status, state} <- [
          {503, "unavailable"},
          {404, "missing_or_inaccessible"},
          {403, "denied"}
        ] do
      Port.command(fixture, "doc-state #{status}\n")
      expected = "DOC_STATE #{status}"
      assert_receive {^fixture, {:data, {:eol, ^expected}}}, 4000

      assert {:ok, refused} =
               SourceLinks.read(
                 c.repository,
                 c.pull,
                 c.owner,
                 c.credential,
                 link["id"],
                 c.connection["generation"]
               )

      assert refused == Map.put(link, "source_state", state)
      assert {:ok, [^link]} = SourceLinks.list(c.repository, c.pull, c.owner, c.credential)
    end

    Port.command(fixture, "doc-state 200\n")
    assert_receive {^fixture, {:data, {:eol, "DOC_STATE 200"}}}, 4000

    assert {:ok, %{"source_state" => "available"}} =
             SourceLinks.read(
               c.repository,
               c.pull,
               c.owner,
               c.credential,
               link["id"],
               c.connection["generation"]
             )

    assert Repo.aggregate(SourceLink, :count) == 1
    assert Repo.aggregate(SourceLinkEvent, :count) == 1
  end

  test "disconnect while attachment source verification is held prevents native activation", c do
    hold(c)
    task = Task.async(fn -> attach(c, "held-attach") end)
    fixture = c.fixture
    assert_receive {^fixture, {:data, {:eol, "BLOCKED_DOCUMENT"}}}, 4000

    assert {:ok, _} =
             BarkparkConnections.disconnect(
               c.owner,
               c.credential,
               c.connection["generation"],
               "disconnect-attach"
             )

    Port.command(fixture, "release\n")
    assert {:error, :connection_changed} = Task.await(task, 8000)
    assert Repo.aggregate(SourceLink, :count) == 0
    assert Repo.aggregate(SourceLinkEvent, :count) == 0
  end

  defp attach(c, key),
    do: SourceLinks.attach(c.repository, c.pull, c.owner, c.credential, c.params, key)

  defp hold(c) do
    fixture = c.fixture
    Port.command(fixture, "hold-docs\n")
    assert_receive {^fixture, {:data, {:eol, "HOLDING_DOCS"}}}, 4000
  end
end
