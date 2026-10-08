defmodule GitgoodWeb.ClientAddressTest do
  use ExUnit.Case, async: false
  import Plug.Conn
  alias GitgoodWeb.ClientAddress

  setup do
    previous = Application.get_env(:gitgood, :proxy_key)
    key = :crypto.strong_rand_bytes(32)
    Application.put_env(:gitgood, :proxy_key, key)
    on_exit(fn -> Application.put_env(:gitgood, :proxy_key, previous) end)
    %{key: key}
  end

  defp signed(key, address, opts \\ []) do
    method = Keyword.get(opts, :method, "POST")
    path = Keyword.get(opts, :path, "/api/session")
    stamp = Keyword.get(opts, :stamp, Integer.to_string(System.system_time(:second)))
    frame = Enum.join(["gitgood-login-origin-v1", address, stamp, method, path], "\n")
    signature = :crypto.mac(:hmac, :sha256, key, frame) |> Base.encode16(case: :lower)
    conn = Plug.Test.conn(method, path)
    conn = %{conn | remote_ip: Keyword.get(opts, :peer, {127, 0, 0, 1})}

    conn
    |> put_req_header("x-gitgood-client-address", address)
    |> put_req_header("x-gitgood-client-time", stamp)
    |> put_req_header("x-gitgood-client-signature", signature)
  end

  test "development uses the actual socket address and ignores forwarding assertions" do
    Application.put_env(:gitgood, :proxy_key, nil)
    conn = Plug.Test.conn("POST", "/api/session") |> put_req_header("x-forwarded-for", "1.2.3.4")
    conn = %{conn | remote_ip: {198, 51, 100, 7}}
    assert ClientAddress.login(conn) == {:ok, {198, 51, 100, 7}}
  end

  test "correct socket-bound assertions accept IPv4 and canonicalize equivalent IPv6", %{key: key} do
    assert ClientAddress.login(signed(key, "198.51.100.8")) == {:ok, {198, 51, 100, 8}}
    assert ClientAddress.login(signed(key, "::ffff:198.51.100.8")) == {:ok, {198, 51, 100, 8}}

    assert ClientAddress.login(signed(key, "2001:db8::8")) ==
             {:ok, {8193, 3512, 0, 0, 0, 0, 0, 8}}
  end

  test "caller forwarding cannot select or replace a correctly signed bucket", %{key: key} do
    conn =
      signed(key, "198.51.100.9")
      |> put_req_header("x-forwarded-for", "1.2.3.4, 5.6.7.8")
      |> put_req_header("forwarded", "for=9.9.9.9")

    assert ClientAddress.login(conn) == {:ok, {198, 51, 100, 9}}

    assert ClientAddress.login(put_req_header(conn, "x-gitgood-client-address", "1.2.3.4")) ==
             {:error, :client_address_unverified}
  end

  test "missing, stale, future, wrong-key and duplicate assertions are refused", %{key: key} do
    assert ClientAddress.login(Plug.Test.conn("POST", "/api/session")) ==
             {:error, :client_address_unverified}

    for offset <- [-120, 120] do
      stamp = Integer.to_string(System.system_time(:second) + offset)

      assert ClientAddress.login(signed(key, "198.51.100.10", stamp: stamp)) ==
               {:error, :client_address_unverified}
    end

    conn = signed(:crypto.strong_rand_bytes(32), "198.51.100.10")
    assert ClientAddress.login(conn) == {:error, :client_address_unverified}
    conn = signed(key, "198.51.100.10")
    conn = %{conn | req_headers: [{"x-gitgood-client-time", "0000000000"} | conn.req_headers]}
    assert ClientAddress.login(conn) == {:error, :client_address_unverified}
  end

  test "signed assertions cannot cross route, query, method or non-loopback peer", %{key: key} do
    conn = signed(key, "198.51.100.11", path: "/api/session?attempt=1")
    assert ClientAddress.login(conn) == {:ok, {198, 51, 100, 11}}

    for changed <- [
          %{conn | request_path: "/api/session/other"},
          %{conn | query_string: "attempt=2"},
          %{conn | method: "GET"},
          %{conn | remote_ip: {198, 51, 100, 12}}
        ] do
      assert ClientAddress.login(changed) == {:error, :client_address_unverified}
    end
  end

  test "signed malformed addresses do not invent usable buckets", %{key: key} do
    for address <- ["198.51.100.9, 1.2.3.4", "localhost", "127.0.0.1%zone", "999.1.1.1", ""] do
      assert ClientAddress.login(signed(key, address)) == {:error, :client_address_unverified}
    end
  end

  test "twenty attempts remain bounded per authenticated address rather than shared web socket",
       %{key: key} do
    last = :erlang.unique_integer([:positive]) |> rem(200) |> Kernel.+(20)
    a = "203.0.113." <> Integer.to_string(last)
    b = "192.0.2." <> Integer.to_string(last)
    {:ok, bucket_a} = ClientAddress.login(signed(key, a))
    {:ok, equivalent} = ClientAddress.login(signed(key, "::ffff:" <> a))
    {:ok, bucket_b} = ClientAddress.login(signed(key, b))
    assert equivalent == bucket_a
    for _ <- 1..20, do: assert(Gitgood.LoginLimiter.allow?(bucket_a))
    refute Gitgood.LoginLimiter.allow?(equivalent)
    assert Gitgood.LoginLimiter.allow?(bucket_b)
  end
end
