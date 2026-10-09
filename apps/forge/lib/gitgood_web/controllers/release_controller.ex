defmodule GitgoodWeb.ReleaseController do
  use GitgoodWeb, :controller
  alias Gitgood.{Releases, Repositories, TransportSlots}
  alias GitgoodWeb.Auth

  def index(conn, params),
    do:
      repository(conn, params, fn repo ->
        response(conn, Releases.list(repo, conn.assigns.user, conn.assigns.credential), :releases)
      end)

  def tags(conn, params),
    do:
      repository(conn, params, fn repo ->
        response(conn, Releases.tags(repo, conn.assigns.user, conn.assigns.credential), :tags)
      end)

  def show(conn, params),
    do:
      repository(conn, params, fn repo ->
        response(
          conn,
          Releases.get(repo, conn.assigns.user, conn.assigns.credential, params["id"])
        )
      end)

  def create(conn, params),
    do:
      repository(conn, params, fn repo ->
        response(
          conn,
          Releases.create(
            repo,
            conn.assigns.user,
            conn.assigns.credential,
            conn.body_params,
            key(conn)
          ),
          :release
        )
      end)

  def transition(conn, params),
    do:
      repository(conn, params, fn repo ->
        response(
          conn,
          Releases.action(
            repo,
            conn.assigns.user,
            conn.assigns.credential,
            params["id"],
            conn.body_params,
            key(conn)
          )
        )
      end)

  def asset(conn, params),
    do:
      repository(conn, params, fn repo ->
        response(
          conn,
          Releases.asset_intent(
            repo,
            conn.assigns.user,
            conn.assigns.credential,
            params["id"],
            conn.body_params,
            key(conn)
          ),
          :asset
        )
      end)

  def cancel(conn, params),
    do:
      repository(conn, params, fn repo ->
        response(
          conn,
          Releases.cancel_asset(
            repo,
            conn.assigns.user,
            conn.assigns.credential,
            params["id"],
            params["asset"]
          ),
          :asset
        )
      end)

  def upload(conn, params) do
    repository(conn, params, fn repo ->
      with {:ok, _} <-
             Releases.upload_allowed(
               repo,
               conn.assigns.user,
               conn.assigns.credential,
               params["id"],
               params["asset"]
             ),
           true <- get_req_header(conn, "content-type") == ["application/octet-stream"] do
        case TransportSlots.with_slot(fn ->
               case read_asset(conn, [], 0, System.monotonic_time(:millisecond) + 15000) do
                 {:ok, conn, body} ->
                   response(
                     conn,
                     Releases.upload(
                       repo,
                       conn.assigns.user,
                       conn.assigns.credential,
                       params["id"],
                       params["asset"],
                       body
                     ),
                     :asset
                   )

                 {:error, conn, reason} ->
                   Auth.reject(conn, 422, Atom.to_string(reason))
               end
             end) do
          %Plug.Conn{} = conn -> conn
          {:error, :busy} -> Auth.reject(conn, 503, "asset_upload_busy_retry")
        end
      else
        false -> Auth.reject(conn, 415, "binary_asset_body_required")
        {:error, reason} -> reject(conn, reason)
      end
    end)
  end

  def download(conn, params) do
    repository(conn, params, fn repo ->
      case TransportSlots.with_slot(fn ->
             case Releases.download(
                    repo,
                    conn.assigns.user,
                    conn.assigns.credential,
                    params["id"],
                    params["asset"]
                  ) do
               {:ok, {asset, data}} ->
                 conn
                 |> put_resp_header("content-type", "application/octet-stream")
                 |> put_resp_header(
                   "content-disposition",
                   ~s(attachment; filename="#{asset.name}")
                 )
                 |> put_resp_header("x-content-type-options", "nosniff")
                 |> put_resp_header("x-gitgood-sha256", asset.sha256)
                 |> put_resp_header("content-length", Integer.to_string(asset.size))
                 |> send_resp(200, data)

               {:error, reason} ->
                 reject(conn, reason)
             end
           end) do
        %Plug.Conn{} = conn -> conn
        {:error, :busy} -> Auth.reject(conn, 503, "asset_download_busy_retry")
      end
    end)
  end

  defp read_asset(conn, chunks, bytes, deadline) do
    if System.monotonic_time(:millisecond) > deadline do
      {:error, conn, :asset_upload_timeout}
    else
      case read_body(conn, length: 65536, read_length: 65536, read_timeout: 5000) do
        {status, chunk, conn} when status in [:ok, :more] ->
          bytes = bytes + byte_size(chunk)

          cond do
            bytes > Releases.limit() -> {:error, conn, :asset_too_large}
            status == :ok -> {:ok, conn, IO.iodata_to_binary(Enum.reverse([chunk | chunks]))}
            true -> read_asset(conn, [chunk | chunks], bytes, deadline)
          end

        _ ->
          {:error, conn, :asset_upload_interrupted_retry}
      end
    end
  end

  defp repository(conn, %{"team" => team, "name" => name}, action) do
    case Repositories.get(conn.assigns.user, team, name) do
      nil -> Auth.reject(conn, 404, "repository_not_found")
      repo -> action.(repo)
    end
  end

  defp key(conn), do: List.first(get_req_header(conn, "idempotency-key"))
  defp response(conn, {:ok, result}), do: json(conn, result)
  defp response(conn, {:error, reason}), do: reject(conn, reason)
  defp response(conn, {:ok, result}, key), do: json(conn, %{key => result})
  defp response(conn, {:error, reason}, _key), do: reject(conn, reason)

  defp reject(conn, reason),
    do:
      Auth.reject(
        conn,
        if(reason in [:release_not_found, :asset_not_found],
          do: 404,
          else: if(reason == :authorization_changed, do: 403, else: 409)
        ),
        Atom.to_string(reason)
      )
end
