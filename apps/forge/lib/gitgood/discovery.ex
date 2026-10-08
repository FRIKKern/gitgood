defmodule Gitgood.Discovery do
  @moduledoc "Permission-filtered native search and full recent-activity snapshots."
  alias Gitgood.{Access, Repo}

  @visible """
  WITH visible AS (
    SELECT r.* FROM repositories r JOIN memberships m ON m.team=r.team
    WHERE m.user_id=$1 AND ($2::bigint IS NULL OR r.id=$2)
  )
  """
  @search """
  , records AS (
    SELECT 'repository'::text AS kind, r.team||'/'||r.name AS uid, r.team, r.name,
      r.team||' / '||r.name AS title, ''::text AS body, r.status AS state,
      u.username AS actor, r.inserted_at AS occurred_at,
      '/repos/'||r.team||'/'||r.name AS url
      FROM visible r JOIN users u ON u.id=r.owner_id
    UNION ALL
    SELECT 'pull', p.public_id::text, r.team, r.name, p.title, p.body, p.state,
      u.username, p.inserted_at, '/repos/'||r.team||'/'||r.name||'/pulls/'||p.public_id::text
      FROM pull_requests p JOIN visible r ON r.id=p.repository_id JOIN users u ON u.id=p.author_id
    UNION ALL
    SELECT 'release', p.id::text, r.team, r.name, p.title, p.notes, p.state,
      u.username, p.inserted_at, '/repos/'||r.team||'/'||r.name||'#release-'||p.id::text
      FROM release_records p JOIN visible r ON r.id=p.repository_id JOIN users u ON u.id=p.creator_id
  )
  """
  @activity """
  , records AS (
    SELECT 'repository'::text AS kind, r.team||'/'||r.name AS uid, r.team, r.name,
      'Repository created'::text AS title, ''::text AS body, r.status AS state,
      u.username AS actor, r.inserted_at AS occurred_at,
      '/repos/'||r.team||'/'||r.name AS url
      FROM visible r JOIN users u ON u.id=r.owner_id
    UNION ALL
    SELECT 'pull', p.public_id::text, r.team, r.name, p.title, p.body, p.state,
      u.username, p.inserted_at, '/repos/'||r.team||'/'||r.name||'/pulls/'||p.public_id::text
      FROM pull_requests p JOIN visible r ON r.id=p.repository_id JOIN users u ON u.id=p.author_id
    UNION ALL
    SELECT 'review', e.public_id::text, r.team, r.name, p.title, e.body, e.kind,
      u.username, e.inserted_at, '/repos/'||r.team||'/'||r.name||'/pulls/'||p.public_id::text||'#review-'||e.public_id::text
      FROM review_events e JOIN pull_requests p ON p.id=e.pull_request_id
      JOIN visible r ON r.id=p.repository_id JOIN users u ON u.id=e.actor_id
    UNION ALL
    SELECT 'release_event', e.public_id::text, r.team, r.name,
      coalesce(e.snapshot->>'title', p.title), coalesce(nullif(e.reason,''),e.snapshot->>'notes',''), e.kind,
      u.username, e.inserted_at, '/repos/'||r.team||'/'||r.name||'#release-'||p.id::text
      FROM release_events e JOIN release_records p ON p.id=e.release_id
      JOIN visible r ON r.id=p.repository_id JOIN users u ON u.id=e.actor_id
    UNION ALL
    SELECT 'operation', o.id::text, r.team, r.name, 'Code '||o.kind,
      ''::text, o.state, u.username, o.updated_at,
      '/repos/'||r.team||'/'||r.name||'/operations/'||o.id::text
      FROM git_operations o JOIN visible r ON r.id=o.repository_id JOIN users u ON u.id=o.actor_id
      WHERE o.kind IN ('push','merge','import')
  )
  """
  @select """
  SELECT kind,uid,team,name,title,left(body,280) AS snippet,state,actor,occurred_at,url
  FROM records WHERE (title ILIKE $3 ESCAPE '!' OR body ILIKE $3 ESCAPE '!')
    AND ($4::text IS NULL OR (team=$4 AND name=$5))
    AND ($6::timestamp IS NULL OR (occurred_at,kind,uid)<($6,$7,$8))
  ORDER BY occurred_at DESC,kind DESC,uid DESC LIMIT 51
  """

  def search(user, credential, params), do: read("search", user, credential, params)
  def activity(user, credential, params), do: read("activity", user, credential, params)

  defp read(mode, user, credential, params) do
    Access.with_session(user, credential, fn context ->
      unless is_map(params) and
               Enum.all?(Map.keys(params), &(&1 in ["q", "cursor", "team", "name"])),
             do: Repo.rollback(:invalid_discovery_query)

      query = if mode == "activity", do: "", else: params["q"]

      if mode == "activity" and Map.has_key?(params, "q"),
        do: Repo.rollback(:invalid_discovery_query)

      unless is_binary(query) and String.valid?(query) and byte_size(query) <= 256 and
               not String.contains?(query, <<0>>) and
               (mode == "activity" or String.trim(query) != ""),
             do: Repo.rollback(:invalid_discovery_query)

      query = String.trim(query)
      team = params["team"]
      name = params["name"]

      unless (is_nil(team) and is_nil(name)) or
               (is_binary(team) and is_binary(name) and
                  Regex.match?(~r/\A[a-z][a-z0-9-]{1,39}\z/, team) and
                  Regex.match?(~r/\A[a-z][a-z0-9-]{1,63}\z/, name)),
             do: Repo.rollback(:invalid_discovery_query)

      if team do
        [[count]] =
          Repo.query!(
            """
            SELECT count(*) FROM repositories r JOIN memberships m ON m.team=r.team
            WHERE m.user_id=$1 AND r.team=$2 AND r.name=$3 AND ($4::bigint IS NULL OR r.id=$4)
            """,
            [user.id, team, name, context.repository_scope]
          ).rows

        unless count == 1, do: Repo.rollback(:repository_not_found)
      end

      filter = digest([mode, query, team, name])
      {time, kind, uid} = decode(params["cursor"], context.context, filter)

      pattern =
        "%" <>
          (query
           |> String.replace("!", "!!")
           |> String.replace("%", "!%")
           |> String.replace("_", "!_")) <> "%"

      Repo.query!("SET LOCAL statement_timeout = '3s'")
      sql = @visible <> if(mode == "search", do: @search, else: @activity) <> @select

      result =
        Repo.query!(sql, [user.id, context.repository_scope, pattern, team, name, time, kind, uid])

      rows = Enum.map(result.rows, &Map.new(Enum.zip(result.columns, &1)))
      shown = Enum.take(rows, 50)

      cursor =
        if length(rows) > 50 do
          last = List.last(shown)
          encode(context.context, filter, last)
        end

      %{
        records: Enum.map(shown, &public/1),
        next_cursor: cursor,
        has_more: length(rows) > 50,
        access_context: context.context,
        snapshot: digest(shown),
        source: "native",
        recorded_at: DateTime.to_iso8601(Gitgood.Accounts.now())
      }
    end)
  end

  defp public(row) do
    row
    |> Map.drop(["uid"])
    |> Map.put("id", digest([row["kind"], row["uid"]]))
    |> Map.update!("occurred_at", &(DateTime.from_naive!(&1, "Etc/UTC") |> DateTime.to_iso8601()))
  end

  defp encode(context, filter, row) do
    Plug.Crypto.encrypt(
      secret(),
      "gitgood-discovery-v1",
      {context, filter, NaiveDateTime.to_iso8601(row["occurred_at"]),
       String.pad_trailing(row["kind"], 16), String.pad_trailing(row["uid"], 112)},
      max_age: 900
    )
  end

  defp decode(nil, _, _), do: {nil, nil, nil}

  defp decode(token, context, filter) when is_binary(token) and byte_size(token) <= 2048 do
    case Plug.Crypto.decrypt(secret(), "gitgood-discovery-v1", token, max_age: 900) do
      {:ok, {^context, ^filter, time, kind, uid}} ->
        with {:ok, time} <- NaiveDateTime.from_iso8601(time),
             true <- is_binary(kind) and byte_size(kind) == 16,
             true <- is_binary(uid) and byte_size(uid) == 112 do
          {time, String.trim_trailing(kind), String.trim_trailing(uid)}
        else
          _ -> Repo.rollback(:discovery_reset_required)
        end

      _ ->
        Repo.rollback(:discovery_reset_required)
    end
  end

  defp decode(_, _, _), do: Repo.rollback(:discovery_reset_required)
  defp secret, do: Application.fetch_env!(:gitgood, GitgoodWeb.Endpoint)[:secret_key_base]

  defp digest(value),
    do:
      :crypto.mac(:hmac, :sha256, secret(), Jason.encode!(value))
      |> Base.url_encode64(padding: false)
end
