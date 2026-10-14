defmodule Gitgood.NativeMigrationInventory do
  @moduledoc "Protected flat migration inventory; reading it grants no execution authority."
  import Bitwise, only: [band: 2]

  def read do
    directory = Application.app_dir(:gitgood, "priv/repo/migrations")
    :ok = protected_directory(directory)
    {:ok, names} = File.ls(directory)
    true = length(names) in 1..1025

    Enum.each(names, fn name ->
      true = name === ".formatter.exs" or Regex.match?(~r/\A[0-9]+_.*\.exs\z/, name)
      {:ok, stat} = File.lstat(Path.join(directory, name))
      true = stat.type === :regular and stat.uid === 0 and stat.links === 1
      true = band(stat.mode, 0o022) === 0
    end)

    names
    |> Enum.reject(&(&1 === ".formatter.exs"))
    |> Enum.map(fn name -> name |> String.split("_", parts: 2) |> hd() |> String.to_integer() end)
    |> Enum.sort()
  end

  defp protected_directory(path) do
    {:ok, stat} = File.lstat(path)
    true = stat.type === :directory and stat.uid === 0 and band(stat.mode, 0o022) === 0
    if Path.dirname(path) === path, do: :ok, else: protected_directory(Path.dirname(path))
  end

  def match_build(build, packaged) do
    with true <- is_map(build) and build["dirty"] === false,
         candidate when is_binary(candidate) <- build["candidate"],
         true <- Regex.match?(~r/\A[0-9a-f]{40}\z/, candidate),
         declared when is_list(declared) <- build["migrations"],
         true <- length(declared) in 1..1024,
         true <- Enum.all?(declared, &(is_binary(&1) and Regex.match?(~r/\A[0-9]+\z/, &1))),
         versions <- Enum.map(declared, &String.to_integer/1),
         true <- Enum.all?(versions, &(&1 > 0 and &1 < 9_223_372_036_854_775_808)),
         true <- versions === Enum.sort(Enum.uniq(versions)) and versions === packaged do
      {:ok, versions}
    else
      _ -> :error
    end
  rescue
    _ -> :error
  end
end
