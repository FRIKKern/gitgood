defmodule Gitgood.Repo.Migrations.AddProtectedCollaboration do
  use Ecto.Migration

  def change do
    create table(:pull_requests) do
      add :repository_id, references(:repositories), null: false
      add :author_id, references(:users), null: false
      add :title, :string, null: false
      add :body, :text, null: false, default: ""
      add :source_ref, :string, null: false
      add :target_ref, :string, null: false
      add :state, :string, null: false, default: "open"
      add :creation_key, :string, null: false
      add :request_digest, :binary, null: false
      timestamps(type: :utc_datetime)
    end

    create unique_index(:pull_requests, [:repository_id, :author_id, :creation_key])

    create table(:review_events) do
      add :pull_request_id, references(:pull_requests), null: false
      add :actor_id, references(:users), null: false
      add :kind, :string, null: false
      add :source_sha, :string, null: false
      add :target_sha, :string, null: false
      add :path, :text
      add :line, :integer
      add :side, :string
      add :excerpt, :text
      add :body, :text, null: false, default: ""
      add :request_key, :string, null: false
      add :request_digest, :binary, null: false
      timestamps(type: :utc_datetime)
    end

    create unique_index(:review_events, [:pull_request_id, :actor_id, :request_key])

    create table(:branch_policies) do
      add :repository_id, references(:repositories), null: false
      add :version, :integer, null: false, default: 1
      add :approvals, :integer, null: false, default: 1
      add :required_checks, {:array, :map}, null: false, default: []
      timestamps(type: :utc_datetime)
    end

    create unique_index(:branch_policies, [:repository_id])

    create table(:check_providers) do
      add :repository_id, references(:repositories), null: false
      add :credential_id, references(:credentials), null: false
      add :name, :string, null: false
      timestamps(type: :utc_datetime)
    end

    create unique_index(:check_providers, [:repository_id, :name])
    create unique_index(:check_providers, [:credential_id])

    create table(:check_runs) do
      add :provider_id, references(:check_providers), null: false
      add :sha, :string, null: false
      add :name, :string, null: false
      add :attempt, :integer, null: false
      add :sequence, :integer, null: false
      add :status, :string, null: false
      timestamps(type: :utc_datetime)
    end

    create unique_index(:check_runs, [:provider_id, :sha, :name, :attempt])

    alter table(:git_operations) do
      add :request_key, :string
      add :request_digest, :binary
      add :metadata, :map, null: false, default: %{}
    end

    create unique_index(:git_operations, [:repository_id, :actor_id, :kind, :request_key])
  end
end
