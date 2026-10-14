defmodule Gitgood.CommandPort do
  @moduledoc false

  # The adapter can finish between a caller's port observation and cleanup.
  # Close the captured port directly; an already closed port is quiescent.
  def close(port) when is_port(port) do
    Port.close(port)
    :ok
  rescue
    ArgumentError -> :ok
  end
end
