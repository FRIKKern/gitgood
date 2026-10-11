# Original backend kernel identity for native recovery

Decision [0018](../decisions/0018-native-supervision-generations.md) requires
original backend absence before replacement. The existing
[activity-view observer](native-prior-backend-observation.md) establishes only
SQL PID/birth absence. `native_kernel_backend.py` adds capture of that live
session's kernel identity and a combined same-boot absence observation.

The caller must independently admit the PostgreSQL server's actual boot, PID
namespace, time namespace and Unix account. These four closed fields are observations supplied
by a trusted allocator/controller, not authority manufactured by this module.
The observer requires its actual boot, PID namespace and time namespace to match.
It requires the native host clock's monotonic and boottime offsets to be zero;
procfs adjusts process start times using the observer's time namespace. It checks the
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
boot/namespace/account, a nonzero time offset, and an unknown or type-aliased record refuse. Observing a
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
the separate actual PostgreSQL proof supplies that component evidence.

Seven real PostgreSQL/kernel checks pass with two actual ordinary-role BEAM
lease owners. A Root fixture independently observes the actual listener's
boot/PID/time namespaces, zero clock offsets, account and pinned PostgreSQL executable. Each owner's
original socket/held session/kernel birth is captured while live; live absence
refuses; normal owner exit establishes both SQL and kernel absence. A second
holder of the same advisory key remains untouched while the first original is
observed absent. The original record bytes and all seven tested source digests
remain unchanged. The first harness attempt refused before launching a BEAM
because an ordinary actor could not read Root-private VM preflight inputs; it
is retained. The corrected Root preflight exports only non-secret quiescence
facts and then runs the proof as the ordinary actor, without widening fixture
permissions. The existing stopped VM's original group/process absence is
verified before this proof. Actual PID reuse, installed identity custody and
complete native recovery remain unverified.

Two further actual child time-namespace checks pass. Both preserve the original
PID namespace and original host clock while entering a new time namespace. A
zero-offset namespace and a namespace with 60-second offsets both refuse before
SQL observation. In the latter, the still-live original parent reads with a
6,000-tick shifted start time, demonstrating why comparing birth ticks without
clock admission would be unsafe. No original process is signalled; the parent
birth and host offsets remain unchanged after both children exit.

All 483 ordinary Linux operator tests pass with 18 platform-specific skips,
including 29 focused kernel/session regressions. All 115 tracked deployment
source digests match before and after the full suite. The 35 planning tests pass;
required CI and full installed application/controller acceptance remain pending.

Kernel field meanings come from the official
[procfs documentation](https://www.kernel.org/doc/html/latest/filesystems/proc.html).
The kernel's [stat implementation](https://github.com/torvalds/linux/blob/master/fs/proc/array.c)
applies the time-namespace boottime offset to process start time. Earlier
predeployment component records lacking explicit time-namespace admission
refuse under this schema; they are retained, not rewritten or adopted.
The original SQL observer's fixed catalog-only environment and deadlines are
preserved. No complete journey or deployment is claimed by this component.
