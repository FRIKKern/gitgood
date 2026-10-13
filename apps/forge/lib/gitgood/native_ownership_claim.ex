defmodule Gitgood.NativeOwnershipClaim do
  @moduledoc "One ownership handoff using the captured local monitor and held database lease."

  alias Gitgood.InstallationGenerationMonitor, as: Monitor
  alias Gitgood.NativeDatabaseLease, as: Lease
  alias Gitgood.NativeOwnershipPublication, as: Publication
  alias Gitgood.NativeOwnershipRecord, as: Record

  @failure {:error, :native_ownership_claim_unavailable}

  # The startup owner must abort on any error, including errors after retention.
  # Nothing here retries, reconnects, cleans a marker or admits replacement.
  def claim(monitor, lease, seal, mode, handoff \\ nil) do
    with true <- local_live?(monitor) and local_live?(lease) and monitor != lease,
         true <- mode in [:runtime, :backup, :restore, :migrate],
         {:ok, context} <- Monitor.ownership_context(monitor),
         {:ok, session} <- Lease.snapshot(lease),
         {:ok, backend_kernel} <- Publication.observe_backend(context.admission, session),
         :ok <- Lease.current(lease),
         :ok <- Monitor.current(monitor),
         {:ok, record} <- build_record(context, session, backend_kernel, seal, mode, handoff),
         {:ok, receipt} <- Publication.publish(record),
         :ok <- Monitor.attach_ownership(monitor, record, receipt),
         :ok <- Lease.current(lease),
         :ok <- Monitor.current(monitor) do
      {:ok, %{record: record, receipt: receipt}}
    else
      _ -> @failure
    end
  rescue
    _ -> @failure
  catch
    :exit, _ -> @failure
  end

  defp build_record(context, session, backend_kernel, seal, mode, nil),
    do: Record.build(context, session, backend_kernel, seal, mode)

  defp build_record(context, session, backend_kernel, seal, mode, handoff),
    do: Record.build(context, session, backend_kernel, seal, mode, handoff)

  defp local_live?(pid),
    do: is_pid(pid) and node(pid) == node() and Process.alive?(pid)
end
