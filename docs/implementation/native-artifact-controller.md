# Ordinary controller artifact inspection

`NativeArtifactInspectionController` executes archive inspection while the
original ordinary systemd controller retains its installation history lock and
database writer session. It records the actual inspection receipt before
beginning `stage`. The fixed Root socket path now connects that request to
serialized policy allocation and protected extraction. The controller validates
actual published code before recording durable stage completion. This source
path remains unverified on a live systemd controller until hosted evidence passes;
production provisioning and the long-lived Root listener remain unfinished.

## Original controller custody

The constructor accepts an installation UUID and exact existing
`GenerationRecordCustody`, `NativeCommandEndpoint` and
`NativeLifecycleResponsibility` objects. They must belong to the original
ordinary MainPID, installation and journal. The caller must have matching ordinary
UID/GID; Root and caller authority maps refuse before resource reads.

The fixed protected generation and operation policies supply original runtime,
inputs, candidate, request, publication, directory/lock identities and limits.
Actual persistent binding, private configuration, controller endpoint and history
remain checked. The controller borrows the original OS custody/endpoint/journal
and owns only its inspection reader, archive descriptor and `psql` writer session.
Application worker groups must remain stopped.

## Controller windows and real inspection

A separate private reader reuses the complete generation/lifecycle validators.
It accepts only running `inspect`, pending inspection completion, running `stage`
and pending stage completion for this original operation. It supplies no worker admission and does not
expand the maintenance/runtime worker stage lists. Other incomplete operations,
changed inputs, generation/publication or journal state refuse.

The original sealed artifact declaration selects the fixed Root-controlled
`/var/lib/gitgood/artifact-inputs/INSTALLATION/OPERATION/archive.tar.gz` by
candidate, SHA-256 and bounded bytes. The ordinary controller needs read access;
the archive and every parent must remain Root-owned and unwritable by ordinary
accounts. Original parent identities and archive descriptor/named metadata remain
checked. There are no caller paths, programs, environments or callbacks.

While holding the original writer exclusion, inspection bounds gzip/tar headers
and inventory before the shared native inspector validates digest, build identity
and candidate. The canonical actual inspection receipt is published through the
owned journal's `succeed('inspect', ...)`. Inspection executes no application code
and establishes no readiness or stage extraction.

Reader refresh admits only the journal's one newly published event and head. All
generation/publication/input metadata, prior lifecycle record identities and
directory inodes must remain unchanged. This permits the controller's actual
transition without adopting a replacement generation, input or old record.

## Serialized staging and completion

`begin_stage()` requires successful actual inspection, begins the durable stage
and retains the same writer session/history custody. It returns the existing
bounded canonical Root controller request with installation/operation and the
original history descriptor. Returning that frame neither sends it nor admits a
Root effect. `stage()` connects only to the independently provisioned
`/run/gitgood/root-artifacts/INSTALLATION.sock`, whose original Root owner, ordinary
group, `0620` mode, inode and protected parents must match. The actual socket peer
must have Root UID/GID. Its bounded canonical response binds this installation,
operation, candidate and stage receipt hash. A refusal or changed peer/path
retains the running stage and every effect.

[The Root dispatcher](native-root-artifact-dispatch.md) authenticates the actual
ordinary MainPID and its original history descriptor, observes its original SQL
writer exclusion, allocates the fixed policy under an actual Root flock, and
brackets every extraction check with that retained original custody. Root SQL
observers close before success is acknowledged; the ordinary controller then
checks its same original writer session again.

The ordinary controller reads only the fixed published Root output. It checks
the response hash against the actual read-only receipt, original request/scope
and running-stage snapshot, archive digest and byte count, inspection-derived
allocation budget, original directory/file identities, exact entry sets, every
regular file's content hash, confined Forge symlinks and the full inventory hash.
Only after those checks and another original-custody check does its owned journal
record `succeed('stage', ...)`. An immutable record and controlled head refresh
then expose pending stage completion. No response alone supplies completion.

Closing or observed loss permanently invalidates the controller and releases only
its owned reader/archive/writer session. Original endpoint, OS lock, journal,
inputs, archive and every retained record remain. Interrupted running stages
still require explicit actual-effect reconciliation.

Thirteen portable admission/window/refresh/transition checks include a real archive
read with explicit controller and journal stand-ins. Four Linux Root output tests
use actual extraction, read-only files, content hashes and original identities,
with explicit controller and fixed-path stand-ins. Ten dispatch boundary/socket
tests keep their authority stand-ins explicit. These checks do not prove live
ordinary systemd custody or complete controller-to-Root dispatch.

The hosted default-release case now selects the complete actual production Forge
and web archive, performs this controller/Root path, records actual inspection and
stage receipts, and launches migration, bootstrap and normal packaged runtime
from the staged code directory. Its public web policy binds the staged web tree.
That expanded case is unverified until its exact source, log and artifact are
reviewed. Production provisioning/listener, interrupted-effect reconciliation,
activation/enrollment and full reboot/replacement recovery remain required before
J14/J15 acceptance or original VM retirement.

The hosted fixture can diagnose a stalled full stage with seventeen fixed method
counters. They record only invocation counts and overlapping cumulative elapsed
milliseconds for the guard, file, SQL, manager and extraction paths. Wrappers
forward the original arguments, return value and exception and restore every
original method on exit, including interruption or partial setup failure. These
counters emit no stacks, paths, arguments, SQL or return values.
The fixed `_code_parent` and `_code_directory` counters distinguish archive entry
traversal from later directory sealing using counts alone. They use the same
forwarding wrapper and inspect no traversal names, descriptors or results.
The installed production modules, payload, guards and deadlines are unchanged.
The fixture additionally profiles only invocation ten of the read-only staging
guard. Every other guard and every effect runs outside that sample. An existing
profiler is preserved without starting another; both legacy profiling and the
CPython monitoring profiler slot are checked. Original arguments, results and
exceptions are forwarded, and profiler state is restored even on interruption.
Only a fixed installed file/function set, source line, call count and self or
cumulative milliseconds can appear in at most 64 deterministic selected rows. No
stack, caller, private path, argument, SQL, environment or return value is emitted.
The same rows also retain bounded microseconds, and the hot subset uses that
precision to avoid millisecond rounding ties. Fixed canonical serialization and
observation-wrapper counters are included. Four fixed `copy` functions are
accepted only from the exact loaded standard-library module, with its path
replaced by the constant `copy.py` label; matching basenames elsewhere refuse.
Six fixed standard-library Path methods additionally require the exact loaded
code filename, first line and function name, and emit only the constant
`pathlib.py` label. This separates path construction and metadata-call cost
without recording filesystem names. Installed-module basename matching cannot
admit either standard-library label. The same single guard and 64-row bound apply.
Nine POSIX file primitives and four socket methods additionally require their
exact closed CPython builtin profiler key. They emit constant `posix.py` or
`socket.py` labels and source line zero; ordinary Python rows still require a
positive bounded source line. Private filenames, builtin representations and
callers are never emitted. Basename matching cannot admit these labels. The
four artifact ancestor helpers, six Path methods, thirteen primitives and seven
fixed validation/copy helpers have priority when present, followed by the
hottest remaining rows within the same 64-row cap. This prevents a low-cost required helper from disappearing and
separates filesystem/socket time from its overlapping Python wrappers.
Portable regressions cover exact builtin keys, spoofed labels, numeric bounds,
required low-cost rows under cap pressure and actual owned socket calls. A
hosted Linux regression profiles reads of its own tiny fixture file; none of
these component probes proves full staging or production performance.
When the sample contains the installed staging guard, eight additional fixed
`guard-self-costs.py` tags partition every profiler entry's self time into
installed Python, pathlib, copy, JSON, regular expressions, UUID, builtin and
unnamed other Python categories. Only counts and summed self time are emitted;
unknown filenames, function names and callers remain unnamed. The categories
use line zero and equal self/cumulative fields because they sum disjoint self
costs, rather than adding overlapping stack costs. They share the same 64-row
cap and priority with required function rows and the guard itself. Category
totals form one partition; function rows are a separate overlapping view and
must not be added to that partition. Invalid counts or self times refuse
postprocessing rather than silently discard cost. Portable regressions check
complete partitioning, privacy, numeric refusal, cap pressure and an actual
cProfile run of an explicitly synthetic guard. No further guard invocation is
profiled, and the production guard and aggregate timer wrappers are unchanged.
Within the same cap, optional self-cost rows identify at most eight known public
production modules, eight closed builtin keys and nine additional exact loaded
pathlib helper code objects. Module rows use the fixed `module_self` tag and line
zero; unknown module basenames and function names are never emitted. Builtin
rows use `builtin-self.py`, fixed tags and line zero. Path helpers use
`pathlib-self.py` and require the loaded filename, first line and function name;
the original six Path code objects remain separate. These optional groups rank
by self time, rather than overlapping cumulative time, after all required rows.
Their equal self/cumulative fields describe self costs only. They overlap the
eight-category partition and must not be added to it. The module allowlist must
match the exact public production closure. Regressions cover that closure,
spoofed keys/labels, numeric bounds, row quotas, actual tiny file reads and
pathlib calls in an explicitly synthetic profile. Original guard forwarding,
profiler ownership, payload, production checks and deadlines remain unchanged.
These instrumented runs are diagnostic; production deadline acceptance still
requires an uninstrumented complete stage and subsequent staged runtime. Private
acceptance rejects either aggregate timers or the guard sample.

An earlier hosted diagnostic compiles a small CPython extension outside the
production module closure. Actual Root-owned Linux file tests compare its
fresh ordered ancestor/leaf metadata observations with the original fingerprint,
including refusal, ownership, links, size, executable mode, encoding and
timestamps. Unsupported prototype inputs fall back to the original method.
No filesystem observation is retained. Public C, adapter and compiled ELF hashes
identify the owned diagnostic files without emitting their runtime paths.

Before the first ready stage guard, that diagnostic runs twenty alternating pairs
of the complete original guard on the same original actors and resources. Each
pair selects either the original fingerprint or the diagnostic adapter; results
must agree, and every check still uses both fresh Root observation passes.
The original fingerprint descriptor is restored after each check and on every
exception. A refusal or mismatch poisons the original views; restoration cannot
revive them. Existing timers and the single guard-ten profile start only after
the comparison. The extra forty read-only checks and their paired elapsed times
are recorded separately, with no arguments, returned values, paths or SQL.

The original fingerprint runs for every subsequent staging effect. These pairs
measure a possible repair; they do not adopt it or prove production performance.
All production source bytes, the complete payload, freshness/effect guards and
the 240-second deadline remain unchanged. A complete uninstrumented stage,
staged runtime and the original installation/recovery gates are still required.

The Root reader prepares the two fixed read-only SELECT envelopes within its
original session. The nonce is a fresh text parameter for each execution, and
all original framing, read-only/session identity, before/after process, pipe,
kernel and socket checks and the poison path remain. Only a bounded set of two
statement kinds is retained; no returned observation or validation is cached.
Each execution reads current data. Closing the original owned client ends its
session and its plans; a failed reader never reconnects. See PostgreSQL's
[prepared-statement contract](https://www.postgresql.org/docs/18/sql-prepare.html).

A prior disposable comparison changed only statement construction in a fixture
copy of the original exchange AST, requiring an inverse transformation to recover
every original node. Twenty alternating whole-guard pairs used the same retained
Root reader and custody checks before any effects. Original methods and session
state were restored before staging. That measured experiment justified selecting
preparation for a production candidate; it did not prove full staging, recovery
or release readiness. The historical helper is retained but is no longer active
in the Root proof. The compiled fingerprint is also inactive there; its separate
standalone equivalence tests remain a diagnostic regression.

Production framing and refusal tests cover fixed statement kinds, nonce
injection, exact query bodies, corrupt plan state and failed preparation without
reconnection. Hosted PostgreSQL tests call production reader methods against a
newly owned database and role, checking repeated replies, changed client counts,
role changes and original client/backend loss. Those SQL tests explicitly
substitute process/base observers; the complete installed Root proof must verify
actual custody. The complete payload, freshness/effect guards, two separate Root
passes and 240-second deadline remain unchanged. Existing aggregate timers and
the single guard-ten sample remain diagnostic only. Complete uninstrumented
staging/runtime plus the original installation and recovery gates still apply.

The hosted fixture also measures process CPU, calling-thread CPU and wall time
around the existing read-only guard calls. A fixed numeric receipt identifies
the number of calls and aggregate milliseconds. Child psql/PostgreSQL processes
and ordinary actors are excluded from these CPU clocks; a wall/CPU difference
can include waiting and descheduling and does not identify their cause.
The wrapper forwards original arguments, results and exceptions, starts no
profile and invokes no additional guard. The original seventeen method timers,
single guard-ten profile and method restoration remain. Numeric/type bounds
refuse invalid counters, and no arguments, paths, returned values or private
attributes are emitted. These clocks guide the next performance repair; they
do not establish an uninstrumented deadline or full journey acceptance.

An earlier hosted trial used a pinned PyPy 3.11 v8.0.1 interpreter for
the Root helper only. The ordinary manager/workers retained their original
Python 3.12 executable. The complete payload, original actors within each
allocated trial, checks and deadlines are unchanged. A lock-parser compatibility
repair expresses the same Linux access mask through `O_WRONLY | O_RDWR` because
the experimental interpreter does not export `O_ACCMODE`; original descriptor,
flock and actor checks remain. Its complete component scope passed under PyPy,
with the original CPython checks retained. The trial tested a larger
execution-cost change after measured Root CPU dominated guard wall time.
It passed 372 Root component cases, actual pidfd/SQL cases and installed source
identity checks, but the full archive still reached the original 240-second
deadline before output verification. PyPy adoption was rejected; the active
proof again uses CPython. This is no same-actor interpreter speed comparison.

The fixture installer verifies the publisher's
[archive checksum](https://pypy.org/checksums.html), bounded paths, link targets,
entry/byte limits and available space before extracting a new Root-owned runtime
namespace. It retains at least 20 GiB free after estimated archive, extraction
and metadata allocations. An immutable package-tree hash, executable hash,
archive hash and closed implementation/version fields identify the actual
interpreter. Runtime downloads and execution happen only on the disposable
hosted runner. No local runtime, dependency payload or VM is created.

All original selected Root component scopes and the production PostgreSQL cases
ran under PyPy before the full installed ownership/stage/runtime proof.
The CPython-specific single-guard profiler was explicitly unsupported in that
trial; original method counts and process/thread CPU clocks remained.
The active CPython proof retains its original profiler path.
The receipt labels the runtime diagnostic only and production adoption false.
A complete result must still preserve every security and recovery gate, and any
runtime adoption requires installation, packaging, cold-start and recovery work
plus uninstrumented acceptance. A component or experimental pass alone cannot
authorize VM retirement or establish release readiness.

For a failed PyPy component scope, the historical trial reran that fixed
synthetic scope with failure-only exception-site tracing. At most 64 source
locations and closed exception type labels from the first failing case are
reported, with an explicit omission count. Only exact repository production
source paths are traced; paths, exception messages, arguments and locals are
absent from the receipt. An existing trace is never displaced, and trace state
is restored on exit. The repeated diagnostic cannot pass the failed gate or
run the dependent full staging proof, even if the repeated scope passes.

The diagnostic's helper-loss injection retains its original pidfd custody and
PID/birth/UID/parent/cgroup and live-state checks before signalling. If the
interpreter omits Python's pidfd functions, a hosted-only bridge invokes the
same libc `pidfd_open` and `pidfd_send_signal` operations with fixed zero flags
and `SIGKILL`; it never substitutes a PID-based signal. Native API failures
propagate without retry through libc, and the original descriptor always closes.
Both interpreters verified actual owned child identities, close-on-exec, unrelated
child survival, dead targets and closed descriptors, including the forced libc
path. This is a fixture compatibility bridge and changes no production module,
stage guard, operation deadline or recovery acceptance requirement.

The active CPython sample attributes direct calls into its exact loaded pathlib
code to fixed installed module/function pairs and their public source lines.
At most eight callers, ranked by cumulative edge time, share the original
combined 64-row cap with the required counters. These overlapping edge costs
have zero attributed self time and are not a disjoint CPU partition. Unknown
source labels, private paths, arguments and stack contents are excluded;
counter/type/time bounds and aggregate overflow are checked. This postprocesses
the same guard-ten profile, invokes no additional guard or filesystem read, and
guides the scope of the next repair while retaining complete staging and
recovery requirements.

The retained fixture-only path comparison tests immutable construction in the three
modules identified by those costs: service scope, durable binding and the Root
database reader. Exact concrete path inputs are reused; at most 64 bounded
exact-string constructor results are retained. Other input types and keyword
arguments use the original constructor. The cache contains only lexical paths,
with no filesystem, process, database, socket or validation observations.

Twenty baseline/prototype pairs alternate order on the same original stage and
actors before any effect and before the original timers and guard-ten profile.
Every module symbol is restored after each invocation and on interruption;
observations must match. Original Root file, binding and reader refusal scopes
also run with the factory active. The original guard and symbols are restored
before staging. Numeric receipts contain only paired times and bounded reuse
counts. This trial adopts no production behavior and does not establish the
full staging deadline, staged runtime or recovery requirements.

That path trial's median ratio was 0.9586 (about 4.1% faster), below its
predeclared 0.80 adoption threshold. It is no longer the active stage experiment.
The tests remain to preserve its refusal and restoration evidence.

The retained selected-query diagnostic compiles the existing systemd `Get` queue and
typed reply loop into a small hosted CPython extension. It binds the original
Root owner, library handle and bus pointer, creates no connection and retains no
observation results. The original `_get_many` still validates arguments and
checks library custody before and after the whole batch. Current Root PID/thread,
owner usability, library/bus object and pointer identity are checked during the
native loop. Selected query order, the five-second deadline, 4096-pump cap,
current-slot ownership, reverse cancellation, ASCII and typed/container bounds
remain mandatory. Callback replies stay borrowed; original slots cancel before
the callback context is released. Interruptions retain the original exception
and outer permanent-close behavior.

The hosted workflow first builds the two small diagnostic/test DSOs with warnings
as errors, exercises deterministic hostile protocol replies and interruption,
runs all 33 original systemd cases under the adapter, and compares 20 fresh batches
on one actual original bus. The stage experiment then runs 20 alternating whole-
guard pairs on the same original actors before timers, profiling or effects.
The original Python method is restored after every invocation and before staging.
At most eight connection bindings retain only original owner/handle lifetime,
and all bindings are released after the comparison without closing their buses.
This trial requires median ratio at most 0.90 with at least 18 of 20 pairs faster
before proposing adoption. Neither that threshold nor protocol tests substitute
for complete uninstrumented staging, staged runtime, installation or recovery.

That selected-query trial passed its 19 protocol cases, all 33 original systemd
cases under the adapter and 20 actual same-connection pairs. Its whole-guard
median ratio was 0.990991, with 15 of 20 pairs faster, below both adoption
criteria. Production adoption is rejected; it is no longer the active stage
comparison. Complete staging still failed at about 240 seconds before output
verification, with every production module unchanged.

The retained hosted diagnostic compiles 20 measured path helper bodies from the exact
installed CPython 3.12 standard-library source using pinned Cython 3.1.8. An inverse
AST check reconstructs every selected body after redirecting global loads to live
original globals and builtins dictionaries. Conservative f-string quoting also
preserves the parsed tree while avoiding Python 3.12 quote-reuse syntax in the
pinned compiler. Original classes, instances and raw
descriptors remain authoritative. Class closure dependencies, unsupported source
shapes and unsafe compiler options refuse. The hosted builder authenticates the
compiler wheel, bounds extraction and temporary storage, and records source,
options, generated-code and ELF identities; it never runs locally.

The loader checks Root-owned source/ELF custody and original runtime function
code before installing function, classmethod and property bodies on the original
classes. Semantic checks cover lexical values/types, PathLike and subclass
behavior, live global replacement/deletion, exception identity, and fresh
stat/lstat/resolve results after filesystem mutation. All 372 original Root
mutation/refusal cases must also pass with the adapter active. Compiled function
and frame metadata have compiler-specific limits; no general interpreter or
production equivalence is claimed by these component results.

Twenty whole-guard pairs then alternate on the original actors, with no active
profiler. Every descriptor restores after each prototype invocation, including
interruption and partial installation, and before original timers, profiling or
staging effects. Code custody is read again after comparison. Receipts retain
only fixed public code identities, selected body labels, counts and paired times.
The adoption threshold is median ratio at most 0.80 with at least 18 of 20 pairs
faster. All filesystem/kernel/SQL observations, complete archive, effect guards
and production deadlines remain unchanged. Production adoption and complete
staging/runtime, installation and recovery acceptance remain unproven.

That compiled path trial passed 13 source checks, 11 adapter/runtime cases and
all 372 original Root cases under the adapter. Its 20 whole-guard pairs had
median ratio 1.047818 with zero pairs faster, failing the unchanged 0.80 and
18-of-20 criteria. Production adoption is rejected. The original full stage
still reached approximately 240 seconds before output verification. The active
full proof no longer loads or copies that experimental runtime; all compiler,
semantic, descriptor-restoration and original Root regression tests remain.

The existing guard-ten diagnostic now ranks at most eight individual installed
function self costs from a closed public function inventory in the measured hot
service, systemd, kernel, binding, reader, lifecycle and generation modules. These
refine the former eight coarse module-total slots. The installed-code category
aggregate, primitive/path quotas and caller attribution remain within the same
combined 64-row limit. Self costs overlap those category totals; they must not
be added as separate work. Labels and source lines identify public functions;
arguments, locals, caller mappings, private paths and observation values are
absent. Unknown source/function keys are excluded and invalid numeric data
refuses. This postprocesses the same existing guard-ten profile and invokes no
additional guard, profile or observation. It selects the next repair and cannot
establish uninstrumented performance, staging, runtime or recovery acceptance.

The broader lexical-path experiment adds derived-path construction to the retained
three-module constructor prototype. It changes only the original PurePath
`with_segments` descriptor during private read-only comparisons. Exact standard
path classes and exact strings can reuse at most 256 join plans, alongside the
existing 64 constructor plans. Keys retain raw lexical strings and classes, with
at most 64 raw components and 1,024 characters in total; resulting paths remain
bounded to 64 parts and 1,024 characters. Oversized or unsupported inputs,
PathLike objects, subclasses, keyword arguments and failures use the original
constructor behavior without caching errors. A conservative 16 MiB memory
estimate covers these small bounded plans.

The actual Root-controlled CPython 3.12 source authenticates the original pure
constructor body and the construction-role code objects. Diagnostic source
identities, namespace/builtin bindings, original classes, construction methods,
Root PID/thread and all-Root UID/GID state are checked. All original metadata
methods remain live; no filesystem, ancestor, process, SQL, socket, validation
or guard observation is retained. Plan objects reuse lexical object identity;
this diagnostic does not claim general standard-library API equivalence.

Twenty-four component cases include portable lexical values, side effects,
exception identity, input bounds, namespace/owner refusal, interruption and
partial-installation cleanup, fresh file/replacement observations and SDK source
shape checks. Three actual Linux cases verify source custody, fresh symlink
changes and all 372 original Root mutation/refusal cases with the combined
adapter active. These cases require current hosted evidence.

The first combined trial passed SDK custody and symlink freshness but failed the
original process-status fixtures because the constructor callable did not expose
the original Path.stat class attribute used for metadata mutation injection.
The diagnostic factory now forwards that narrow interface to the same original
class. Reads stay live, nested test-directed mutations unwind in order, and all
pending mutations restore during adapter cleanup even after interruption. Normal
adapter installation does not change any metadata method. The original tests
and their read-order/refusal assertions remain unchanged; no metadata result is
cached by this interface.

Twenty whole-guard baseline/prototype pairs alternate on the same original stage
and actors before the original timers and guard-ten profiler. The original
method descriptor and all three module symbols restore after every prototype
invocation and before any staging effect, including failures and interruptions.
All plans clear after comparison. Only numeric counts/times and fixed public
code hashes appear in the receipt. The proposal threshold remains median ratio
at most 0.80 and at least 18 of 20 pairs faster. Production adoption, complete
uninstrumented staging and staged runtime, installation and recovery remain
separate unproven requirements. Neither earlier rejected path experiment is
rerun unchanged or treated as accepted behavior.

The combined lexical trial subsequently passed all 24 cases and all 372 original
Root cases under the adapter. All 20 whole-guard pairs were faster, but their
median ratio was 0.945437, failing the unchanged 0.80 gate. Adoption is rejected.
The original full stage still failed at approximately 240 seconds before output
verification. That runtime is no longer copied or loaded by the full proof; its
component regression gate remains.

The next hosted diagnostic selects 116 bodies across the seven installed hot
modules identified by the existing self-cost profile. The original production
files and classes remain authoritative. Only function bodies and direct module
aliases in the admitted deployment directory are replaced during read-only
comparison. Arbitrary decorators, the selected-bus callback closure, Root pass
wrappers and unsupported class-closure dependencies stay on the interpreter.
Global loads use each original function's live module and builtins dictionaries;
an inverse AST check reconstructs every selected body. Bounded literal default
arithmetic is checked without executing supplied source and stays unchanged.

The builder uses the existing authenticated Cython 3.1.8 wheel and conservative
options on the disposable hosted runner, with a 512 MiB temporary allocation
estimate and the 20 GiB volume reserve. It copies only the bounded source,
manifest and extension closure to Root-owned storage. The loader checks exact
installed source/code identities, ELF identity and file custody again after the
comparison. Original classes, exception types and all metadata/kernel/SQL reads
remain live. This is a compiler experiment, with compiler-specific frame and
function metadata limits, not general Python equivalence or product adoption;
see the [compiler's documented limitations](https://cython.readthedocs.io/en/3.1.x/src/userguide/limitations.html).

Fourteen cases cover source admission, lexical scope/global mutation, direct
aliases, static/class methods, original exceptions, owner refusal, partial
installation and complete restoration after interruption. Three require actual
Linux Root: exact code custody, fresh file mutation and all 372 unchanged
original Root cases with the compiled bodies active. Hosted results remain
pending. Twenty alternating whole-guard pairs on the original actors must have
median ratio at most 0.80 and at least 18 pairs faster before proposing adoption.
Every body and alias restores before each baseline and before the unchanged
timers, guard-ten profile and staging effects. No observation result is retained;
receipts contain fixed public code hashes/labels and bounded counters/times.
Complete uninstrumented staging/output, staged normal runtime, production
listener/provisioning, interruption reconciliation, installation and actual
replacement-host restore remain required before original VM retirement.
