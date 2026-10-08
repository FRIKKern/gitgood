defmodule Gitgood.Repo.Migrations.VersionManagedGitStorage do
  use Ecto.Migration

  def change do
    alter table(:repositories) do
      add :storage_version, :integer, null: false, default: 1
    end
  end
end
