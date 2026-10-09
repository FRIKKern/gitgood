defmodule Gitgood.Git do
  @moduledoc "Trusted Git process boundary. Arguments are separate; storage uses internal UUIDs."
  def executable,
    do: Application.get_env(:gitgood, :git_executable, "git") |> System.find_executable()

  def path(repository),
    do:
      Path.join(Application.fetch_env!(:gitgood, :storage_root), repository.storage_key <> ".git")

  def init(repository) do
    path = path(repository)

    with :ok <- File.mkdir_p(Path.dirname(path)),
         {_, 0} <-
           run([
             "init",
             "--bare",
             "--template=",
             "--object-format=sha1",
             "--initial-branch=main",
             path
           ]),
         :ok <- settings(path),
         :ok <- install_hook(path) do
      :ok
    else
      _ -> {:error, :storage_failed}
    end
  rescue
    _ -> {:error, :storage_failed}
  end

  defp settings(path) do
    settings = [
      {"receive.fsckObjects", "true"},
      {"transfer.fsckObjects", "true"},
      {"receive.denyNonFastForwards", "true"},
      {"receive.denyDeletes", "true"},
      {"receive.maxInputSize", "33554432"},
      {"http.getanyfile", "false"},
      {"http.maxRequestBuffer", "33554432"}
    ]

    Enum.reduce_while(settings, :ok, fn {key, value}, _ ->
      case run(["--git-dir", path, "config", key, value]) do
        {_, 0} -> {:cont, :ok}
        _ -> {:halt, {:error, :storage_failed}}
      end
    end)
  end

  defp install_hook(path) do
    hooks = Path.join(path, "hooks")

    with :ok <- File.mkdir_p(hooks),
         :ok <-
           File.cp(
             Application.app_dir(:gitgood, "priv/pre-receive"),
             Path.join(hooks, "pre-receive")
           ),
         :ok <- File.chmod(Path.join(hooks, "pre-receive"), 0o700),
         {_, 0} <- run(["--git-dir", path, "config", "core.hooksPath", hooks]) do
      :ok
    else
      _ -> {:error, :storage_failed}
    end
  end

  def command_args(args), do: [executable(), "-c", "pack.threads=2" | args]

  def command(args, opts \\ []), do: Gitgood.Command.run(command_args(args), opts)

  def run(args, opts \\ []) do
    case command(args, opts) do
      {:ok, output, status} -> {output, status}
      {:error, _} -> {"", 1}
    end
  end

  def ref(repository, ref) do
    case command(
           [
             "--git-dir",
             path(repository),
             "for-each-ref",
             "--format=%(refname) %(objectname)",
             ref
           ],
           limit: 65536
         ) do
      {:ok, output, 0} ->
        prefix = ref <> " "

        case String.split(output, "\n", trim: true)
             |> Enum.find(&String.starts_with?(&1, prefix)) do
          nil ->
            {:error, :missing_ref}

          line ->
            value = String.replace_prefix(line, prefix, "")

            if Regex.match?(~r/\A[0-9a-f]{40}\z/, value),
              do: {:ok, value},
              else: {:error, :ref_unavailable}
        end

      _ ->
        {:error, :ref_unavailable}
    end
  end
end
