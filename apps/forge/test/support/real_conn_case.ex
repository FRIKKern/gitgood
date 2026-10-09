defmodule GitgoodWeb.RealConnCase do
  @moduledoc """
  Serial integration tests for responsibility committed by an independent connection.
  Shared SQL sandbox transactions cannot exercise that boundary. Fixtures commit to
  the disposable test database and each test removes only its own identified rows.
  """
  use ExUnit.CaseTemplate

  using do
    quote do
      @endpoint GitgoodWeb.Endpoint
      import Plug.Conn
      import Phoenix.ConnTest
    end
  end

  setup tags do
    unless tags[:async] == false, do: raise("Real database tests must run serially")
    :ok = Ecto.Adapters.SQL.Sandbox.mode(Gitgood.Repo, :auto)
    on_exit(fn -> Ecto.Adapters.SQL.Sandbox.mode(Gitgood.Repo, :manual) end)
    :ok
  end
end
