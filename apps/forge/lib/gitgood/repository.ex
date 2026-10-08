defmodule Gitgood.Repository do
  use Ecto.Schema
  import Ecto.Changeset

  schema "repositories" do
    belongs_to :owner, Gitgood.User
    field :team, :string
    field :name, :string
    field :storage_key, Ecto.UUID
    field :status, :string, default: "creating"
    field :creation_key, :string
    timestamps(type: :utc_datetime)
  end

  def changeset(repository, attrs) do
    repository
    |> cast(attrs, [:name])
    |> validate_required([:name])
    |> validate_format(:name, ~r/\A[a-z][a-z0-9-]{1,63}\z/)
    |> unique_constraint([:team, :name])
    |> unique_constraint([:owner_id, :creation_key])
  end
end
