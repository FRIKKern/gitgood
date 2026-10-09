defmodule Gitgood.Repo.Migrations.AddEvidenceIntents do
  use Ecto.Migration

  def up do
    create table(:evidence_intents) do
      add :public_id, :uuid, null: false
      add :repository_id, references(:repositories, on_delete: :restrict), null: false
      add :pull_request_id, references(:pull_requests, on_delete: :restrict), null: false

      add :source_link_id, references(:source_links, type: :uuid, on_delete: :restrict),
        null: false

      add :actor_id, references(:users, on_delete: :restrict), null: false
      add :creation_key, :string, size: 128, null: false
      add :request_digest, :binary, null: false
      add :payload_cipher, :binary, null: false
      add :state, :string, null: false, default: "pending"
      add :receipt, :map
      timestamps(type: :utc_datetime)
    end

    create unique_index(:evidence_intents, [:public_id])
    create unique_index(:evidence_intents, [:source_link_id, :actor_id, :creation_key])

    create unique_index(:evidence_intents, [:source_link_id, :actor_id],
             name: :evidence_intents_one_pending,
             where: "state IN ('pending', 'confirmed')"
           )

    create constraint(:evidence_intents, :evidence_intents_state,
             check:
               "state IN ('pending', 'confirmed', 'acknowledged', 'retired') AND ((state IN ('confirmed', 'acknowledged')) = (receipt IS NOT NULL))"
           )

    create constraint(:evidence_intents, :evidence_intents_bounds,
             check:
               "octet_length(request_digest) = 32 AND octet_length(payload_cipher) BETWEEN 30 AND 1048576"
           )
  end

  def down do
    execute("""
    DO $$ BEGIN
      LOCK TABLE evidence_intents IN ACCESS EXCLUSIVE MODE;
      IF EXISTS (SELECT 1 FROM evidence_intents) THEN
        RAISE EXCEPTION 'durable evidence requests must be preserved; use forward repair';
      END IF;
    END $$;
    """)

    drop table(:evidence_intents)
  end
end
