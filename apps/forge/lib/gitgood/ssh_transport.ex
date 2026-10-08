defmodule Gitgood.SSHTransport do
  alias Gitgood.{CommandStream, Git, Lease, Pushes, Repositories, SSHIdentities, SSHKeys}
  def parse(command) when is_list(command), do: parse(to_string(command))

  def parse(command) when is_binary(command) and byte_size(command) <= 256 do
    case Regex.run(
           ~r/\Agit-(upload|receive)-pack '\/?([a-z][a-z0-9-]{1,39})\/([a-z][a-z0-9-]{1,63})\.git'\z/,
           command
         ) do
      [_, service, team, name] -> {:ok, service, team, name}
      _ -> {:error, :command_denied}
    end
  end

  def parse(_), do: {:error, :command_denied}

  def serve(connection, receiver, command, protocol) do
    result =
      Gitgood.TransportSlots.with_slot(fn ->
        with {:ok, service, team, name} <- parse(command),
             {:ok, user_id, credential_id} <- SSHIdentities.resolve(connection),
             {:ok, user, credential} <- SSHKeys.current(user_id, credential_id),
             repository when not is_nil(repository) <- Repositories.get(user, team, name),
             true <- repository.status == "ready" and repository.storage_version >= 2 do
          run = fn extra ->
            CommandStream.run(
              [Git.executable(), service <> "-pack", Git.path(repository)],
              receiver,
              env: [{"GIT_PROTOCOL", protocol} | extra],
              timeout: 60_000,
              limit: 33_554_432
            )
          end

          if service == "receive" do
            Pushes.receive(repository, user, credential, fn operation, capability ->
              run.([
                {"GITGOOD_PUSH_ID", operation.id},
                {"GITGOOD_HOOK_TOKEN", capability},
                {"GITGOOD_PYTHON",
                 Application.fetch_env!(:gitgood, :python_executable) |> System.find_executable()},
                {"GITGOOD_HOOK_SCRIPT", Application.app_dir(:gitgood, "priv/push_hook.py")},
                {"GITGOOD_INTERNAL_URL", Application.fetch_env!(:gitgood, :internal_url)}
              ])
            end)
            |> case do
              {:ok, {result, _outcome}} -> result
              {:error, error} -> {:error, error}
            end
          else
            Lease.actor(
              repository,
              user,
              credential,
              ["owner", "writer", "reader"],
              fn _ -> run.([]) end,
              "ssh"
            )
            |> case do
              {:ok, result} -> result
              {:error, error} -> {:error, error}
            end
          end
        else
          _ -> {:error, :repository_or_identity_unavailable}
        end
      end)

    send(receiver, {:gitgood_ssh_result, self(), result})
  rescue
    _ -> send(receiver, {:gitgood_ssh_result, self(), {:error, :operation_failed}})
  catch
    _, _ -> send(receiver, {:gitgood_ssh_result, self(), {:error, :operation_interrupted}})
  end
end
