defmodule Gitgood.BarkparkConnectionEvent do
  use Ecto.Schema
  @primary_key {:id, :binary_id, autogenerate: true}
  schema "barkpark_connection_events" do
    field :user_id, :integer
    field :request_key, :string
    field :request_digest, :binary
    field :receipt, :map
    timestamps(type: :utc_datetime, updated_at: false)
  end
end
