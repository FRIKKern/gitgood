defmodule Gitgood.SourceLink do
  use Ecto.Schema
  @primary_key {:id, :binary_id, autogenerate: true}
  schema "source_links" do
    field :generation, Ecto.UUID, autogenerate: true
    field :repository_id, :integer
    field :pull_request_id, :integer
    field :actor_id, :integer
    field :connection_id, Ecto.UUID
    field :source_identity, :map
    field :locator, :map
    field :source_digest, :binary
    field :verified_revision, :string
    field :state, :string, default: "active"
    timestamps(type: :utc_datetime)
  end
end

defmodule Gitgood.SourceLinkEvent do
  use Ecto.Schema
  @primary_key {:id, :binary_id, autogenerate: true}
  schema "source_link_events" do
    field :link_id, Ecto.UUID
    field :pull_request_id, :integer
    field :actor_id, :integer
    field :request_key, :string
    field :request_digest, :binary
    field :kind, :string
    field :source_actor, :map
    field :receipt, :map
    timestamps(type: :utc_datetime)
  end
end
