defmodule GitgoodWeb.SSHKeyController do
  use GitgoodWeb, :controller
  alias Gitgood.SSHKeys
  alias GitgoodWeb.Auth

  def index(conn, _),
    do:
      json(conn, %{
        keys: Enum.map(SSHKeys.list(conn.assigns.user), &SSHKeys.public/1),
        transport: Gitgood.SSHDaemon.public()
      })

  def create(conn, params) do
    case SSHKeys.register(
           conn.assigns.user,
           conn.assigns.credential,
           params,
           List.first(get_req_header(conn, "idempotency-key"))
         ) do
      {:ok, key} ->
        conn |> put_status(201) |> json(SSHKeys.public(key))

      {:error, error} ->
        Auth.reject(
          conn,
          if(error in [:key_label_required, :supported_ed25519_public_key_required],
            do: 422,
            else: 409
          ),
          Atom.to_string(error)
        )
    end
  end
end
