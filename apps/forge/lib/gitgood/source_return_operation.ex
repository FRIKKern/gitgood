defmodule Gitgood.SourceReturnOperation do
  use Ecto.Schema
  @primary_key {:id, :binary_id, autogenerate: true}
  @derive {Inspect, except: [:payload_cipher]}
  schema "source_return_operations" do
    field :repository_id, :integer
    field :pull_request_id, :integer
    field :link_id, Ecto.UUID
    field :link_generation, Ecto.UUID
    field :actor_id, :integer
    field :actor_label, :string
    field :credential_id, :integer
    field :connection_id, Ecto.UUID
    field :connection_generation, Ecto.UUID
    field :source_identity, :map
    field :locator, :map
    field :destination, :string
    field :request_key, :string
    field :request_digest, :binary
    field :state, :string, default: "queued"
    field :attempts, :integer, default: 0
    field :automatic_until, :integer, default: 5
    field :attempt_id, Ecto.UUID
    field :lease_until, :utc_datetime
    field :next_at, :utc_datetime
    field :sent_once, :boolean, default: false
    field :payload_cipher, :binary
    field :payload_digest, :binary
    field :before_revision, :string
    field :after_revision, :string
    field :source_transaction, :string
    field :observation, :map
    field :reason, :string
    timestamps(type: :utc_datetime)
  end
end
