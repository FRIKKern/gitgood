defmodule Gitgood.GitPackTest do
  use ExUnit.Case, async: false
  alias Gitgood.{CommandStream, Git}

  test "buffered and streaming pack transfer fits the existing memory limit despite repository thread settings" do
    root = Path.join(System.tmp_dir!(), "gitgood-pack-" <> Ecto.UUID.generate())
    repository = Path.join(root, "source.git")
    target = Path.join(root, "target.git")
    File.mkdir_p!(root)
    on_exit(fn -> File.rm_rf!(root) end)
    assert {:ok, _, 0} = Git.command(["init", "--bare", "--template=", repository])

    # A high thread setting reproduces the native pack-worker failure even on small CI hosts.
    assert {:ok, _, 0} = Git.command(["--git-dir", repository, "config", "pack.threads", "32"])

    blobs =
      for index <- 1..5000 do
        content = :crypto.hash(:sha256, Integer.to_string(index)) |> :binary.copy(64)
        ["blob\nmark :", Integer.to_string(index), "\ndata 2048\n", content, "\n"]
      end

    files = for index <- 1..5000, do: "M 100644 :#{index} file-#{index}.bin\n"

    input =
      IO.iodata_to_binary([
        blobs,
        "commit refs/heads/main\ncommitter Fixture <fixture@example.invalid> 1700000000 +0000\ndata 0\n\n",
        files,
        "\n"
      ])

    assert {:ok, _, 0} =
             Git.command(["--git-dir", repository, "fast-import", "--quiet"],
               input: input,
               timeout: 60_000
             )

    assert {:ok, head, 0} = Git.command(["--git-dir", repository, "rev-parse", "refs/heads/main"])
    sha = String.trim(head)
    request = packet("want " <> sha <> "\n") <> "0000" <> packet("done\n")
    args = ["upload-pack", "--stateless-rpc", repository]

    assert {:ok, <<"0008NAK\n", "PACK", _::binary>> = output, 0} =
             Git.command(args, input: request, limit: 33_554_432, timeout: 60_000)

    receiver = self()
    supervisor = start_supervised!({Task.Supervisor, name: nil})

    task =
      Task.Supervisor.async_nolink(supervisor, fn ->
        CommandStream.run(Git.command_args(args), receiver,
          limit: 33_554_432,
          timeout: 60_000
        )
      end)

    assert_receive {:gitgood_stream_started, worker}, 5000
    assert :ok = CommandStream.input(worker, request)
    assert :ok = CommandStream.eof(worker)
    assert collect(worker, byte_size(output), []) == output
    assert Task.await(task, 65_000) == {:ok, 0}

    assert {:ok, _, 0} = Git.command(["init", "--bare", "--template=", target])
    <<"0008NAK\n", pack::binary>> = output

    assert {:ok, _, 0} =
             Git.command(["--git-dir", target, "index-pack", "--stdin", "--strict"],
               input: pack,
               timeout: 60_000
             )

    assert {:ok, _, 0} = Git.command(["--git-dir", target, "cat-file", "-e", sha <> "^{commit}"])
    assert {:ok, tree, 0} = Git.command(["--git-dir", target, "ls-tree", sha], limit: 1_048_576)
    assert length(String.split(tree, "\n", trim: true)) == 5000
  end

  defp packet(body),
    do: String.pad_leading(Integer.to_string(byte_size(body) + 4, 16), 4, "0") <> body

  defp collect(_, 0, chunks), do: chunks |> Enum.reverse() |> IO.iodata_to_binary()

  defp collect(worker, remaining, chunks) do
    receive do
      {:gitgood_stream_data, ^worker, 0, data} ->
        assert byte_size(data) <= remaining
        collect(worker, remaining - byte_size(data), [data | chunks])

      {:gitgood_stream_data, ^worker, 1, _} ->
        collect(worker, remaining, chunks)
    after
      65_000 -> flunk("Bounded pack stream did not complete")
    end
  end
end
