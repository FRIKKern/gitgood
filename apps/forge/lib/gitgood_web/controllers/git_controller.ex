defmodule GitgoodWeb.GitController do
  use GitgoodWeb, :controller
  alias Gitgood.{Accounts, Git, Pushes, Repositories}
  alias GitgoodWeb.Auth

  def handle(conn, params) do
    case Gitgood.TransportSlots.with_slot(fn -> serve(conn, params) end) do
      {:error, :busy} -> Auth.reject(conn, 503, "transport_busy_retry")
      result -> result
    end
  end

  defp serve(conn, %{"team" => team, "name" => filename, "path" => path}) do
    conn = fetch_query_params(conn)

    with {:ok, user, credential} <- identity(conn),
         true <- String.ends_with?(filename, ".git"),
         name = String.trim_trailing(filename, ".git"),
         repository when not is_nil(repository) <- Repositories.get(user, team, name),
         true <- repository.status == "ready" and repository.storage_version >= 2,
         true <- credential.repository_id == repository.id,
         {:ok, service} <- service(conn, path),
         :ok <- writable(service, user.id, team),
         {:ok, body, conn} <-
           read_bounded(conn, [], 0, System.monotonic_time(:millisecond) + 15000) do
      version =
        if service == "upload" and get_req_header(conn, "git-protocol") == ["version=2"],
          do: "version=2",
          else: ""

      args =
        if conn.method == "GET",
          do: ["--stateless-rpc", "--advertise-refs"],
          else: ["--stateless-rpc"]

      run = fn extra ->
        Git.command(["#{service}-pack" | args] ++ [Git.path(repository)],
          input: body,
          env: [{"GIT_PROTOCOL", version} | extra],
          timeout: 60_000,
          limit: 33_554_432
        )
      end

      result =
        if service == "receive" and conn.method == "POST" do
          case Pushes.receive(repository, user, credential, fn operation, capability ->
                 run.([
                   {"GITGOOD_PUSH_ID", operation.id},
                   {"GITGOOD_HOOK_TOKEN", capability},
                   {"GITGOOD_PYTHON",
                    Application.fetch_env!(:gitgood, :python_executable)
                    |> System.find_executable()},
                   {"GITGOOD_HOOK_SCRIPT", Application.app_dir(:gitgood, "priv/push_hook.py")},
                   {"GITGOOD_INTERNAL_URL", Application.fetch_env!(:gitgood, :internal_url)}
                 ])
               end) do
            {:ok, {result, _}} -> result
            {:error, _} -> {:error, :operation_failed}
          end
        else
          run.([])
        end

      respond(conn, result, service, version)
    else
      {:error, :unauthorized} ->
        conn
        |> put_resp_header("www-authenticate", "Basic realm=\"Gitgood\"")
        |> Auth.reject(401, "git_credential_required")

      {:error, :write_denied} ->
        Auth.reject(conn, 403, "push_denied_read_only")

      {:error, :input_limit} ->
        conn |> put_resp_header("connection", "close") |> Auth.reject(413, "push_size_limit")

      {:error, :body_timeout} ->
        Auth.reject(conn, 408, "request_body_timeout")

      _ ->
        Auth.reject(conn, 404, "repository_or_service_unavailable")
    end
  rescue
    _ -> Auth.reject(conn, 503, "git_operation_unavailable")
  end

  defp writable("receive", user_id, team),
    do:
      if(Accounts.role(user_id, team) in ["owner", "writer"],
        do: :ok,
        else: {:error, :write_denied}
      )

  defp writable(_, _, _), do: :ok

  defp identity(conn) do
    with ["Basic " <> encoded] <- get_req_header(conn, "authorization"),
         true <- byte_size(encoded) <= 512,
         {:ok, value} <- Base.decode64(encoded),
         [username, token] <- String.split(value, ":", parts: 2),
         {user, credential} <- Accounts.resolve(token, "git"),
         true <- user.username == username do
      {:ok, user, credential}
    else
      _ -> {:error, :unauthorized}
    end
  end

  defp service(conn, ["info", "refs"]) when conn.method == "GET" do
    case conn.query_params["service"] do
      "git-upload-pack" -> {:ok, "upload"}
      "git-receive-pack" -> {:ok, "receive"}
      _ -> {:error, :unsupported_service}
    end
  end

  defp service(conn, [rpc])
       when conn.method == "POST" and rpc in ["git-upload-pack", "git-receive-pack"] do
    expected = "application/x-" <> rpc <> "-request"

    if get_req_header(conn, "content-type") == [expected] and
         get_req_header(conn, "content-encoding") in [[], ["identity"]],
       do: {:ok, if(rpc == "git-upload-pack", do: "upload", else: "receive")},
       else: {:error, :unsupported_encoding}
  end

  defp service(_, _), do: {:error, :unsupported_service}

  defp read_bounded(conn, chunks, bytes, deadline) do
    remaining = max(1, deadline - System.monotonic_time(:millisecond))

    case read_body(conn, length: 1_048_576, read_length: 65536, read_timeout: remaining) do
      {status, body, conn} when status in [:ok, :more] ->
        bytes = bytes + byte_size(body)

        cond do
          System.monotonic_time(:millisecond) >= deadline ->
            {:error, :body_timeout}

          bytes > 33_554_432 ->
            {:error, :input_limit}

          status == :more ->
            read_bounded(conn, [body | chunks], bytes, deadline)

          true ->
            {:ok, IO.iodata_to_binary(Enum.reverse([body | chunks])), conn}
        end

      _ ->
        {:error, :body_timeout}
    end
  end

  defp respond(conn, {:ok, output, 0}, service, version) do
    {type, body} =
      if conn.method == "GET" do
        # Follow Git's smart HTTP advertisement framing. Protocol v2 omits the v0/v1 service preamble.
        preamble = "# service=git-#{service}-pack\n"
        framed = if version == "version=2", do: output, else: packet(preamble) <> "0000" <> output
        {"application/x-git-#{service}-pack-advertisement", framed}
      else
        {"application/x-git-#{service}-pack-result", output}
      end

    conn
    |> put_resp_content_type(type)
    |> put_resp_header("cache-control", "no-store")
    |> send_resp(200, body)
  end

  defp respond(conn, _, _, _),
    do: Auth.reject(conn, 503, "git_operation_failed_retry_after_fetch")

  defp packet(body),
    do:
      (Integer.to_string(byte_size(body) + 4, 16)
       |> String.downcase()
       |> String.pad_leading(4, "0")) <> body
end
