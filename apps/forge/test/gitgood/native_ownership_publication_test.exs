defmodule Gitgood.NativeOwnershipPublicationTest do
  use ExUnit.Case, async: true
  alias Gitgood.NativeOwnershipPublication, as: Publication

  defp record do
    Map.new(
      ~w(protocol kind installation operation candidate mode binding_sha256 pointer scope owner database_session guard),
      &{&1, %{}}
    )
    |> Map.merge(%{
      "protocol" => 2,
      "kind" => "native_application_ownership",
      "mode" => "runtime",
      "owner" => %{"pid" => 42}
    })
  end

  defp reply do
    %{
      "protocol" => 2,
      "status" => "retained",
      "ownership_marker_retained" => true,
      "operation" => "operation",
      "record_sha256" => String.duplicate("a", 64),
      "marker_sha256" => String.duplicate("b", 64),
      "installation_readiness_established" => false,
      "replacement_admitted" => false,
      "writer_exclusion_established" => false,
      "lifecycle_responsibility_admitted" => false
    }
  end

  test "canonical bytes agree with Python sorted ASCII JSON including surrogate pairs" do
    assert Publication.canonical(%{"z" => [true, false, nil, 123], "a" => "é😀\n\"\\"}) ==
             ~S({"a":"\u00e9\ud83d\ude00\n\"\\","z":[true,false,null,123]})
  end

  test "canonical grammar rejects floats atoms nonstring keys and excessive nesting" do
    for value <- [
          1.0,
          :arbitrary,
          %{atom: 1},
          <<255>>,
          Enum.reduce(1..14, 1, fn _, value -> [value] end)
        ] do
      assert_raise ArgumentError, fn -> Publication.canonical(value) end
    end
  end

  test "request is closed and bound to the actual calling owner" do
    assert {:ok, request, digest} = Publication.request(record(), 42)
    assert Jason.decode!(request) == %{"protocol" => 2, "record" => record()}

    assert digest ==
             :crypto.hash(:sha256, Publication.canonical(record())) |> Base.encode16(case: :lower)

    for changed <- [
          Map.put(record(), "command", "ignored"),
          Map.delete(record(), "guard"),
          Map.put(record(), "protocol", 2.0),
          Map.put(record(), "mode", "arbitrary"),
          put_in(record(), ["owner", "pid"], 43)
        ] do
      assert {:error, :native_ownership_publication_unavailable} =
               Publication.request(changed, 42)
    end
  end

  test "oversized request refuses before execution" do
    assert {:error, :native_ownership_publication_unavailable} =
             Publication.request(
               Map.put(record(), "candidate", String.duplicate("a", 16_384)),
               42
             )
  end

  test "retained reply establishes no readiness replacement or lifecycle authority" do
    assert :ok = Publication.validate_reply(reply(), "operation", String.duplicate("a", 64))

    for field <-
          ~w(installation_readiness_established replacement_admitted writer_exclusion_established lifecycle_responsibility_admitted) do
      assert :error =
               Publication.validate_reply(
                 Map.put(reply(), field, true),
                 "operation",
                 String.duplicate("a", 64)
               )
    end
  end

  test "changed operation record digest malformed marker or extra authority refuses" do
    for changed <- [
          Map.put(reply(), "operation", "other"),
          Map.put(reply(), "record_sha256", String.duplicate("c", 64)),
          Map.put(reply(), "marker_sha256", "invalid"),
          Map.put(reply(), "extra", true),
          Map.delete(reply(), "replacement_admitted"),
          Map.put(reply(), "ownership_marker_retained", false)
        ] do
      assert :error = Publication.validate_reply(changed, "operation", String.duplicate("a", 64))
    end
  end
end
