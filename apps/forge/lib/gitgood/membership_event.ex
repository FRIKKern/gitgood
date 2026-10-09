defmodule Gitgood.MembershipEvent do
  use Ecto.Schema
  @primary_key {:id, Ecto.UUID, autogenerate: true}
  schema "membership_events" do
    field :team, :string
    belongs_to :actor, Gitgood.User
    belongs_to :target, Gitgood.User
    field :previous_role, :string
    field :role, :string
    field :request_key, :string
    field :request_digest, :binary
    timestamps(type: :utc_datetime)
  end
end
