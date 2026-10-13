defmodule Gitgood.InstallationGenerationAdmission do
  @moduledoc "Bounded initial admission through the fixed Root-installed generation observer."
  import Bitwise

  @python "/usr/bin/python3.12"
  @helper "/opt/gitgood/native/v2/native_generation_admission_entry.py"
  @maximum 16_385
  @timeout 30_000
  @uuid ~r/\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\z/

  def admit(root, mode) do
    with {:unix, :linux} <- :os.type(),
         {:ok, installation} <- installation(root),
         {:ok, worker} <- worker(mode),
         {:ok, python} <- trusted_file(@python, true),
         {:ok, helper} <- trusted_file(@helper, false),
         request <- %{
           protocol: 2,
           installation: installation,
           worker: worker,
           owner_pid: String.to_integer(System.pid())
         },
         {:ok, output} <- exchange(Jason.encode!(request) <> "\n"),
         {:ok, value} <- Jason.decode(output),
         :ok <- validate(value, installation, worker, String.to_integer(System.pid())),
         {:ok, ^python} <- trusted_file(@python, true),
         {:ok, ^helper} <- trusted_file(@helper, false) do
      {:ok, value}
    else
      _ -> {:error, :installation_generation_unavailable}
    end
  rescue
    _ -> {:error, :installation_generation_unavailable}
  catch
    :exit, _ -> {:error, :installation_generation_unavailable}
  end

  defp installation(root) when is_binary(root) do
    case String.split(root, "/") do
      ["", "var", "lib", "gitgood", "installations", identity, "storage"] ->
        if Regex.match?(@uuid, identity), do: {:ok, identity}, else: :error

      _ ->
        :error
    end
  end

  defp installation(_), do: :error
  defp worker(:runtime), do: {:ok, "native"}
  defp worker(mode) when mode in [:backup, :restore, :migrate], do: {:ok, "maintenance"}
  defp worker(_), do: :error

  defp trusted_file(path, executable) do
    with {:ok, info} <- File.lstat(path),
         true <-
           info.type == :regular and info.uid == 0 and info.links == 1 and
             (info.mode &&& 0o022) == 0,
         true <- not executable or (info.mode &&& 0o111) != 0,
         true <- trusted_parents?(Path.dirname(path)) do
      {:ok,
       {info.inode, info.major_device, info.minor_device, info.size, info.mtime, info.ctime,
        info.mode}}
    else
      _ -> :error
    end
  end

  defp trusted_parents?(path) do
    case File.lstat(path) do
      {:ok, info} when info.type == :directory and info.uid == 0 ->
        (info.mode &&& 0o022) == 0 and (path == "/" or trusted_parents?(Path.dirname(path)))

      _ ->
        false
    end
  end

  defp exchange(request) do
    environment =
      System.get_env()
      |> Map.drop(["PATH", "LANG", "PYTHONDONTWRITEBYTECODE"])
      |> Enum.map(fn {key, _} -> {String.to_charlist(key), false} end)

    environment =
      environment ++
        [
          {~c"PATH", ~c"/usr/sbin:/usr/bin:/sbin:/bin"},
          {~c"LANG", ~c"C.UTF-8"},
          {~c"PYTHONDONTWRITEBYTECODE", ~c"1"}
        ]

    port =
      Port.open({:spawn_executable, @python}, [
        :binary,
        :exit_status,
        :use_stdio,
        :stderr_to_stdout,
        {:args, ["-I", "-S", @helper]},
        {:env, environment}
      ])

    try do
      true = Port.command(port, request)
      receive_output(port, <<>>, System.monotonic_time(:millisecond) + @timeout)
    after
      if Port.info(port), do: Port.close(port)
    end
  end

  defp receive_output(port, collected, deadline) do
    remaining = max(0, deadline - System.monotonic_time(:millisecond))

    receive do
      {^port, {:data, bytes}} when byte_size(collected) + byte_size(bytes) <= @maximum ->
        receive_output(port, collected <> bytes, deadline)

      {^port, {:exit_status, 0}} ->
        if byte_size(collected) > 0 and byte_size(collected) <= @maximum and
             String.ends_with?(collected, "\n"), do: {:ok, collected}, else: :error

      {^port, _} ->
        :error
    after
      remaining -> :error
    end
  end

  @doc false
  def validate(value, installation, worker, owner_pid) do
    fields =
      ~w(protocol installation worker pointer binding_sha256 worker_observation database seal_file published_generation_admitted writer_exclusion_established installation_readiness_established lifecycle_responsibility_admitted)

    fields =
      if is_map(value) and Map.has_key?(value, "lifecycle_observation"),
        do: ["lifecycle_observation" | fields],
        else: fields

    with true <- is_map(value) and MapSet.new(Map.keys(value)) == MapSet.new(fields),
         true <-
           value["protocol"] === 2 and value["installation"] === installation and
             value["worker"] === worker,
         true <-
           value["published_generation_admitted"] === true and
             value["writer_exclusion_established"] === false and
             value["installation_readiness_established"] === false and
             value["lifecycle_responsibility_admitted"] === false,
         observation when is_map(observation) <- value["worker_observation"],
         true <- observation["worker"] === worker and observation["owner"]["pid"] === owner_pid,
         true <- unsigned_text?(observation["owner"]["birth"]),
         true <-
           observation["service_scope"]["installation"] === installation and
             observation["service_scope"]["protocol"] === 2 and
             observation["service_scope"]["service_scope_observed"] === true,
         pointer when is_map(pointer) <- value["pointer"],
         true <-
           MapSet.new(Map.keys(pointer)) ==
             MapSet.new(~w(protocol installation operation generation_sha256 transition_sha256)),
         true <-
           pointer["installation"] === installation and pointer["protocol"] === 2 and
             is_binary(pointer["operation"]) and Regex.match?(@uuid, pointer["operation"]) and
             digest?(pointer["generation_sha256"]) and digest?(pointer["transition_sha256"]),
         true <- valid_lifecycle?(value, pointer, worker),
         true <- digest?(value["binding_sha256"]),
         seal when is_map(seal) <- value["seal_file"],
         true <- MapSet.new(Map.keys(seal)) == MapSet.new(~w(path device inode bytes sha256)),
         true <-
           Enum.all?(~w(device inode bytes), &(is_integer(seal[&1]) and seal[&1] > 0)) and
             digest?(seal["sha256"]),
         true <-
           seal["path"] ===
             "/etc/gitgood/installations/" <> installation <> "/generation-admission-v2.json" do
      :ok
    else
      _ -> {:error, :invalid_generation_admission}
    end
  rescue
    _ -> {:error, :invalid_generation_admission}
  end

  defp valid_lifecycle?(value, pointer, worker) do
    case Map.fetch(value, "lifecycle_observation") do
      :error ->
        true

      {:ok, observed} ->
        fields =
          ~w(operation purpose candidate request_sha256 origin_sha256 snapshot_sha256 generation_sha256 epoch stage recorded_status worker)

        is_map(observed) and MapSet.new(Map.keys(observed)) == MapSet.new(fields) and
          is_binary(observed["operation"]) and Regex.match?(@uuid, observed["operation"]) and
          observed["operation"] !== "00000000-0000-0000-0000-000000000000" and
          observed["operation"] !== value["installation"] and
          is_binary(observed["candidate"]) and
          Regex.match?(~r/\A[0-9a-f]{40}\z/, observed["candidate"]) and
          Enum.all?(
            ~w(request_sha256 origin_sha256 snapshot_sha256 generation_sha256),
            &digest?(observed[&1])
          ) and
          is_integer(observed["epoch"]) and observed["epoch"] > 0 and
          observed["epoch"] < 18_446_744_073_709_551_616 and
          observed["worker"] === worker and lifecycle_window?(observed, pointer, worker)
    end
  end

  defp lifecycle_window?(observed, pointer, worker) do
    case {observed["purpose"], observed["recorded_status"], worker} do
      {"native_initial_enrollment", "running", "maintenance"} ->
        observed["stage"] in ["migrate", "bootstrap"] and
          observed["generation_sha256"] === pointer["generation_sha256"]

      {"native_initial_enrollment", "running", "native"} ->
        observed["stage"] in ["verify", "activate", "enroll"] and
          observed["generation_sha256"] === pointer["generation_sha256"]

      {"native_upgrade_execution", "running", "maintenance"} ->
        observed["stage"] === "migrate" and
          observed["generation_sha256"] === pointer["generation_sha256"]

      {"native_upgrade_execution", "running", "native"} ->
        observed["stage"] in ["verify", "activate", "public_verify"] and
          observed["generation_sha256"] === pointer["generation_sha256"]

      {"native_initial_enrollment", "complete", "native"} ->
        observed["stage"] === "enroll"

      {"native_upgrade_execution", "complete", "native"} ->
        observed["stage"] === "public_verify"

      _ ->
        false
    end
  end

  defp digest?(value), do: is_binary(value) and Regex.match?(~r/\A[0-9a-f]{64}\z/, value)

  defp unsigned_text?(value) when is_binary(value) do
    byte_size(value) <= 20 and Regex.match?(~r/\A[1-9][0-9]{0,19}\z/, value) and
      String.to_integer(value) < 18_446_744_073_709_551_616
  end

  defp unsigned_text?(_), do: false
end
