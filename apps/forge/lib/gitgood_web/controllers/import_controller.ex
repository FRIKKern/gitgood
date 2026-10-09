defmodule GitgoodWeb.ImportController do
  use GitgoodWeb, :controller
  alias Gitgood.{Imports, Merges, Repositories, TransportSlots}
  alias GitgoodWeb.Auth

  def create(conn, params) do
    with_repository(conn, params, fn repository ->
      body = Map.drop(params, ["team", "name"])

      respond(
        conn,
        Imports.begin(
          repository,
          conn.assigns.user,
          conn.assigns.credential,
          body,
          List.first(get_req_header(conn, "idempotency-key"))
        )
      )
    end)
  end

  def cancel(conn, params) do
    with_repository(conn, params, fn repository ->
      respond(
        conn,
        Imports.cancel(repository, conn.assigns.user, conn.assigns.credential, params["id"])
      )
    end)
  end

  def source(conn, params) do
    with_repository(conn, params, fn repository ->
      case Imports.upload_allowed(
             repository,
             conn.assigns.user,
             conn.assigns.credential,
             params["id"]
           ) do
        {:ok, operation} ->
          if get_req_header(conn, "content-type") == ["application/octet-stream"] do
            result =
              TransportSlots.with_slot(fn ->
                upload(conn, repository, operation)
              end)

            case result do
              %Plug.Conn{} = conn -> conn
              {:error, :busy} -> Auth.reject(conn, 503, "import_upload_busy_retry")
            end
          else
            Auth.reject(conn, 415, "binary_bundle_body_required")
          end

        {:error, reason} ->
          Auth.reject(conn, 409, Atom.to_string(reason))
      end
    end)
  end

  defp upload(conn, repository, operation) do
    temporary = Imports.temporary_path()
    {:ok, file} = File.open(temporary, [:write, :binary, :exclusive])
    :ok = File.chmod(temporary, 0o600)

    try do
      case read_source(conn, file, 0, System.monotonic_time(:millisecond) + 15000) do
        {:ok, conn} ->
          :ok = File.close(file)

          respond(
            conn,
            Imports.accept_source(
              repository,
              conn.assigns.user,
              conn.assigns.credential,
              operation.id,
              temporary
            )
          )

        {:error, conn, reason} ->
          Auth.reject(conn, 422, Atom.to_string(reason))
      end
    after
      File.close(file)
      File.rm(temporary)
    end
  rescue
    _ -> Auth.reject(conn, 503, "source_interrupted_retry_same_operation")
  end

  defp read_source(conn, file, count, deadline) do
    if System.monotonic_time(:millisecond) > deadline do
      {:error, conn, :source_upload_timeout}
    else
      case read_body(conn, length: 65536, read_length: 65536, read_timeout: 5000) do
        {status, body, conn} when status in [:ok, :more] ->
          bytes = count + byte_size(body)

          cond do
            bytes > Imports.limit() -> {:error, conn, :source_too_large}
            IO.binwrite(file, body) != :ok -> {:error, conn, :source_staging_failed}
            status == :ok -> {:ok, conn}
            true -> read_source(conn, file, bytes, deadline)
          end

        _ ->
          {:error, conn, :source_interrupted}
      end
    end
  end

  defp with_repository(conn, %{"team" => team, "name" => name}, action) do
    case Repositories.get(conn.assigns.user, team, name) do
      nil -> Auth.reject(conn, 404, "repository_not_found")
      repository -> action.(repository)
    end
  end

  defp respond(conn, {:ok, operation}),
    do: conn |> put_status(202) |> json(%{operation: Merges.public(operation)})

  defp respond(conn, {:error, reason}), do: Auth.reject(conn, 409, Atom.to_string(reason))
end
