defmodule Gitgood.CriterionEvidence do
  use Ecto.Schema

  schema "criterion_evidence" do
    field :public_id, Ecto.UUID, autogenerate: true
    field :repository_id, :integer
    field :pull_request_id, :integer
    field :source_link_id, Ecto.UUID
    field :link_generation, Ecto.UUID
    field :actor_id, :integer
    field :credential_id, :integer
    field :criterion_index, :integer
    field :criterion_sha256, :string
    field :source_revision, :string
    field :source_sha, :string
    field :target_sha, :string
    field :source_actor, :map
    field :outcome, :string
    field :manifest, :map
    field :artifact_name, :string
    field :artifact_sha256, :string
    field :artifact_size, :integer
    field :artifact_content, :binary, load_in_query: false
    field :creation_key, :string
    field :request_digest, :binary
    timestamps(type: :utc_datetime)
  end
end

defmodule Gitgood.CriterionEvidenceEvent do
  use Ecto.Schema

  schema "criterion_evidence_events" do
    field :evidence_id, :integer
    field :actor_id, :integer
    field :credential_id, :integer
    field :kind, :string
    field :reason, :string
    field :request_key, :string
    field :request_digest, :binary
    timestamps(type: :utc_datetime)
  end
end
