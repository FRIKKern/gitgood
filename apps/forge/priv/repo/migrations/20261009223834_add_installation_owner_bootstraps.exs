defmodule Gitgood.Repo.Migrations.AddInstallationOwnerBootstraps do
  use Ecto.Migration

  def change do
    create table(:installation_owner_bootstraps, primary_key: false) do
      add :id, :smallint, primary_key: true
      add :installation, :uuid, null: false
      add :request, :uuid, null: false
      add :username, :string, size: 40, null: false
      add :team, :string, size: 40, null: false
      add :user_id, references(:users, on_delete: :restrict), null: false
      add :input_commitment, :binary, null: false
      timestamps(type: :utc_datetime)
    end

    create constraint(:installation_owner_bootstraps, :installation_owner_bootstraps_singleton,
             check: "id = 1"
           )

    create constraint(:installation_owner_bootstraps, :installation_owner_bootstraps_bounds,
             check:
               "octet_length(input_commitment) = 32 AND username ~ '^[a-z][a-z0-9-]{1,39}$' AND team ~ '^[a-z][a-z0-9-]{1,39}$'"
           )
  end
end
