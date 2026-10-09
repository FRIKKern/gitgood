defmodule Gitgood.ConnectionSecrets do
  @moduledoc "Versioned authenticated encryption; separate installation key, actor and generation binding."
  def configured? do
    case key() do
      {:ok, _} -> true
      _ -> false
    end
  end

  def seal(value, binding) when is_binary(value) do
    with {:ok, key} <- key() do
      nonce = :crypto.strong_rand_bytes(12)

      {cipher, tag} =
        :crypto.crypto_one_time_aead(:aes_256_gcm, key, nonce, value, aad(binding), true)

      {:ok, <<1, nonce::binary-size(12), tag::binary-size(16), cipher::binary>>}
    end
  end

  def open(<<1, nonce::binary-size(12), tag::binary-size(16), cipher::binary>>, binding) do
    with {:ok, key} <- key() do
      case :crypto.crypto_one_time_aead(
             :aes_256_gcm,
             key,
             nonce,
             cipher,
             aad(binding),
             tag,
             false
           ) do
        value when is_binary(value) -> {:ok, value}
        _ -> {:error, :connection_secret_unavailable}
      end
    end
  rescue
    _ -> {:error, :connection_secret_unavailable}
  end

  def open(_, _), do: {:error, :connection_secret_unavailable}

  def digest(value) do
    with {:ok, key} <- key(),
         do:
           {:ok,
            :crypto.mac(
              :hmac,
              :sha256,
              key,
              "gitgood-connection-request-v1:" <> Jason.encode!(value)
            )}
  end

  defp aad(binding), do: "gitgood-barkpark-credential-v1:" <> Jason.encode!(binding)

  defp key do
    case Application.get_env(:gitgood, :connection_key) do
      key when is_binary(key) and byte_size(key) == 32 -> {:ok, key}
      _ -> {:error, :connection_key_unconfigured}
    end
  end
end
