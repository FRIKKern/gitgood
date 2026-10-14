defmodule Gitgood.NativeRuntime do
  @moduledoc "Fixed permanent native runtime; activation accepts no worker or program overrides."
  @app :gitgood_native_runtime
  @failure :native_runtime_unavailable

  def start do
    with :ok <- load_product(),
         true <- Application.get_env(:gitgood, :supervision_profile) === "systemd-v2",
         root when is_binary(root) <- Application.fetch_env!(:gitgood, :storage_root),
         :ok <-
           Gitgood.NativeOwnershipStartup.validate_lifecycle_options(root: root, action: :runtime),
         true <-
           not Enum.any?(Application.started_applications(), fn {app, _, _} ->
             app in [:gitgood, :gitgood_native_maintenance, @app]
           end),
         dependencies when is_list(dependencies) <- Application.spec(:gitgood, :applications),
         :ok <-
           :application.load(
             {:application, @app,
              [
                vsn: ~c"1",
                mod: {Gitgood.NativeRuntimeApplication, []},
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

  defp load_product do
    case Application.load(:gitgood) do
      :ok -> :ok
      {:error, {:already_loaded, :gitgood}} -> :ok
      _ -> {:error, @failure}
    end
  end

  def run do
    with :ok <- start(), {:ok, outcome} <- Gitgood.NativeRuntimeWorker.activate() do
      {:ok, outcome}
    else
      _ -> {:error, @failure}
    end
  catch
    :exit, _ -> {:error, @failure}
  end
end

defmodule Gitgood.NativeRuntimeApplication do
  @moduledoc false
  use Application

  @impl true
  def start(_, []) do
    Gitgood.NativeOwnershipSupervisor.start_lifecycle_link(
      Application.fetch_env!(:gitgood, :storage_root),
      :runtime,
      [
        {Gitgood.Repo, parameters: [search_path: "pg_catalog, public"]},
        Gitgood.NativeRuntimeWorker
      ]
    )
  end
end
