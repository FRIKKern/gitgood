defmodule Gitgood.Credential do
  use Ecto.Schema

  schema "credentials" do
    belongs_to :user, Gitgood.User
    field :digest, :binary
    field :kind, :string
    field :expires_at, :utc_datetime
    field :revoked_at, :utc_datetime
    field :repository_id, :integer
    timestamps(type: :utc_datetime)
  end
end
