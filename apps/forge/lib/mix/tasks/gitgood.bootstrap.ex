defmodule Mix.Tasks.Gitgood.Bootstrap do
  use Mix.Task
  @shortdoc "Create a local actor and membership using GITGOOD_BOOTSTRAP_PASSWORD"
  def run([username, team, role]) do
    Mix.Task.run("app.start")
    password = System.fetch_env!("GITGOOD_BOOTSTRAP_PASSWORD")
    {:ok, user} = Gitgood.Accounts.create_user(username, password)
    {:ok, _} = Gitgood.Accounts.add_member(user, team, role)

    Mix.shell().info(
      "Created #{username} as #{role} in #{team}. Sign in through the web interface."
    )
  end

  def run(_), do: Mix.raise("Usage: mix gitgood.bootstrap USER TEAM owner|writer|reader")
end
