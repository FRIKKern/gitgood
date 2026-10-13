defmodule Gitgood.NativeOwnershipPublication do
  @moduledoc "Bounded publication through the fixed protected ownership entry."
  import Bitwise

  @python "/usr/bin/python3.12"
  @entry "/opt/gitgood/native/v2/native_ownership_publication_entry.py"
  @backend_entry "/opt/gitgood/native/v2/native_backend_observation_entry.py"
  @handoff_entry "/opt/gitgood/native/v2/native_ownership_handoff_entry.py"
  @fields ~w(protocol kind installation operation candidate mode binding_sha256 pointer scope owner database_session guard backend_kernel)
  @reply_fields ~w(protocol status ownership_marker_retained operation marker_sha256 record_sha256 installation_readiness_established replacement_admitted writer_exclusion_established lifecycle_responsibility_admitted)
  @timeout 60_000
  @failure {:error, :native_ownership_publication_unavailable}

  def admit_owner(admission, authority, mode) do
    with {:unix, :linux} <- :os.type(),
         true <- mode in [:runtime, :backup, :restore, :migrate],
         request <-
           canonical(%{
             "protocol" => 4,
             "action" => "admit",
             "installation" => admission["installation"],
             "mode" => Atom.to_string(mode),
             "owner_pid" => String.to_integer(System.pid())
           }),
         {:ok, python} <- trusted_file(@python, true),
         {:ok, entry} <- trusted_file(@handoff_entry, false),
         {:ok, output} <- exchange(request <> "\n", @handoff_entry),
         {:ok, value} <- Jason.decode(output),
         :ok <- validate_handoff_reply(value, admission, authority, mode),
         true <- output === canonical(value) <> "\n",
         {:ok, ^python} <- trusted_file(@python, true),
         {:ok, ^entry} <- trusted_file(@handoff_entry, false) do
      {:ok, value}
    else
      _ -> @failure
    end
  rescue
    _ -> @failure
  catch
    _, _ -> @failure
  end

  @doc false
  def validate_handoff_reply(value, admission, authority, mode) do
    observation = admission["worker_observation"]

    with true <-
           closed?(
             value,
             ~w(protocol status installation operation candidate claim mode pointer predecessor_sha256 reservation_sha256 owner controller)
           ),
         true <- value["protocol"] === 4 and value["status"] === "admitted",
         true <- Enum.all?(~w(installation operation candidate), &(value[&1] === authority[&1])),
         true <-
           value["installation"] === admission["installation"] and
             value["mode"] === Atom.to_string(mode),
         true <-
           value["pointer"] === admission["pointer"] and value["owner"] === observation["owner"],
         true <- value["controller"] === observation["service_scope"]["manager"],
         true <-
           is_binary(value["claim"]) and
             Regex.match?(
               ~r/\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\z/,
               value["claim"]
             ),
         true <-
           value["claim"] not in [
             value["installation"],
             value["operation"],
             value["pointer"]["operation"]
           ],
         true <- digest?(value["reservation_sha256"]),
         true <- is_nil(value["predecessor_sha256"]) or digest?(value["predecessor_sha256"]) do
      :ok
    else
      _ -> :error
    end
  rescue
    _ -> :error
  end

  def observe_backend(admission, session) do
    owner_pid = String.to_integer(System.pid())
    installation = admission["installation"]
    worker = get_in(admission, ["worker_observation", "worker"])

    with {:unix, :linux} <- :os.type(),
         :ok <-
           Gitgood.InstallationGenerationAdmission.validate(
             admission,
             installation,
             worker,
             owner_pid
           ),
         true <- closed?(session, ~w(database backend_pid backend_birth)),
         true <- session["database"] === admission["database"],
         :ok <- Gitgood.InstallationDatabaseSession.validate_database(session["database"]),
         request <-
           canonical(%{
             "protocol" => 2,
             "kind" => "native_backend_observation",
             "installation" => installation,
             "worker" => worker,
             "owner_pid" => owner_pid,
             "database_session" => session
           }),
         true <- byte_size(request) <= 8_192,
         {:ok, python} <- trusted_file(@python, true),
         {:ok, entry} <- trusted_file(@backend_entry, false),
         {:ok, output} <- exchange(request <> "\n", @backend_entry),
         {:ok, value} <- Jason.decode(output),
         :ok <- validate_backend_reply(value, admission, session),
         true <- output === canonical(value) <> "\n",
         {:ok, ^python} <- trusted_file(@python, true),
         {:ok, ^entry} <- trusted_file(@backend_entry, false) do
      {:ok, value["kernel_record"]}
    else
      _ -> {:error, :native_backend_observation_unavailable}
    end
  rescue
    _ -> {:error, :native_backend_observation_unavailable}
  catch
    _, _ -> {:error, :native_backend_observation_unavailable}
  end

  @doc false
  def validate_backend_reply(value, admission, session) do
    observation = admission["worker_observation"]

    with true <-
           closed?(
             value,
             ~w(protocol status installation worker owner_pid owner kernel_record service_scope_sha256 ownership_retained writer_exclusion_established installation_readiness_established replacement_admitted)
           ),
         true <- value["protocol"] === 2 and value["status"] === "observed",
         true <-
           value["installation"] === admission["installation"] and
             value["worker"] === observation["worker"],
         true <-
           value["owner_pid"] === observation["owner"]["pid"] and
             value["owner"] === observation["owner"],
         true <-
           value["service_scope_sha256"] ===
             :crypto.hash(:sha256, canonical(observation["service_scope"]))
             |> Base.encode16(case: :lower),
         true <-
           Enum.all?(
             ~w(ownership_retained writer_exclusion_established installation_readiness_established replacement_admitted),
             &(value[&1] === false)
           ),
         :ok <- validate_backend_kernel(value["kernel_record"], admission, session),
         true <- byte_size(canonical(value)) <= 4_096 do
      :ok
    else
      _ -> :error
    end
  rescue
    _ -> :error
  end

  @doc false
  def validate_backend_kernel(kernel, admission, session) do
    scope = kernel["server_scope"]
    observation = admission["worker_observation"]

    with true <- closed?(kernel, ~w(protocol kind server_scope database_session kernel_birth)),
         true <- kernel["protocol"] === 2 and kernel["kind"] === "native_backend_kernel_identity",
         true <-
           kernel["database_session"] === session and
             session["database"] === admission["database"],
         true <- closed?(session, ~w(database backend_pid backend_birth)),
         :ok <- Gitgood.InstallationDatabaseSession.validate_database(session["database"]),
         true <- is_integer(session["backend_pid"]) and session["backend_pid"] in 1..2_147_483_647,
         true <-
           positive_birth?(session["backend_birth"]) and positive_birth?(kernel["kernel_birth"]),
         true <- closed?(scope, ~w(boot_id pid_namespace time_namespace postgres_uid)),
         true <- scope["boot_id"] === observation["service_scope"]["boot_id"],
         true <-
           is_binary(scope["pid_namespace"]) and
             Regex.match?(~r/\Apid:\[[1-9][0-9]{0,19}\]\z/, scope["pid_namespace"]),
         true <-
           is_binary(scope["time_namespace"]) and
             Regex.match?(~r/\Atime:\[[1-9][0-9]{0,19}\]\z/, scope["time_namespace"]),
         true <- is_integer(scope["postgres_uid"]) and scope["postgres_uid"] in 1..4_294_967_295 do
      :ok
    else
      _ -> :error
    end
  rescue
    _ -> :error
  end

  defp closed?(value, fields),
    do: is_map(value) and MapSet.new(Map.keys(value)) === MapSet.new(fields)

  defp positive_birth?(value),
    do:
      is_binary(value) and Regex.match?(~r/\A[1-9][0-9]{0,19}\z/, value) and
        String.to_integer(value) < 18_446_744_073_709_551_616

  def publish(record) do
    selected_entry = if record["protocol"] == 4, do: @handoff_entry, else: @entry

    with {:unix, :linux} <- :os.type(),
         {:ok, request, record_digest} <- request(record, String.to_integer(System.pid())),
         {:ok, python} <- trusted_file(@python, true),
         {:ok, entry} <- trusted_file(selected_entry, false),
         {:ok, output} <- exchange(request, selected_entry),
         {:ok, value} <- Jason.decode(output),
         :ok <- validate_reply(value, record["operation"], record_digest, record["claim"]),
         true <- output == canonical(value) <> "\n",
         {:ok, ^python} <- trusted_file(@python, true),
         {:ok, ^entry} <- trusted_file(selected_entry, false) do
      {:ok, value}
    else
      _ -> @failure
    end
  rescue
    _ -> @failure
  catch
    _, _ -> @failure
  end

  @doc false
  def request(record, owner_pid) do
    fields =
      if record["protocol"] == 4,
        do: @fields ++ ~w(claim predecessor_sha256 reservation_sha256),
        else: @fields

    with true <- is_map(record) and MapSet.new(Map.keys(record)) == MapSet.new(fields),
         true <-
           record["protocol"] in [3, 4] and record["kind"] === "native_application_ownership",
         true <- valid_claim?(record),
         true <- is_integer(owner_pid) and owner_pid > 1 and record["owner"]["pid"] === owner_pid,
         true <- record["mode"] in ~w(runtime backup restore migrate),
         :ok <-
           validate_backend_kernel(
             record["backend_kernel"],
             %{
               "database" => record["database_session"]["database"],
               "worker_observation" => %{"service_scope" => record["scope"]}
             },
             record["database_session"]
           ),
         bytes <- canonical(record),
         true <- byte_size(bytes) <= 16_384,
         request <-
           canonical(
             if record["protocol"] == 4,
               do: %{"protocol" => 4, "action" => "publish", "record" => record},
               else: %{"protocol" => 3, "record" => record}
           ),
         true <- byte_size(request) <= 32_768 do
      digest = :crypto.hash(:sha256, bytes) |> Base.encode16(case: :lower)
      {:ok, request <> "\n", digest}
    else
      _ -> @failure
    end
  rescue
    _ -> @failure
  end

  @doc false
  def validate_reply(value, operation, digest, claim \\ nil) do
    fields = if is_nil(claim), do: @reply_fields, else: @reply_fields ++ ["claim"]
    protocol = if is_nil(claim), do: 3, else: 4

    if is_map(value) and MapSet.new(Map.keys(value)) == MapSet.new(fields) and
         value["protocol"] === protocol and value["claim"] === claim and
         value["status"] === "retained" and
         value["ownership_marker_retained"] === true and value["operation"] === operation and
         value["record_sha256"] === digest and digest?(digest) and
         digest?(value["marker_sha256"]) and
         Enum.all?(
           ~w(installation_readiness_established replacement_admitted writer_exclusion_established lifecycle_responsibility_admitted),
           &(value[&1] === false)
         ) do
      :ok
    else
      :error
    end
  rescue
    _ -> :error
  end

  @doc false
  def canonical(value), do: encode(value, 0) |> IO.iodata_to_binary()

  defp encode(_, depth) when depth > 12, do: raise(ArgumentError)
  defp encode(value, _) when is_boolean(value) or is_nil(value), do: Jason.encode!(value)
  defp encode(value, _) when is_integer(value), do: Integer.to_string(value)

  defp encode(value, _) when is_binary(value) do
    if not String.valid?(value), do: raise(ArgumentError)

    value
    |> Jason.encode!()
    |> String.to_charlist()
    |> Enum.map(fn
      point when point < 128 ->
        <<point>>

      point when point <= 0xFFFF ->
        unicode_escape(point)

      point ->
        shifted = point - 0x10000
        [unicode_escape(0xD800 + (shifted >>> 10)), unicode_escape(0xDC00 + (shifted &&& 0x3FF))]
    end)
  end

  defp encode(value, depth) when is_map(value) and map_size(value) <= 128 do
    if not Enum.all?(Map.keys(value), &is_binary/1), do: raise(ArgumentError)

    pairs =
      value
      |> Enum.sort_by(&elem(&1, 0))
      |> Enum.map(fn {key, child} ->
        [encode(key, depth + 1), ":", encode(child, depth + 1)]
      end)

    ["{", Enum.intersperse(pairs, ","), "}"]
  end

  defp encode(value, depth) when is_list(value) and length(value) <= 128,
    do: ["[", Enum.intersperse(Enum.map(value, &encode(&1, depth + 1)), ","), "]"]

  defp encode(_, _), do: raise(ArgumentError)

  defp unicode_escape(point),
    do: "\\u" <> String.pad_leading(Integer.to_string(point, 16) |> String.downcase(), 4, "0")

  defp digest?(value), do: is_binary(value) and Regex.match?(~r/\A[0-9a-f]{64}\z/, value)

  defp valid_claim?(%{"protocol" => 3}), do: true

  defp valid_claim?(%{"protocol" => 4} = record) do
    is_binary(record["claim"]) and
      Regex.match?(
        ~r/\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\z/,
        record["claim"]
      ) and
      record["claim"] not in [
        record["installation"],
        record["operation"],
        record["pointer"]["operation"]
      ] and
      digest?(record["reservation_sha256"]) and
      (is_nil(record["predecessor_sha256"]) or digest?(record["predecessor_sha256"]))
  end

  defp valid_claim?(_), do: false

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

  defp exchange(request, entry) do
    environment =
      System.get_env()
      |> Map.drop(["PATH", "LANG"])
      |> Enum.map(fn {key, _} -> {String.to_charlist(key), false} end)

    port =
      Port.open({:spawn_executable, @python}, [
        :binary,
        :exit_status,
        :use_stdio,
        {:args, ["-I", "-S", "-B", entry]},
        {:env, environment ++ [{~c"PATH", ~c"/usr/bin:/bin"}, {~c"LANG", ~c"C.UTF-8"}]}
      ])

    try do
      true = Port.command(port, request)
      receive_output(port, <<>>, System.monotonic_time(:millisecond) + @timeout)
    after
      if Port.info(port), do: Port.close(port)
    end
  end

  defp receive_output(port, collected, deadline) do
    remaining = deadline - System.monotonic_time(:millisecond)

    if remaining <= 0 do
      :error
    else
      receive do
        {^port, {:data, bytes}} when byte_size(collected) + byte_size(bytes) <= 4_097 ->
          receive_output(port, collected <> bytes, deadline)

        {^port, {:exit_status, 0}} ->
          if byte_size(collected) > 0 and String.ends_with?(collected, "\n"),
            do: {:ok, collected},
            else: :error

        {^port, _} ->
          :error
      after
        remaining -> :error
      end
    end
  end
end
