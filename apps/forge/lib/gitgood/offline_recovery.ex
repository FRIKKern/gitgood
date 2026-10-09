defmodule Gitgood.OfflineRecovery do
  @moduledoc "Offline release commands; no listeners or mutation workers are started."

  def run(mode) when mode in [:backup, :restore, :checkpoint] do
    lease_mode = if mode == :checkpoint, do: :backup, else: mode

    Gitgood.InstallationLease.with_offline(lease_mode, fn lease ->
      {:ok, context} = Gitgood.InstallationLease.context(lease)
      config = Gitgood.Repo.config()

      unless config[:hostname] in ["localhost", "127.0.0.1"] and config[:ssl] in [nil, false],
        do: raise("Offline recovery requires the supported local PostgreSQL profile")

      environment = [
        {"GITGOOD_RECOVERY_CONTEXT", Jason.encode!(context)},
        {"PGHOST", config[:hostname]},
        {"PGPORT", to_string(config[:port] || 5432)},
        {"PGUSER", config[:username]},
        {"PGPASSWORD", config[:password] || ""},
        {"PGDATABASE", config[:database]},
        {"GITGOOD_PYTHON", Application.fetch_env!(:gitgood, :python_executable)},
        {"GITGOOD_GIT", Application.fetch_env!(:gitgood, :git_executable)}
      ]

      script = Application.app_dir(:gitgood, "priv/operations/recovery-operator.mjs")
      node = System.get_env("GITGOOD_NODE", "node")

      case System.cmd(node, [script, to_string(mode)], env: environment, stderr_to_stdout: true) do
        {output, 0} ->
          receipt = Jason.decode!(output)
          if mode == :restore, do: finish_restore(lease, context.root)
          IO.puts(Jason.encode!(Map.put(receipt, "status", "complete")))

        _ ->
          raise(
            "Offline recovery refused; keep private restore materials and the incomplete gate"
          )
      end
    end)
  rescue
    _ -> raise("Offline recovery failed; keep private restore materials and the incomplete gate")
  end

  defp finish_restore(lease, root) do
    configuration =
      System.fetch_env!("GITGOOD_RECOVERY_INSTALLATION")
      |> Path.join("configuration/installation.json")
      |> File.read!()
      |> Jason.decode!()

    encoded = configuration["forge"]["GITGOOD_CONNECTION_KEY"]

    key =
      case encoded do
        nil ->
          nil

        value ->
          {:ok, bytes} = Base.decode64(value)
          if byte_size(bytes) != 32, do: raise("Recovered key is invalid")
          bytes
      end

    Application.put_env(:gitgood, :connection_key, key)
    :ok = Gitgood.InstallationLease.verify_recovered(lease)
    :ok = Gitgood.InstallationLease.assert_held(lease)
    :ok = File.rm(Path.join(root, ".gitgood-restore-incomplete-v1.json"))
    python = Application.fetch_env!(:gitgood, :python_executable)
    script = Application.app_dir(:gitgood, "priv/operations/sync_directory.py")
    {"synced\n", 0} = System.cmd(python, ["-I", script, root], stderr_to_stdout: true)
  end
end
