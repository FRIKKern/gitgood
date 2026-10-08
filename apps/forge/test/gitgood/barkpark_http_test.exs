defmodule Gitgood.BarkparkHTTPTest do
  use ExUnit.Case, async: false
  alias Gitgood.BarkparkHTTP
  @token "synthetic-fixture-credential"

  setup do
    saved_origin = Application.get_env(:gitgood, :barkpark_origin)
    saved_loopback = Application.get_env(:gitgood, :barkpark_allow_loopback_http)
    python = System.find_executable(Application.fetch_env!(:gitgood, :python_executable))
    openssl = System.find_executable(System.get_env("GITGOOD_OPENSSL", "openssl"))
    assert is_binary(openssl), "The transport wire fixture requires OpenSSL"

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

    {http, https} =
      receive do
        {^fixture, {:data, {:eol, "READY " <> ports}}} ->
          [http, https] = String.split(ports)
          {"http://127.0.0.1:" <> http, "https://127.0.0.1:" <> https}
      after
        20_000 -> flunk("Private HTTP fixture did not become ready")
      end

    Application.put_env(:gitgood, :barkpark_origin, http)
    Application.put_env(:gitgood, :barkpark_allow_loopback_http, true)

    on_exit(fn ->
      if Port.info(fixture), do: Port.close(fixture)
      restore(:barkpark_origin, saved_origin)
      restore(:barkpark_allow_loopback_http, saved_loopback)
    end)

    %{fixture: fixture, http: http, https: https}
  end

  test "authenticated requests retain source status, body and mutation key" do
    assert {:ok, %{status: 200, body: %{"authorized" => true}}} = BarkparkHTTP.get("/ok", @token)

    for {path, status, code} <- [
          {"/denied", 403, "forbidden"},
          {"/missing", 404, "not_found"},
          {"/unavailable", 503, "storage_unavailable"}
        ] do
      assert {:ok, %{status: ^status, body: %{"error" => %{"code" => ^code}}}} =
               BarkparkHTTP.get(path, @token)
    end

    assert {:ok,
            %{
              status: 200,
              body: %{
                "authorized" => true,
                "payload" => %{"value" => "Résumé"},
                "key" => "fixture-operation-1"
              }
            }} =
             BarkparkHTTP.post("/mutate", @token, %{"value" => "Résumé"}, "fixture-operation-1")
  end

  test "redirects, oversized, encoded and malformed responses fail without exposing raw contents" do
    for path <- ["/redirect", "/oversize", "/unbounded", "/malformed", "/compressed"] do
      assert {:error, :barkpark_unavailable} = BarkparkHTTP.get(path, @token)
    end

    assert {:ok, %{body: %{"count" => 0}}} = BarkparkHTTP.get("/redirect-count", @token)
    assert {:ok, %{body: %{"value" => value}}} = BarkparkHTTP.get("/exact-limit", @token)
    assert byte_size(value) == 1_048_564
  end

  test "a self-signed peer remains refused even when local plain HTTP is enabled", %{https: https} do
    Application.put_env(:gitgood, :barkpark_origin, https)
    assert {:error, :barkpark_unavailable} = BarkparkHTTP.get("/ok", @token)
  end

  test "unconfigured and invalid requests never become an anonymous or redirected read" do
    for origin <- [
          "https://user:password@example.invalid",
          "https://example.invalid/private",
          "https://example.invalid?other=1",
          "http://example.invalid"
        ] do
      Application.put_env(:gitgood, :barkpark_origin, origin)
      assert {:error, :invalid_barkpark_request} = BarkparkHTTP.get("/ok", @token)
    end

    Application.put_env(:gitgood, :barkpark_origin, "https://example.invalid")

    for path <- [
          "https://other.invalid/record",
          "//other.invalid/record",
          "/ok#fragment",
          "/ok\r\nheader"
        ] do
      assert {:error, :invalid_barkpark_request} = BarkparkHTTP.get(path, @token)
    end

    assert {:error, :invalid_barkpark_request} = BarkparkHTTP.get("/ok", "bad\r\ncredential")
    Application.delete_env(:gitgood, :barkpark_origin)
    assert {:error, :barkpark_unconfigured} = BarkparkHTTP.get("/ok", @token)
  end

  test "parked external requests fill only their own workers and ordinary Git still runs", %{
    fixture: fixture
  } do
    tasks = for _ <- 1..4, do: Task.async(fn -> BarkparkHTTP.get("/blocked", @token) end)

    for _ <- tasks do
      assert_receive {^fixture, {:data, {:eol, "BLOCKED"}}}, 4000
    end

    assert {:error, :barkpark_busy} = BarkparkHTTP.get("/ok", @token)
    assert {:ok, version, 0} = Gitgood.Git.command(["--version"])
    assert String.starts_with?(version, "git version ")
    Port.command(fixture, "release\n")

    for task <- tasks do
      assert {:ok, %{status: 200, body: %{"ok" => true}}} = Task.await(task, 5000)
    end

    assert DynamicSupervisor.count_children(Gitgood.BarkparkRequests).active == 0
  end

  defp restore(key, nil), do: Application.delete_env(:gitgood, key)
  defp restore(key, value), do: Application.put_env(:gitgood, key, value)
end
