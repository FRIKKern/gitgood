# Root observing the original controller's database exclusion

Artifact authority needs the original controller's actual database writer lease,
not a supplied backend record. `NativeRootDatabaseExclusionObservation` discovers
and retains that live lease under an authenticated original controller request.
It observes cooperative exclusion; it neither acquires a lease nor grants an
artifact effect.

## Original request and private resources

The Root-only constructor accepts an exact `NativeRootControllerRequest` and
takes custody of it. That request already checks the original kernel peer,
history-lock descriptor, protected policy, complete history and live binding.
Runtime, database identity and private configuration come from that original
view. The independently protected backend scope fixes the boot, server PID/time
namespaces and PostgreSQL account. There are no caller paths, SQL, programs,
environments, backend records or lease identifiers.

The fixed read-only query discovers exactly one granted exclusive advisory lock
in the native application's existing namespace/key and current database, held by
the expected ordinary database role. Actual cluster/database/role identity must
match the sealed binding. There must be exactly two client backends: the retained
writer and this short-lived observer. Missing, multiple, foreign or unexpected
clients refuse. Credentials stay in the child process's explicit private
environment, outside argv/status; output and execution use the existing bounded
database reader.

## Client socket and server kernel identity

The controller's bounded direct-child inventory must contain exactly one client
running the pinned Root-controlled `psql` image. Actual parent PID, process birth,
ordinary UID/GID, capability limits, original driver cgroup and mount/cgroup/
network/PID/time namespaces are checked. Disappearance may be skipped only
before selection; a selected client is never replaced.

The original client's actual TCP row and descriptor must match the discovered
loopback client/server ports and ordinary UID. The existing socket primitive is
shared behind separate admission. The ordinary owner route retains its original
UID/EUID check before reaching that primitive. Root checks the original admitted
client before and after socket observation.

The existing backend observer captures the server's distinct SQL and kernel
births while the original held lease is present. Every later check brackets fixed
SQL and client-socket observations with the captured server kernel birth,
original request/history/resources, protected backend scope and client identity.
Observed client/backend/lease/socket loss or change permanently poisons the view.
Closing releases only its owned Root request; it never terminates the original
controller, client or server, and never reacquires or adopts a replacement lease.

## Evidence and remaining authority

Local parser, admission, selection and loss tests use explicit account/process/
SQL/socket stand-ins. The hosted ownership proof observes the actual ordinary
controller's reservation, retains this Root view through the real handoff, and
requires refusal after the original controller client and server backend are
absent while the original peer/history/resources still match. Those installed
observations remain unverified until the exact candidate's evidence passes.

Status contains operation references and bounded observation flags. It does not
return configuration, database/session details, client ports, kernel records or
socket identities. `database_writer_exclusion_verified` describes the sampled
original cooperative lease and client exclusion. It is not uninterrupted
exclusion between samples or serialization of consequential Root requests.

Production Root listener/dispatcher, serialized effect authority, fixed artifact
policy allocation, actual ordinary inspection/protected staging, interruption
reconciliation and runtime from staged code remain unfinished. Activation,
enrollment, unhealthy-candidate preservation, public routing and full reboot/
replacement recovery remain required for J14/J15 acceptance or original VM
retirement. Lease acquisition, lifecycle/effect authority and whole-journey
acceptance remain false.
