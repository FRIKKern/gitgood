defmodule Gitgood.PullRequest do
  use Ecto.Schema

  schema "pull_requests" do
    field :public_id, Ecto.UUID, autogenerate: true
    belongs_to :repository, Gitgood.Repository
    belongs_to :author, Gitgood.User
    field :title, :string
    field :body, :string, default: ""
    field :source_ref, :string
    field :target_ref, :string
    field :state, :string, default: "open"
    field :creation_key, :string
    field :request_digest, :binary
    timestamps(type: :utc_datetime)
  end
end

defmodule Gitgood.ReviewEvent do
  use Ecto.Schema

  schema "review_events" do
    field :public_id, Ecto.UUID, autogenerate: true
    belongs_to :pull_request, Gitgood.PullRequest
    belongs_to :actor, Gitgood.User
    field :kind, :string
    field :source_sha, :string
    field :target_sha, :string
    field :path, :string
    field :line, :integer
    field :side, :string
    field :excerpt, :string
    field :body, :string, default: ""
    field :request_key, :string
    field :request_digest, :binary
    timestamps(type: :utc_datetime)
  end
end

defmodule Gitgood.BranchPolicy do
  use Ecto.Schema

  schema "branch_policies" do
    belongs_to :repository, Gitgood.Repository
    field :version, :integer, default: 1
    field :approvals, :integer, default: 1
    field :required_checks, {:array, :map}, default: []
    timestamps(type: :utc_datetime)
  end
end

defmodule Gitgood.CheckProvider do
  use Ecto.Schema

  schema "check_providers" do
    belongs_to :repository, Gitgood.Repository
    belongs_to :credential, Gitgood.Credential
    field :name, :string
    timestamps(type: :utc_datetime)
  end
end

defmodule Gitgood.CheckRun do
  use Ecto.Schema

  schema "check_runs" do
    belongs_to :provider, Gitgood.CheckProvider
    belongs_to :credential, Gitgood.Credential
    field :sha, :string
    field :name, :string
    field :attempt, :integer
    field :sequence, :integer
    field :status, :string
    timestamps(type: :utc_datetime)
  end
end
