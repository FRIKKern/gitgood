defmodule Gitgood.RecoverySecretsTest do
  use ExUnit.Case, async: false

  alias Gitgood.{
    BarkparkConnection,
    BarkparkConnections,
    ConnectionSecrets,
    SourceReturnOperation,
    SourceReturns
  }

  setup do
    previous = Application.get_env(:gitgood, :connection_key)
    Application.put_env(:gitgood, :connection_key, :crypto.strong_rand_bytes(32))
    on_exit(fn -> Application.put_env(:gitgood, :connection_key, previous) end)
    :ok
  end

  test "recoverable credential requires the correct key, owner and generation without returning plaintext" do
    row = %BarkparkConnection{
      id: Ecto.UUID.generate(),
      user_id: 123,
      generation: Ecto.UUID.generate(),
      origin: "https://source.example.invalid"
    }

    {:ok, cipher} =
      ConnectionSecrets.seal("synthetic-credential", [
        row.user_id,
        row.id,
        row.generation,
        row.origin
      ])

    row = %{row | token_cipher: cipher}
    assert BarkparkConnections.recoverable_secret?(row)
    refute BarkparkConnections.recoverable_secret?(%{row | user_id: 124})
    refute BarkparkConnections.recoverable_secret?(%{row | generation: Ecto.UUID.generate()})
    Application.put_env(:gitgood, :connection_key, :crypto.strong_rand_bytes(32))
    refute BarkparkConnections.recoverable_secret?(row)
  end

  test "sealed source responsibility also verifies its exact payload digest and original binding" do
    op = %SourceReturnOperation{
      id: Ecto.UUID.generate(),
      actor_id: 123,
      link_generation: Ecto.UUID.generate(),
      connection_id: Ecto.UUID.generate(),
      connection_generation: Ecto.UUID.generate(),
      locator: %{"origin" => "https://source.example.invalid"}
    }

    body = ~s({"mutations":[]})

    binding = [
      "source-journal-payload-v1",
      op.id,
      op.actor_id,
      op.link_generation,
      op.connection_id,
      op.connection_generation,
      op.locator["origin"]
    ]

    {:ok, cipher} = ConnectionSecrets.seal(body, binding)
    op = %{op | payload_cipher: cipher, payload_digest: :crypto.hash(:sha256, body)}
    assert SourceReturns.recoverable_request?(op)

    refute SourceReturns.recoverable_request?(%{
             op
             | payload_digest: :crypto.hash(:sha256, "different")
           })

    refute SourceReturns.recoverable_request?(%{op | actor_id: 124})
    refute SourceReturns.recoverable_request?(%{op | connection_generation: Ecto.UUID.generate()})
    Application.put_env(:gitgood, :connection_key, nil)
    refute SourceReturns.recoverable_request?(op)
  end
end
