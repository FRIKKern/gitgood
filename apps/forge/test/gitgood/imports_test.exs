defmodule Gitgood.ImportsTest do
  use GitgoodWeb.RealConnCase, async: false
  alias Gitgood.{Accounts, Git, GitOperation, ImportBundle, Imports, Repo, Repositories}
  import Ecto.Query

  setup do
    {:ok, owner} = Accounts.create_user("importer", "synthetic-password")
    {:ok, writer} = Accounts.create_user("import-writer", "synthetic-password")
    {:ok, reader} = Accounts.create_user("import-reader", "synthetic-password")

    for {user, role} <- [{owner, "owner"}, {writer, "writer"}, {reader, "reader"}],
        do: Accounts.add_member(user, "imports", role)

    {token, credential} = Accounts.issue(owner, "session")
    {:ok, repository} = Repositories.create(owner, "imports", "target", "import-target-create")
    source = %Gitgood.Repository{storage_key: Ecto.UUID.generate()}
    :ok = Git.init(source)
    initial = commit(source, "original\n", nil)
    main = commit(source, "current\n", initial)
    feature = commit(source, "feature\n", main)
    git(source, ["update-ref", "refs/heads/main", main])
    git(source, ["update-ref", "refs/heads/feature", feature])

    git(source, [
      "-c",
      "user.name=Fixture",
      "-c",
      "user.email=fixture@example.invalid",
      "tag",
      "-a",
      "v1",
      "-m",
      "Release fixture",
      main
    ])

    bundle = Path.join(Git.path(source), "fixture.bundle")
    git(source, ["bundle", "create", bundle, "--branches", "--tags"])

    on_exit(fn ->
      operations = Repo.all(from o in GitOperation, where: o.repository_id == ^repository.id)
      Enum.each(operations, &File.rm(Imports.source_path(&1)))
      Repo.delete_all(from o in GitOperation, where: o.repository_id == ^repository.id)
      Repo.delete!(Repo.get!(Gitgood.Repository, repository.id))
      ids = [owner.id, writer.id, reader.id]
      Repo.delete_all(from c in Gitgood.Credential, where: c.user_id in ^ids)
      Repo.delete_all(from m in Gitgood.Membership, where: m.user_id in ^ids)
      Repo.delete_all(from u in Gitgood.User, where: u.id in ^ids)
      File.rm_rf!(Git.path(source))
      File.rm_rf!(Git.path(repository))
    end)

    %{
      owner: owner,
      writer: writer,
      reader: reader,
      credential: credential,
      token: token,
      repository: repository,
      source: source,
      bundle: bundle,
      initial: initial,
      main: main,
      feature: feature
    }
  end

  defp git(repository, args, input \\ "") do
    assert {output, 0} = Git.run(["--git-dir", Git.path(repository) | args], input: input)
    String.trim(output)
  end

  defp commit(repository, text, parent) do
    blob = git(repository, ["hash-object", "-w", "--stdin"], text)
    tree = git(repository, ["mktree"], "100644 blob #{blob}\tREADME.md\n")

    args = [
      "-c",
      "user.name=Fixture",
      "-c",
      "user.email=fixture@example.invalid",
      "commit-tree",
      tree
    ]

    git(repository, if(parent, do: args ++ ["-p", parent], else: args), "Fixture commit\n")
  end

  defp params(path) do
    {:ok, sha, bytes} = Imports.fingerprint(path)
    %{"source_name" => "fixture.bundle", "source_sha256" => sha, "source_bytes" => bytes}
  end

  defp begin(ctx, key \\ "import-request") do
    {:ok, operation} =
      Imports.begin(ctx.repository, ctx.owner, ctx.credential, params(ctx.bundle), key)

    operation
  end

  defp upload(ctx, operation, bundle \\ nil) do
    temporary = Imports.temporary_path()
    File.cp!(bundle || ctx.bundle, temporary)

    Imports.accept_source(ctx.repository, ctx.owner, ctx.credential, operation.id, temporary,
      enqueue: false
    )
  end

  test "native full bundle preserves branch/tag objects and history; all replay uses one identity",
       ctx do
    operation = begin(ctx)
    assert operation.metadata["phase"] == "waiting_source"
    assert operation.metadata["warnings"] == Imports.warnings()

    assert {:ok, %{id: id}} =
             Imports.begin(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               params(ctx.bundle),
               "import-request"
             )

    assert id == operation.id
    assert {:ok, _} = upload(ctx, operation)
    assert :ok = ImportBundle.empty?(ctx.repository)
    assert {:ok, applied} = Imports.execute(operation.id)
    assert applied.state == "applied"
    assert applied.actor_id == ctx.owner.id
    assert applied.credential_id == ctx.credential.id
    assert length(applied.updates) == 3
    assert applied.metadata["source_sha256"] == params(ctx.bundle)["source_sha256"]

    assert git(ctx.repository, [
             "for-each-ref",
             "--format=%(refname) %(objectname)",
             "refs/heads",
             "refs/tags"
           ]) ==
             git(ctx.source, [
               "for-each-ref",
               "--format=%(refname) %(objectname)",
               "refs/heads",
               "refs/tags"
             ])

    objects = fn repository ->
      git(repository, ["rev-list", "--all", "--objects"])
      |> String.split("\n", trim: true)
      |> Enum.map(&(String.split(&1, " ") |> hd()))
      |> Enum.uniq()
      |> Enum.sort()
    end

    assert objects.(ctx.repository) == objects.(ctx.source)

    for branch <- ["main", "feature"] do
      assert git(ctx.repository, ["rev-list", "--topo-order", branch]) ==
               git(ctx.source, ["rev-list", "--topo-order", branch])
    end

    assert git(ctx.repository, ["show", ctx.initial <> ":README.md"]) == "original"
    assert git(ctx.repository, ["fsck", "--full", "--strict"]) == ""
    assert Git.ref(ctx.repository, ImportBundle.marker(applied)) == {:ok, ctx.main}
    assert git(ctx.repository, ["config", "transfer.hideRefs"]) == "refs/gitgood/"
    refute File.exists?(Imports.source_path(applied))

    assert {:ok, %{id: ^id, state: "applied"}} =
             Imports.begin(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               params(ctx.bundle),
               "import-request"
             )

    assert Repo.aggregate(
             from(o in GitOperation,
               where: o.kind == "import" and o.repository_id == ^ctx.repository.id
             ),
             :count
           ) == 1

    assert {:error, :repository_not_empty} =
             Imports.begin(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               params(ctx.bundle),
               "another-import"
             )

    # Marker proves the atomic event even after later authorized history advances.
    git(ctx.repository, ["update-ref", "refs/heads/feature", ctx.main, ctx.feature])
    assert Imports.reconcile_operation(ctx.repository, applied).state == "applied"
  end

  test "unsupported versions, prerequisites, internal refs, duplicate refs and missing main are rejected",
       ctx do
    sha = ctx.main

    bad = [
      "# v3 git bundle\n@object-format=sha256\n#{sha} refs/heads/main\n\n",
      "# v2 git bundle\n-#{sha} prerequisite\n#{sha} refs/heads/main\n\n",
      "# v2 git bundle\n#{sha} refs/gitgood/imports/forged\n#{sha} refs/heads/main\n\n",
      "# v2 git bundle\n#{sha} refs/heads/main\n#{sha} refs/heads/main\n\n",
      "# v2 git bundle\n#{sha} refs/heads/feature\n\n",
      "# v2 git bundle\n#{sha} refs/tags/../../escape\n#{sha} refs/heads/main\n\n",
      "# v2 git bundle\n" <> String.duplicate("x", 100_000) <> "\n\n"
    ]

    for content <- bad do
      path = Imports.temporary_path()
      File.write!(path, content)
      assert {:error, _} = ImportBundle.refs(path)
      File.rm!(path)
    end

    assert :ok = ImportBundle.empty?(ctx.repository)
  end

  test "partial or wrong-digest intake retains the intent; busy execution retains complete source and retry applies",
       ctx do
    operation = begin(ctx)
    partial = Imports.temporary_path()
    File.write!(partial, "partial")

    assert {:error, :source_size_or_digest_mismatch} =
             Imports.accept_source(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               operation.id,
               partial,
               enqueue: false
             )

    refute File.exists?(partial)
    assert Repo.get!(GitOperation, operation.id).metadata["phase"] == "waiting_source"
    assert {:ok, _} = upload(ctx, operation)
    assert {:ok, _} = upload(ctx, operation)

    nested = fn recurse, remaining ->
      if remaining == 0,
        do: Imports.execute(operation.id),
        else: Gitgood.TransportSlots.with_slot(fn -> recurse.(recurse, remaining - 1) end)
    end

    assert {:error, :busy} = nested.(nested, 4)
    assert File.exists?(Imports.source_path(operation))
    assert Repo.get!(GitOperation, operation.id).state == "started"
    assert {:ok, %{state: "applied"}} = Imports.execute(operation.id)
  end

  test "corrupt pack never publishes a ref; failed identity is stable and a fresh request may recover",
       ctx do
    corrupted = Path.join(Git.path(ctx.source), "corrupt.bundle")
    bytes = File.read!(ctx.bundle)
    File.write!(corrupted, binary_part(bytes, 0, byte_size(bytes) - 40))
    ctx = %{ctx | bundle: corrupted}
    operation = begin(ctx)
    assert {:ok, _} = upload(ctx, operation)
    assert {:ok, %{state: "failed"}} = Imports.execute(operation.id)
    assert :ok = ImportBundle.empty?(ctx.repository)
    refute File.exists?(Imports.source_path(operation))

    assert {:ok, %{id: id, state: "failed"}} =
             Imports.begin(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               params(corrupted),
               "import-request"
             )

    assert id == operation.id
    original = Path.join(Git.path(ctx.source), "fixture.bundle")
    ctx = %{ctx | bundle: original}
    next = begin(ctx, "recovered-import")
    assert {:ok, _} = upload(ctx, next)
    assert {:ok, %{state: "applied"}} = Imports.execute(next.id)
  end

  test "only current creator session may intake; queued revoked responsibility fails without refs",
       ctx do
    {_, writer_credential} = Accounts.issue(ctx.writer, "session")
    {_, reader_credential} = Accounts.issue(ctx.reader, "session")

    assert {:error, :repository_creator_required} =
             Imports.begin(
               ctx.repository,
               ctx.writer,
               writer_credential,
               params(ctx.bundle),
               "writer-import"
             )

    assert {:error, :authorization_changed} =
             Imports.begin(
               ctx.repository,
               ctx.reader,
               reader_credential,
               params(ctx.bundle),
               "reader-import"
             )

    assert {:error, :authorization_changed} =
             Imports.begin(
               ctx.repository,
               ctx.owner,
               writer_credential,
               params(ctx.bundle),
               "foreign-session"
             )

    assert {:error, :bounded_bundle_source_required} =
             Imports.begin(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               Map.put(params(ctx.bundle), "source_url", "http://127.0.0.1/private"),
               "url-import"
             )

    assert {:error, :bounded_bundle_source_required} =
             Imports.begin(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               Map.put(params(ctx.bundle), "source_bytes", Imports.limit() + 1),
               "huge-import"
             )

    operation = begin(ctx)
    assert {:ok, _} = upload(ctx, operation)
    {:ok, _} = Accounts.revoke(ctx.credential)

    assert {:ok, %{state: "failed", outcome: %{"error" => "authorization_changed"}}} =
             Imports.execute(operation.id)

    assert :ok = ImportBundle.empty?(ctx.repository)
    refute File.exists?(Imports.source_path(operation))
  end

  test "malformed but checksummed objects are rejected before object installation and a valid retry works",
       ctx do
    bad_tree =
      git(
        ctx.source,
        ["hash-object", "--literally", "-t", "tree", "-w", "--stdin"],
        "invalid tree bytes"
      )

    objects =
      git(ctx.source, ["rev-list", "--objects", "--all"])
      |> String.split("\n", trim: true)
      |> Enum.map(&(String.split(&1, " ") |> hd()))

    {pack, 0} =
      Git.run(["--git-dir", Git.path(ctx.source), "pack-objects", "--stdout"],
        input: Enum.join(objects ++ [bad_tree], "\n") <> "\n"
      )

    malicious = Path.join(Git.path(ctx.source), "malformed.bundle")
    File.write!(malicious, "# v2 git bundle\n#{ctx.main} refs/heads/main\n\n" <> pack)
    bad = %{ctx | bundle: malicious}
    operation = begin(bad, "malformed-import")
    assert {:ok, _} = upload(bad, operation)
    assert {:ok, %{state: "failed"}} = Imports.execute(operation.id)
    assert :ok = ImportBundle.empty?(ctx.repository)
    assert {_, 0} = Git.run(["--git-dir", Git.path(ctx.repository), "fsck", "--full", "--strict"])

    assert {_, status} =
             Git.run(["--git-dir", Git.path(ctx.repository), "cat-file", "-e", bad_tree])

    assert status != 0
    next = begin(ctx, "valid-after-malformed")
    assert {:ok, _} = upload(ctx, next)
    assert {:ok, %{state: "applied"}} = Imports.execute(next.id)
  end

  test "full source validation cannot borrow missing advertised history from prior target objects",
       ctx do
    # A previous interrupted, valid preparation may have installed objects without refs.
    assert {:ok, _} = ImportBundle.prepare(ctx.repository, ctx.bundle)
    assert :ok = ImportBundle.empty?(ctx.repository)
    blob = git(ctx.source, ["hash-object", "-w", "--stdin"], "Unrelated complete object\n")

    {pack, 0} =
      Git.run(["--git-dir", Git.path(ctx.source), "pack-objects", "--stdout"],
        input: blob <> "\n"
      )

    incomplete = Path.join(Git.path(ctx.source), "missing-history.bundle")
    File.write!(incomplete, "# v2 git bundle\n#{ctx.main} refs/heads/main\n\n" <> pack)
    bad = %{ctx | bundle: incomplete}
    operation = begin(bad, "missing-history-import")
    assert {:ok, _} = upload(bad, operation)
    assert {:ok, %{state: "failed"}} = Imports.execute(operation.id)
    assert :ok = ImportBundle.empty?(ctx.repository)
    assert {_, status} = Git.run(["--git-dir", Git.path(ctx.repository), "cat-file", "-e", blob])
    assert status != 0
    next = begin(ctx, "valid-after-missing-history")
    assert {:ok, _} = upload(ctx, next)
    assert {:ok, %{state: "applied"}} = Imports.execute(next.id)
  end

  test "pending request conflicts, explicit cancellation and competing ref creation preserve responsibilities",
       ctx do
    operation = begin(ctx)

    assert {:error, :idempotency_conflict} =
             Imports.begin(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               Map.put(params(ctx.bundle), "source_name", "changed.bundle"),
               "import-request"
             )

    assert {:error, :import_already_pending} =
             Imports.begin(
               ctx.repository,
               ctx.owner,
               ctx.credential,
               params(ctx.bundle),
               "parallel-import"
             )

    assert {:ok, %{state: "failed", outcome: %{"error" => "cancelled"}}} =
             Imports.cancel(ctx.repository, ctx.owner, ctx.credential, operation.id)

    second = begin(ctx, "second-import")
    assert {:ok, _} = upload(ctx, second)

    assert {:error, :only_waiting_import_can_be_cancelled} =
             Imports.cancel(ctx.repository, ctx.owner, ctx.credential, second.id)

    independent = commit(ctx.repository, "independent\n", nil)
    git(ctx.repository, ["update-ref", "refs/heads/main", independent])

    assert {:ok, %{state: "failed", outcome: %{"error" => "repository_not_empty"}}} =
             Imports.execute(second.id)

    assert Git.ref(ctx.repository, "refs/heads/main") == {:ok, independent}
    assert Git.ref(ctx.repository, "refs/heads/feature") == {:error, :missing_ref}
  end

  test "intake HTTP enforces CSRF, canonical binary type and scoped operation lookup", ctx do
    uri = "/api/repos/imports/target/imports"

    conn =
      build_conn()
      |> put_req_header("cookie", "gitgood_session=" <> ctx.token)
      |> post(uri, params(ctx.bundle))

    assert json_response(conn, 403)["error"] == "csrf_required"

    conn =
      build_conn()
      |> put_req_header("authorization", "Bearer " <> ctx.token)
      |> put_req_header("idempotency-key", "http-import")
      |> post(uri, params(ctx.bundle))

    operation = json_response(conn, 202)["operation"]

    conn =
      build_conn()
      |> put_req_header("authorization", "Bearer " <> ctx.token)
      |> put(uri <> "/" <> operation["id"] <> "/source", %{})

    assert json_response(conn, 415)["error"] == "binary_bundle_body_required"

    conn =
      build_conn()
      |> put_req_header("authorization", "Bearer " <> ctx.token)
      |> get("/api/repos/imports/target/operations/" <> operation["id"])

    assert json_response(conn, 200)["operation"]["metadata"]["phase"] == "waiting_source"

    conn =
      build_conn()
      |> put_req_header("authorization", "Bearer " <> ctx.token)
      |> delete(uri <> "/" <> operation["id"])

    assert json_response(conn, 202)["operation"]["state"] == "failed"
  end

  test "staging cleanup removes expired owned partials and preserves current or unknown source files",
       _ctx do
    expired = Imports.temporary_path()
    current = Imports.temporary_path()

    unknown =
      Path.join(Imports.directory(), "unrecognized-" <> Ecto.UUID.generate() <> ".partial")

    for path <- [expired, current, unknown], do: File.write!(path, "synthetic partial")
    on_exit(fn -> Enum.each([expired, current, unknown], &File.rm/1) end)
    :ok = File.touch(expired, System.os_time(:second) - 3601)
    Imports.cleanup_staging()
    refute File.exists?(expired)
    assert File.exists?(current)
    assert File.exists?(unknown)
  end
end
