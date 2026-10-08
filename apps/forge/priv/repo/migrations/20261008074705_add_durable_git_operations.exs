defmodule Gitgood.Repo.Migrations.AddDurableGitOperations do
  use Ecto.Migration

  def change do
    create table(:git_operations, primary_key: false) do
      add :id, :uuid, primary_key: true
      add :repository_id, references(:repositories), null: false
      add :actor_id, references(:users), null: false
      add :credential_id, references(:credentials), null: false
      add :kind, :string, null: false
      add :state, :string, null: false
      add :capability_digest, :binary
      add :expires_at, :utc_datetime
      add :updates, {:array, :map}, null: false, default: []
      add :outcome, :map, null: false, default: %{}
      timestamps(type: :utc_datetime)
    end

    create index(:git_operations, [:repository_id, :state])
  end
end
