defmodule Gitgood.NativeOwnershipPublication do
  @moduledoc "Bounded publication through the fixed protected ownership entry."
  import Bitwise

  @python "/usr/bin/python3.12"
  @entry "/opt/gitgood/native/v2/native_ownership_publication_entry.py"
  @fields ~w(protocol kind installation operation candidate mode binding_sha256 pointer scope owner database_session guard)
  @reply_fields ~w(protocol status ownership_marker_retained operation marker_sha256 record_sha256 installation_readiness_established replacement_admitted writer_exclusion_established lifecycle_responsibility_admitted)
  @timeout 60_000
  @failure {:error, :native_ownership_publication_unavailable}

  def publish(record) do
    with {:unix, :linux} <- :os.type(),
         {:ok, request, record_digest} <- request(record, String.to_integer(System.pid())),
         {:ok, python} <- trusted_file(@python, true),
         {:ok, entry} <- trusted_file(@entry, false),
         {:ok, output} <- exchange(request),
         {:ok, value} <- Jason.decode(output),
         :ok <- validate_reply(value, record["operation"], record_digest),
         true <- output == canonical(value) <> "\n",
         {:ok, ^python} <- trusted_file(@python, true),
         {:ok, ^entry} <- trusted_file(@entry, false) do
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
    with true <- is_map(record) and MapSet.new(Map.keys(record)) == MapSet.new(@fields),
         true <- record["protocol"] === 2 and record["kind"] === "native_application_ownership",
         true <- is_integer(owner_pid) and owner_pid > 1 and record["owner"]["pid"] === owner_pid,
         true <- record["mode"] in ~w(runtime backup restore migrate),
         bytes <- canonical(record),
         true <- byte_size(bytes) <= 16_384,
         request <- canonical(%{"protocol" => 2, "record" => record}),
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
  def validate_reply(value, operation, digest) do
    if is_map(value) and MapSet.new(Map.keys(value)) == MapSet.new(@reply_fields) and
         value["protocol"] === 2 and value["status"] === "retained" and
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
      |> Map.drop(["PATH", "LANG"])
      |> Enum.map(fn {key, _} -> {String.to_charlist(key), false} end)

    port =
      Port.open({:spawn_executable, @python}, [
        :binary,
        :exit_status,
        :use_stdio,
        {:args, ["-I", "-S", "-B", @entry]},
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
