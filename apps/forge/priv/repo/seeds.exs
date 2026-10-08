# Disposable development fixtures only. Production bootstrap is explicit and password comes from the environment.
if Mix.env() == :prod, do: raise("Synthetic fixtures are forbidden in production")

for {name, team, role} <- [
      {"owner", "team", "owner"},
      {"reviewer", "team", "writer"},
      {"reader", "team", "reader"},
      {"outsider", "elsewhere", "owner"}
    ] do
  unless Gitgood.Repo.get_by(Gitgood.User, username: name) do
    {:ok, user} = Gitgood.Accounts.create_user(name, "synthetic-password")
    {:ok, _} = Gitgood.Accounts.add_member(user, team, role)
  end
end
