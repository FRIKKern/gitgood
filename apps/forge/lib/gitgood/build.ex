defmodule Gitgood.Build do
  @file Path.expand("../../priv/build-identity.json", __DIR__)
  @external_resource @file
  @identity if File.exists?(@file),
              do: Jason.decode!(File.read!(@file)),
              else: %{"candidate" => "unconfigured", "dirty" => true, "migrations" => []}
  def identity, do: @identity

  def valid?,
    do: Regex.match?(~r/\A[0-9a-f]{40}\z/, @identity["candidate"]) and @identity["dirty"] == false

  def public, do: Map.take(@identity, ["candidate", "dirty", "built_at", "locks", "requirements"])
end
