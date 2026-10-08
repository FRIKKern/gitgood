defmodule Gitgood.BarkparkConnection do
  use Ecto.Schema
  import Ecto.Changeset
  @primary_key {:id, :binary_id, autogenerate: true}
  @derive {Inspect, except: [:token_cipher]}
  schema "barkpark_connections" do
    field :user_id, :integer
    field :generation, Ecto.UUID
    field :origin, :string
    field :workspace, :string
    field :project, :string
    field :dataset, :string
    field :source_identity, :map
    field :token_cipher, :binary
    field :disconnected_at, :utc_datetime
    timestamps(type: :utc_datetime)
  end

  def changeset(row, attrs) do
    row
    |> change(attrs)
    |> validate_required([
      :user_id,
      :generation,
      :origin,
      :workspace,
      :project,
      :dataset,
      :source_identity
    ])
    |> unique_constraint(:user_id)
    |> foreign_key_constraint(:user_id)
    |> check_constraint(:token_cipher, name: :barkpark_connection_secret_state)
  end
end
