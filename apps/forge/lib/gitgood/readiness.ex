defmodule Gitgood.Readiness do
  alias Gitgood.{Build, Repo}

  def check do
    checks = %{
      database: database?(),
      storage: storage?(),
      executables: executables?(),
      artifact: Application.get_env(:gitgood, :environment) != :prod or Build.valid?()
    }

    %{ready: Enum.all?(checks, fn {_, value} -> value end), checks: checks}
  end

  defp database? do
    case Repo.query("SELECT version::text FROM schema_migrations", [], timeout: 3000) do
      {:ok, %{rows: rows}} ->
        actual = List.flatten(rows)
        Enum.all?(Build.identity()["migrations"] || [], &(&1 in actual))

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
