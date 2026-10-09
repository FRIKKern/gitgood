defmodule Gitgood.EvidenceIntent do
  use Ecto.Schema

  schema "evidence_intents" do
    field :public_id, Ecto.UUID, autogenerate: true
    field :repository_id, :integer
    field :pull_request_id, :integer
    field :source_link_id, Ecto.UUID
    field :actor_id, :integer
    field :creation_key, :string
    field :request_digest, :binary
    field :payload_cipher, :binary, load_in_query: false
    field :state, :string, default: "pending"
    field :receipt, :map
    timestamps(type: :utc_datetime)
  end
end
