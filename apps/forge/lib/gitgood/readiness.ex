defmodule Gitgood.Readiness do
  alias Gitgood.{Build, Repo}

  def check do
    native = Application.get_env(:gitgood, :supervision_profile) === "systemd-v2"
    installation = installation?()
    admitted = not native or installation

    checks = %{
      database: admitted and database?(),
      installation: installation,
      storage: admitted and storage?(),
      executables: executables?(),
      ssh: is_nil(Application.get_env(:gitgood, :ssh_port)) or Gitgood.SSHDaemon.public().enabled,
      artifact: Application.get_env(:gitgood, :environment) != :prod or Build.valid?()
    }

    checks =
      if native,
        do: Map.put(checks, :installation, installation and installation?()),
        else: checks

    %{ready: Enum.all?(checks, fn {_, value} -> value end), checks: checks}
  end

  defp installation? do
    if Application.get_env(:gitgood, :supervision_profile) === "systemd-v2" do
      {Gitgood.NativeOwnershipStartup, startup, _, _} =
        List.keyfind(
          Supervisor.which_children(Gitgood.Supervisor),
          Gitgood.NativeOwnershipStartup,
          0
        )

      Gitgood.NativeOwnershipStartup.current(startup) === :ok
    else
      Gitgood.InstallationLease.ready?()
    end
  rescue
    _ -> false
  catch
    :exit, _ -> false
  end

  defp database? do
    case Repo.query("SELECT version::text FROM public.schema_migrations ORDER BY version", [],
           timeout: 3000
         ) do
      {:ok, %{rows: rows}} ->
        actual = List.flatten(rows)

        if Application.get_env(:gitgood, :supervision_profile) === "systemd-v2" do
          actual !== [] and actual === Build.identity()["migrations"] and
            Gitgood.NativeMaintenanceWorker.validate_database(:bootstrap, %{
              "target_versions" => Enum.map(actual, &String.to_integer/1)
            }) === :ok
        else
          Enum.all?(Build.identity()["migrations"] || [], &(&1 in actual))
        end

      _ ->
        false
    end
  rescue
    _ -> false
  end

  defp storage? do
    root = Application.fetch_env!(:gitgood, :storage_root)
    path = Path.join(root, ".readiness-" <> Ecto.UUID.generate())

    with true <- File.dir?(root),
         {:ok, file} <- File.open(path, [:write, :exclusive, :binary]) do
      result = IO.binwrite(file, "probe") == :ok
      File.close(file)
      File.rm(path)
      result
    else
      _ -> false
    end
  rescue
    _ -> false
  end

  defp executables? do
    Enum.all?(
      [
        Application.fetch_env!(:gitgood, :git_executable),
        Application.fetch_env!(:gitgood, :python_executable)
      ],
      &(not is_nil(System.find_executable(&1)))
    )
  end
end
