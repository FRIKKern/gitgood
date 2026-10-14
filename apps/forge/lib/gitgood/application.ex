defmodule Gitgood.Application do
  # See https://elixir.hexdocs.pm/Application.html
  # for more information on OTP Applications
  @moduledoc false

  use Application

  @impl true
  def start(type, args) do
    root = Application.fetch_env!(:gitgood, :storage_root)

    case Gitgood.InstallationProfile.resolve(
           Application.get_env(:gitgood, :supervision_profile),
           root,
           :runtime
         ) do
      {:ok, %{profile: :development_v1}} ->
        start_development(root)

      {:ok, %{profile: :systemd_v2}} when type == :normal and args == [] ->
        Gitgood.NativeRuntime.start_application()

      {:ok, %{profile: :systemd_v2}} ->
        {:error, :native_runtime_unavailable}

      {:error, reason} ->
        {:error, reason}
    end
  end

  defp start_development(root) do
    :ok = File.mkdir_p(root)

    children = [GitgoodWeb.Telemetry, Gitgood.Repo] ++ Gitgood.RuntimeWorkers.children()

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
