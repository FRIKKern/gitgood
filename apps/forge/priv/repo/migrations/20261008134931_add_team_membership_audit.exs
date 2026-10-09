defmodule Gitgood.Repo.Migrations.AddTeamMembershipAudit do
  use Ecto.Migration

  def up do
    create table(:membership_events, primary_key: false) do
      add :id, :uuid, primary_key: true
      add :team, :string, null: false
      add :actor_id, references(:users), null: false
      add :target_id, references(:users), null: false
      add :previous_role, :string
      add :role, :string
      add :request_key, :string, null: false
      add :request_digest, :binary, null: false
      timestamps(type: :utc_datetime)
    end

    create unique_index(:membership_events, [:team, :actor_id, :request_key])
    create index(:membership_events, [:team, :inserted_at])

    create constraint(:membership_events, :valid_previous_role,
             check: "previous_role IS NULL OR previous_role IN ('owner','writer','reader')"
           )

    create constraint(:membership_events, :valid_new_role,
             check: "role IS NULL OR role IN ('owner','writer','reader')"
           )
  end

  def down do
    execute """
    DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM membership_events) THEN
        RAISE EXCEPTION 'Membership audit records must be preserved; use a forward-compatible recovery';
      END IF;
    END $$;
    """

    drop table(:membership_events)
  end
end
