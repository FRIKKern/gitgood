defmodule Gitgood.Repo.Migrations.CreateBarkparkConnections do
  use Ecto.Migration

  def change do
    create table(:barkpark_connections, primary_key: false) do
      add :id, :uuid, primary_key: true
      add :user_id, references(:users, on_delete: :restrict), null: false
      add :generation, :uuid, null: false
      add :origin, :text, null: false
      add :workspace, :text, null: false
      add :project, :text, null: false
      add :dataset, :text, null: false
      add :source_identity, :map, null: false
      add :token_cipher, :binary
      add :disconnected_at, :utc_datetime
      timestamps(type: :utc_datetime)
    end

    create unique_index(:barkpark_connections, [:user_id])

    create constraint(:barkpark_connections, :barkpark_connection_secret_state,
             check:
               "(disconnected_at IS NULL AND token_cipher IS NOT NULL) OR (disconnected_at IS NOT NULL AND token_cipher IS NULL)"
           )

    create table(:barkpark_connection_events, primary_key: false) do
      add :id, :uuid, primary_key: true
      add :user_id, references(:users, on_delete: :restrict), null: false
      add :request_key, :text, null: false
      add :request_digest, :binary, null: false
      add :receipt, :map, null: false
      timestamps(type: :utc_datetime, updated_at: false)
    end

    create unique_index(:barkpark_connection_events, [:user_id, :request_key])
  end
end
