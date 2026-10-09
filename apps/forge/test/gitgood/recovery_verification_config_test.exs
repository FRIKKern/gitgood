defmodule Gitgood.RecoveryVerificationConfigTest do
  use ExUnit.Case, async: false

  @operation "a51f8ef6-1fbb-47bb-9562-70ad91b8d37e"
  @keys ~w(GITGOOD_RECOVERY_VERIFY_ONLY GITGOOD_RECOVERY_VERIFY_OPERATION GITGOOD_BARKPARK_ORIGIN GITGOOD_BARKPARK_CA GITGOOD_CONNECTION_KEY GITGOOD_PROXY_KEY DATABASE_URL PHX_HOST GITGOOD_PUBLIC_URL GITGOOD_WEB_ORIGIN GITGOOD_STORAGE SECRET_KEY_BASE GITGOOD_SSH_PORT GITGOOD_SSH_HOST_KEY_DIRECTORY GITGOOD_SSH_PUBLIC_HOST GITGOOD_SSH_PUBLIC_PORT PORT)

  setup do
    before = Map.new(@keys, &{&1, System.get_env(&1)})
    Enum.each(@keys, &System.delete_env/1)

    System.put_env(%{
      "GITGOOD_RECOVERY_VERIFY_ONLY" => "true",
      "GITGOOD_RECOVERY_VERIFY_OPERATION" => @operation,
      "DATABASE_URL" =>
        "postgresql://fixture:inert@127.0.0.1:55432/gitgood_retirement_restore_" <>
          String.replace(@operation, "-", ""),
      "PHX_HOST" => "127.0.0.1",
      "GITGOOD_PUBLIC_URL" => "https://127.0.0.1:28620",
      "GITGOOD_WEB_ORIGIN" => "https://127.0.0.1:28620",
      "GITGOOD_STORAGE" => "/tmp/gitgood-verification-config-inert",
      "SECRET_KEY_BASE" => String.duplicate("inert", 16),
      "GITGOOD_PROXY_KEY" => Base.encode64(:binary.copy(<<17>>, 32))
    })

    on_exit(fn ->
      Enum.each(before, fn
        {key, nil} -> System.delete_env(key)
        {key, value} -> System.put_env(key, value)
      end)
    end)

    :ok
  end

  defp read do
    Config.Reader.read!(Path.expand("../../config/runtime.exs", __DIR__),
      env: :prod,
      target: :host
    )
  end

  test "verification configuration disables automatic reconciliation without opening connections" do
    configuration = read() |> Keyword.fetch!(:gitgood)
    assert configuration[:recovery_verification] == true
    assert configuration[:reconcile] == false
    assert configuration[:barkpark_origin] == nil
  end

  test "malformed, original-database and external-origin verification inputs refuse privately" do
    for {key, value} <- [
          {"GITGOOD_RECOVERY_VERIFY_ONLY", "yes"},
          {"GITGOOD_RECOVERY_VERIFY_OPERATION", "not-an-operation"},
          {"DATABASE_URL", "postgresql://fixture:inert@127.0.0.1:55432/original"},
          {"DATABASE_URL",
           "postgresql://fixture:private-parser-sentinel@127.0.0.1:invalid/target"},
          {"GITGOOD_PUBLIC_URL", "https://example.invalid:28620"},
          {"GITGOOD_PUBLIC_URL", "https://127.0.0.1:invalid"},
          {"GITGOOD_BARKPARK_ORIGIN", "https://example.invalid"}
        ] do
      previous = System.get_env(key)
      System.put_env(key, value)
      assert_raise RuntimeError, "Recovery verification startup refused", fn -> read() end
      if previous == nil, do: System.delete_env(key), else: System.put_env(key, previous)
    end

    System.put_env("GITGOOD_RECOVERY_VERIFY_ONLY", "false")
    assert_raise RuntimeError, "Recovery verification startup refused", fn -> read() end
    System.delete_env("GITGOOD_RECOVERY_VERIFY_OPERATION")
    assert (read() |> Keyword.fetch!(:gitgood))[:recovery_verification] == false
  end
end
