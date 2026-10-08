defmodule Gitgood.Repo.Migrations.AddSshKeys do
  use Ecto.Migration

  def up do
    drop constraint(:credentials, :kind_allowed)

    create constraint(:credentials, :kind_allowed,
             check: "kind IN ('session','git','checks','ssh')"
           )

    create table(:ssh_keys) do
      add :user_id, references(:users), null: false
      add :credential_id, references(:credentials), null: false
      add :public_key, :text, null: false
      add :fingerprint, :string, null: false
      add :label, :string, null: false
      add :request_key, :string, null: false
      add :request_digest, :binary, null: false
      timestamps(type: :utc_datetime)
    end

    create unique_index(:ssh_keys, [:fingerprint])
    create unique_index(:ssh_keys, [:credential_id])
    create unique_index(:ssh_keys, [:user_id, :request_key])
  end

  def down do
    execute "DO $$ BEGIN IF EXISTS (SELECT 1 FROM credentials WHERE kind = 'ssh') THEN RAISE EXCEPTION 'SSH credential history requires a compatible rollback artifact'; END IF; END $$"
    drop table(:ssh_keys)
    drop constraint(:credentials, :kind_allowed)
    create constraint(:credentials, :kind_allowed, check: "kind IN ('session','git','checks')")
  end
end
