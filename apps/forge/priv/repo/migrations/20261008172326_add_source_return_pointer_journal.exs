defmodule Gitgood.Repo.Migrations.AddSourceReturnPointerJournal do
  use Ecto.Migration

  def up do
    create table(:source_return_operations, primary_key: false) do
      add :id, :uuid, primary_key: true
      add :repository_id, references(:repositories, on_delete: :restrict), null: false
      add :pull_request_id, references(:pull_requests, on_delete: :restrict), null: false
      add :link_id, references(:source_links, type: :uuid, on_delete: :restrict), null: false
      add :link_generation, :uuid, null: false
      add :actor_id, references(:users, on_delete: :restrict), null: false
      add :actor_label, :string, size: 40, null: false
      add :credential_id, references(:credentials, on_delete: :restrict), null: false

      add :connection_id, references(:barkpark_connections, type: :uuid, on_delete: :restrict),
        null: false

      add :connection_generation, :uuid, null: false
      add :source_identity, :map, null: false
      add :locator, :map, null: false
      add :destination, :string, size: 2048, null: false
      add :request_key, :string, size: 128, null: false
      add :request_digest, :binary, null: false
      add :state, :string, null: false
      add :attempts, :integer, null: false, default: 0
      add :automatic_until, :integer, null: false, default: 5
      add :attempt_id, :uuid
      add :lease_until, :utc_datetime
      add :next_at, :utc_datetime, null: false
      add :sent_once, :boolean, null: false, default: false
      add :payload_cipher, :binary
      add :payload_digest, :binary
      add :before_revision, :string, size: 128
      add :after_revision, :string, size: 128
      add :source_transaction, :string, size: 128
      add :observation, :map
      add :reason, :string, size: 64
      timestamps(type: :utc_datetime)
    end

    create unique_index(:source_return_operations, [:pull_request_id, :actor_id, :request_key])
    create index(:source_return_operations, [:state, :next_at, :lease_until])

    create constraint(:source_return_operations, :source_return_operations_state,
             check:
               "state IN ('queued','prepared','sending','unknown','paused','applied','observed','denied','conflict','unsupported','stopped')"
           )

    create constraint(:source_return_operations, :source_return_operations_attempts,
             check: "attempts >= 0 AND automatic_until >= attempts"
           )

    create constraint(:source_return_operations, :source_return_operations_digests,
             check:
               "octet_length(request_digest) = 32 AND (payload_digest IS NULL OR octet_length(payload_digest) = 32)"
           )
  end

  def down do
    execute("""
    DO $$
    BEGIN
      LOCK TABLE source_return_operations IN ACCESS EXCLUSIVE MODE;
      IF EXISTS (SELECT 1 FROM source_return_operations) THEN
        RAISE EXCEPTION 'source write responsibility must be preserved; restore the previous release without dropping this journal';
      END IF;
    END
    $$;
    """)

    drop table(:source_return_operations)
  end
end
