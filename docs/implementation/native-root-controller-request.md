# Original controller requests to Root

Protected artifact effects must identify the original installation controller,
not simply a process using the same account. `NativeRootControllerRequest`
authenticates a connected local request and observes that controller's original
held history descriptor. This is a prerequisite for artifact authority; it does
not yet dispatch an effect or establish database writer exclusion.

## Fixed original admission

The Root-only constructor accepts installation and operation UUIDs plus one
connected Unix socket. It takes custody of that socket, including on refusal.
`NativeRootLiveBindingObservation` supplies the independently protected original
controller, complete history, request and actual resource/database identity.
Linux `SO_PEERCRED` must identify exactly that controller's PID, UID and GID.
The live view checks its original process birth, service and namespaces before
and after observations. A different process under the same account refuses.

One canonical, half-closed frame is read through the existing bounded receiver:
at most 512 bytes within its unchanged two-second deadline. The closed protocol-2
frame has kind `native_root_controller_request`, installation/operation UUIDs and
an integer `history_lock_fd`. It carries no paths, SQL, programs, environments,
callbacks or authority maps. The operation must match the independently admitted
original operation; booleans, unknown fields and noncanonical data refuse.

## The controller's existing history lock

The descriptor number selects only a descriptor of the authenticated original
controller. Its actual procfs target must equal the original ordinary-owned
history lock metadata captured by the Root history view and fixed generation
seal. Root does not open a replacement lock or call `flock`.

The bounded `/proc/PID/fdinfo/FD` observation must describe an `O_RDWR` descriptor,
the original inode, and a whole-file exclusive advisory `FLOCK` held by the
original controller PID on the original device/inode. Duplicate, unknown,
missing or oversized fields and shared/OFD/POSIX/foreign locks refuse. The
descriptor target is checked around the kernel read, and the complete original
live view and peer/socket identity bracket the observation. The parser uses the
[Linux kernel's documented fdinfo lock format](https://docs.kernel.org/filesystems/proc.html).

Later checks retain the captured descriptor and metadata; an observed change
permanently poisons the request and closes only its socket and owned Root views.
The controller's original descriptor, lock, files and history remain. This proves
the sampled held lock, not uninterrupted ownership between observations.

## Evidence and remaining work

Portable parser, frame, admission and poison tests use explicit kernel/account
stand-ins. Three Linux tests use real descriptors and `flock`: an exclusive
original lock, actual unlock, and a separate descriptor of the same inode.
The existing hosted ownership proof installs the module and uses the actual
ordinary systemd MainPID to send requests while retaining its real reservation.
It exercises a different process under the same account, a wrong operation from
the original controller, and repeated successful peer/history-lock observations.
Those installed results remain unverified until the exact candidate passes.

The fixture's listener allocation and scheduling are not a production Root
listener or dispatcher. No artifact-stage command is admitted, and the fixture
still uses metadata for inspection/staging. Database session/kernel/socket
exclusion, serialization of consequential requests, Root policy allocation,
actual ordinary inspection/protected staging, interruption reconciliation and
normal runtime from staged code remain required. Activation/enrollment and full
reboot/replacement recovery remain necessary before J14/J15 acceptance or
original VM retirement. Status exposes bounded references and observation flags,
with every effect/exclusion/whole-journey grant false.
