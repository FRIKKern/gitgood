defmodule Gitgood.BarkparkConnections do
  def recoverable_secret?(row) do
    case Gitgood.ConnectionSecrets.open(row.token_cipher, [
           row.user_id,
           row.id,
           row.generation,
           row.origin
         ]) do
      {:ok, value} when is_binary(value) -> true
      _ -> false
    end
  end

  @moduledoc "Private per-account scoped source connections; external I/O never holds a database lock."
  import Ecto.Query

  alias Gitgood.{
    Accounts,
    BarkparkConnection,
    BarkparkConnectionEvent,
    BarkparkHTTP,
    ConnectionSecrets,
    Credential,
    Lease,
    Repo
  }

  def show(user, credential), do: owned(user, credential, fn row -> public(row) end)

  def connect(user, credential, params, key) do
    with :ok <- parameters(params),
         true <- ConnectionSecrets.configured?(),
         origin when is_binary(origin) <- Application.get_env(:gitgood, :barkpark_origin),
         {:ok, digest} <-
           ConnectionSecrets.digest(%{action: "connect", origin: origin, params: params}),
         {:ok, preparation} <-
           prepare(user, credential, key, digest, params["expected_generation"]) do
      case preparation do
        {:replay, receipt} ->
          {:ok, receipt}

        :new ->
          with {:ok, identity} <- verify(params),
               {:ok, result} <-
                 finish(
                   user,
                   credential,
                   key,
                   digest,
                   params["expected_generation"],
                   fn current ->
                     unless origin == Application.get_env(:gitgood, :barkpark_origin),
                       do: Repo.rollback(:connection_changed)

                     id = if current, do: current.id, else: Ecto.UUID.generate()
                     generation = Ecto.UUID.generate()
                     binding = [user.id, id, generation, origin]
                     {:ok, cipher} = ConnectionSecrets.seal(params["token"], binding)

                     attrs = %{
                       generation: generation,
                       origin: origin,
                       workspace: params["workspace"],
                       project: params["project"],
                       dataset: params["dataset"],
                       source_identity: identity,
                       token_cipher: cipher,
                       disconnected_at: nil
                     }

                     changeset =
                       BarkparkConnection.changeset(
                         current || %BarkparkConnection{id: id, user_id: user.id},
                         attrs
                       )

                     if current, do: Repo.update!(changeset), else: Repo.insert!(changeset)
                   end
                 ) do
            {:ok, result}
          end
      end
    else
      false -> {:error, :connection_key_unconfigured}
      nil -> {:error, :barkpark_unconfigured}
      error -> error
    end
  end

  # Internal source consumers can make a short, generation-bound decision without
  # receiving or exposing the encrypted credential. Network I/O belongs outside it.
  def with_current(user, credential, generation, action) do
    # A generation mismatch changes nothing. An inner rollback would also abort
    # a surrounding evidence transaction before its source refusal is resolved.
    case owned(user, credential, fn row ->
           if row && is_nil(row.disconnected_at) && row.generation == generation &&
                row.origin == Application.get_env(:gitgood, :barkpark_origin),
              do: {:current, action.(public(row))},
              else: :connection_changed
         end) do
      {:ok, {:current, result}} -> {:ok, result}
      {:ok, :connection_changed} -> {:error, :connection_changed}
      error -> error
    end
  end

  def disconnect(user, credential, generation, key) do
    with true <- valid_generation?(generation),
         {:ok, digest} <-
           ConnectionSecrets.digest(%{action: "disconnect", generation: generation}) do
      finish(user, credential, key, digest, generation, fn
        nil ->
          Repo.rollback(:connection_changed)

        row ->
          Repo.update!(
            BarkparkConnection.changeset(row, %{
              generation: Ecto.UUID.generate(),
              disconnected_at: Accounts.now(),
              token_cipher: nil
            })
          )
      end)
    else
      false -> {:error, :invalid_connection_request}
      error -> error
    end
  end

  # Consumers receive a bounded source response, never the raw credential.
  # The current session and connection generation are rechecked after the network response.
  def read(user, credential, generation, path) do
    with {:ok, row} <-
           owned(user, credential, fn row ->
             unless row && is_nil(row.disconnected_at) && row.generation == generation,
               do: Repo.rollback(:connection_changed)

             unless row.origin == Application.get_env(:gitgood, :barkpark_origin),
               do: Repo.rollback(:connection_changed)

             row
           end),
         {:ok, token} <-
           ConnectionSecrets.open(row.token_cipher, [user.id, row.id, row.generation, row.origin]),
         response <- BarkparkHTTP.get(path, token),
         {:ok, :current} <-
           owned(user, credential, fn current ->
             unless current && current.generation == row.generation &&
                      is_nil(current.disconnected_at),
                    do: Repo.rollback(:connection_changed)

             :current
           end) do
      response
    end
  end

  # Journal consumers record the actual write reply even after access changes.
  # The raw credential never leaves this internal boundary; API replies must apply
  # their own current native guard. Unlike a read, a known write cannot be undone
  # by discarding its response after I/O.
  def write_bytes(user, credential, generation, path, payload, key) do
    with {:ok, row} <-
           owned(user, credential, fn row ->
             unless row && is_nil(row.disconnected_at) && row.generation == generation &&
                      row.origin == Application.get_env(:gitgood, :barkpark_origin),
                    do: Repo.rollback(:connection_changed)

             row
           end),
         {:ok, token} <-
           ConnectionSecrets.open(
             row.token_cipher,
             [user.id, row.id, row.generation, row.origin]
           ) do
      BarkparkHTTP.post_bytes(path, token, payload, key)
    end
  end

  defp prepare(user, credential, key, digest, expected) do
    owned(user, credential, fn row ->
      key = Lease.key!(key)

      case replay(user, key, digest) do
        nil ->
          expected!(row, expected)
          :new

        event ->
          {:replay, event.receipt}
      end
    end)
  end

  defp finish(user, credential, key, digest, expected, mutation) do
    owned(user, credential, fn row ->
      key = Lease.key!(key)

      case replay(user, key, digest) do
        nil ->
          expected!(row, expected)
          changed = mutation.(row)
          receipt = public(changed)

          Repo.insert!(%BarkparkConnectionEvent{
            user_id: user.id,
            request_key: key,
            request_digest: digest,
            receipt: receipt
          })

          receipt

        event ->
          event.receipt
      end
    end)
  end

  defp replay(user, key, digest) do
    case Repo.get_by(BarkparkConnectionEvent, user_id: user.id, request_key: key) do
      nil ->
        nil

      event ->
        unless event.request_digest == digest, do: Repo.rollback(:idempotency_conflict)
        event
    end
  end

  defp owned(user, credential, action) do
    Repo.transaction(fn ->
      current = Repo.one(from c in Credential, where: c.id == ^credential.id, lock: "FOR SHARE")

      unless current && current.user_id == user.id && current.kind == "session" &&
               is_nil(current.repository_id) && is_nil(current.revoked_at) &&
               DateTime.compare(current.expires_at, Accounts.now()) == :gt,
             do: Repo.rollback(:authorization_changed)

      Repo.query!("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", [
        "gitgood-barkpark-account:" <> Integer.to_string(user.id)
      ])

      row =
        Repo.one(from c in BarkparkConnection, where: c.user_id == ^user.id, lock: "FOR UPDATE")

      action.(row)
    end)
  rescue
    _ in [DBConnection.ConnectionError, Postgrex.Error] -> {:error, :connection_unavailable}
  end

  defp expected!(row, expected) do
    actual = if row, do: row.generation, else: "absent"
    unless actual == expected, do: Repo.rollback(:connection_changed)
  end

  defp public(nil), do: %{"state" => "unconfigured", "generation" => "absent"}

  defp public(row) do
    %{
      "id" => row.id,
      "generation" => row.generation,
      "state" => if(row.disconnected_at, do: "disconnected", else: "connected"),
      "origin" => row.origin,
      "workspace" => row.workspace,
      "project" => row.project,
      "dataset" => row.dataset,
      "source_identity" => row.source_identity,
      "updated_at" => DateTime.to_iso8601(row.updated_at)
    }
  end

  defp parameters(params) do
    if is_map(params) &&
         Enum.sort(Map.keys(params)) == [
           "dataset",
           "expected_generation",
           "project",
           "token",
           "workspace"
         ] &&
         Enum.all?(["dataset", "project", "workspace"], &slug?(params[&1])) &&
         (params["expected_generation"] == "absent" ||
            valid_generation?(params["expected_generation"])) &&
         is_binary(params["token"]) && byte_size(params["token"]) in 16..512 &&
         Enum.all?(:binary.bin_to_list(params["token"]), &(&1 in 33..126)),
       do: :ok,
       else: {:error, :invalid_connection_request}
  end

  defp slug?(value), do: is_binary(value) && Regex.match?(~r/\A[a-z][a-z0-9-]{0,63}\z/, value)
  defp valid_generation?(value), do: match?({:ok, _}, Ecto.UUID.cast(value))

  defp verify(params) do
    with {:ok, identity} <- get("/v1/tokens/current", params["token"]),
         {:ok, manifest} <- get("/v1/capabilities?token=1&build=1", params["token"]),
         :ok <- identity(identity, manifest, params),
         {:ok, projects} <-
           get("/api/workspaces/" <> params["workspace"] <> "/projects", params["token"]),
         {:ok, datasets} <-
           get(
             "/api/workspaces/" <>
               params["workspace"] <> "/projects/" <> params["project"] <> "/datasets",
             params["token"]
           ),
         true <- scope?(projects, datasets, identity, params) do
      token = identity["token"]

      {:ok,
       %{
         "token_id" => token["id"],
         "kind" => token["kind"],
         "label" => token["label"],
         "permissions" => token["permissions"],
         "expires_at" => token["expires_at"],
         "workspace_id" => token["workspace_id"],
         "project_id" => datasets["project"]["id"],
         "dataset_id" =>
           Enum.find(datasets["datasets"], &(&1["slug"] == params["dataset"]))["id"],
         "build" => Map.take(manifest["build"] || %{}, ["version", "commit", "built_at"]),
         "verified_at" => DateTime.to_iso8601(Accounts.now())
       }}
    else
      false -> {:error, :barkpark_scope_denied}
      error -> error
    end
  rescue
    _ -> {:error, :barkpark_contract_unavailable}
  end

  defp identity(%{"token" => token, "memberships" => memberships}, manifest, params)
       when is_map(token) and is_list(memberships) do
    with {:ok, _, _} <- DateTime.from_iso8601(token["expires_at"] || ""),
         true <-
           valid_generation?(token["id"]) && valid_generation?(token["workspace_id"]) &&
             token["kind"] == "api" && token["workspace"] == params["workspace"] &&
             is_binary(token["label"]) && byte_size(token["label"]) <= 256 &&
             token["permissions"] in [["read"], ["read", "write"], ["write", "read"]] &&
             manifest["auth_tier"] in ["read", "write"] &&
             get_in(manifest, ["token", "public_read"]) == false &&
             length(memberships) == 1 &&
             hd(memberships)["workspace_id"] == token["workspace_id"] &&
             hd(memberships)["workspace_slug"] == params["workspace"] do
      {:ok, expires, _} = DateTime.from_iso8601(token["expires_at"])

      if DateTime.compare(expires, Accounts.now()) == :gt,
        do: :ok,
        else: {:error, :barkpark_scope_denied}
    else
      _ -> {:error, :barkpark_scope_denied}
    end
  end

  defp identity(_, _, _), do: {:error, :barkpark_contract_unavailable}

  defp scope?(projects, datasets, identity, params) do
    workspace = identity["token"]["workspace_id"]

    projects["workspace"]["id"] == workspace && datasets["workspace"]["id"] == workspace &&
      datasets["project"]["slug"] == params["project"] &&
      valid_generation?(datasets["project"]["id"]) &&
      Enum.any?(
        projects["projects"],
        &(&1["slug"] == params["project"] && &1["id"] == datasets["project"]["id"])
      ) &&
      Enum.any?(
        datasets["datasets"],
        &(&1["slug"] == params["dataset"] && valid_generation?(&1["id"]))
      )
  end

  defp get(path, token) do
    case BarkparkHTTP.get(path, token) do
      {:ok, %{status: 200, body: body}} when is_map(body) -> {:ok, body}
      {:ok, %{status: status}} when status in [401, 403] -> {:error, :barkpark_access_denied}
      {:ok, %{status: 404}} -> {:error, :barkpark_scope_missing}
      {:ok, _} -> {:error, :barkpark_unavailable}
      error -> error
    end
  end
end
