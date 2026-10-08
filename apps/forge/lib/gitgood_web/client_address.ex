defmodule GitgoodWeb.ClientAddress do
  @moduledoc "Login rate bucket from authenticated web/edge context, never caller forwarding headers."
  import Plug.Conn
  @headers ["x-gitgood-client-address", "x-gitgood-client-time", "x-gitgood-client-signature"]

  def login(conn) do
    case Application.get_env(:gitgood, :proxy_key) do
      nil ->
        {:ok, normalize(conn.remote_ip)}

      key when is_binary(key) and byte_size(key) == 32 ->
        with true <- loopback?(conn.remote_ip),
             [address] <- get_req_header(conn, Enum.at(@headers, 0)),
             [stamp] <- get_req_header(conn, Enum.at(@headers, 1)),
             [signature] <- get_req_header(conn, Enum.at(@headers, 2)),
             true <- byte_size(address) <= 45 and Regex.match?(~r/\A[0-9a-fA-F:.]+\z/, address),
             {:ok, ip} <- :inet.parse_strict_address(String.to_charlist(address)),
             true <- Regex.match?(~r/\A[0-9]{10}\z/, stamp),
             true <- abs(System.system_time(:second) - String.to_integer(stamp)) <= 30,
             true <- Regex.match?(~r/\A[0-9a-f]{64}\z/, signature),
             frame =
               Enum.join(
                 ["gitgood-login-origin-v1", address, stamp, conn.method, path(conn)],
                 "\n"
               ),
             expected = :crypto.mac(:hmac, :sha256, key, frame) |> Base.encode16(case: :lower),
             true <- Plug.Crypto.secure_compare(signature, expected) do
          {:ok, normalize(ip)}
        else
          _ -> {:error, :client_address_unverified}
        end
    end
  end

  defp path(%{query_string: ""} = conn), do: conn.request_path
  defp path(conn), do: conn.request_path <> "?" <> conn.query_string
  defp loopback?({127, _, _, _}), do: true
  defp loopback?({0, 0, 0, 0, 0, 0, 0, 1}), do: true
  defp loopback?({0, 0, 0, 0, 0, 65535, a, _}) when a in 32512..32767, do: true
  defp loopback?(_), do: false

  defp normalize({0, 0, 0, 0, 0, 65535, a, b}),
    do: {div(a, 256), rem(a, 256), div(b, 256), rem(b, 256)}

  defp normalize(ip), do: ip
end
