defmodule Gitgood.NativeMaintenance do
  @moduledoc "Fixed permanent native maintenance application; no caller programs or workers."
  @app :gitgood_native_maintenance
  @failure :native_maintenance_unavailable

  def start(action) when action in [:migrate, :bootstrap] do
    with :ok <- load_product(),
         true <- Application.get_env(:gitgood, :supervision_profile) === "systemd-v2",
         root when is_binary(root) <- Application.fetch_env!(:gitgood, :storage_root),
         :ok <-
           Gitgood.NativeOwnershipStartup.validate_lifecycle_options(root: root, action: action),
         true <-
           not Enum.any?(Application.started_applications(), fn {app, _, _} ->
             app in [:gitgood, @app]
           end),
         dependencies when is_list(dependencies) <- Application.spec(:gitgood, :applications),
         :ok <-
           :application.load(
             {:application, @app,
              [
                vsn: ~c"1",
                mod: {Gitgood.NativeMaintenanceApplication, action},
                applications: dependencies
              ]}
           ),
         {:ok, _} <- Application.ensure_all_started(@app, :permanent) do
      :ok
    else
      _ -> {:error, @failure}
    end
  rescue
    _ -> {:error, @failure}
  catch
    :exit, _ -> {:error, @failure}
  end

  def start(_), do: {:error, @failure}

  defp load_product do
    case Application.load(:gitgood) do
      :ok -> :ok
      {:error, {:already_loaded, :gitgood}} -> :ok
      _ -> {:error, @failure}
    end
  end

  def run(action) do
    with :ok <- start(action), {:ok, result} <- Gitgood.NativeMaintenanceWorker.execute() do
      {:ok, result}
    else
      _ -> {:error, @failure}
    end
  catch
    :exit, _ -> {:error, @failure}
  end
end

defmodule Gitgood.NativeMaintenanceApplication do
  @moduledoc false
  use Application

  @impl true
  def start(_, action) when action in [:migrate, :bootstrap] do
    Gitgood.NativeOwnershipSupervisor.start_lifecycle_link(
      Application.fetch_env!(:gitgood, :storage_root),
      action,
      [Gitgood.Repo, {Gitgood.NativeMaintenanceWorker, action}]
    )
  end
end
