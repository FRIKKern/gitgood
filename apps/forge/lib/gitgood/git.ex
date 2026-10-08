defmodule Gitgood.Git do
  @moduledoc "Trusted Git process boundary. Arguments are separate from executable; storage uses internal UUIDs."
  def path(repository),
    do:
      Path.join(Application.fetch_env!(:gitgood, :storage_root), repository.storage_key <> ".git")

  def init(repository) do
    path = path(repository)

    with :ok <- File.mkdir_p(Path.dirname(path)),
         {_, 0} <- run(["init", "--bare", "--template=", "--initial-branch=main", path]),
         {_, 0} <- run(["--git-dir", path, "config", "receive.fsckObjects", "true"]),
         {_, 0} <- run(["--git-dir", path, "config", "transfer.fsckObjects", "true"]) do
      :ok
    else
      _ -> {:error, :storage_failed}
    end
  rescue
    _ -> {:error, :storage_failed}
  end

  def run(args),
    do:
      System.cmd(Application.get_env(:gitgood, :git_executable, "git"), args,
        stderr_to_stdout: true,
        env: [
          {"GIT_CONFIG_NOSYSTEM", "1"},
          {"GIT_CONFIG_GLOBAL", if(match?({:win32, _}, :os.type()), do: "NUL", else: "/dev/null")}
        ]
      )
end
