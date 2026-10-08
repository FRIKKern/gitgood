defmodule Gitgood.User do
  use Ecto.Schema
  import Ecto.Changeset

  schema "users" do
    field :username, :string
    field :password_hash, :binary
    field :password_salt, :binary
    timestamps(type: :utc_datetime)
  end

  def changeset(user, attrs) do
    user
    |> cast(attrs, [:username])
    |> validate_required([:username])
    |> validate_format(:username, ~r/\A[a-z][a-z0-9-]{1,39}\z/)
    |> unique_constraint(:username)
  end
end
