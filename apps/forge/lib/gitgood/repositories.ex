defmodule Gitgood.Repositories do
  import Ecto.Query
  alias Gitgood.{Accounts, Git, Membership, Repo, Repository}

  def list(user) do
    Repo.all(
      from r in Repository,
        join: m in Membership,
        on: m.team == r.team,
        where: m.user_id == ^user.id,
        order_by: [desc: r.id]
    )
  end

  def get(user, team, name) do
    if Accounts.role(user.id, team),
      do: Repo.get_by(Repository, team: team, name: name),
      else: nil
  end

  def create(user, team, name, key)
      when is_binary(team) and is_binary(name) and is_binary(key) and byte_size(key) in 8..128 do
    if Accounts.role(user.id, team) in ["owner", "writer"] do
      case Repo.get_by(Repository, owner_id: user.id, creation_key: key) do
        %Repository{team: ^team, name: ^name} = repository ->
          finish(repository)

        %Repository{} ->
          {:error, :idempotency_conflict}

        nil ->
          %Repository{
            owner_id: user.id,
            team: team,
            storage_key: Ecto.UUID.generate(),
            creation_key: key
          }
          |> Repository.changeset(%{name: name})
          |> Repo.insert()
          |> case do
            {:ok, repository} ->
              finish(repository)

            {:error, changeset} ->
              case Repo.get_by(Repository, owner_id: user.id, creation_key: key) do
                %Repository{team: ^team, name: ^name} = repository -> finish(repository)
                %Repository{} -> {:error, :idempotency_conflict}
                nil -> {:error, changeset}
              end
          end
      end
    else
      {:error, :forbidden}
    end
  end

  def create(_, _, _, _), do: {:error, :idempotency_key_required}

  def finish(repository) do
    # The intent row commits first. This lock serializes initialization/recovery across nodes.
    Repo.transaction(fn ->
      current = Repo.one!(from r in Repository, where: r.id == ^repository.id, lock: "FOR UPDATE")

      if current.status == "ready" do
        current
      else
        case Git.init(current) do
          :ok -> current |> Ecto.Changeset.change(status: "ready") |> Repo.update!()
          {:error, error} -> Repo.rollback(error)
        end
      end
    end)
  end

  def reconcile do
    Repo.all(from r in Repository, where: r.status == "creating") |> Enum.map(&finish/1)
  end

  def public(repository) do
    %{
      id: repository.id,
      team: repository.team,
      name: repository.name,
      owner_id: repository.owner_id,
      status: repository.status,
      url: "/repos/#{repository.team}/#{repository.name}",
      clone_url:
        Application.fetch_env!(:gitgood, :public_url) <>
          "/git/#{repository.team}/#{repository.name}.git"
    }
  end
end
