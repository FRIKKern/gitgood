defmodule Gitgood.NativeOwnershipInputs do
  @moduledoc "Bounded private startup inputs; only protected claim publication admits ownership."
  import Bitwise
  alias Gitgood.NativeOwnershipPublication, as: Publication
  @authority_fields ~w(protocol kind installation operation candidate binding_sha256)
  @uuid ~r/\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\z/
  @metadata [
    :type,
    :inode,
    :major_device,
    :minor_device,
    :size,
    :mtime,
    :ctime,
    :uid,
    :gid,
    :mode,
    :links
  ]

  def read(storage, admission) do
    installation = admission["installation"]
    root = "/var/lib/gitgood/installations/" <> installation
    uid = admission["worker_observation"]["service_scope"]["uid"]

    with true <- storage == root <> "/storage" and valid_uuid?(installation),
         true <- is_integer(uid) and uid in 1..4_294_967_295,
         {:ok, authority} <-
           read_file(
             "/etc/gitgood/installations/" <> installation <> "/ownership-admission-v3.json",
             0,
             16_384,
             nil
           ),
         {:ok, configuration} <-
           read_file(root <> "/configuration/installation.json", uid, 131_072, root),
         {:ok, inputs} <- decode(configuration, authority, storage, admission) do
      {:ok, inputs}
    else
      _ -> {:error, :native_ownership_inputs_unavailable}
    end
  rescue
    _ -> {:error, :native_ownership_inputs_unavailable}
  catch
    :exit, _ -> {:error, :native_ownership_inputs_unavailable}
  end

  @doc false
  def decode(configuration_raw, authority_raw, storage, admission) do
    installation = admission["installation"]
    root = "/var/lib/gitgood/installations/" <> installation
    database = admission["database"]

    with true <- storage == root <> "/storage" and valid_uuid?(installation),
         true <- is_binary(configuration_raw) and byte_size(configuration_raw) in 1..131_072,
         true <- is_binary(authority_raw) and byte_size(authority_raw) in 1..16_384,
         {:ok, configuration} <- json(configuration_raw),
         {:ok, authority} <- json(authority_raw),
         true <- closed?(configuration, ~w(protocol installation forge web edge)),
         true <- configuration["protocol"] === 1 and configuration["installation"] == installation,
         true <-
           is_map(configuration["forge"]) and is_map(configuration["web"]) and
             is_map(configuration["edge"]),
         true <- configuration["forge"]["GITGOOD_INSTALLATION_ID"] == installation,
         true <- configuration["forge"]["GITGOOD_STORAGE"] == storage,
         true <- configuration["forge"]["GITGOOD_SSH_HOST_KEY_DIRECTORY"] == root <> "/ssh-host",
         true <- closed?(authority, @authority_fields),
         true <-
           authority["protocol"] === 3 and
             authority["kind"] === "native_application_ownership_seal",
         true <- authority["installation"] == installation and valid_uuid?(authority["operation"]),
         true <- authority["operation"] != installation,
         true <-
           is_binary(authority["candidate"]) and
             Regex.match?(~r/\A[0-9a-f]{40,64}\z/, authority["candidate"]),
         true <-
           is_binary(authority["binding_sha256"]) and
             Regex.match?(~r/\A[0-9a-f]{64}\z/, authority["binding_sha256"]),
         true <- authority["binding_sha256"] == admission["binding_sha256"],
         true <- Publication.canonical(authority) == authority_raw,
         :ok <- Gitgood.InstallationDatabaseSession.validate_database(database),
         {:ok, connection} <- connection(configuration["forge"]["DATABASE_URL"], database) do
      {:ok, %{authority: authority, connection: connection}}
    else
      _ -> {:error, :native_ownership_inputs_unavailable}
    end
  rescue
    _ -> {:error, :native_ownership_inputs_unavailable}
  catch
    :exit, _ -> {:error, :native_ownership_inputs_unavailable}
  end

  defp connection(value, database) do
    with true <-
           is_binary(value) and byte_size(value) in 1..8_192 and
             not String.contains?(value, <<0>>),
         uri <- URI.parse(value),
         true <-
           uri.scheme in ["postgres", "postgresql"] and uri.host in ["127.0.0.1", "localhost"],
         true <- uri.port === database["port"] and uri.query == nil and uri.fragment == nil,
         true <- is_binary(uri.path) and URI.decode(uri.path) == "/" <> database["database"],
         true <- is_binary(uri.userinfo),
         [encoded_role | encoded_password] <- String.split(uri.userinfo, ":", parts: 2),
         true <- URI.decode(encoded_role) == database["role"],
         password <- if(encoded_password == [], do: nil, else: URI.decode(hd(encoded_password))),
         true <-
           is_nil(password) or
             (byte_size(password) <= 8_192 and not String.contains?(password, <<0>>)) do
      options = [
        hostname: database["address"],
        port: database["port"],
        database: database["database"],
        username: database["role"]
      ]

      {:ok, if(is_nil(password), do: options, else: options ++ [password: password])}
    else
      _ -> :error
    end
  end

  defp json(raw) do
    with {:ok, value} <- Jason.decode(raw, objects: :ordered_objects),
         {:ok, normalized} <- normalize(value, 0) do
      {:ok, normalized}
    end
  end

  defp normalize(_, depth) when depth > 16, do: :error

  defp normalize(%Jason.OrderedObject{values: pairs}, depth) when length(pairs) <= 128 do
    keys = Enum.map(pairs, &elem(&1, 0))

    if length(Enum.uniq(keys)) == length(keys) do
      Enum.reduce_while(pairs, {:ok, %{}}, fn {key, value}, {:ok, result} ->
        case normalize(value, depth + 1) do
          {:ok, normalized} -> {:cont, {:ok, Map.put(result, key, normalized)}}
          _ -> {:halt, :error}
        end
      end)
    else
      :error
    end
  end

  defp normalize(value, _)
       when is_binary(value) or is_number(value) or is_boolean(value) or is_nil(value),
       do: {:ok, value}

  defp normalize(_, _), do: :error

  defp closed?(value, fields),
    do: is_map(value) and MapSet.new(Map.keys(value)) == MapSet.new(fields)

  defp valid_uuid?(value),
    do:
      is_binary(value) and Regex.match?(@uuid, value) and
        value != "00000000-0000-0000-0000-000000000000"

  defp read_file(path, uid, maximum, private_root) do
    with {:ok, parents} <- parents(Path.dirname(path), uid, private_root),
         {:ok, info} <- File.lstat(path, time: :posix),
         true <-
           info.type == :regular and info.uid == uid and info.links == 1 and
             info.size in 1..maximum,
         true <-
           if(private_root, do: (info.mode &&& 0o777) == 0o600, else: (info.mode &&& 0o022) == 0),
         {:ok, descriptor} <- :file.open(String.to_charlist(path), [:read, :binary, :raw]) do
      try do
        with {:ok, before} <- :file.read_file_info(descriptor, time: :posix),
             true <-
               Map.take(File.Stat.from_record(before), @metadata) == Map.take(info, @metadata),
             {:ok, raw} <- :file.read(descriptor, maximum + 1),
             true <- byte_size(raw) == info.size,
             {:ok, after_read} <- :file.read_file_info(descriptor, time: :posix),
             {:ok, named} <- File.lstat(path, time: :posix),
             true <-
               Map.take(File.Stat.from_record(after_read), @metadata) == Map.take(info, @metadata),
             true <- Map.take(named, @metadata) == Map.take(info, @metadata),
             {:ok, ^parents} <- parents(Path.dirname(path), uid, private_root) do
          {:ok, raw}
        else
          _ -> :error
        end
      after
        :file.close(descriptor)
      end
    else
      _ -> :error
    end
  end

  defp parents(path, uid, private_root) do
    with {:ok, info} <- File.lstat(path, time: :posix),
         true <- info.type == :directory,
         private <-
           private_root != nil and path in [private_root, private_root <> "/configuration"],
         true <-
           if(private,
             do: info.uid == uid and (info.mode &&& 0o777) == 0o700,
             else: info.uid == 0 and (info.mode &&& 0o022) == 0
           ),
         {:ok, above} <-
           if(path == "/", do: {:ok, []}, else: parents(Path.dirname(path), uid, private_root)) do
      {:ok, [{path, Map.take(info, @metadata)} | above]}
    else
      _ -> :error
    end
  end
end
