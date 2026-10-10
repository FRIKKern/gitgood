defmodule Gitgood.NativeOwnershipSupervisor do
  @moduledoc "Root supervision for an already admitted native owner; it never restarts children."

  # Native admission and immutable/live ownership publication must finish before
  # this tree starts application workers. The packaged application must run as
  # :permanent: root failure must terminate its whole BEAM, not merely this tree.
  def start_link(children) when is_list(children) and length(children) in 1..64 do
    children = Enum.map(children, &Supervisor.child_spec(&1, restart: :permanent))

    Supervisor.start_link(children,
      name: Gitgood.Supervisor,
      strategy: :one_for_all,
      max_restarts: 0
    )
  end
end
