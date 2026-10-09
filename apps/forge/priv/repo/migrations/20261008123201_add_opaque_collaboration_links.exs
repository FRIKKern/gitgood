defmodule Gitgood.Repo.Migrations.AddOpaqueCollaborationLinks do
  use Ecto.Migration

  def up do
    for table_name <- [:pull_requests, :review_events, :release_events] do
      alter table(table_name) do
        add :public_id, :uuid, null: false, default: fragment("gen_random_uuid()")
      end

      create unique_index(table_name, [:public_id])
    end
  end

  def down do
    execute """
    DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pull_requests) OR EXISTS (SELECT 1 FROM review_events)
         OR EXISTS (SELECT 1 FROM release_events) THEN
        RAISE EXCEPTION 'Opaque collaboration links exist; restore a compatible backup instead of discarding links';
      END IF;
    END $$;
    """

    for table_name <- [:release_events, :review_events, :pull_requests] do
      drop unique_index(table_name, [:public_id])

      alter table(table_name) do
        remove :public_id
      end
    end
  end
end
