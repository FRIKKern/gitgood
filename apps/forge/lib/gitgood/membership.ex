defmodule Gitgood.Membership do
  use Ecto.Schema

  schema "memberships" do
    belongs_to :user, Gitgood.User
    field :team, :string
    field :role, :string
    timestamps(type: :utc_datetime)
  end
end
