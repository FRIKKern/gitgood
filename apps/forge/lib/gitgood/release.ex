defmodule Gitgood.Release do
  @app :gitgood
  def backup, do: Gitgood.OfflineRecovery.run(:backup)
  def export, do: Gitgood.OfflineRecovery.run(:backup)
  def retirement_checkpoint, do: Gitgood.OfflineRecovery.run(:checkpoint)
  def restore, do: Gitgood.OfflineRecovery.run(:restore)

  def migrate do
    Application.load(@app)

    migration = fn ->
      for repo <- Application.fetch_env!(@app, :ecto_repos) do
        {:ok, _, _} = Ecto.Migrator.with_repo(repo, &Ecto.Migrator.run(&1, :up, all: true))
      end
    end

    if Gitgood.InstallationLease.enabled?(),
      do: Gitgood.InstallationLease.with_offline(:migrate, fn _ -> migration.() end),
      else: migration.()
  end

  def bootstrap do
    {:ok, _} = Application.ensure_all_started(@app)
    username = System.fetch_env!("GITGOOD_BOOTSTRAP_USERNAME")
    team = System.fetch_env!("GITGOOD_BOOTSTRAP_TEAM")
    role = System.get_env("GITGOOD_BOOTSTRAP_ROLE", "owner")
    password = System.fetch_env!("GITGOOD_BOOTSTRAP_PASSWORD")

    unless role in ["owner", "writer", "reader"], do: raise("Invalid bootstrap role")

    result =
      Gitgood.Repo.transaction(fn ->
        with {:ok, user} <- Gitgood.Accounts.create_user(username, password),
             {:ok, member} <- Gitgood.Accounts.add_member(user, team, role) do
          member
        else
          _ -> Gitgood.Repo.rollback(:invalid_actor)
        end
      end)

    case result do
      {:ok, _} ->
        IO.puts("Created bootstrap actor")

      _ ->
        raise("Bootstrap failed; inspect the actor configuration without exposing its password")
    end
  end

  def bootstrap_owner do
    owner_bootstrap(:create)
  end

  def observe_bootstrap_owner do
    owner_bootstrap(:observe)
  end

  defp owner_bootstrap(action) do
    params = %{
      "installation" => System.fetch_env!("GITGOOD_BOOTSTRAP_INSTALLATION"),
      "request" => System.fetch_env!("GITGOOD_BOOTSTRAP_REQUEST"),
      "username" => System.fetch_env!("GITGOOD_BOOTSTRAP_USERNAME"),
      "team" => System.fetch_env!("GITGOOD_BOOTSTRAP_TEAM"),
      "password" => System.fetch_env!("GITGOOD_BOOTSTRAP_PASSWORD")
    }

    expected = System.fetch_env!("GITGOOD_BOOTSTRAP_REQUEST_SHA256")
    {:ok, _payload} = Gitgood.InstallationOwnerBootstrap.validate(params, expected)

    result =
      case action do
        :create ->
          {:ok, _} = Application.ensure_all_started(@app)
          Gitgood.InstallationOwnerBootstrap.create(params, expected)

        :observe ->
          Application.load(@app)

          {:ok, observed, _} =
            Ecto.Migrator.with_repo(Gitgood.Repo, fn _ ->
              Gitgood.InstallationOwnerBootstrap.observe(params, expected)
            end)

          observed
      end

    case result do
      {:ok, receipt} -> IO.puts(Jason.encode!(receipt))
      _ -> raise "Installation owner bootstrap refused"
    end
  rescue
    _ -> raise "Installation owner bootstrap refused"
  end
end
