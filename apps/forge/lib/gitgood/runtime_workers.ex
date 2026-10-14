defmodule Gitgood.RuntimeWorkers do
  @moduledoc "Fixed product worker/listener specifications, excluding Repo and ownership."

  def children do
    [
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
      GitgoodWeb.Endpoint
    ] ++ ssh()
  end

  defp ssh do
    case Application.get_env(:gitgood, :ssh_port) do
      nil ->
        []

      port ->
        [
          {Gitgood.SSHDaemon,
           [port: port, directory: Application.fetch_env!(:gitgood, :ssh_host_key_directory)]}
        ]
    end
  end
end
