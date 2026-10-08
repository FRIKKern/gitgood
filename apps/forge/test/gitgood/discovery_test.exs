defmodule Gitgood.DiscoveryTest do
  use GitgoodWeb.ConnCase, async: false
  alias Gitgood.{Accounts, Discovery, Membership, PullRequest, Repo, Repository}

  setup do
    {:ok, reader} = Accounts.create_user("discovery-reader", "synthetic-password")
    {:ok, owner} = Accounts.create_user("discovery-owner", "synthetic-password")
    {:ok, hidden} = Accounts.create_user("discovery-hidden", "synthetic-password")
    Accounts.add_member(reader, "visible", "reader")
    Accounts.add_member(owner, "visible", "owner")
    Accounts.add_member(hidden, "hidden", "owner")
    {_, credential} = Accounts.issue(reader, "session")
    {_, foreign} = Accounts.issue(hidden, "session")

    make = fn actor, team ->
      %Repository{
        owner_id: actor.id,
        team: team,
        storage_key: Ecto.UUID.generate(),
        creation_key: "discover-" <> team
      }
      |> Repository.changeset(%{name: "project"})
      |> Repo.insert!()
    end

    repository = make.(owner, "visible")
    private = make.(hidden, "hidden")
    # Metadata fixtures exercise the read index; actual Git/browser flows prove
    # creation and navigation separately.
    add = fn repository, actor, title, index ->
      Repo.insert!(%PullRequest{
        repository_id: repository.id,
        author_id: actor.id,
        title: title,
        body: "Résumé context for " <> title,
        source_ref: "refs/heads/feature",
        target_ref: "refs/heads/main",
        creation_key: "discovery-" <> to_string(index),
        request_digest: Accounts.digest(to_string(index))
      })
    end

    allowed = add.(repository, owner, "Visible literal %_! needle", 1)
    add.(private, hidden, "Hidden needle", 2)

    %{
      reader: reader,
      credential: credential,
      foreign: foreign,
      owner: owner,
      repository: repository,
      private: private,
      allowed: allowed,
      add: add
    }
  end

  test "search snippets, links and activity include only permitted records", ctx do
    assert {:ok, result} = Discovery.search(ctx.reader, ctx.credential, %{"q" => "needle"})
    assert [record] = result.records
    assert record["title"] == ctx.allowed.title
    assert record["actor"] == ctx.owner.username
    assert record["url"] == "/repos/visible/project/pulls/" <> ctx.allowed.public_id
    assert String.starts_with?(record["snippet"], "Résumé")
    refute Map.has_key?(result, :total_count)
    refute Map.has_key?(record, "uid")
    assert {:ok, hidden} = Discovery.search(ctx.reader, ctx.credential, %{"q" => "Hidden"})
    assert hidden.records == []
    assert {:ok, feed} = Discovery.activity(ctx.reader, ctx.credential, %{})
    assert Enum.all?(feed.records, &(&1["team"] == "visible"))
    assert Enum.all?(feed.records, &(is_binary(&1["occurred_at"]) and byte_size(&1["id"]) == 43))

    assert {:error, :repository_not_found} =
             Discovery.activity(ctx.reader, ctx.credential, %{
               "team" => "hidden",
               "name" => "project"
             })

    assert {:error, :authorization_changed} =
             Discovery.search(ctx.reader, ctx.foreign, %{"q" => "needle"})
  end

  test "wildcards are literal, UTF8 is retained, bad and unknown inputs are refused", ctx do
    assert {:ok, result} = Discovery.search(ctx.reader, ctx.credential, %{"q" => "%_!"})
    assert length(result.records) == 1
    assert {:ok, unicode} = Discovery.search(ctx.reader, ctx.credential, %{"q" => "Résumé"})
    assert length(unicode.records) == 1

    for params <- [
          %{"q" => ""},
          %{"q" => String.duplicate("a", 257)},
          %{"q" => <<0>>},
          %{"q" => <<255>>},
          %{"q" => []},
          %{"q" => "needle", "actor_id" => ctx.owner.id},
          %{"q" => "needle", "team" => "hidden"}
        ] do
      assert {:error, :invalid_discovery_query} =
               Discovery.search(ctx.reader, ctx.credential, params)
    end
  end

  test "bounded opaque pages contain no hidden counts and reset across context/filter changes",
       ctx do
    for index <- 3..57, do: ctx.add.(ctx.repository, ctx.owner, "Paged needle #{index}", index)
    assert {:ok, first} = Discovery.search(ctx.reader, ctx.credential, %{"q" => "needle"})
    assert length(first.records) == 50 and first.has_more
    assert is_binary(first.next_cursor)

    assert {:ok, second} =
             Discovery.search(ctx.reader, ctx.credential, %{
               "q" => "needle",
               "cursor" => first.next_cursor
             })

    assert length(second.records) == 6 and not second.has_more

    assert Enum.uniq_by(first.records ++ second.records, & &1["id"]) ==
             first.records ++ second.records

    for params <- [
          %{"q" => "other", "cursor" => first.next_cursor},
          %{"q" => "needle", "cursor" => first.next_cursor <> "tampered"},
          %{"q" => "needle", "cursor" => String.duplicate("x", 2049)}
        ] do
      assert {:error, :discovery_reset_required} =
               Discovery.search(ctx.reader, ctx.credential, params)
    end

    {_, replacement} = Accounts.issue(ctx.reader, "session")

    assert {:error, :discovery_reset_required} =
             Discovery.search(ctx.reader, replacement, %{
               "q" => "needle",
               "cursor" => first.next_cursor
             })

    member = Repo.get_by!(Membership, user_id: ctx.reader.id, team: "visible")
    Repo.delete!(member)

    assert {:error, :discovery_reset_required} =
             Discovery.search(ctx.reader, ctx.credential, %{
               "q" => "needle",
               "cursor" => first.next_cursor
             })

    assert {:ok, empty} = Discovery.search(ctx.reader, ctx.credential, %{"q" => "needle"})
    assert empty.records == [] and empty.next_cursor == nil and not empty.has_more
  end

  test "repository-scoped session is filtered before search and page boundaries", ctx do
    Accounts.add_member(ctx.reader, "hidden", "reader")
    {_, scoped} = Accounts.issue(ctx.reader, "session", ctx.repository.id)
    assert {:ok, result} = Discovery.search(ctx.reader, scoped, %{"q" => "needle"})
    assert length(result.records) == 1
    assert {:ok, activity} = Discovery.activity(ctx.reader, scoped, %{})
    assert Enum.all?(activity.records, &(&1["team"] == "visible"))

    assert {:error, :repository_not_found} =
             Discovery.activity(ctx.reader, scoped, %{"team" => "hidden", "name" => "project"})
  end

  test "a stable older review link retains its selected event without crossing pull scope", ctx do
    alias Gitgood.{Pulls, ReviewEvent}
    now = Accounts.now()

    rows =
      for index <- 1..501 do
        %{
          public_id: Ecto.UUID.generate(),
          pull_request_id: ctx.allowed.id,
          actor_id: ctx.owner.id,
          kind: "comment",
          source_sha: String.duplicate("1", 40),
          target_sha: String.duplicate("2", 40),
          body: "Retained review #{index}",
          request_key: "retained-#{index}",
          request_digest: Accounts.digest(to_string(index)),
          inserted_at: now,
          updated_at: now
        }
      end

    Repo.insert_all(ReviewEvent, rows)
    oldest = List.first(rows).public_id
    assert length(Pulls.events(ctx.allowed)) == 500
    refute Enum.any?(Pulls.events(ctx.allowed), &(&1.public_id == oldest))
    selected = Pulls.events(ctx.allowed, oldest)
    assert length(selected) == 501
    assert Enum.count(selected, &(&1.public_id == oldest)) == 1
    other = ctx.add.(ctx.repository, ctx.owner, "Other conversation", 999)
    assert Pulls.events(other, oldest) == []
  end
end
