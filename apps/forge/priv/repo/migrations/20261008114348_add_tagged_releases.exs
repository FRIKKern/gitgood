defmodule Gitgood.Repo.Migrations.AddTaggedReleases do
  use Ecto.Migration

  def up do
    create table(:release_records, primary_key: false) do
      add :id, :uuid, primary_key: true
      add :repository_id, references(:repositories), null: false
      add :creator_id, references(:users), null: false
      add :credential_id, references(:credentials), null: false
      add :tag, :text, null: false
      add :tag_object, :string, null: false
      add :commit_sha, :string, null: false
      add :base_sha, :string
      add :changes, :map, null: false
      add :title, :text, null: false
      add :notes, :text, null: false
      add :state, :string, null: false, default: "draft"
      add :version, :integer, null: false, default: 1
      add :creation_key, :string, null: false
      add :request_digest, :binary, null: false
      add :published_at, :utc_datetime
      add :withdrawn_at, :utc_datetime
      timestamps(type: :utc_datetime)
    end

    create unique_index(:release_records, [:repository_id, :creator_id, :creation_key])
    create unique_index(:release_records, [:repository_id, :tag])

    create constraint(:release_records, :release_state,
             check: "state IN ('draft','published','withdrawn') AND version > 0"
           )

    create table(:release_assets, primary_key: false) do
      add :id, :uuid, primary_key: true
      add :release_id, references(:release_records, type: :uuid), null: false
      add :actor_id, references(:users), null: false
      add :credential_id, references(:credentials), null: false
      add :name, :string, null: false
      add :sha256, :string, null: false
      add :size, :integer, null: false
      add :state, :string, null: false, default: "waiting"
      add :data, :binary
      add :creation_key, :string, null: false
      add :request_digest, :binary, null: false
      timestamps(type: :utc_datetime)
    end

    create unique_index(:release_assets, [:release_id, :actor_id, :creation_key])

    create unique_index(:release_assets, [:release_id, :name],
             where: "state != 'cancelled'",
             name: :active_release_asset_name
           )

    create constraint(:release_assets, :release_asset_identity,
             check:
               "size BETWEEN 1 AND 16777216 AND sha256 ~ '^[0-9a-f]{64}$' AND ((state = 'ready' AND data IS NOT NULL AND octet_length(data) = size) OR (state IN ('waiting','cancelled') AND data IS NULL))"
           )

    create table(:release_events) do
      add :release_id, references(:release_records, type: :uuid), null: false
      add :actor_id, references(:users), null: false
      add :credential_id, references(:credentials), null: false
      add :kind, :string, null: false
      add :snapshot, :map, null: false
      add :reason, :text, null: false, default: ""
      add :request_key, :string
      add :request_digest, :binary
      timestamps(type: :utc_datetime)
    end

    create unique_index(:release_events, [:release_id, :actor_id, :request_key])
  end

  def down do
    execute """
    DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM release_records) THEN
        RAISE EXCEPTION 'Release claims and assets must be preserved; restore a compatible backup instead';
      END IF;
    END $$;
    """

    drop table(:release_events)
    drop table(:release_assets)
    drop table(:release_records)
  end
end
