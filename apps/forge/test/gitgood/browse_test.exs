defmodule Gitgood.BrowseTest do
  use GitgoodWeb.ConnCase, async: false
  alias Gitgood.{Accounts, Browse, Git, Repositories}

  setup do
    {:ok, user} = Accounts.create_user("browser", "synthetic-password")
    {:ok, _} = Accounts.add_member(user, "browse", "owner")
    {:ok, repository} = Repositories.create(user, "browse", "fixture", "browse-create")
    on_exit(fn -> File.rm_rf!(Git.path(repository)) end)
    %{repository: repository, user: user}
  end

  defp command(repository, args, input \\ "") do
    assert {value, 0} = Git.run(["--git-dir", Git.path(repository) | args], input: input)
    String.trim(value)
  end

  defp fixture(repository) do
    text = command(repository, ["hash-object", "-w", "--stdin"], "<script>untrusted()</script>\n")
    binary = command(repository, ["hash-object", "-w", "--stdin"], <<0, 255, 1>>)
    large = command(repository, ["hash-object", "-w", "--stdin"], String.duplicate("x", 262_145))

    tree =
      command(
        repository,
        ["mktree", "-z"],
        "100644 blob #{text}\tspace & $(demo).txt\0" <>
          "100644 blob #{binary}\tbinary.dat\0" <>
          "100644 blob #{large}\tlarge.txt\0"
      )

    commit =
      command(
        repository,
        [
          "-c",
          "user.name=Fixture",
          "-c",
          "user.email=fixture@example.invalid",
          "commit-tree",
          tree
        ],
        "Fixture commit\n"
      )

    command(repository, ["update-ref", "refs/heads/main", commit])
    commit
  end

  test "tree, literal filename, binary, large preview, history and bounded diff", ctx do
    sha = fixture(ctx.repository)
    assert {:ok, [%{name: "main", sha: ^sha}]} = Browse.branches(ctx.repository)

    assert {:ok,
            %{kind: "tree", history: [%{sha: ^sha, subject: "Fixture commit"}], entries: entries}} =
             Browse.snapshot(ctx.repository, sha, "")

    assert length(entries) == 3

    assert {:ok, %{kind: "text", content: "<script>untrusted()</script>\n"}} =
             Browse.snapshot(ctx.repository, sha, "space & $(demo).txt")

    assert {:ok, %{kind: "binary", content: nil}} =
             Browse.snapshot(ctx.repository, sha, "binary.dat")

    assert {:ok, %{kind: "large_file", size: 262_145}} =
             Browse.snapshot(ctx.repository, sha, "large.txt")

    assert {:error, :diff_too_large} = Browse.diff(ctx.repository, sha, nil)
    assert {:error, :invalid_path} = Browse.snapshot(ctx.repository, sha, "../escape")
    assert {:error, :invalid_commit} = Browse.snapshot(ctx.repository, "--all", "")
  end

  test "deleted references and unreachable objects never disclose content", ctx do
    sha = fixture(ctx.repository)
    {token, _} = Accounts.issue(ctx.user, "session")
    conn = build_conn() |> put_req_header("authorization", "Bearer " <> token)
    assert get(conn, "/api/repos/browse/fixture/snapshot?sha=" <> sha) |> json_response(200)
    {:ok, outsider} = Accounts.create_user("outsider", "synthetic-password")
    {other, _} = Accounts.issue(outsider, "session")

    assert build_conn()
           |> put_req_header("authorization", "Bearer " <> other)
           |> get("/api/repos/browse/fixture/snapshot?sha=" <> sha)
           |> json_response(404)

    command(ctx.repository, ["update-ref", "-d", "refs/heads/main", sha])
    assert {:error, :commit_not_available} = Browse.snapshot(ctx.repository, sha, "")
    assert get(conn, "/api/repos/browse/fixture/snapshot?sha=" <> sha) |> json_response(422)
  end

  test "temporary command saturation is retryable, rather than a missing commit", ctx do
    sha = fixture(ctx.repository)
    command(ctx.repository, ["update-ref", "refs/heads/work", sha])
    {token, credential} = Accounts.issue(ctx.user, "session")

    {:ok, pull} =
      Gitgood.Pulls.create(
        ctx.repository,
        ctx.user,
        credential,
        %{"source" => "work", "title" => "Busy review"},
        "busy-review-create"
      )

    pull_path = "pulls/" <> Gitgood.Pulls.public(pull).id
    {:ok, listener} = :gen_tcp.listen(0, [:binary, active: false, ip: {127, 0, 0, 1}])
    on_exit(fn -> :gen_tcp.close(listener) end)
    {:ok, {_, port}} = :inet.sockname(listener)
    tasks = start_supervised!({Task.Supervisor, name: nil})
    python = Application.fetch_env!(:gitgood, :python_executable) |> System.find_executable()

    code =
      "import socket; s=socket.create_connection(('127.0.0.1',#{port})); s.sendall(b'ready'); s.recv(1)"

    workers =
      for _ <- 1..4,
          do:
            Task.Supervisor.async_nolink(tasks, fn ->
              Gitgood.Command.run([python, "-c", code])
            end)

    sockets =
      for _ <- 1..4 do
        {:ok, socket} = :gen_tcp.accept(listener, 5000)
        assert {:ok, "ready"} = :gen_tcp.recv(socket, 5, 5000)
        socket
      end

    assert {:error, :git_unavailable} = Browse.reachable(ctx.repository, sha)

    for path <- [
          "branches",
          "snapshot?sha=" <> sha,
          "diff?sha=" <> sha,
          pull_path,
          pull_path <> "/diff"
        ] do
      expected =
        if String.starts_with?(path, pull_path), do: "ref_unavailable", else: "git_unavailable"

      assert %{"error" => ^expected} =
               build_conn()
               |> put_req_header("authorization", "Bearer " <> token)
               |> get("/api/repos/browse/fixture/" <> path)
               |> json_response(503)
    end

    Enum.each(sockets, &:gen_tcp.close/1)
    for worker <- workers, do: assert(Task.await(worker, 5000) == {:ok, "", 0})
  end

  defp await_slots(expected, deadline) do
    actual = GenServer.call(Gitgood.BrowseSlots, :counts)

    if actual != expected do
      assert System.monotonic_time(:millisecond) < deadline, inspect(actual)

      receive do
      after
        1 -> await_slots(expected, deadline)
      end
    end
  end

  test "review diffs bind exact current branches and refuse deleted or invalid references", ctx do
    commit = fn content, parent ->
      blob = command(ctx.repository, ["hash-object", "-w", "--stdin"], content)
      tree = command(ctx.repository, ["mktree"], "100644 blob #{blob}\tREADME.md\n")

      args = [
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit-tree",
        tree
      ]

      command(
        ctx.repository,
        args ++ if(parent, do: ["-p", parent], else: []),
        "Review fixture\n"
      )
    end

    main = commit.("original\n", nil)
    source = commit.("first change\n", main)
    command(ctx.repository, ["update-ref", "refs/heads/main", main])
    command(ctx.repository, ["update-ref", "refs/heads/work", source])
    {token, credential} = Accounts.issue(ctx.user, "session")

    {:ok, pull} =
      Gitgood.Pulls.create(
        ctx.repository,
        ctx.user,
        credential,
        %{"source" => "work", "title" => "Bound revision"},
        "bound-revision-create"
      )

    path = "/api/repos/browse/fixture/pulls/" <> Gitgood.Pulls.public(pull).id

    get_as_owner = fn suffix ->
      build_conn() |> put_req_header("authorization", "Bearer " <> token) |> get(path <> suffix)
    end

    assert %{"source_sha" => ^source, "target_sha" => ^main} =
             get_as_owner.("") |> json_response(200)

    assert %{"sha" => ^source, "base" => ^main, "text" => text} =
             get_as_owner.("/diff") |> json_response(200)

    assert text =~ "+first change"

    advanced = commit.("later change\n", source)
    command(ctx.repository, ["update-ref", "refs/heads/work", advanced, source])

    assert %{"sha" => ^advanced, "base" => ^main, "text" => later} =
             get_as_owner.("/diff") |> json_response(200)

    assert later =~ "+later change" and not (later =~ "+first change")

    assert {:error, :ref_unavailable} =
             Git.branch_pair(ctx.repository, "--all", "refs/heads/main")

    assert {:error, :ref_unavailable} =
             Browse.current_branch_diff(ctx.repository, "refs/tags/private", "refs/heads/main")

    command(ctx.repository, ["update-ref", "-d", "refs/heads/work", advanced])
    command(ctx.repository, ["update-ref", "refs/heads/work/deep", advanced])

    assert {:error, :missing_ref} =
             Git.branch_pair(ctx.repository, "refs/heads/work", "refs/heads/main")

    for suffix <- ["", "/diff"],
        do:
          assert(
            get_as_owner.(suffix) |> json_response(409) == %{"error" => "branches_unavailable"}
          )
  end

  test "eight authorized pull reads queue while outsiders and excess callers refuse", ctx do
    sha = fixture(ctx.repository)
    command(ctx.repository, ["update-ref", "refs/heads/work", sha])
    {token, credential} = Accounts.issue(ctx.user, "session")

    {:ok, pull} =
      Gitgood.Pulls.create(
        ctx.repository,
        ctx.user,
        credential,
        %{"source" => "work", "title" => "Queued review"},
        "queued-pull-create"
      )

    public = Gitgood.Pulls.public(pull)
    path = "/api/repos/browse/fixture/pulls/" <> public.id

    readers =
      for index <- 1..8 do
        {:ok, reader} = Accounts.create_user("queued-reader-#{index}", "synthetic-password")
        {:ok, _} = Accounts.add_member(reader, "browse", "reader")
        {reader_token, _} = Accounts.issue(reader, "session")
        reader_token
      end

    {:ok, outsider} = Accounts.create_user("queued-outsider", "synthetic-password")
    {outside_token, _} = Accounts.issue(outsider, "session")
    tasks = start_supervised!({Task.Supervisor, name: nil})
    owner = self()

    holders =
      for _ <- 1..4 do
        Task.Supervisor.async_nolink(tasks, fn ->
          Gitgood.BrowseSlots.with_slot(fn ->
            send(owner, {:holding_browse, self()})

            receive do
              :release_browse -> :released
            end
          end)
        end)
      end

    holder_pids =
      for _ <- 1..4 do
        assert_receive {:holding_browse, pid}
        pid
      end

    requests =
      readers
      |> Enum.with_index()
      |> Enum.map(fn {reader_token, index} ->
        Task.Supervisor.async_nolink(tasks, fn ->
          suffix = if rem(index, 2) == 0, do: "", else: "/diff"

          result =
            build_conn()
            |> put_req_header("authorization", "Bearer " <> reader_token)
            |> get(path <> suffix)
            |> json_response(200)

          if suffix == "" do
            assert result["source_sha"] == sha and result["target_sha"] == sha
          else
            assert result["sha"] == sha and result["base"] == sha and result["text"] == ""
          end
        end)
      end)

    await_slots(%{active: 4, waiting: 8}, System.monotonic_time(:millisecond) + 3000)

    assert build_conn()
           |> put_req_header("authorization", "Bearer " <> outside_token)
           |> get(path)
           |> json_response(404) == %{"error" => "repository_not_found"}

    assert build_conn()
           |> put_req_header("authorization", "Bearer " <> token)
           |> get(path)
           |> json_response(503) == %{"error" => "browse_busy_retry"}

    Enum.each(holder_pids, &send(&1, :release_browse))
    for holder <- holders, do: assert(Task.await(holder, 10000) == :released)
    for request <- requests, do: Task.await(request, 10000)
    await_slots(%{active: 0, waiting: 0}, System.monotonic_time(:millisecond) + 1000)
  end
end
