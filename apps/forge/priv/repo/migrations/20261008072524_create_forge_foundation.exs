defmodule Gitgood.Repo.Migrations.CreateForgeFoundation do
  use Ecto.Migration

  def change do
    create table(:users) do
      add :username, :string, null: false
      add :password_hash, :binary, null: false
      add :password_salt, :binary, null: false
      timestamps(type: :utc_datetime)
    end

    create unique_index(:users, [:username])

    create table(:memberships) do
      add :user_id, references(:users), null: false
      add :team, :string, null: false
      add :role, :string, null: false
      timestamps(type: :utc_datetime)
    end

    create unique_index(:memberships, [:user_id, :team])
    create constraint(:memberships, :role_allowed, check: "role IN ('owner','writer','reader')")

    create table(:repositories) do
      add :owner_id, references(:users), null: false
      add :team, :string, null: false
      add :name, :string, null: false
      add :storage_key, :uuid, null: false
      add :status, :string, null: false
      add :creation_key, :string, null: false
      timestamps(type: :utc_datetime)
    end

    create unique_index(:repositories, [:team, :name])
    create unique_index(:repositories, [:owner_id, :creation_key])
    create unique_index(:repositories, [:storage_key])

    create table(:credentials) do
      add :user_id, references(:users), null: false
      add :digest, :binary, null: false
      add :kind, :string, null: false
      add :repository_id, references(:repositories)
      add :expires_at, :utc_datetime, null: false
      add :revoked_at, :utc_datetime
      timestamps(type: :utc_datetime)
    end

    create unique_index(:credentials, [:digest])
    create constraint(:credentials, :kind_allowed, check: "kind IN ('session','git','checks')")
  end
end
