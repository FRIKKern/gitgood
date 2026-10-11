# Protected observation of the original Postgres backend

The existing [kernel observer](native-kernel-backend.md) captures one original
held SQL session's process identity. `native_backend_observation.py` exposes
that observation through a fixed protected entry for an ordinary native or
maintenance worker. `NativeOwnershipPublication.observe_backend/2` sends a
closed request and validates the bounded reply against its original admission
and SQL snapshot. Neither interface grants lifecycle or replacement authority.

The request contains protocol, fixed purpose, installation, worker, actual
calling BEAM PID and SQL snapshot. It cannot supply a command, executable,
database URL, server account or namespace. Canonical JSON, duplicate rejection,
strict integer types and an 8 KiB bound precede observation. Errors return only
the constant refusal, without private paths, credentials or diagnostic output.

The Python entry accepts only `/opt/gitgood/native/v2` under Root-controlled
file and parent custody. Isolated Python loads the independently checked fixed
module directory. The generation admission seal supplies the database, psql
path, unit identity and resource limits. Actual worker ancestry supplies the
owner identity and service boot; merely opening the guard does not capture or
admit a published generation.

The separately protected scope file is fixed by installation and observed boot:
`/etc/gitgood/installations/<installation>/backend-kernel-<boot>.json`.
Its closed canonical format is protocol 2, kind
`native_backend_kernel_scope_seal`, installation and `server_scope`. The latter
has only boot ID, PID namespace, time namespace and Postgres Unix UID. The
allocator must independently establish these observations from the actual
server before creating this file. There is no scope enrollment or seal writer
in this change; a caller-supplied scope cannot authorize its own observation.

The bridge reads the installation configuration and Root-protected psql
identity, then invokes the existing kernel capture with the actual worker
owner. That capture brackets live procfs observation with original SQL session,
socket-owner and held-lease checks. The bridge rechecks configuration, psql,
both protected seals and worker identity before returning the kernel record.
Its reply binds the complete original owner and canonical service-scope digest.
The Elixir decoder requires the original admitted database and exact SQL
snapshot, same service boot, closed kernel grammar and bounded unsigned births.
SQL birth and kernel birth keep their distinct meanings.

Every success explicitly reports false for ownership retention, writer
exclusion, installation readiness and replacement admission. The observation
does not write a marker, acquire an advisory lock, signal a process or admit
a generation. Its historical result cannot replace fresh independent checks
before a consequential operation.

Eight Python bridge tests use explicit service/SQL stand-ins to verify ordering,
protected scope custody changes, changed original owners, configuration and
executable replacement, malformed requests and changed kernel replies. Eleven
actual ordinary Linux Elixir checks cover this decoder and existing publication
behavior. These are component checks; they do not exercise the installed entry
or establish a complete native application journey.

The full ordinary Linux operator run executes 517 tests: 488 pass and 29 skip
for platform or privilege requirements. All 121 operator source digests match
before and after execution; actual database fixtures run with the configured
native locale profile. The generated README/changelog and 35 planning checks
pass. Required CI remains a separate integration gate. An earlier run omitted
the database-profile flag and skipped 54 tests; its result is retained alongside
the corrected run, rather than substituting those skips for database coverage.

The [protocol-3 ownership integration](native-kernel-ownership.md) now requires
immutable retention of this identity, independent protected publisher checks
and original monitor/lease/claim handoff. Independently sealed product allocator
enrollment, installed handoff, complete application abort on loss and controller
reconciliation before replacement remain required. The native startup gate stays
closed. Existing records are not rewritten or silently upgraded by observation.
