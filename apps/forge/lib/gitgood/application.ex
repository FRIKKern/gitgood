defmodule Gitgood.Application do
  # See https://elixir.hexdocs.pm/Application.html
  # for more information on OTP Applications
  @moduledoc false

  use Application

  @impl true
  def start(_type, _args) do
    root = Application.fetch_env!(:gitgood, :storage_root)

    with :ok <-
           Gitgood.InstallationProfile.ensure_development(
             Application.get_env(:gitgood, :supervision_profile),
             root,
             :runtime
           ) do
      start_development(root)
    end
  end

  defp start_development(root) do
    :ok = File.mkdir_p(root)

    children = [
      GitgoodWeb.Telemetry,
      Gitgood.Repo,
      {Gitgood.BrowseSlots, []},
      {DynamicSupervisor, name: Gitgood.Commands, strategy: :one_for_one, max_children: 4},
      {DynamicSupervisor,
       name: Gitgood.BarkparkRequests, strategy: :one_for_one, max_children: 4},
      {Task.Supervisor, name: Gitgood.DurableWrites},
      {DynamicSupervisor, name: Gitgood.PushWorkers, strategy: :one_for_one, max_children: 4},
      {DynamicSupervisor, name: Gitgood.MergeWorkers, strategy: :one_for_one, max_children: 4},
      {DynamicSupervisor, name: Gitgood.ImportWorkers, strategy: :one_for_one, max_children: 2},
      Gitgood.TransportSlots,
      Gitgood.LoginLimiter,
      Gitgood.SSHIdentities,
      {Task.Supervisor, name: Gitgood.SSHJobs, max_children: 16},
      {Task.Supervisor, name: Gitgood.SourceReturnJobs, max_children: 2},
      Gitgood.SourceReturnWorker,
      Gitgood.Reconciler,
      {Phoenix.PubSub, name: Gitgood.PubSub},
      # Start a worker by calling: Gitgood.Worker.start_link(arg)
      # {Gitgood.Worker, arg},
      # Start to serve requests, typically the last entry
      GitgoodWeb.Endpoint
    ]

    # See https://elixir.hexdocs.pm/Supervisor.html
    # for other strategies and supported options
    children =
      children ++
        case Application.get_env(:gitgood, :ssh_port) do
          nil ->
            []

          port ->
            [
              {Gitgood.SSHDaemon,
               [port: port, directory: Application.fetch_env!(:gitgood, :ssh_host_key_directory)]}
            ]
        end

    children =
      if Gitgood.InstallationLease.enabled?(),
        do: List.insert_at(children, 2, Gitgood.InstallationLease),
        else: children

    opts = [strategy: :rest_for_one, name: Gitgood.Supervisor]
    Supervisor.start_link(children, opts)
  end

  # Tell Phoenix to update the endpoint configuration
  # whenever the application is updated.
  @impl true
  def config_change(changed, _new, removed) do
    GitgoodWeb.Endpoint.config_change(changed, removed)
    :ok
  end
end
