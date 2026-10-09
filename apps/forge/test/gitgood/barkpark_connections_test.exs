defmodule Gitgood.BarkparkConnectionsTest do
  use GitgoodWeb.ConnCase, async: false

  alias Gitgood.{
    Accounts,
    BarkparkConnection,
    BarkparkConnectionEvent,
    BarkparkConnections,
    ConnectionSecrets,
    Repo
  }

  @token "synthetic-fixture-credential"

  setup do
    saved =
      Map.new(
        [:barkpark_origin, :barkpark_allow_loopback_http, :connection_key],
        &{&1, Application.get_env(:gitgood, &1)}
      )

    python = System.find_executable(Application.fetch_env!(:gitgood, :python_executable))
    openssl = System.find_executable(System.get_env("GITGOOD_OPENSSL", "openssl"))
    assert is_binary(openssl)

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
        20_000 -> flunk("Connection wire fixture not ready")
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

    {:ok, owner} = Accounts.create_user("connection-owner", "synthetic-password")
    {:ok, other} = Accounts.create_user("connection-other", "synthetic-password")
    {session_token, credential} = Accounts.issue(owner, "session")
    {_, other_credential} = Accounts.issue(other, "session")

    params = %{
      "token" => @token,
      "workspace" => "fixture-workspace",
      "project" => "default",
      "dataset" => "production",
      "expected_generation" => "absent"
    }

    %{
      owner: owner,
      other: other,
      credential: credential,
      other_credential: other_credential,
      session_token: session_token,
      fixture: fixture,
      params: params
    }
  end

  test "source-verified identity and randomized actor-bound encrypted credential survive exact retries",
       c do
    assert {:ok, first} =
             BarkparkConnections.connect(c.owner, c.credential, c.params, "connect-first")

    assert first["state"] == "connected"
    assert first["source_identity"]["token_id"] == "d6c87ac9-f908-4b7b-9d14-f1c0e359fb47"
    refute Jason.encode!(first) =~ @token
    row = Repo.get_by!(BarkparkConnection, user_id: c.owner.id)
    refute row.token_cipher =~ @token
    refute inspect(row) =~ row.token_cipher
    binding = [c.owner.id, row.id, row.generation, row.origin]
    assert {:ok, @token} = ConnectionSecrets.open(row.token_cipher, binding)

    assert {:error, :connection_secret_unavailable} =
             ConnectionSecrets.open(row.token_cipher, [
               c.other.id,
               row.id,
               row.generation,
               row.origin
             ])

    assert {:ok, second_cipher} = ConnectionSecrets.seal(@token, binding)
    refute row.token_cipher == second_cipher

    assert {:ok, ^first} =
             BarkparkConnections.connect(c.owner, c.credential, c.params, "connect-first")

    assert Repo.aggregate(BarkparkConnectionEvent, :count) == 1

    assert {:error, :idempotency_conflict} =
             BarkparkConnections.connect(
               c.owner,
               c.credential,
               %{c.params | "token" => "synthetic-other-credential"},
               "connect-first"
             )

    assert {:ok, %{"state" => "unconfigured"}} =
             BarkparkConnections.show(c.other, c.other_credential)

    assert {:error, :authorization_changed} = BarkparkConnections.show(c.other, c.credential)
  end

  test "rotation uses current generation and disconnect removes secret without replay resurrection",
       c do
    {:ok, first} = BarkparkConnections.connect(c.owner, c.credential, c.params, "connect-first")

    rotated = %{
      c.params
      | "expected_generation" => first["generation"],
        "token" => "synthetic-next-credential"
    }

    assert {:ok, second} =
             BarkparkConnections.connect(c.owner, c.credential, rotated, "connect-rotate")

    refute first["generation"] == second["generation"]

    assert {:error, :connection_changed} =
             BarkparkConnections.connect(c.owner, c.credential, rotated, "connect-stale")

    assert {:ok, gone} =
             BarkparkConnections.disconnect(
               c.owner,
               c.credential,
               second["generation"],
               "disconnect-first"
             )

    assert gone["state"] == "disconnected"
    assert is_nil(Repo.get_by!(BarkparkConnection, user_id: c.owner.id).token_cipher)

    assert {:ok, ^first} =
             BarkparkConnections.connect(c.owner, c.credential, c.params, "connect-first")

    assert {:ok, ^gone} = BarkparkConnections.show(c.owner, c.credential)

    assert {:ok, ^gone} =
             BarkparkConnections.disconnect(
               c.owner,
               c.credential,
               second["generation"],
               "disconnect-first"
             )

    assert Repo.aggregate(BarkparkConnectionEvent, :count) == 3
  end

  test "unsupported scope, privileged source and outage never change a current connection", c do
    {:ok, first} = BarkparkConnections.connect(c.owner, c.credential, c.params, "connect-first")
    params = %{c.params | "expected_generation" => first["generation"]}

    assert {:error, :barkpark_scope_denied} =
             BarkparkConnections.connect(
               c.owner,
               c.credential,
               %{params | "workspace" => "foreign-workspace"},
               "connect-foreign"
             )

    assert {:error, :barkpark_scope_denied} =
             BarkparkConnections.connect(
               c.owner,
               c.credential,
               %{params | "token" => "synthetic-broad-credential"},
               "connect-broad"
             )

    assert {:error, :barkpark_unavailable} =
             BarkparkConnections.connect(
               c.owner,
               c.credential,
               %{params | "token" => "synthetic-unavailable-credential"},
               "connect-outage"
             )

    assert {:ok, ^first} = BarkparkConnections.show(c.owner, c.credential)
    assert Repo.aggregate(BarkparkConnectionEvent, :count) == 1
    Application.delete_env(:gitgood, :connection_key)

    assert {:error, :connection_key_unconfigured} =
             BarkparkConnections.connect(c.owner, c.credential, params, "connect-no-key")
  end

  test "disconnect wins over a parked external read; the private response is discarded", c do
    {:ok, first} = BarkparkConnections.connect(c.owner, c.credential, c.params, "connect-first")

    task =
      Task.async(fn ->
        BarkparkConnections.read(c.owner, c.credential, first["generation"], "/blocked")
      end)

    fixture = c.fixture
    assert_receive {^fixture, {:data, {:eol, "BLOCKED"}}}, 4000

    assert {:ok, %{"state" => "disconnected"}} =
             BarkparkConnections.disconnect(
               c.owner,
               c.credential,
               first["generation"],
               "disconnect-held"
             )

    Port.command(fixture, "release\n")
    assert {:error, :connection_changed} = Task.await(task, 6000)

    assert {:error, :connection_changed} =
             BarkparkConnections.read(c.owner, c.credential, first["generation"], "/ok")
  end

  test "revoked and repository-scoped sessions cannot manage or replay external credentials", c do
    {:ok, first} = BarkparkConnections.connect(c.owner, c.credential, c.params, "connect-first")
    Accounts.revoke(c.credential)

    assert {:error, :authorization_changed} =
             BarkparkConnections.connect(c.owner, c.credential, c.params, "connect-first")

    assert {:error, :authorization_changed} =
             BarkparkConnections.disconnect(
               c.owner,
               c.credential,
               first["generation"],
               "disconnect-revoked"
             )

    assert {:error, :authorization_changed} = BarkparkConnections.show(c.owner, c.credential)
    assert Repo.get_by!(BarkparkConnection, user_id: c.owner.id).generation == first["generation"]
  end

  test "session revocation while source verification is held refuses activation after I/O", c do
    params = %{c.params | "token" => "synthetic-held-credential"}

    task =
      Task.async(fn ->
        BarkparkConnections.connect(c.owner, c.credential, params, "connect-held")
      end)

    fixture = c.fixture
    assert_receive {^fixture, {:data, {:eol, "BLOCKED"}}}, 4000
    Accounts.revoke(c.credential)
    Port.command(fixture, "release\n")
    assert {:error, :authorization_changed} = Task.await(task, 8000)
    assert Repo.aggregate(BarkparkConnection, :count) == 0
    assert Repo.aggregate(BarkparkConnectionEvent, :count) == 0
  end

  test "repository-scoped session cannot even read or change an account connection", c do
    repository =
      Repo.insert!(%Gitgood.Repository{
        owner_id: c.owner.id,
        team: "connection-team",
        name: "fixture-repository",
        storage_key: Ecto.UUID.generate(),
        creation_key: "connection-scope-fixture"
      })

    {token, scoped} = Accounts.issue(c.owner, "session", repository.id)
    assert {:error, :authorization_changed} = BarkparkConnections.show(c.owner, scoped)

    assert {:error, :authorization_changed} =
             BarkparkConnections.connect(c.owner, scoped, c.params, "connect-scoped")

    assert build_conn()
           |> put_req_header("authorization", "Bearer " <> token)
           |> get("/api/connections/barkpark")
           |> json_response(403) == %{"error" => "credential_scope_denied"}

    assert Repo.aggregate(BarkparkConnection, :count) == 0
  end

  test "ciphertext tampering and key replacement fail closed while account disconnect remains possible",
       c do
    {:ok, first} = BarkparkConnections.connect(c.owner, c.credential, c.params, "connect-first")
    row = Repo.get_by!(BarkparkConnection, user_id: c.owner.id)
    <<prefix::binary-size(29), tail::binary>> = row.token_cipher
    <<byte, rest::binary>> = tail
    tampered = <<prefix::binary, Bitwise.bxor(byte, 1), rest::binary>>
    binding = [c.owner.id, row.id, row.generation, row.origin]
    assert {:error, :connection_secret_unavailable} = ConnectionSecrets.open(tampered, binding)
    Application.put_env(:gitgood, :connection_key, :crypto.strong_rand_bytes(32))

    assert {:error, :connection_secret_unavailable} =
             BarkparkConnections.read(c.owner, c.credential, first["generation"], "/ok")

    assert {:ok, %{"state" => "disconnected"}} =
             BarkparkConnections.disconnect(
               c.owner,
               c.credential,
               first["generation"],
               "disconnect-key-replaced"
             )
  end

  test "HTTP is private, CSRF checked, strictly shaped and never returns the source secret", c do
    anonymous = build_conn() |> get("/api/connections/barkpark") |> json_response(401)
    assert anonymous == %{"error" => "sign_in_required"}
    cookie = build_conn() |> put_req_cookie("gitgood_session", c.session_token)

    assert cookie |> post("/api/connections/barkpark", c.params) |> json_response(403) == %{
             "error" => "csrf_required"
           }

    conn = fn ->
      build_conn()
      |> put_req_header("authorization", "Bearer " <> c.session_token)
      |> put_req_header("idempotency-key", "connect-http")
    end

    result = conn.() |> post("/api/connections/barkpark", c.params) |> json_response(200)
    refute Jason.encode!(result) =~ @token
    assert result["source_identity"]["label"] == "Fixture service"
    assert conn.() |> get("/api/connections/barkpark") |> json_response(200) == result

    assert conn.()
           |> post("/api/connections/barkpark", Map.put(c.params, "user_id", c.other.id))
           |> json_response(422) ==
             %{"error" => "invalid_connection_request"}

    assert Phoenix.Logger.filter_values(%{"token" => @token}) == %{"token" => "[FILTERED]"}
  end
end
