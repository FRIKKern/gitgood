defmodule GitgoodWeb.Router do
  use GitgoodWeb, :router

  pipeline :api do
    plug :accepts, ["json"]
    plug :put_secure_browser_headers
    plug :no_cache
  end

  pipeline :authenticated do
    plug GitgoodWeb.Auth
  end

  scope "/", GitgoodWeb do
    pipe_through :api
    get "/health/ready", HealthController, :show
    post "/api/session", SessionController, :create
    post "/api/checks/:team/:name", CheckController, :report
  end

  scope "/api", GitgoodWeb do
    pipe_through [:api, :authenticated]
    get "/session", SessionController, :show
    delete "/session", SessionController, :delete
    get "/repos", RepositoryController, :index
    post "/repos", RepositoryController, :create
    get "/repos/:team/:name", RepositoryController, :show
    get "/repos/:team/:name/branches", BrowseController, :branches
    get "/repos/:team/:name/snapshot", BrowseController, :snapshot
    get "/repos/:team/:name/diff", BrowseController, :diff
    post "/repos/:team/:name/credentials", CredentialController, :create
    get "/repos/:team/:name/pulls", PullController, :index
    post "/repos/:team/:name/pulls", PullController, :create
    get "/repos/:team/:name/pulls/:id", PullController, :show
    get "/repos/:team/:name/pulls/:id/diff", PullController, :diff
    post "/repos/:team/:name/pulls/:id/reviews", PullController, :review
    post "/repos/:team/:name/pulls/:id/merge", PullController, :merge
    get "/repos/:team/:name/operations", PullController, :operations
    get "/repos/:team/:name/operations/:id", PullController, :operation
    get "/repos/:team/:name/policy", CheckController, :show
    put "/repos/:team/:name/policy", CheckController, :policy
    post "/repos/:team/:name/providers", CheckController, :provider
    post "/repos/:team/:name/providers/:id/rotate", CheckController, :rotate
    delete "/credentials/:id", CredentialController, :delete
  end

  scope "/", GitgoodWeb do
    match :*, "/git/:team/:name/*path", GitController, :handle
    post "/internal/pushes/:id", PushHookController, :create
  end

  defp no_cache(conn, _), do: Plug.Conn.put_resp_header(conn, "cache-control", "no-store")
end
