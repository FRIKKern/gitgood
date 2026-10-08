defmodule Gitgood.SSHKey do
  use Ecto.Schema

  schema "ssh_keys" do
    belongs_to :user, Gitgood.User
    belongs_to :credential, Gitgood.Credential
    field :public_key, :string
    field :fingerprint, :string
    field :label, :string
    field :request_key, :string
    field :request_digest, :binary
    timestamps(type: :utc_datetime)
  end
end
