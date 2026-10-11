# Native ownership before application workers

Implement the missing startup boundary under decision 0018. The first child of
the permanent native root must start its original protected generation monitor,
obtain the admitted database identity, start its non-retrying lease, and execute
the protocol-3 claim once before application workers start. No caller-supplied
seal map establishes Root authority; the protected bridge and publisher still
independently observe their fixed seals, service, persistent identity and original
SQL/kernel ownership. Keep the application profile gate closed until installed
startup, complete BEAM abort and functional activation are verified.

`NativeOwnershipStartup` receives only a canonical installation storage root and
a fixed mode. `NativeOwnershipSupervisor.start_native_link/3` places it before
all application workers. Neither authority maps nor connection credentials enter
the supervisor child specification. The startup child requires the actual native
profile before starting a helper. After the original monitor admits the generation,
it reads the fixed Root protocol-3 seal and private installation configuration
through `NativeOwnershipInputs`, starts the original lease, then claims once.
It keeps original PIDs and the returned claim, never connection credentials. It
starts no replacement and retries no claim. A failed initialization ends the
linked helpers while preserving uncertain retained effects. The permanent root
must still end the whole BEAM on child failure.

The unsupported-startup regression runs the actual native root factory in a
separate BEAM because the normal backend test application already owns the
`Gitgood.Supervisor` name. The fixture bounds boot, calls and shutdown, limits
the child to two schedulers, checks the original startup-child refusal and keeps
the parent supervisor alive. It changes no production names or admission gates.

The input reader checks file ownership, modes, link counts, bounded raw descriptor
reads, and unchanged descriptor/path/parent metadata across the read. It rejects
duplicate JSON keys and constrains the database URL to the admitted local database,
role and port. Its bounded configuration projection does not replace complete
configuration admission. `File.Stat` timestamps have second precision; this reader
does not establish persistent live file custody. The protected monitor and
publisher retain responsibility for complete configuration validation and current
protected identity before effects. Restoring valid inputs permits a new read;
it cannot revive a failed generation or establish Root authority.

The linked `NativeOwnershipFence` independently watches both original helper
PIDs before the synchronous claim begins. A normal helper exit must stop its
owner even while the owner waits for publication. The fence converts any observed
original exit into failure. It resolves no process name, captures no replacement,
and grants no admission or writer authority. Both original helpers remain linked
to the startup owner for immediate abnormal-exit propagation. Normal shutdown
stops the fence before closing the original lease and monitor; records remain.

Current focused verification passes 55 Elixir tests, including the original
ownership tests, normal and abnormal helper loss during blocked owner startup,
invalid startup refusal before effects, closed constructor options and bounded
input decoding. Nine additional actual fixed-path input checks run the reader as
UID 1000 against an isolated Root seal and private configuration fixture. They
cover permissions, ownership, symlinks, duplicate keys and restored inputs;
the synthetic credential is absent from output. These are component checks.

Six isolated BEAM fixtures also pass with the actual non-retrying Postgres lease,
original-helper fence and permanent root supervisor. Normal monitor and lease
loss during blocked startup, normal monitor and lease loss during runtime, killed
monitor loss and normal connection loss end the complete BEAM. Independent SQL
and kernel observation then confirms original backend absence. Each helper starts
once; blocked-startup workers never start. The startup owner, generation monitor
and mutation worker are explicit fixture stand-ins. The fixture executes no
protected claim and does not verify the packaged native application.

Verification must cover normal and abnormal helper exits during blocked startup,
exactly one helper start, remaining-original cleanup, invalid/aliased/dead helper
refusal, unsupported startup before any effect, actual protected successful claim,
and whole-BEAM exit under the packaged permanent application. Process stand-ins
cannot verify installed ownership, Postgres authentication, artifact identity,
functional readiness, controller recovery, Cloud deployment or complete journeys.

This component is not yet wired into `Gitgood.Application`. Native runtime and
maintenance admission, controller reconciliation and the complete native root
remain required. No startup or release acceptance is established by this plan.
