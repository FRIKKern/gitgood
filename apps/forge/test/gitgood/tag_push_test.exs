defmodule Gitgood.TagPushTest do
  use Gitgood.DataCase, async: false
  alias Gitgood.{Accounts, Git, Pushes, Repositories}
  @zero String.duplicate("0", 40)
  setup do
    {:ok, owner} = Accounts.create_user("tag-owner", "synthetic-password")
    Accounts.add_member(owner, "tags", "owner")
    {:ok, repository} = Repositories.create(owner, "tags", "project", "tag-project")
    {_, credential} = Accounts.issue(owner, "git", repository.id)
    on_exit(fn -> File.rm_rf!(Git.path(repository)) end)
    %{owner: owner, repository: repository, credential: credential}
  end

  test "new valid tags enter durable push responsibility; replacement, deletion and duplicate refs are denied",
       ctx do
    new = String.duplicate("1", 40)

    for ref <- ["refs/tags/v1", "refs/tags/releases/v2"] do
      {operation, capability} = Pushes.begin(ctx.repository, ctx.owner, ctx.credential)
      assert {:ok, result} = Pushes.validate(operation.id, capability, "#{@zero} #{new} #{ref}\n")
      assert result.state == "validated"
      assert result.updates == [%{"old" => @zero, "new" => new, "ref" => ref}]
    end

    for body <- [
          "#{new} #{@zero} refs/tags/v1\n",
          "#{new} #{String.duplicate("2", 40)} refs/tags/v1\n",
          "#{@zero} #{new} refs/tags/../invalid\n",
          "#{@zero} #{new} refs/gitgood/releases/hidden\n",
          "#{@zero} #{new} refs/tags/v1\n#{@zero} #{new} refs/tags/v1\n"
        ] do
      {operation, capability} = Pushes.begin(ctx.repository, ctx.owner, ctx.credential)
      assert {:error, :denied} = Pushes.validate(operation.id, capability, body)
    end
  end

  test "reader and revoked credentials cannot validate tag creation", ctx do
    {:ok, reader} = Accounts.create_user("tag-reader", "synthetic-password")
    Accounts.add_member(reader, "tags", "reader")
    {_, credential} = Accounts.issue(reader, "git", ctx.repository.id)

    for credential <- [credential, ctx.credential] do
      if credential.user_id == ctx.owner.id, do: Accounts.revoke(credential)
      actor = if credential.user_id == reader.id, do: reader, else: ctx.owner
      {operation, capability} = Pushes.begin(ctx.repository, actor, credential)

      assert {:error, :denied} =
               Pushes.validate(
                 operation.id,
                 capability,
                 "#{@zero} #{String.duplicate("1", 40)} refs/tags/v1\n"
               )
    end
  end
end
