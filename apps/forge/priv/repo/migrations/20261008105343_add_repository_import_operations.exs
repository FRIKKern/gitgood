defmodule Gitgood.Repo.Migrations.AddRepositoryImportOperations do
  use Ecto.Migration

  def up do
    create unique_index(:git_operations, [:repository_id],
             name: :one_pending_repository_import,
             where: "kind = 'import' AND state IN ('started', 'validated', 'uncertain')"
           )
  end

  def down do
    execute """
    DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM git_operations WHERE kind = 'import') THEN
        RAISE EXCEPTION 'Preserve import responsibility: restore matching artifacts instead of downgrading';
      END IF;
    END $$;
    """

    drop index(:git_operations, [:repository_id], name: :one_pending_repository_import)
  end
end
