defmodule Gitgood.SSHIdentityTest do
  use ExUnit.Case, async: false
  alias Gitgood.SSHIdentities

  test "a offered public key is inactive until successful signed authentication activates that connection" do
    user = %{id: 123, username: "fixture"}
    credential = %{id: 456}
    assert SSHIdentities.offer(user, credential)
    assert {:error, :unauthorized} = SSHIdentities.resolve(self())
    assert :denied = SSHIdentities.activate("fixture", "password")
    assert :denied = SSHIdentities.activate("another-user", "publickey")
    assert {:error, :unauthorized} = SSHIdentities.resolve(self())
    assert :ok = SSHIdentities.activate("fixture", "publickey")
    assert {:ok, 123, 456} = SSHIdentities.resolve(self())
    assert {:error, :unauthorized} = SSHIdentities.resolve(Process.whereis(Gitgood.Supervisor))
  end
end
