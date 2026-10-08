defmodule Gitgood.PaperReturnPointer do
  @moduledoc "Owned Paper block transformation; no source contents in failure results."

  def block(operation) do
    %{
      "id" => "gitgood-link-" <> operation.link_id,
      "type" => "paragraph",
      "content" => [
        %{
          "type" => "link",
          "href" => operation.destination,
          "children" => [%{"type" => "text", "value" => "Open linked Gitgood change"}]
        }
      ]
    }
  end

  def check(document, operation) do
    with :ok <- identity(document, operation),
         blocks when is_list(blocks) <- document["blocks"],
         true <- length(blocks) <= 1000 do
      owned = Enum.filter(blocks, &(is_map(&1) && &1["id"] == block(operation)["id"]))

      case owned do
        [] ->
          {:ok, :absent}

        [value] ->
          if value == block(operation), do: {:ok, :present}, else: {:error, :pointer_conflict}

        _ ->
          {:error, :pointer_conflict}
      end
    else
      _ -> {:error, :unsupported_paper}
    end
  end

  def prepare(document, operation) do
    case check(document, operation) do
      {:ok, :absent} ->
        payload =
          Jason.encode!(%{
            "mutations" => [
              %{
                "patch" => %{
                  "id" => document["_id"],
                  "type" => "paper",
                  "ifRevisionID" => document["_rev"],
                  "set" => %{"blocks" => document["blocks"] ++ [block(operation)]}
                }
              }
            ]
          })

        if byte_size(payload) <= 400_000,
          do: {:ok, payload, document["_rev"]},
          else: {:error, :unsupported_paper}

      other ->
        other
    end
  end

  defp identity(document, operation) when is_map(document) do
    if document["_type"] == "paper" && document["_id"] == operation.locator["document_id"] &&
         is_binary(document["_rev"]) && byte_size(document["_rev"]) in 1..128,
       do: :ok,
       else: {:error, :unsupported_paper}
  end

  defp identity(_, _), do: {:error, :unsupported_paper}
end
