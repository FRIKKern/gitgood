defmodule Gitgood.ImportBundle do
  @moduledoc "Offline, bounded full SHA-1 bundle validation; never checks out or fetches user code."
  alias Gitgood.Git
  @zero String.duplicate("0", 40)

  def refs(path) do
    with {:ok, file} <- File.open(path, [:read, :binary, :raw]) do
      try do
        if :file.read(file, 16) == {:ok, "# v2 git bundle\n"},
          do: header(file, [], 0),
          else: {:error, :full_sha1_v2_bundle_required}
      after
        File.close(file)
      end
    end
  end

  defp header(file, refs, bytes) when bytes <= 65536 and length(refs) <= 64 do
    case read_line(file) do
      "\n" ->
        refs = Enum.reverse(refs)

        if length(refs) in 1..64 and Enum.uniq_by(refs, & &1["ref"]) == refs and
             Enum.any?(refs, &(&1["ref"] == "refs/heads/main")),
           do: {:ok, refs},
           else: {:error, :unique_branches_tags_and_main_required}

      line when is_binary(line) and byte_size(line) <= 2048 ->
        case Regex.run(~r/\A([0-9a-f]{40}) (refs\/(?:heads|tags)\/[^\n]+)\n\z/u, line) do
          [_, sha, ref] ->
            if sha != @zero and valid_ref?(ref),
              do:
                header(
                  file,
                  [%{"old" => @zero, "new" => sha, "ref" => ref} | refs],
                  bytes + byte_size(line)
                ),
              else: {:error, :invalid_import_ref}

          _ ->
            {:error, :full_bundle_branches_tags_only}
        end

      _ ->
        {:error, :bundle_header_invalid_or_too_large}
    end
  rescue
    _ -> {:error, :bundle_header_invalid_or_too_large}
  end

  defp header(_, _, _), do: {:error, :bundle_header_invalid_or_too_large}

  defp read_line(file) do
    with {:ok, bytes} <- :file.read(file, 2049),
         {index, 1} when index < 2048 <- :binary.match(bytes, "\n"),
         {:ok, _} <- :file.position(file, {:cur, -(byte_size(bytes) - index - 1)}) do
      binary_part(bytes, 0, index + 1)
    else
      _ -> :error
    end
  end

  defp valid_ref?("refs/heads/" <> _ = ref), do: Gitgood.Ref.branch?(ref)
  defp valid_ref?("refs/tags/" <> tag), do: Gitgood.Ref.branch?("refs/heads/" <> tag)

  def prepare(repository, path) do
    validation = validation_path(path)

    with {:ok, refs} <- refs(path),
         :ok <- initialize_validation(validation),
         :ok <- run(validation, ["bundle", "verify", path]),
         :ok <- install_pack(validation, path),
         :ok <- run(validation, ["fsck", "--full", "--strict"], timeout: 60000),
         :ok <- object_types(validation, refs),
         :ok <- install_pack(repository, path),
         :ok <- run(repository, ["config", "transfer.hideRefs", "refs/gitgood/"]) do
      {:ok, refs}
    end
  end

  def empty?(repository) do
    case Git.command(
           [
             "--git-dir",
             Git.path(repository),
             "for-each-ref",
             "--count=1",
             "--format=%(refname)"
           ],
           limit: 2048
         ) do
      {:ok, "", 0} -> :ok
      {:ok, _, 0} -> {:error, :repository_not_empty}
      _ -> {:error, :repository_storage_unavailable}
    end
  end

  def publish(repository, operation) do
    main = Enum.find(operation.updates, &(&1["ref"] == "refs/heads/main"))

    creates =
      Enum.map_join(operation.updates, "", &("create " <> &1["ref"] <> " " <> &1["new"] <> "\n"))

    run(repository, ["update-ref", "--stdin"],
      input:
        "start\n" <>
          creates <> "create " <> marker(operation) <> " " <> main["new"] <> "\nprepare\ncommit\n"
    )
  end

  def marker(operation), do: "refs/gitgood/imports/" <> operation.id
  def validation_path(path), do: path <> ".verify.git"

  defp initialize_validation(path) do
    safe =
      case File.lstat(path) do
        {:error, :enoent} -> true
        {:ok, %{type: :directory}} -> true
        _ -> false
      end

    if safe do
      case Git.command(
             [
               "init",
               "--bare",
               "--template=",
               "--object-format=sha1",
               "--initial-branch=main",
               path
             ],
             limit: 4096
           ) do
        {:ok, _, 0} -> File.chmod(path, 0o700)
        {:error, :busy} -> {:error, :busy}
        _ -> {:error, :validation_storage_unavailable}
      end
    else
      {:error, :validation_storage_unavailable}
    end
  end

  defp directory(path) when is_binary(path), do: path
  defp directory(repository), do: Git.path(repository)

  defp install_pack(repository, path) do
    python = Application.fetch_env!(:gitgood, :python_executable) |> System.find_executable()
    adapter = Application.app_dir(:gitgood, "priv/import_pack.py")

    case Gitgood.Command.run(
           [python, "-I", "-B", adapter, Git.executable(), directory(repository), path],
           timeout: 60000,
           limit: 4096
         ) do
      {:ok, _, 0} -> :ok
      {:error, :busy} -> {:error, :busy}
      _ -> {:error, :bundle_pack_not_strict_and_self_contained}
    end
  end

  defp object_types(repository, refs) do
    input = Enum.map_join(refs, "", &(&1["new"] <> "\n"))

    case Git.command(
           [
             "--git-dir",
             directory(repository),
             "cat-file",
             "--batch-check=%(objectname) %(objecttype)"
           ],
           input: input,
           limit: 8192
         ) do
      {:ok, output, 0} ->
        lines = String.split(output, "\n", trim: true)

        if length(lines) == length(refs) and
             Enum.zip(refs, lines)
             |> Enum.all?(fn {ref, line} ->
               types =
                 if String.starts_with?(ref["ref"], "refs/heads/"),
                   do: ["commit"],
                   else: ["commit", "tag", "tree", "blob"]

               Enum.any?(types, &(line == ref["new"] <> " " <> &1))
             end), do: :ok, else: {:error, :invalid_import_object_types}

      _ ->
        {:error, :import_objects_unavailable}
    end
  end

  defp run(repository, args, opts \\ []) do
    case Git.command(
           ["--git-dir", directory(repository) | args],
           Keyword.merge([timeout: 15000, limit: 131_072], opts)
         ) do
      {:ok, _, 0} -> :ok
      {:error, :busy} -> {:error, :busy}
      _ -> {:error, :bundle_validation_or_git_write_failed}
    end
  end
end
