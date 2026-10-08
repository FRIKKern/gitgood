defmodule Gitgood.GitOperation do
  use Ecto.Schema
  @primary_key {:id, :binary_id, autogenerate: true}
  schema "git_operations" do
    belongs_to :repository, Gitgood.Repository
    belongs_to :actor, Gitgood.User
    belongs_to :credential, Gitgood.Credential
    field :kind, :string
    field :state, :string, default: "started"
    field :capability_digest, :binary
    field :expires_at, :utc_datetime
    field :updates, {:array, :map}, default: []
    field :outcome, :map, default: %{}
    timestamps(type: :utc_datetime)
  end
end
