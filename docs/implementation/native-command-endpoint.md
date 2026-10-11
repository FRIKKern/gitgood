# Native controller endpoint ownership

Implementation under [decision 0018](../decisions/0018-native-supervision-generations.md).
The command decoder now has an owned pathname-listener implementation. It is
not installed or connected to lifecycle dispatch. The native application gate
remains closed.

`NativeCommandEndpoint` takes only an installation UUID. `NativeControllerScope`
reads `/etc/gitgood/installations/UUID/controller-endpoint-v2.json`, validates its
closed canonical protocol-2 format and Root file/parent custody, and observes the
actual allocated systemd service through the existing protected observer. The
caller must be that service's original MainPID, with its admitted ordinary UID,
GID, unit digest, limits, process birth and exact delegation. Root allocation of
the account, unit, seal and private directory remains separate implementation
work. A service observation alone grants no operation or generation admission.

The Root seal fields are `protocol`, `kind`, `installation`, `uid`, `gid`,
`unit_sha256`, `directory_identity` and `limits`. Kind is
`native_controller_endpoint_seal`; directory identity contains device, inode and
UID, and limits contain the existing CPU quota and memory bounds. No socket path,
program, callback, environment, provider token or caller authority map is accepted.
The fixed private directory is `/run/gitgood/installations/UUID`: admitted
UID/GID, mode 0700, original inode and protected Root parents. The controller
does not create that directory.

The listener binds `controller.sock` beneath its held directory descriptor,
sets mode 0600, listens with backlog one and retains the original pathname node
and listener descriptor identities. Existing files, sockets and symlinks refuse
without removal. Checks bracket accept and decoding. Root seal, parent, directory,
socket, service or controller identity loss permanently closes this instance;
restored names or bytes cannot revive it. Forked processes cannot use the original
controller's listener custody.

One accepted connection uses the existing 4096-byte, two-second absolute request
deadline and actual Linux peer credentials. Invalid frames and wrong peers close
that connection; they do not replace the current listener. Accept waiting is
bounded to at most two seconds. A decoded result explicitly carries false
operation, lifecycle-exclusion, generation-publication and readiness flags. It
contains no response granting authority and invokes no stage engine.

Closing the listener retains its original socket node, including on normal close
or refusal. Safe restart cleanup requires independent original-owner death and
generation reconciliation before an allocator/controller may remove that exact
node. That cleanup, controller entry point, sealed-purpose operation admission,
durable lost-response handling, lifecycle dispatch and status responses remain
required. A stale socket is not silently adopted or unlinked.

Verification uses actual ordinary pathname sockets for replacement, permissions,
malformed clients, descriptor ownership, fork refusal and retained close. A
separate actual Root/private fixed-path fixture checks seal ownership, canonical
JSON, directory custody, distinct Root/ordinary peers and seal replacement during
request reception. Its systemd service observation and observer-cache freeze are
explicit stand-ins; the Root files, socket descriptors and peer credentials are
actual. Those checks do not prove actual native service admission, product
allocator enrollment, installed controller execution, dispatch or complete J14.
