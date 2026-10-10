defmodule Gitgood.InstallationOwnerReceipt do
  use Ecto.Schema
  @primary_key {:id, :integer, autogenerate: false}

  schema "installation_owner_bootstraps" do
    field :installation, Ecto.UUID
    field :request, Ecto.UUID
    field :username, :string
    field :team, :string
    field :input_commitment, :binary
    belongs_to :user, Gitgood.User
    timestamps(type: :utc_datetime)
  end
end
