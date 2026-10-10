defmodule Gitgood.InstallationDatabaseSession do
  @moduledoc "Read-only identity checks on an already held installation lease connection."

  @fields ~w(cluster database database_oid owner_oid role session_role role_oid encoding version address port can_login superuser create_database create_role replication bypass_rls memberships)
  @administrator_flags ~w(superuser create_database create_role replication bypass_rls)
  @sql """
  SELECT json_build_object(
    'database', (SELECT json_build_object(
      'cluster', (SELECT system_identifier::text FROM pg_control_system()),
      'database', d.datname, 'database_oid', d.oid::bigint, 'owner_oid', d.datdba::bigint,
      'role', r.rolname, 'session_role', session_user, 'role_oid', r.oid::bigint,
      'encoding', pg_encoding_to_char(d.encoding), 'version', current_setting('server_version'),
      'address', host(inet_server_addr()), 'port', inet_server_port(),
      'can_login', r.rolcanlogin, 'superuser', r.rolsuper, 'create_database', r.rolcreatedb,
      'create_role', r.rolcreaterole, 'replication', r.rolreplication, 'bypass_rls', r.rolbypassrls,
      'memberships', (SELECT count(*) FROM pg_auth_members WHERE member=r.oid))
      FROM pg_database d JOIN pg_roles r ON r.rolname=current_user
      WHERE d.datname=current_database() AND d.datdba=r.oid),
    'backend_pid', pg_backend_pid(),
    'backend_birth', (SELECT floor(extract(epoch FROM backend_start)*1000000)::bigint::text
      FROM pg_stat_activity WHERE pid=pg_backend_pid()),
    'held', EXISTS (SELECT 1 FROM pg_locks WHERE locktype='advisory'
      AND pid=pg_backend_pid() AND classid::bigint=1197034575 AND objid::bigint=1
      AND objsubid=2 AND mode='ExclusiveLock' AND granted))
  """

  def capture(connection, expected_database) do
    with true <- valid_database?(expected_database),
         {:ok, %{rows: [[observed]]}} <- Postgrex.query(connection, @sql, [], timeout: 3000),
         {:ok, snapshot} <- validate_observation(expected_database, observed) do
      {:ok, snapshot}
    else
      _ -> {:error, :installation_database_session_unavailable}
    end
  rescue
    _ -> {:error, :installation_database_session_unavailable}
  catch
    :exit, _ -> {:error, :installation_database_session_unavailable}
  end

  def check(connection, snapshot) do
    with true <- valid_snapshot?(snapshot),
         {:ok, current} <- capture(connection, snapshot["database"]),
         true <- current == snapshot do
      :ok
    else
      _ -> {:error, :installation_database_session_lost}
    end
  rescue
    _ -> {:error, :installation_database_session_lost}
  catch
    :exit, _ -> {:error, :installation_database_session_lost}
  end

  @doc false
  def validate_database(value) do
    if valid_database?(value), do: :ok, else: {:error, :invalid_database}
  rescue
    _ -> {:error, :invalid_database}
  end

  @doc false
  def validate_observation(expected, observed) do
    if valid_database?(expected) and is_map(observed) and
         MapSet.new(Map.keys(observed)) == MapSet.new(~w(database backend_pid backend_birth held)) and
         observed["held"] === true and observed["database"] === expected do
      snapshot = Map.take(observed, ~w(database backend_pid backend_birth))
      if valid_snapshot?(snapshot), do: {:ok, snapshot}, else: {:error, :invalid_session}
    else
      {:error, :invalid_session}
    end
  end

  defp valid_snapshot?(value) when is_map(value) do
    MapSet.new(Map.keys(value)) == MapSet.new(~w(database backend_pid backend_birth)) and
      valid_database?(value["database"]) and
      positive_integer?(value["backend_pid"], 2_147_483_648) and
      unsigned_text?(value["backend_birth"])
  end

  defp valid_snapshot?(_), do: false

  defp valid_database?(value) when is_map(value) do
    MapSet.new(Map.keys(value)) == MapSet.new(@fields) and unsigned_text?(value["cluster"]) and
      Enum.all?(~w(database_oid owner_oid role_oid), &positive_integer?(value[&1], 4_294_967_296)) and
      value["owner_oid"] === value["role_oid"] and
      bounded_name?(value["database"]) and bounded_name?(value["role"]) and
      value["role"] === value["session_role"] and value["encoding"] === "UTF8" and
      value["version"] === "18.4" and value["address"] === "127.0.0.1" and
      positive_integer?(value["port"], 65_536) and value["can_login"] === true and
      Enum.all?(@administrator_flags, &(value[&1] === false)) and value["memberships"] === 0
  end

  defp valid_database?(_), do: false

  defp positive_integer?(value, maximum), do: is_integer(value) and value > 0 and value < maximum

  defp unsigned_text?(value) when is_binary(value) do
    byte_size(value) <= 20 and Regex.match?(~r/\A[1-9][0-9]{0,19}\z/, value) and
      String.to_integer(value) < 18_446_744_073_709_551_616
  end

  defp unsigned_text?(_), do: false

  defp bounded_name?(value),
    do:
      is_binary(value) and byte_size(value) in 1..63 and String.valid?(value) and
        not String.contains?(value, <<0>>)
end
