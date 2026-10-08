defmodule Gitgood.Repo.Migrations.AddNativeSourceLinks do
  use Ecto.Migration

  def up do
    create table(:source_links, primary_key: false) do
      add :id, :uuid, primary_key: true
      add :generation, :uuid, null: false
      add :repository_id, references(:repositories, on_delete: :restrict), null: false
      add :pull_request_id, references(:pull_requests, on_delete: :restrict), null: false
      add :actor_id, references(:users, on_delete: :restrict), null: false

      add :connection_id, references(:barkpark_connections, type: :uuid, on_delete: :restrict),
        null: false

      add :source_identity, :map, null: false
      add :locator, :map, null: false
      add :source_digest, :binary, null: false
      add :verified_revision, :string, size: 128, null: false
      add :state, :string, null: false
      timestamps(type: :utc_datetime)
    end

    create unique_index(:source_links, [:pull_request_id, :source_digest])
    create constraint(:source_links, :source_links_state, check: "state IN ('active', 'removed')")

    create constraint(:source_links, :source_links_digest,
             check: "octet_length(source_digest) = 32"
           )

    create table(:source_link_events, primary_key: false) do
      add :id, :uuid, primary_key: true
      add :link_id, references(:source_links, type: :uuid, on_delete: :restrict), null: false
      add :pull_request_id, references(:pull_requests, on_delete: :restrict), null: false
      add :actor_id, references(:users, on_delete: :restrict), null: false
      add :request_key, :string, size: 128, null: false
      add :request_digest, :binary, null: false
      add :kind, :string, null: false
      add :source_actor, :map
      add :receipt, :map, null: false
      timestamps(type: :utc_datetime)
    end

    create unique_index(:source_link_events, [:pull_request_id, :actor_id, :request_key])

    create constraint(:source_link_events, :source_link_events_kind,
             check: "kind IN ('attach', 'remove')"
           )

    create constraint(:source_link_events, :source_link_events_digest,
             check: "octet_length(request_digest) = 32"
           )
  end

  def down do
    execute("""
    DO $$
    BEGIN
      LOCK TABLE source_links, source_link_events IN ACCESS EXCLUSIVE MODE;
      IF EXISTS (SELECT 1 FROM source_links) OR EXISTS (SELECT 1 FROM source_link_events) THEN
        RAISE EXCEPTION 'native source link responsibility must be preserved; restore the previous release without dropping these records';
      END IF;
    END
    $$;
    """)

    drop table(:source_link_events)
    drop table(:source_links)
  end
end
