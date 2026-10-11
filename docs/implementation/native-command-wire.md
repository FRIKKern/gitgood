# Native controller command framing

Implementation under [decision 0018](../decisions/0018-native-supervision-generations.md).
`native_command_wire.py` supplies the local request transport boundary. It does
not bind a socket, install a service, admit a lifecycle operation or dispatch
an effect. The native application gate remains closed.

The controller must independently admit its installation and ordinary account,
retain its private socket directory and original socket identity, and accept only
connections to that owned endpoint. The reader checks actual Linux `SO_PEERCRED`
on an AF_UNIX stream against that admitted non-root UID. It brackets the complete
request with the same kernel peer credentials. The PID is caller attribution;
it is not a process-lifetime binding and authorizes no process signal.

Each connection carries one canonical JSON request followed by a newline and
write-side EOF. The complete frame is at most 4,096 bytes and must finish within
two seconds. Incremental reads use one absolute deadline. Duplicate keys,
numeric aliases, unknown fields, trailing frames and unsupported actions refuse.
Refusal closes the original connection. A successful read restores its previous
timeout; the controller owns any acknowledgement and eventual close.

The fixed actions are status, enroll, enroll-resume, upgrade, upgrade-recover,
upgrade-resume, backup, restore, export and retire. Status carries only the
protocol, kind, installation and action. Every other action also names an
original nonzero operation UUID and sealed request SHA-256. Caller-supplied
programs, paths, argument vectors, environment and provider operations are absent
from the schema. Names do not grant permission or establish implemented engines.

The decoded request remains unadmitted. Before dispatch, the controller must
observe its actual Root-sealed request, bind its purpose/action, operation,
installation, original input digests and retained lifecycle responsibility,
establish current generation and writer/lifecycle exclusion, and invoke only the
fixed corresponding engine. A matching account or supplied digest is insufficient.
Lost caller responses must preserve durable operation ownership and uncertain
effects. This module creates no journal, retries no effect, and implements no
response, reservation, readiness or cancellation protocol. Existing initial,
upgrade and retirement commands remain on their original development profile.

Kernel socket tests use actual ordinary Linux credentials, including wrong
expected UID refusal, unsupported socket types, missing EOF, excess frames and
closed refused connections. They do not establish a Root-enrolled product
endpoint, independently sealed operation, installed controller or complete J14.

A separate actual pathname-socket fixture runs its server as UID 1000. An actual
Root process connects first and refuses; a distinct ordinary process connects
next and passes with its own kernel PID/UID/GID. The private mode-0600 socket's
identity remains unchanged. No operation is dispatched, and the independently
owned fixture endpoint is not product enrollment.

All 13 focused tests and 35 planning tests pass. The socket fixture verifies
unchanged component source bytes before and after its actual connections.
All 496 operator regression tests pass in 66.875 seconds, with 18 expected
platform skips. All 117 tracked operator source hashes remain unchanged across
the run. Required CI remains pending. These checks do not establish installed
native application or controller acceptance.

Linux documents peer credentials as belonging to connection/socket-pair creation
in the [Unix socket manual](https://man7.org/linux/man-pages/man7/unix.7.html).
