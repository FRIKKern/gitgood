defmodule Gitgood.SSHDaemon do
  use GenServer
  def start_link(options), do: GenServer.start_link(__MODULE__, options, name: __MODULE__)

  def init(options) do
    port = Keyword.fetch!(options, :port)
    directory = Keyword.fetch!(options, :directory)

    with {:ok, private_key} <-
           :ssh_file.host_key(:"ssh-ed25519", system_dir: String.to_charlist(directory)),
         public_key <- :ssh_file.extract_public_key(private_key),
         {:ok, key} <- Gitgood.SSHKeys.parse(:ssh_file.encode([{public_key, []}], :openssh_key)),
         {:ok, daemon} <-
           :ssh.daemon({127, 0, 0, 1}, port,
             system_dir: String.to_charlist(directory),
             key_cb: Gitgood.SSHKeyCallback,
             ssh_cli: {Gitgood.SSHChannel, []},
             shell: :disabled,
             exec: :disabled,
             subsystems: [],
             auth_methods: ~c"publickey",
             preferred_algorithms: [public_key: [:"ssh-ed25519"]],
             connectfun: activate_callback(&Gitgood.SSHIdentities.activate/2),
             tcpip_tunnel_in: false,
             tcpip_tunnel_out: false,
             max_sessions: 16,
             max_channels: 4,
             parallel_login: true,
             hello_timeout: 5000,
             negotiation_timeout: 10000,
             max_initial_idle_time: 10000,
             idle_time: 10000,
             max_log_item_len: 0
           ) do
      {:ok, %{daemon: daemon, monitor: Process.monitor(daemon), directory: directory, key: key}}
    else
      _ -> {:stop, :ssh_host_key_or_daemon_unavailable}
    end
  rescue
    _ -> {:stop, :ssh_host_key_or_daemon_unavailable}
  catch
    _, _ -> {:stop, :ssh_host_key_or_daemon_unavailable}
  end

  defp activate_callback(fun), do: fn user, _peer, method -> fun.(user, method) end

  def public do
    case Process.whereis(__MODULE__) do
      nil -> %{enabled: false}
      pid -> GenServer.call(pid, :public, 3000)
    end
  catch
    :exit, _ -> %{enabled: false}
  end

  def handle_call(:public, _, state) do
    available =
      match?({:port, _}, :ssh.daemon_info(state.daemon, :port)) and
        File.regular?(Path.join(state.directory, "ssh_host_ed25519_key"))

    public =
      if available,
        do: %{
          enabled: true,
          host: Application.fetch_env!(:gitgood, :ssh_public_host),
          port: Application.fetch_env!(:gitgood, :ssh_public_port),
          public_key: state.key.canonical,
          fingerprint: state.key.fingerprint
        },
        else: %{enabled: false}

    {:reply, public, state}
  end

  def handle_info({:DOWN, monitor, :process, _, _}, %{monitor: monitor} = state) do
    {:stop, :ssh_daemon_unavailable, state}
  end

  def clone_url(repository, user) do
    case public() do
      %{enabled: true, host: host, port: port} ->
        URI.to_string(%URI{
          scheme: "ssh",
          userinfo: user.username,
          host: host,
          port: port,
          path: "/#{repository.team}/#{repository.name}.git"
        })

      _ ->
        nil
    end
  end

  def terminate(_, state), do: :ssh.stop_daemon(state.daemon)
end
