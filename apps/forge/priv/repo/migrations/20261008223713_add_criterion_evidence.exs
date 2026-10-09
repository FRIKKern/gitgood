defmodule Gitgood.Repo.Migrations.AddCriterionEvidence do
  use Ecto.Migration

  def up do
    create table(:criterion_evidence) do
      add :public_id, :uuid, null: false
      add :repository_id, references(:repositories, on_delete: :restrict), null: false
      add :pull_request_id, references(:pull_requests, on_delete: :restrict), null: false

      add :source_link_id, references(:source_links, type: :uuid, on_delete: :restrict),
        null: false

      add :link_generation, :uuid, null: false
      add :actor_id, references(:users, on_delete: :restrict), null: false
      add :credential_id, references(:credentials, on_delete: :restrict), null: false
      add :criterion_index, :integer, null: false
      add :criterion_sha256, :string, size: 64, null: false
      add :source_revision, :string, size: 128, null: false
      add :source_sha, :string, size: 40, null: false
      add :target_sha, :string, size: 40, null: false
      add :source_actor, :map, null: false
      add :outcome, :string, null: false
      add :manifest, :map, null: false
      add :artifact_name, :string, size: 128, null: false
      add :artifact_sha256, :string, size: 64, null: false
      add :artifact_size, :integer, null: false
      add :artifact_content, :binary, null: false
      add :creation_key, :string, size: 128, null: false
      add :request_digest, :binary, null: false
      timestamps(type: :utc_datetime)
    end

    create unique_index(:criterion_evidence, [:public_id])
    create unique_index(:criterion_evidence, [:source_link_id, :actor_id, :creation_key])
    create index(:criterion_evidence, [:source_link_id, :id])

    create constraint(:criterion_evidence, :criterion_evidence_outcome,
             check: "outcome IN ('passed', 'failed', 'inconclusive')"
           )

    create constraint(:criterion_evidence, :criterion_evidence_bounds,
             check:
               "criterion_index BETWEEN 0 AND 99 AND artifact_size BETWEEN 1 AND 65536 AND artifact_size = octet_length(artifact_content) AND octet_length(request_digest) = 32"
           )

    create constraint(:criterion_evidence, :criterion_evidence_hashes,
             check:
               "criterion_sha256 ~ '^[0-9a-f]{64}$' AND artifact_sha256 ~ '^[0-9a-f]{64}$' AND source_sha ~ '^[0-9a-f]{40}$' AND target_sha ~ '^[0-9a-f]{40}$'"
           )

    create table(:criterion_evidence_events) do
      add :evidence_id, references(:criterion_evidence, on_delete: :restrict), null: false
      add :actor_id, references(:users, on_delete: :restrict), null: false
      add :credential_id, references(:credentials, on_delete: :restrict), null: false
      add :kind, :string, null: false
      add :reason, :string, size: 1000, null: false
      add :request_key, :string, size: 128, null: false
      add :request_digest, :binary, null: false
      timestamps(type: :utc_datetime)
    end

    create unique_index(:criterion_evidence_events, [:evidence_id, :actor_id, :request_key])

    create constraint(:criterion_evidence_events, :criterion_evidence_events_kind,
             check: "kind = 'artifact_unavailable' AND octet_length(request_digest) = 32"
           )
  end

  def down do
    execute("""
    DO $$
    BEGIN
      LOCK TABLE criterion_evidence, criterion_evidence_events IN ACCESS EXCLUSIVE MODE;
      IF EXISTS (SELECT 1 FROM criterion_evidence) OR EXISTS (SELECT 1 FROM criterion_evidence_events) THEN
        RAISE EXCEPTION 'criterion evidence history must be preserved; restore the previous release without dropping these records';
      END IF;
    END
    $$;
    """)

    drop table(:criterion_evidence_events)
    drop table(:criterion_evidence)
  end
end
