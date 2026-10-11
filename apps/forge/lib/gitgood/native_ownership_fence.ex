defmodule Gitgood.NativeOwnershipFence do
  @moduledoc "Watch original helpers while startup waits; loss ends the linked owner."
  use GenServer

  def start_link(monitor, lease), do: GenServer.start_link(__MODULE__, {self(), monitor, lease})
  def current(pid), do: GenServer.call(pid, :current, 1_000)

  @impl true
  def init({owner, monitor, lease}) do
    originals = [monitor, lease]

    if Enum.all?(originals, &(is_pid(&1) and node(&1) == node() and &1 != owner)) and
         monitor != lease and Enum.all?(originals, &Process.alive?/1) do
      references = Map.new(originals, &{Process.monitor(&1), &1})

      if Enum.all?(originals, &Process.alive?/1),
        do: {:ok, references},
        else: {:stop, :native_ownership_helpers_lost}
    else
      {:stop, :native_ownership_helpers_unavailable}
    end
  end

  @impl true
  def handle_call(:current, _from, references) do
    if Enum.all?(Map.values(references), &Process.alive?/1),
      do: {:reply, :ok, references},
      else:
        {:stop, :native_ownership_helpers_lost, {:error, :native_ownership_helpers_lost},
         references}
  end

  @impl true
  def handle_info({:DOWN, reference, :process, original, _reason}, references) do
    if references[reference] == original,
      do: {:stop, :native_ownership_helpers_lost, references},
      else: {:stop, :native_ownership_helpers_unavailable, references}
  end

  def handle_info(_, references), do: {:stop, :native_ownership_helpers_unavailable, references}
end
