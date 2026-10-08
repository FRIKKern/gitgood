defmodule Gitgood.Repo.Migrations.BindCheckResultsToCredentialEpoch do
  use Ecto.Migration

  def up do
    alter table(:check_runs), do: add(:credential_id, references(:credentials))

    execute(
      "UPDATE check_runs SET credential_id = check_providers.credential_id FROM check_providers WHERE check_providers.id = check_runs.provider_id"
    )

    execute("ALTER TABLE check_runs ALTER COLUMN credential_id SET NOT NULL")
  end

  def down do
    alter table(:check_runs), do: remove(:credential_id)
  end
end
