defmodule Gitgood.SSHConnectionTest do
  use Gitgood.DataCase, async: false
  alias Gitgood.{Accounts, Credential, Repo, Repositories, SSHDaemon, SSHKeys}

  test "existing authenticated SSH connection rechecks key on its next command" do
    directory = Path.join(System.tmp_dir!(), "gitgood-ssh-" <> Ecto.UUID.generate())
    server = Path.join(directory, "host")
    client = Path.join(directory, "client")
    File.mkdir_p!(server)
    File.mkdir_p!(client)

    keygen =
      System.get_env("GITGOOD_SSH_KEYGEN") ||
        if(match?({:win32, _}, :os.type()),
          do: "C:/Windows/System32/OpenSSH/ssh-keygen.exe",
          else: "ssh-keygen"
        )

    assert {_, 0} =
             keygen(keygen, [
               "-q",
               "-t",
               "ed25519",
               "-N",
               "",
               "-f",
               Path.join(server, "ssh_host_ed25519_key")
             ])

    assert {_, 0} =
             keygen(keygen, [
               "-q",
               "-t",
               "ed25519",
               "-N",
               "",
               "-f",
               Path.join(client, "id_ed25519")
             ])

    {:ok, owner} = Accounts.create_user("ssh-connection", "synthetic-password")
    {:ok, _} = Accounts.add_member(owner, "team", "owner")
    {_, session} = Accounts.issue(owner, "session")

    {:ok, key} =
      SSHKeys.register(
        owner,
        session,
        %{
          "label" => "Connection",
          "public_key" => File.read!(Path.join(client, "id_ed25519.pub"))
        },
        "ssh-connection"
      )

    {:ok, repository} = Repositories.create(owner, "team", "ssh-existing", "ssh-create-repo")
    daemon = start_supervised!({SSHDaemon, [port: 0, directory: server]})
    state = :sys.get_state(daemon)
    {:port, port} = :ssh.daemon_info(state.daemon, :port)
    # Known-host verification is asserted by real OpenSSH clients in e2e. This
    # isolated OTP fixture uses an ephemeral host for the existing-channel check.
    {:ok, connection} =
      :ssh.connect(~c"127.0.0.1", port,
        user: String.to_charlist(owner.username),
        user_dir: String.to_charlist(client),
        silently_accept_hosts: true,
        user_interaction: false,
        auth_methods: ~c"publickey",
        preferred_algorithms: [public_key: [:"ssh-ed25519"]]
      )

    on_exit(fn -> :ssh.close(connection) end)
    {:ok, channel} = :ssh_connection.session_channel(connection, 5000)

    assert :success =
             :ssh_connection.exec(
               connection,
               channel,
               ~c"git-upload-pack '/team/ssh-existing.git'",
               5000
             )

    assert_receive {:ssh_cm, ^connection, {:data, ^channel, 0, "0000"}}, 5000
    assert :ok = :ssh_connection.send(connection, channel, "0000", 5000)
    assert :ok = :ssh_connection.send_eof(connection, channel)
    assert_receive {:ssh_cm, ^connection, {:exit_status, ^channel, 0}}, 5000
    {:ok, _} = Accounts.revoke(Repo.get!(Credential, key.credential_id))
    {:ok, next} = :ssh_connection.session_channel(connection, 5000)

    assert :success =
             :ssh_connection.exec(
               connection,
               next,
               ~c"git-upload-pack '/team/ssh-existing.git'",
               5000
             )

    assert_receive {:ssh_cm, ^connection, {:data, ^next, 1, message}}, 5000
    assert message =~ "unavailable"
    assert_receive {:ssh_cm, ^connection, {:exit_status, ^next, 1}}, 5000
    :ssh.close(connection)
    stop_supervised!(SSHDaemon)
    root = Application.fetch_env!(:gitgood, :storage_root) |> Path.expand()
    path = Gitgood.Git.path(repository) |> Path.expand()
    assert String.starts_with?(path, root <> "/")
    File.rm_rf!(path)
    assert String.starts_with?(Path.expand(directory), Path.expand(System.tmp_dir!()) <> "/")
    File.rm_rf!(directory)
  end

  defp keygen(executable, args) do
    python = Application.fetch_env!(:gitgood, :python_executable) |> System.find_executable()
    # Python passes the empty passphrase correctly on Windows and Linux alike.
    code =
      "import subprocess; raise SystemExit(subprocess.call(" <>
        Jason.encode!([executable | args]) <> "))"

    System.cmd(python, ["-c", code], stderr_to_stdout: true)
  end
end
