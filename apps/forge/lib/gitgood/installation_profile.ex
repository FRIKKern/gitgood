defmodule Gitgood.InstallationProfile do
  @moduledoc "Select startup policy before mutation; selection grants no native admission."

  @native "systemd-v2"
  @uuid "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
  @root Regex.compile!("\\A/var/lib/gitgood/installations/(#{@uuid})/storage\\z")
  @group Regex.compile!(
           "\\A0::/system.slice/gitgood-installation-(#{@uuid})\\.service/(native|maintenance)\\n?\\z"
         )
  @modes [:runtime, :backup, :restore, :migrate]

  def resolve(requested, root, mode) do
    with true <-
           is_binary(root) and byte_size(root) in 1..4096 and not String.contains?(root, <<0>>),
         {:ok, evidence} <- evidence(root) do
      select(requested, root, mode, evidence)
    else
      _ -> {:error, :installation_profile_unavailable}
    end
  rescue
    _ -> {:error, :installation_profile_unavailable}
  end

  def ensure_development(requested, root, mode) do
    case resolve(requested, root, mode) do
      {:ok, %{profile: :development_v1}} -> :ok
      {:ok, %{profile: :systemd_v2}} -> {:error, :installation_native_ownership_unavailable}
      {:error, reason} -> {:error, reason}
    end
  end

  defp evidence(root) do
    paths =
      Enum.map(
        [".gitgood-runtime-v2.json", ".gitgood-maintenance-v2.json", ".gitgood-ownership-v2"],
        &Path.join(root, &1)
      )

    paths =
      case Regex.run(@root, root) do
        [_, installation] ->
          paths ++
            [
              "/etc/gitgood/installations/#{installation}/generation-admission-v2.json",
              Path.join(Path.dirname(root), "history/durable-binding-v2.json"),
              Path.join(Path.dirname(root), "history/current-generation-v2.json"),
              Path.join(Path.dirname(root), "history/generation-records-v2")
            ]

        _ ->
          paths
      end

    with {:ok, native_files} <- presence(paths), {:ok, kernel} <- kernel_context() do
      {:ok,
       %{
         native_files: native_files,
         kernel: kernel,
         platform: :os.type(),
         architecture: to_string(:erlang.system_info(:system_architecture))
       }}
    end
  end

  defp presence(paths) do
    Enum.reduce_while(paths, {:ok, false}, fn path, {:ok, found} ->
      case File.lstat(path) do
        {:error, :enoent} -> {:cont, {:ok, found}}
        {:ok, _} -> {:cont, {:ok, true}}
        _ -> {:halt, :error}
      end
    end)
  end

  defp kernel_context do
    case :os.type() do
      {:unix, :linux} ->
        with {:ok, bytes} <- File.read("/proc/self/cgroup"), true <- byte_size(bytes) <= 4096 do
          {:ok, decode_kernel(bytes)}
        else
          _ -> :error
        end

      _ ->
        {:ok, :none}
    end
  end

  @doc false
  def decode_kernel(bytes) when is_binary(bytes) and byte_size(bytes) <= 4096 do
    case Regex.run(@group, bytes) do
      [_, installation, worker] -> {:managed, installation, worker}
      _ -> if String.contains?(bytes, "gitgood-installation-"), do: :invalid_native, else: :none
    end
  end

  def decode_kernel(_), do: :invalid_native

  @doc false
  def select(requested, root, mode, evidence) when mode in @modes do
    case {requested, evidence} do
      {nil, %{native_files: false, kernel: :none}} ->
        {:ok, %{profile: :development_v1}}

      {nil, _} ->
        {:error, :installation_native_profile_required}

      {@native,
       %{
         platform: {:unix, :linux},
         architecture: architecture,
         kernel: {:managed, installation, worker}
       }} ->
        expected_worker = if mode == :runtime, do: "native", else: "maintenance"

        if String.starts_with?(architecture, "x86_64-") and
             Regex.run(@root, root) == [root, installation] and worker == expected_worker do
          {:ok, %{profile: :systemd_v2, installation: installation, worker: worker}}
        else
          {:error, :installation_profile_unavailable}
        end

      _ ->
        {:error, :installation_profile_unavailable}
    end
  rescue
    _ -> {:error, :installation_profile_unavailable}
  end

  def select(_, _, _, _), do: {:error, :installation_profile_unavailable}
end
