defmodule Gitgood.Browse do
  alias Gitgood.Git
  @limit 262_144
  @empty "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
  def branches(repository) do
    Gitgood.BrowseSlots.with_slot(fn -> read_branches(repository) end)
  end

  defp read_branches(repository) do
    with {:ok, output, 0} <-
           run(
             repository,
             ["for-each-ref", "--format=%(objectname) %(refname)", "refs/heads/"],
             65536
           ) do
      entries =
        for line <- String.split(output, "\n", trim: true),
            [sha, ref] <- [String.split(line, " ", parts: 2)],
            do: %{sha: sha, name: String.replace_prefix(ref, "refs/heads/", "")}

      if length(entries) <= 256, do: {:ok, entries}, else: {:error, :branch_limit}
    else
      _ -> {:error, :git_unavailable}
    end
  end

  def snapshot(repository, sha, path) do
    Gitgood.BrowseSlots.with_slot(fn -> read_snapshot(repository, sha, path) end)
  end

  defp read_snapshot(repository, sha, path) do
    with :ok <- reachable(repository, sha),
         {:ok, segments} <- segments(path),
         {:ok, object, kind, mode} <- walk(repository, sha, segments) do
      case kind do
        "tree" ->
          with {:ok, entries} <- tree(repository, object),
               {:ok, history} <- history(repository, sha) do
            {:ok, %{sha: sha, path: path, kind: "tree", entries: entries, history: history}}
          end

        "blob" ->
          blob(repository, sha, path, object, mode)

        _ ->
          {:ok, %{sha: sha, path: path, kind: "submodule", object: object}}
      end
    end
  end

  def diff(repository, sha, base) do
    Gitgood.BrowseSlots.with_slot(fn -> read_diff(repository, sha, base) end)
  end

  defp read_diff(repository, sha, base) do
    with :ok <- reachable(repository, sha),
         {:ok, base} <- base(repository, sha, base),
         {:ok, text, 0} <-
           run(
             repository,
             ["diff", "--no-ext-diff", "--no-textconv", "--no-renames", base, sha, "--"],
             @limit
           ) do
      {:ok, %{sha: sha, base: base, text: safe(text), limit: @limit}}
    else
      {:error, "output_limit"} -> {:error, :diff_too_large}
      {:error, :output_limit} -> {:error, :diff_too_large}
      {:error, reason} -> {:error, reason}
      _ -> {:error, :git_unavailable}
    end
  end

  def reachable(repository, sha) do
    if is_binary(sha) and Regex.match?(~r/\A[0-9a-f]{40}\z/, sha) do
      case run(
             repository,
             [
               "for-each-ref",
               "--contains=" <> sha,
               "--count=1",
               "--format=%(refname)",
               "refs/heads/",
               "refs/tags/"
             ],
             4096
           ) do
        {:ok, value, 0} when value != "" -> :ok
        {:error, _} -> {:error, :git_unavailable}
        _ -> {:error, :commit_not_available}
      end
    else
      {:error, :invalid_commit}
    end
  end

  defp segments(path) when is_binary(path) and byte_size(path) <= 4096 do
    parts = if path == "", do: [], else: String.split(path, "/")

    if String.valid?(path) and
         Enum.all?(parts, &(&1 not in ["", ".", ".."] and not String.contains?(&1, <<0>>))),
       do: {:ok, parts},
       else: {:error, :invalid_path}
  end

  defp segments(_), do: {:error, :invalid_path}
  defp walk(_repository, sha, []), do: {:ok, sha, "tree", "040000"}

  defp walk(repository, object, [part | rest]) do
    with {:ok, entries} <- tree(repository, object),
         entry when not is_nil(entry) <-
           Enum.find(entries, &(&1.name == part and not &1.unsupported_encoding)) do
      if rest == [],
        do: {:ok, entry.sha, entry.kind, entry.mode},
        else:
          if(entry.kind == "tree",
            do: walk(repository, entry.sha, rest),
            else: {:error, :path_not_found}
          )
    else
      nil -> {:error, :path_not_found}
      {:error, reason} -> {:error, reason}
    end
  end

  defp tree(repository, object) do
    with {:ok, output, 0} <- run(repository, ["ls-tree", "-z", object], @limit) do
      entries =
        for row <- :binary.split(output, <<0>>, [:global]),
            row != "",
            [header, name] = :binary.split(row, "\t"),
            [mode, kind, sha] = String.split(header, " "),
            do: %{
              name: safe(name),
              unsupported_encoding: not String.valid?(name),
              mode: mode,
              kind: kind,
              sha: sha
            }

      {:ok, entries}
    else
      {:error, "output_limit"} -> {:error, :tree_too_large}
      _ -> {:error, :git_unavailable}
    end
  end

  defp blob(repository, sha, path, object, mode) do
    with {:ok, size, 0} <- run(repository, ["cat-file", "-s", object], 64),
         {size, _} <- Integer.parse(size) do
      if size > @limit do
        {:ok, %{sha: sha, path: path, kind: "large_file", size: size, limit: @limit}}
      else
        with {:ok, content, 0} <- run(repository, ["cat-file", "blob", object], @limit) do
          binary = not String.valid?(content) or :binary.match(content, <<0>>) != :nomatch

          {:ok,
           %{
             sha: sha,
             path: path,
             kind: if(binary, do: "binary", else: "text"),
             size: size,
             mode: mode,
             content: if(binary, do: nil, else: content)
           }}
        else
          _ -> {:error, :git_unavailable}
        end
      end
    else
      _ -> {:error, :git_unavailable}
    end
  end

  defp history(repository, sha) do
    case run(
           repository,
           ["log", "--max-count=50", "--format=%H%x00%P%x00%an%x00%aI%x00%s%x00", sha, "--"],
           @limit
         ) do
      {:ok, output, 0} ->
        rows = String.split(output, <<0>>)

        commits =
          rows
          |> Enum.chunk_every(5, 5, :discard)
          |> Enum.map(fn [id, parents, author, date, subject] ->
            %{
              sha: String.trim(id),
              parents: String.split(parents, " ", trim: true),
              author: safe(author),
              date: date,
              subject: safe(subject)
            }
          end)

        {:ok, commits}

      _ ->
        {:error, :history_unavailable}
    end
  end

  defp base(repository, sha, nil) do
    case run(repository, ["rev-list", "--parents", "-n", "1", sha, "--"], 8192) do
      {:ok, output, 0} ->
        case String.split(String.trim(output), " ") do
          [_] -> {:ok, @empty}
          [_, parent | _] -> {:ok, parent}
        end

      _ ->
        {:error, :git_unavailable}
    end
  end

  defp base(repository, _sha, base) do
    with :ok <- reachable(repository, base), do: {:ok, base}
  end

  defp run(repository, args, limit) do
    case Git.command(["--git-dir", Git.path(repository) | args], limit: limit) do
      {:error, reason}
      when reason in [:busy, :process_failed, :timeout, "timeout", "caller_interrupted"] ->
        {:error, :git_unavailable}

      result ->
        result
    end
  end

  defp safe(value),
    do:
      if(String.valid?(value),
        do: value,
        else: for(<<byte <- value>>, into: "", do: if(byte in 32..126, do: <<byte>>, else: "�"))
      )
end
