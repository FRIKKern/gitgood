defmodule GitgoodWeb.NativeChangeController do
  use GitgoodWeb, :controller
  alias Gitgood.NativeChanges
  alias GitgoodWeb.Auth

  def show(conn, %{"id" => id}) do
    case NativeChanges.locate(conn.assigns.user, conn.assigns.credential, id) do
      {:ok, change} -> json(conn, change)
      {:error, :change_not_found} -> Auth.reject(conn, 404, "change_not_found")
      {:error, :authorization_changed} -> Auth.reject(conn, 401, "sign_in_required")
      {:error, _} -> Auth.reject(conn, 503, "access_unavailable")
    end
  end
end
