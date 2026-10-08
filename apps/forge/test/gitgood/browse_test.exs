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
end
