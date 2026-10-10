# Read-only published generation admission

`tools/deployment/native_generation_reader.py` admits an actual native or
maintenance owner against the current completed resource generation. Allocation
must independently seal the expected durable binding digest, history and existing
lock identities, service unit digest, runtime paths and limits. The reader never
uses stored values as that independent authority.

The reader shares the existing publication and record validators. It opens the
existing lock read-only without acquiring it, creates no directories and refuses
all mutation methods. This permits a controller to keep its lifecycle lock while
starting a worker without deadlocking its observation helper. It grants no writer
exclusion or lifecycle authority.

Admission requires actual worker scope and ancestry, a complete canonical current
pointer and receipt, validated retained transitions and generation ancestry, one
unbranched record tip matching the current pointer, and exact current service
scope. Bounded directory inventories reject unknown responsibility and all
retained partial files. Individual file identities and bytes, directory identities,
worker observations and persistent binding must remain unchanged across repeated
observations. An unfinished pointer, staged successor, old boot or manager, changed
binding or replaced file leaves admission unavailable without repairing history.

This first reader admits only publication-only transitions with empty lifecycle
responsibility. A historical uncertain pointer can remain referenced by its
completed successor; its missing receipt is preserved. Other unfinished work
requires its explicit generation-aware reconciliation before admission.

Run admission before starting the application's database lease. Persistent
identity queries use temporary read-only connections and retain no session. The
generation-aware Elixir lease must independently verify the expected database
identity through its own held connection and preserve exact generation identity
in its markers. This component does not implement those application semantics,
periodic lease admission, packaged readiness, lifecycle dispatch or allocation.

Eleven boundary tests use actual ordinary Linux file custody with explicit service
and database stand-ins. They cover completion, retained uncertainty, live scope and
binding changes, replaced files, unavailable custody and mutation refusal. Actual
VM evidence passes 22 checks across actual manager interruption, recovery and two
kernel boots. Both roles admit the current completed generation and refuse changed
binding, history, lock and unit seals on each boot. Fixed Root-installed observation
helpers are short-lived; independent Root observation matches the still-live owner
births, completed pointer, binding and service scope checksum. Four custody checks
bind 46 current operator modules and eleven empty retained fixture groups. Four
powered-off disk checks verify thirteen exact installed files and preserve the
original overlay. The full Linux suite passes 298 tests with twelve expected
platform skips; all 33 planning checks pass. Current required CI remains separate.
See the [supervision decision](../decisions/0018-native-supervision-generations.md).
