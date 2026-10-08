defmodule Gitgood.Application do
  # See https://elixir.hexdocs.pm/Application.html
  # for more information on OTP Applications
  @moduledoc false

  use Application

  @impl true
  def start(_type, _args) do
    children = [
      GitgoodWeb.Telemetry,
      Gitgood.Repo,
      {DynamicSupervisor, name: Gitgood.Commands, strategy: :one_for_one, max_children: 4},
      {Task.Supervisor, name: Gitgood.DurableWrites},
      {DynamicSupervisor, name: Gitgood.PushWorkers, strategy: :one_for_one, max_children: 4},
      {DynamicSupervisor, name: Gitgood.MergeWorkers, strategy: :one_for_one, max_children: 4},
      Gitgood.TransportSlots,
      Gitgood.LoginLimiter,
      Gitgood.Reconciler,
      {Phoenix.PubSub, name: Gitgood.PubSub},
      # Start a worker by calling: Gitgood.Worker.start_link(arg)
      # {Gitgood.Worker, arg},
      # Start to serve requests, typically the last entry
      GitgoodWeb.Endpoint
    ]

    # See https://elixir.hexdocs.pm/Supervisor.html
    # for other strategies and supported options
    opts = [strategy: :one_for_one, name: Gitgood.Supervisor]
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
