# Original backend kernel identity for native recovery

Decision [0018](../decisions/0018-native-supervision-generations.md) requires
original backend absence before replacement. The existing
[activity-view observer](native-prior-backend-observation.md) establishes only
SQL PID/birth absence. `native_kernel_backend.py` adds capture of that live
session's kernel identity and a combined same-boot absence observation.

The caller must independently admit the PostgreSQL server's actual boot, PID
namespace and Unix account. These three closed fields are observations supplied
by a trusted allocator/controller, not authority manufactured by this module.
The observer requires its actual boot and PID namespace to match. It checks the
observer's PID, thread-group and namespace mappings against its actual PID.
Nested server namespaces and foreign/ancestor procfs PID mappings refuse. This
is a local native host profile, not a general remote/container PID translator.
Persistent installation/host continuity remains a separate admission requirement;
an empty WSL machine-id is not made into a valid durable installation binding.

Capture checks the exact original database/session/held advisory lease before
and after kernel observation. The backend's procfs PID, thread group, namespace
PID hierarchy and four Unix UIDs must match the admitted server account and SQL
PID. Repeated bounded stat reads must report the same live original kernel birth.
Capture retains a closed record with the original SQL snapshot, server scope and
kernel birth. SQL birth is microseconds since the epoch; kernel birth is ticks
since boot. They are distinct identities and are never compared as equal values.
The returned record has no mutable alias to the caller's snapshot or scope.

Absence requires that captured record under the same independently admitted
scope. It brackets the existing catalog-only SQL absence query with fresh kernel
absence reads. Only missing original PID/stat or a different kernel birth
establishes kernel absence. A zombie with the original birth refuses until it is
reaped. Unreadable/malformed process data, missing scope observations, a changed
boot/namespace/account, and an unknown or type-aliased record refuse. Observing a
different birth never returns, signals or adopts the current reused PID.

All procfs reads are fixed, bounded and read-only. There is no process scan,
process signal, advisory lock acquisition, marker/journal write or readiness
claim. The combined result explicitly withholds owner/descendant absence,
writer exclusion and replacement admission. It cannot authorize reboot recovery;
that still needs independently observed persistent continuity and a generation
transition. The application ownership format and native startup gate are
unchanged. Production admission/retention of this extra identity and complete
controller/lifecycle integration remain required.

Component tests cover lost leases, changed kernel births, malformed and aliased
records, scope changes, nested PID mappings, permission failures, SQL/kernel
bracketing and PID reuse without adoption. Actual ordinary Linux process tests
exercise live-child refusal, zombie refusal and disappearance after reaping.
These process tests do not prove that a real PostgreSQL backend is bound;
an actual held-session capture/normal-exit proof remains required.

Kernel field meanings come from the official
[procfs documentation](https://www.kernel.org/doc/html/latest/filesystems/proc.html).
The original SQL observer's fixed catalog-only environment and deadlines are
preserved. No complete journey or deployment is claimed by this component.
