defmodule Gitgood.Ref do
  @moduledoc "The supported UTF-8 branch/tag subset of git-check-ref-format, checked again by standard Git."
  def tag?("refs/tags/" <> name), do: branch?("refs/heads/" <> name)
  def tag?(_), do: false

  def branch?(ref) when is_binary(ref) do
    String.valid?(ref) and String.starts_with?(ref, "refs/heads/") and byte_size(ref) <= 1024 and
      not Regex.match?(~r/[\x00-\x20\x7f~^:?*\[\\]/, ref) and
      not String.contains?(ref, ["..", "@{", "//"]) and not String.ends_with?(ref, ["/", "."]) and
      Enum.all?(String.split(ref, "/"), fn part ->
        part != "" and not String.starts_with?(part, ".") and not String.ends_with?(part, ".lock")
      end)
  end

  def branch?(_), do: false
end
