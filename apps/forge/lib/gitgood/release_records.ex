defmodule Gitgood.ReleaseRecord do
  use Ecto.Schema
  @primary_key {:id, :binary_id, autogenerate: true}
  schema "release_records" do
    belongs_to :repository, Gitgood.Repository
    belongs_to :creator, Gitgood.User
    belongs_to :credential, Gitgood.Credential
    field :tag, :string
    field :tag_object, :string
    field :commit_sha, :string
    field :base_sha, :string
    field :changes, :map
    field :title, :string
    field :notes, :string
    field :state, :string, default: "draft"
    field :version, :integer, default: 1
    field :creation_key, :string
    field :request_digest, :binary
    field :published_at, :utc_datetime
    field :withdrawn_at, :utc_datetime
    timestamps(type: :utc_datetime)
  end
end

defmodule Gitgood.ReleaseAsset do
  use Ecto.Schema
  @primary_key {:id, :binary_id, autogenerate: true}
  schema "release_assets" do
    belongs_to :release, Gitgood.ReleaseRecord, type: :binary_id
    belongs_to :actor, Gitgood.User
    belongs_to :credential, Gitgood.Credential
    field :name, :string
    field :sha256, :string
    field :size, :integer
    field :state, :string, default: "waiting"
    field :data, :binary, load_in_query: false
    field :creation_key, :string
    field :request_digest, :binary
    timestamps(type: :utc_datetime)
  end
end

defmodule Gitgood.ReleaseEvent do
  use Ecto.Schema

  schema "release_events" do
    belongs_to :release, Gitgood.ReleaseRecord, type: :binary_id
    belongs_to :actor, Gitgood.User
    belongs_to :credential, Gitgood.Credential
    field :kind, :string
    field :snapshot, :map
    field :reason, :string, default: ""
    field :request_key, :string
    field :request_digest, :binary
    timestamps(type: :utc_datetime)
  end
end
