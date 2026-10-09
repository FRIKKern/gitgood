defmodule Gitgood.BarkparkHTTP do
  @moduledoc "Bounded, origin-pinned external I/O on workers independent of Git transport."

  @response_limit 1_100_000

  def get(path, token), do: request("GET", path, token, nil, nil)
  def post(path, token, payload, key), do: request("POST", path, token, payload, key)

  def post_bytes(path, token, payload, key) when is_binary(payload),
    do: request("POST_BYTES", path, token, payload, key)

  defp request(method, path, token, payload, key) do
    origin = Application.get_env(:gitgood, :barkpark_origin)
    loopback? = Application.get_env(:gitgood, :barkpark_allow_loopback_http, false)

    with {:ok, origin} <- origin(origin, loopback?),
         :ok <- path(path),
         :ok <- token(token),
         {:ok, input} <-
           Jason.encode(%{
             url: origin <> path,
             method: if(method == "POST_BYTES", do: "POST", else: method),
             token: token,
             payload: if(method == "POST_BYTES", do: nil, else: payload),
             payload_bytes: if(method == "POST_BYTES", do: payload, else: nil),
             idempotency_key: key,
             allow_loopback_http: loopback?
           }),
         {:ok, output, 0} <-
           Gitgood.Command.run(
             [
               System.find_executable(Application.fetch_env!(:gitgood, :python_executable)),
               "-I",
               Application.app_dir(:gitgood, "priv/barkpark_http.py")
             ],
             env: certificate_environment(),
             input: input,
             timeout: 5000,
             limit: @response_limit,
             supervisor: Gitgood.BarkparkRequests
           ),
         {:ok, %{"status" => status, "body" => body}} <- Jason.decode(output),
         true <- is_integer(status) and status in 100..599 do
      {:ok, %{status: status, body: body}}
    else
      {:error, :barkpark_unconfigured} = error -> error
      {:error, :invalid_barkpark_request} = error -> error
      {:error, :busy} -> {:error, :barkpark_busy}
      _ -> {:error, :barkpark_unavailable}
    end
  rescue
    _ -> {:error, :barkpark_unavailable}
  end

  # Only explicit installation trust is passed to this worker. The normal TLS
  # chain and hostname checks remain enabled; arbitrary inherited trust/proxies
  # stay outside Command.environment's allowlist.
  defp certificate_environment do
    case Application.get_env(:gitgood, :barkpark_ca_file) do
      nil -> []
      file when is_binary(file) -> [{"SSL_CERT_FILE", file}]
    end
  end

  defp origin(nil, _), do: {:error, :barkpark_unconfigured}

  defp origin(value, loopback?) when is_binary(value) do
    case URI.new(value) do
      {:ok,
       %URI{scheme: scheme, host: host, userinfo: nil, query: nil, fragment: nil, path: path}}
      when is_binary(host) and host != "" and path in [nil, "", "/"] ->
        if scheme == "https" or
             (scheme == "http" and loopback? and host in ["localhost", "127.0.0.1", "::1"]),
           do: {:ok, String.trim_trailing(value, "/")},
           else: {:error, :invalid_barkpark_request}

      _ ->
        {:error, :invalid_barkpark_request}
    end
  end

  defp origin(_, _), do: {:error, :invalid_barkpark_request}

  defp path(value) when is_binary(value) and byte_size(value) <= 2048 do
    case URI.new(value) do
      {:ok, %URI{scheme: nil, host: nil, userinfo: nil, fragment: nil, path: "/" <> _}} ->
        if String.starts_with?(value, "//") or String.contains?(value, ["\r", "\n"]),
          do: {:error, :invalid_barkpark_request},
          else: :ok

      _ ->
        {:error, :invalid_barkpark_request}
    end
  end

  defp path(_), do: {:error, :invalid_barkpark_request}

  defp token(value) when is_binary(value) and byte_size(value) in 16..512 do
    if Enum.all?(:binary.bin_to_list(value), &(&1 in 33..126)),
      do: :ok,
      else: {:error, :invalid_barkpark_request}
  end

  defp token(_), do: {:error, :invalid_barkpark_request}
end
