defmodule Gitgood.SSHKeyCallback do
  @behaviour :ssh_server_key_api
  @impl true
  def host_key(algorithm, options) do
    :ssh_file.host_key(algorithm, options)
  rescue
    _ -> {:error, :host_key_unavailable}
  end

  @impl true
  def is_auth_key(key, username, _) do
    public = :ssh_file.encode([{key, []}], :openssh_key)

    case Gitgood.SSHKeys.authenticate(public, to_string(username)) do
      {:ok, user, credential} -> Gitgood.SSHIdentities.offer(user, credential)
      _ -> false
    end
  rescue
    _ -> false
  end
end
