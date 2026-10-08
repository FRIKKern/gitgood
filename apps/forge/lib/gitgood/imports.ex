defmodule Gitgood.Imports do
  @moduledoc "Durable, creator-owned bundle imports with resumable intake and atomic publication."
  import Ecto.Query

  alias Gitgood.{
    Accounts,
    Credential,
    Git,
    GitOperation,
    ImportBundle,
    Lease,
    Repo,
    Repository,
    User
  }

  @limit 33_554_432
  @warnings [
    "Only Git objects, branches and tags are imported.",
    "Git LFS objects, submodule repositories, issues, reviews, CI, credentials and forge settings are not imported.",
    "LFS pointers and .gitmodules remain ordinary source files; no external content is downloaded."
  ]

  def limit, do: @limit
  def warnings, do: @warnings

  def begin(repository, user, credential, params, key) do
    Lease.actor(repository, user, credential, ["owner", "writer"], fn repository ->
      owner!(repository, user)
      key = Lease.key!(key)
      source = source!(params)
      digest = Lease.digest(source)

      existing =
        Repo.get_by(GitOperation,
          repository_id: repository.id,
          actor_id: user.id,
          kind: "import",
          request_key: key
        )

      if existing do
        if existing.request_digest == digest,
          do: existing,
          else: Repo.rollback(:idempotency_conflict)
      else
        reconcile_repository(repository)
        mutation_available!(repository)
        ensure_empty!(repository)

        if Repo.exists?(
             from o in GitOperation,
               where:
                 o.repository_id == ^repository.id and
                   o.kind == "import" and o.state in ["started", "validated", "uncertain"]
           ),
           do: Repo.rollback(:import_already_pending)

        Repo.insert!(%GitOperation{
          repository_id: repository.id,
          actor_id: user.id,
          credential_id: credential.id,
          kind: "import",
          request_key: key,
          request_digest: digest,
          metadata: Map.merge(source, %{"phase" => "waiting_source", "warnings" => @warnings})
        })
      end
    end)
  end

  def upload_allowed(repository, user, credential, id) do
    Lease.actor(repository, user, credential, ["owner", "writer"], fn repository ->
      owner!(repository, user)
      operation = operation!(repository, user, id)

      unless operation.state == "started" and
               operation.metadata["phase"] in ["waiting_source", "queued"],
             do: Repo.rollback(:import_source_already_closed)

      operation
    end)
  end

  def accept_source(repository, user, credential, id, temporary, opts \\ []) do
    result =
      Lease.actor(repository, user, credential, ["owner", "writer"], fn repository ->
        owner!(repository, user)
        operation = operation!(repository, user, id)
        unless operation.state == "started", do: Repo.rollback(:import_source_already_closed)

        unless operation.metadata["phase"] in ["waiting_source", "queued"],
          do: Repo.rollback(:import_source_already_closed)

        unless fingerprint(temporary) ==
                 {:ok, operation.metadata["source_sha256"], operation.metadata["source_bytes"]},
               do: Repo.rollback(:source_size_or_digest_mismatch)

        target = source_path(operation)
        :ok = File.mkdir_p(Path.dirname(target))
        # Matching complete upload is immutable; concurrent/lost-reply retries reuse it.
        if File.exists?(target) do
          unless fingerprint(target) == fingerprint(temporary),
            do: Repo.rollback(:staged_source_unavailable)
        else
          unless File.rename(temporary, target) == :ok, do: Repo.rollback(:source_staging_failed)
        end

        operation
        |> Ecto.Changeset.change(metadata: Map.put(operation.metadata, "phase", "queued"))
        |> Repo.update!()
      end)

    if opts[:enqueue] != false and match?({:ok, _}, result),
      do: dispatch(elem(result, 1).id)

    result
  after
    File.rm(temporary)
  end

  def cancel(repository, user, credential, id) do
    result =
      Lease.actor(repository, user, credential, ["owner", "writer"], fn repository ->
        owner!(repository, user)
        operation = operation!(repository, user, id)

        unless operation.state == "started" and operation.metadata["phase"] == "waiting_source",
          do: Repo.rollback(:only_waiting_import_can_be_cancelled)

        fail(operation, :cancelled)
      end)

    cleanup_result(result)
    result
  end

  def source_path(operation),
    do: Path.join(directory(), operation.id <> ".bundle")

  def directory,
    do: Path.join(Application.fetch_env!(:gitgood, :storage_root), ".gitgood-imports")

  def temporary_path do
    :ok = File.mkdir_p(directory())
    :ok = File.chmod(directory(), 0o700)
    Path.join(directory(), Ecto.UUID.generate() <> ".partial")
  end

  def fingerprint(path) do
    case File.stat(path) do
      {:ok, %{size: size, type: :regular}} when size in 1..@limit ->
        digest =
          path
          |> File.stream!(65_536, [])
          |> Enum.reduce(:crypto.hash_init(:sha256), &:crypto.hash_update(&2, &1))

        {:ok, Base.encode16(:crypto.hash_final(digest), case: :lower), size}

      _ ->
        {:error, :invalid_source_size}
    end
  rescue
    _ -> {:error, :source_unavailable}
  end

  def dispatch(id) do
    DynamicSupervisor.start_child(Gitgood.ImportWorkers, {Gitgood.ImportWorker, id})
  end

  def execute(id, opts \\ []) do
    with %GitOperation{kind: "import"} = operation <- Repo.get(GitOperation, id),
         %Repository{} = repository <- Repo.get(Repository, operation.repository_id),
         %User{} = user <- Repo.get(User, operation.actor_id),
         %Credential{} = credential <- Repo.get(Credential, operation.credential_id) do
      result =
        Gitgood.TransportSlots.with_slot(fn ->
          Lease.actor(repository, user, credential, ["owner", "writer"], fn repository ->
            owner!(repository, user)
            operation = Repo.get!(GitOperation, operation.id)

            cond do
              operation.state in ["applied", "failed"] ->
                operation

              operation.state in ["validated", "uncertain"] ->
                reconcile_operation(repository, operation)

              operation.metadata["phase"] != "queued" ->
                operation

              true ->
                if (operation.metadata["attempts"] || 0) >= 3 do
                  fail(operation, :import_retry_limit_reached)
                else
                  task =
                    Task.Supervisor.async_nolink(Gitgood.DurableWrites, fn ->
                      Repo.get!(GitOperation, operation.id)
                      |> Ecto.Changeset.change(
                        metadata:
                          Map.merge(operation.metadata, %{
                            "attempts" => (operation.metadata["attempts"] || 0) + 1,
                            "last_started_at" => DateTime.to_iso8601(Accounts.now())
                          })
                      )
                      |> Repo.update!()
                    end)

                  prepare_and_publish(repository, Task.await(task, 10000), opts)
                end
            end
          end)
        end)

      # An expired/revoked credential cannot leave a queued source executing later.
      result =
        case result do
          {:error, reason}
          when reason in [:authorization_changed, :repository_creator_required] ->
            terminal_failure(repository, operation.id, reason)

          other ->
            other
        end

      cleanup_result(result)
      result
    else
      _ -> {:error, :import_not_found}
    end
  end

  defp prepare_and_publish(repository, operation, opts) do
    Gitgood.Pushes.reconcile_repository(repository, nil)
    Gitgood.Merges.reconcile_repository(repository)
    mutation_available!(repository)

    case ImportBundle.empty?(repository) do
      :ok ->
        prepared =
          if fingerprint(source_path(operation)) ==
               {:ok, operation.metadata["source_sha256"], operation.metadata["source_bytes"]},
             do: ImportBundle.prepare(repository, source_path(operation)),
             else: {:error, :staged_source_unavailable}

        case prepared do
          {:ok, refs} ->
            fault(opts, :before_validation, operation)
            # This connection commits the complete expected ref set before any ref can change.
            task =
              Task.Supervisor.async_nolink(Gitgood.DurableWrites, fn ->
                Repo.get!(GitOperation, operation.id)
                |> Ecto.Changeset.change(
                  state: "validated",
                  updates: refs,
                  metadata:
                    Map.merge(operation.metadata, %{
                      "phase" => "publishing",
                      "validated_at" => DateTime.to_iso8601(Accounts.now())
                    })
                )
                |> Repo.update!()
              end)

            operation = Task.await(task, 10000)
            fault(opts, :before_ref, operation)
            _ = ImportBundle.publish(repository, operation)
            fault(opts, :after_ref, operation)
            fault(opts, :before_outcome, operation)
            reconcile_operation(repository, operation)

          {:error, :busy} ->
            operation

          {:error, reason} ->
            fail(operation, reason)
        end

      {:error, reason} ->
        fail(operation, reason)
    end
  end

  def reconcile_repository(repository) do
    Repo.all(
      from o in GitOperation,
        where:
          o.repository_id == ^repository.id and
            o.kind == "import" and o.state in ["validated", "uncertain"]
    )
    |> Enum.each(&reconcile_operation(repository, &1))
  end

  def reconcile_operation(repository, operation) do
    main = Enum.find(operation.updates, &(&1["ref"] == "refs/heads/main"))
    marker = Git.ref(repository, ImportBundle.marker(operation))

    state =
      case marker do
        {:ok, sha} when not is_nil(main) ->
          if sha == main["new"], do: "applied", else: "uncertain"

        {:error, :missing_ref} ->
          "failed"

        _ ->
          "uncertain"
      end

    outcome = %{
      "marker" => ImportBundle.marker(operation),
      "marker_sha" =>
        case marker do
          {:ok, sha} -> sha
          _ -> nil
        end,
      "error" => if(state == "failed", do: "import_not_published"),
      "reconciled_at" => DateTime.to_iso8601(Accounts.now())
    }

    operation |> Ecto.Changeset.change(state: state, outcome: outcome) |> Repo.update!()
  end

  def reconcile do
    cleanup_staging()

    ids =
      Repo.all(
        from o in GitOperation,
          where:
            o.kind == "import" and
              o.state in ["validated", "uncertain"],
          distinct: o.repository_id,
          select: o.repository_id
      )

    for id <- ids do
      result =
        Repo.transaction(fn ->
          repository =
            Repo.one!(from r in Repository, where: r.id == ^id, lock: "FOR NO KEY UPDATE")

          reconcile_repository(repository)

          Repo.all(
            from o in GitOperation,
              where:
                o.repository_id == ^id and o.kind == "import" and
                  o.state in ["applied", "failed"]
          )
        end)

      case result do
        {:ok, operations} -> Enum.each(operations, &cleanup/1)
        _ -> :ok
      end
    end

    Repo.all(
      from o in GitOperation,
        where:
          o.kind == "import" and o.state == "started" and
            fragment("?->>'phase' = 'queued'", o.metadata),
        order_by: [asc: o.inserted_at],
        limit: 32,
        select: o.id
    )
    |> Enum.each(&dispatch/1)
  end

  defp terminal_failure(repository, id, reason) do
    Repo.transaction(fn ->
      Repo.one!(from r in Repository, where: r.id == ^repository.id, lock: "FOR NO KEY UPDATE")
      operation = Repo.get!(GitOperation, id)
      if operation.state == "started", do: fail(operation, reason), else: operation
    end)
  end

  defp fail(operation, reason),
    do:
      operation
      |> Ecto.Changeset.change(
        state: "failed",
        outcome: %{
          "error" => Atom.to_string(reason),
          "finished_at" => DateTime.to_iso8601(Accounts.now())
        }
      )
      |> Repo.update!()

  defp owner!(repository, user) do
    unless repository.owner_id == user.id and repository.status == "ready" and
             repository.storage_version >= 2,
           do: Repo.rollback(:repository_creator_required)
  end

  defp ensure_empty!(repository) do
    case ImportBundle.empty?(repository) do
      :ok -> :ok
      {:error, reason} -> Repo.rollback(reason)
    end
  end

  defp mutation_available!(repository) do
    if Repo.exists?(
         from o in GitOperation,
           where: o.repository_id == ^repository.id and o.state == "uncertain"
       ),
       do: Repo.rollback(:recovery_required)
  end

  defp operation!(repository, user, id) do
    with {:ok, id} <- Ecto.UUID.cast(id),
         %GitOperation{kind: "import", actor_id: actor} = op <-
           Repo.get_by(GitOperation, id: id, repository_id: repository.id),
         true <- actor == user.id do
      op
    else
      _ -> Repo.rollback(:import_not_found)
    end
  end

  defp source!(params) do
    name = params["source_name"]
    sha = params["source_sha256"]
    bytes = params["source_bytes"]

    unless Enum.sort(Map.keys(params)) == ["source_bytes", "source_name", "source_sha256"] and
             is_binary(name) and byte_size(name) in 1..160 and String.valid?(name) and
             not Regex.match?(~r/[\x00-\x1f\x7f]/u, name) and
             is_binary(sha) and Regex.match?(~r/\A[0-9a-f]{64}\z/, sha) and
             is_integer(bytes) and bytes in 1..@limit,
           do: Repo.rollback(:bounded_bundle_source_required)

    Map.take(params, ["source_name", "source_sha256", "source_bytes"])
  end

  defp fault(opts, point, operation),
    do: if(callback = opts[:fault], do: callback.(point, operation))

  defp cleanup_result({:ok, %GitOperation{} = operation}), do: cleanup(operation)
  defp cleanup_result(_), do: :ok

  defp cleanup(%GitOperation{state: state} = operation) when state in ["applied", "failed"] do
    source = source_path(operation)
    if match?({:ok, %{type: :regular}}, File.lstat(source)), do: File.rm(source)
    validation = ImportBundle.validation_path(source) |> Path.expand()
    # Only this operation's internal directory may be removed recursively.
    if Path.dirname(validation) == Path.expand(directory()) and
         match?({:ok, %{type: :directory}}, File.lstat(validation)),
       do: File.rm_rf(validation)

    :ok
  end

  defp cleanup(_), do: :ok

  def cleanup_staging do
    now = System.os_time(:second)

    case File.ls(directory()) do
      {:ok, names} ->
        for name <- names,
            Regex.match?(
              ~r/\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(?:partial|bundle(?:\.verify\.git)?)\z/,
              name
            ) do
          path = Path.join(directory(), name)

          case File.lstat(path, time: :posix) do
            {:ok, %{type: type, mtime: modified}} when type in [:regular, :directory] ->
              cond do
                type == :regular and String.ends_with?(name, ".partial") and now - modified > 3600 ->
                  File.rm(path)

                String.contains?(name, ".bundle") ->
                  id = name |> String.split(".") |> hd()

                  case Repo.get(GitOperation, id) do
                    %GitOperation{kind: "import", state: state} = operation
                    when state in ["applied", "failed"] ->
                      cleanup(operation)

                    _ ->
                      :ok
                  end

                true ->
                  :ok
              end

            _ ->
              :ok
          end
        end

      _ ->
        :ok
    end
  end
end
